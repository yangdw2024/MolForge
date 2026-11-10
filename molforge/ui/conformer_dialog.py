"""构象浏览与聚类分析对话框：列出构象能量，支持 Kabsch RMSD 结构聚类与多构象预览。"""
from __future__ import annotations

from typing import Optional, List, Dict
import numpy as np
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QWidget, QDoubleSpinBox, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, QTimer

from molforge.application.trajectory_analysis import cluster_conformer_ensemble


class ConformerDialog(QDialog):
    def __init__(self, parent, ensemble, on_apply, on_preview=None):
        super().__init__(parent)
        self.setWindowTitle("构象浏览与 RMSD 聚类分析 · ETKDG")
        self.setMinimumSize(480, 580)
        self.ensemble = ensemble
        self.on_apply = on_apply
        self.on_preview = on_preview
        self.cluster_result: Optional[dict] = None

        lay = QVBoxLayout(self)
        head = QLabel(
            f"共 {ensemble.count} 个构象 · 方法 {ensemble.method} · 种子 {ensemble.seed}"
            + (f" · 力场 {ensemble.forcefield}" if ensemble.forcefield else ""))
        head.setWordWrap(True)
        lay.addWidget(head)

        if ensemble.failures:
            warn = QLabel("提示：" + "；".join(ensemble.failures))
            warn.setStyleSheet("color:#D8B679;")
            warn.setWordWrap(True)
            lay.addWidget(warn)

        # 聚类控制条
        cluster_grp = QGroupBox("RMSD 结构聚类 (Kabsch 对偶距离矩阵)")
        c_lay = QHBoxLayout(cluster_grp)
        c_lay.addWidget(QLabel("截断半径 (Å):"))
        self.spin_thresh = QDoubleSpinBox()
        self.spin_thresh.setRange(0.1, 5.0)
        self.spin_thresh.setSingleStep(0.1)
        self.spin_thresh.setValue(0.5)
        c_lay.addWidget(self.spin_thresh)

        btn_cluster = QPushButton("🔍 聚类分析")
        btn_cluster.clicked.connect(self._run_clustering)
        c_lay.addWidget(btn_cluster)

        btn_reset = QPushButton("恢复全部列表")
        btn_reset.clicked.connect(self._populate_list)
        c_lay.addWidget(btn_reset)
        lay.addWidget(cluster_grp)

        self.listw = QListWidget()
        self.listw.currentRowChanged.connect(self._on_row)
        lay.addWidget(self.listw, 1)

        self.status_lbl = QLabel()
        self.status_lbl.setStyleSheet("color: #40C4FF; font-size: 11px;")
        lay.addWidget(self.status_lbl)

        btns = QHBoxLayout()
        self.apply_btn = QPushButton("应用此构象")
        self.apply_btn.setProperty("role", "action")
        self.apply_btn.clicked.connect(self._apply)
        cancel = QPushButton("关闭")
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(self.apply_btn)
        lay.addLayout(btns)

        self._populate_list()

    def _populate_list(self):
        self.listw.clear()
        self.cluster_result = None
        for c in self.ensemble.conformers:
            en = f"{c.energy:.3f} {c.energy_unit}" if c.energy is not None else "未计算能量"
            it = QListWidgetItem(f"构象 {c.index + 1}　{en}　" + ("已收敛" if c.minimized else "未确认收敛"))
            it.setData(Qt.ItemDataRole.UserRole, c.index)
            self.listw.addItem(it)
        if self.ensemble.count > 0:
            self.listw.setCurrentRow(0)
        self.status_lbl.setText(f"当前显示全部 {self.ensemble.count} 个生成构象。")

    def _run_clustering(self):
        if self.ensemble.count < 2:
            QMessageBox.information(self, "提示", "至少需要 2 个构象才能进行 RMSD 聚类。")
            return

        thresh = self.spin_thresh.value()
        coords_list = [c.coords for c in self.ensemble.conformers]
        res = cluster_conformer_ensemble(coords_list, rmsd_threshold=thresh)
        self.cluster_result = res

        self.listw.clear()
        n_clusters = res["n_clusters"]
        for cid, members in res["clusters"].items():
            medoid_idx = res["medoids"][cid]
            medoid_c = self.ensemble.conformers[medoid_idx]
            en = f"{medoid_c.energy:.3f} {medoid_c.energy_unit}" if medoid_c.energy is not None else "未知"
            # 簇中心代表
            it_center = QListWidgetItem(
                f"🏷 簇 {cid + 1} 中心 · 构象 {medoid_idx + 1} ({en}) · 共 {len(members)} 构象"
            )
            it_center.setForeground(Qt.GlobalColor.cyan)
            it_center.setData(Qt.ItemDataRole.UserRole, medoid_idx)
            self.listw.addItem(it_center)

            for m in members:
                if m == medoid_idx:
                    continue
                c = self.ensemble.conformers[m]
                d = res["matrix"][medoid_idx, m]
                en_m = f"{c.energy:.3f}" if c.energy is not None else "--"
                it_sub = QListWidgetItem(f"    ├─ 构象 {m + 1} (ΔRMSD={d:.2f}Å, {en_m} kcal/mol)")
                it_sub.setData(Qt.ItemDataRole.UserRole, m)
                self.listw.addItem(it_sub)

        if self.listw.count() > 0:
            self.listw.setCurrentRow(0)
        self.status_lbl.setText(f"聚类完成: 在截断半径 {thresh:.2f} Å 下聚为 {n_clusters} 个结构簇。")

    def _on_row(self, row):
        if row < 0 or row >= self.listw.count():
            return
        item = self.listw.item(row)
        if not item:
            return
        conf_idx = item.data(Qt.ItemDataRole.UserRole)
        if 0 <= conf_idx < self.ensemble.count:
            c = self.ensemble.conformers[conf_idx]
            if self.on_preview is not None:
                QTimer.singleShot(0, lambda: self.on_preview(c.coords) if self.isVisible() else None)

    def _apply(self):
        row = self.listw.currentRow()
        if row < 0 or row >= self.listw.count():
            return
        item = self.listw.item(row)
        if not item:
            return
        conf_idx = item.data(Qt.ItemDataRole.UserRole)
        if 0 <= conf_idx < self.ensemble.count:
            if self.on_apply(self.ensemble.conformers[conf_idx].coords) is False:
                return
        self.accept()
