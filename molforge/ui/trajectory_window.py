"""轨迹播放与动力学动力学分析窗口：MDAnalysis 加载 + VTK 零拷贝流式渲染 + QTimer 播放 + Kabsch RMSD/RMSF。"""
from __future__ import annotations

import csv
import threading
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel,
    QComboBox, QSplitter, QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QProgressBar
)
from pyvistaqt import QtInteractor
import pyvista as pv

from molforge.io.mdanalysis_adapter import TrajectoryAdapter
from molforge.application.trajectory_analysis import (
    kabsch_align, calculate_radius_of_gyration, calculate_trajectory_metrics
)

# 残基类型配色（ACC 给/受体区分）
_RES_COLORS = {
    "ACC": (0.40, 0.87, 0.79),   # 青
    "DON": (0.49, 0.68, 0.98),   # 蓝
    "DIO": (0.85, 0.71, 0.47),   # 琥珀
}


class _AnalysisWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, adapter: TrajectoryAdapter, stride: int = 1):
        super().__init__()
        self.adapter = adapter
        self.stride = stride

    def run(self):
        try:
            res = calculate_trajectory_metrics(self.adapter, ref_frame=0, stride=self.stride)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


class TrajectoryWindow(QMainWindow):
    def __init__(self, topology: str, trajectory: str, name: str = "trajectory", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"分子动力学轨迹流式播放器 · {name}")
        self.resize(1350, 880)

        self.adapter = TrajectoryAdapter(topology, trajectory, chunk_size=10, max_chunks=8)
        self.frame = 0
        self.playing = False
        self.ref_coords = self.adapter.get_frame(0)
        self.analysis_data: Optional[dict] = None

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ---------------- 左侧：3D 视图与播放控制 ----------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # VTK 视图
        self.plotter = QtInteractor(left_widget)
        self.plotter.set_background([0.06, 0.10, 0.16], top=[0.12, 0.18, 0.26])
        left_layout.addWidget(self.plotter, 1)

        # 第一帧网格初始化
        self._build_mesh(self.ref_coords)
        self.plotter.reset_camera()
        self.plotter.camera.zoom(1.2)

        # 控制条
        ctrl = QHBoxLayout()
        self.btn_prev = QPushButton("⏮ 上一帧")
        self.btn_play = QPushButton("▶ 播放")
        self.btn_next = QPushButton("⏭ 下一帧")
        self.btn_prev.clicked.connect(self.prev_frame)
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_next.clicked.connect(self.next_frame)
        for b in (self.btn_prev, self.btn_play, self.btn_next):
            ctrl.addWidget(b)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self.adapter.n_frames - 1)
        self.slider.valueChanged.connect(self._slider_frame)
        ctrl.addWidget(self.slider, 1)

        self.time_label = QLabel()
        self.time_label.setStyleSheet("font-weight: bold; color: #40C4FF; min-width: 160px;")
        ctrl.addWidget(self.time_label)

        self.speed = QComboBox()
        for label, ms in [("0.5x", 200), ("1x", 100), ("2x", 50), ("4x", 25), ("10x", 10)]:
            self.speed.addItem(label, ms)
        self.speed.setCurrentIndex(1)
        self.speed.currentIndexChanged.connect(self._restart_timer)
        ctrl.addWidget(self.speed)

        self.btn_toggle_panel = QPushButton("📊 动力学指标面板")
        self.btn_toggle_panel.setCheckable(True)
        self.btn_toggle_panel.setChecked(True)
        self.btn_toggle_panel.toggled.connect(self._toggle_panel)
        ctrl.addWidget(self.btn_toggle_panel)

        left_layout.addLayout(ctrl)
        splitter.addWidget(left_widget)

        # ---------------- 右侧：动力学物理指标面板 ----------------
        self.side_panel = QWidget()
        side_layout = QVBoxLayout(self.side_panel)
        side_layout.setContentsMargins(4, 4, 4, 4)
        side_layout.setSpacing(8)

        # 实时单帧指标
        live_grp = QGroupBox("当前帧物理量 (对齐初始构象)")
        live_layout = QVBoxLayout(live_grp)
        self.lbl_live_rmsd = QLabel("Kabsch RMSD: 0.000 Å")
        self.lbl_live_rg = QLabel("回旋半径 Rg: 0.000 Å")
        self.lbl_live_atoms = QLabel(f"体系原子数: {self.adapter.n_atoms} | 总帧数: {self.adapter.n_frames}")
        for l in (self.lbl_live_rmsd, self.lbl_live_rg, self.lbl_live_atoms):
            l.setStyleSheet("font-size: 12px; padding: 2px;")
            live_layout.addWidget(l)
        side_layout.addWidget(live_grp)

        # 全轨迹统计与流式计算
        stats_grp = QGroupBox("全轨迹统计分析 (Streaming Welford)")
        stats_layout = QVBoxLayout(stats_grp)

        btn_run_analysis = QPushButton("🚀 运行全轨迹 RMSD & RMSF 批处理")
        btn_run_analysis.setProperty("role", "action")
        btn_run_analysis.clicked.connect(self._run_batch_analysis)
        stats_layout.addWidget(btn_run_analysis)

        self.analysis_progress = QProgressBar()
        self.analysis_progress.setVisible(False)
        self.analysis_progress.setRange(0, 0) # 忙碌等待状态
        stats_layout.addWidget(self.analysis_progress)

        self.lbl_stats_summary = QLabel("尚未运行全轨迹分析。\n点击上方按钮进行后台非阻塞计算。")
        self.lbl_stats_summary.setStyleSheet("color: #888; font-size: 11px;")
        self.lbl_stats_summary.setWordWrap(True)
        stats_layout.addWidget(self.lbl_stats_summary)

        # 高涨落原子列表 (Top RMSF)
        self.table_rmsf = QTableWidget(0, 3)
        self.table_rmsf.setHorizontalHeaderLabels(["原子序号", "元素/残基", "RMSF (Å)"])
        self.table_rmsf.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        stats_layout.addWidget(self.table_rmsf, 1)

        btn_export = QPushButton("💾 导出分析数据 (CSV)...")
        btn_export.clicked.connect(self._export_analysis_csv)
        stats_layout.addWidget(btn_export)

        side_layout.addWidget(stats_grp, 1)
        splitter.addWidget(self.side_panel)
        splitter.setSizes([950, 400])

        # 播放定时器（主线程，按节拍切帧）
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self._update_label()

    def _residue_colors(self):
        try:
            resnames = np.array(self.adapter.u.atoms.resnames)
            colors = np.zeros((self.adapter.n_atoms, 3), dtype=np.float32)
            for r, c in _RES_COLORS.items():
                colors[resnames == r] = c
            return colors
        except Exception:
            return np.full((self.adapter.n_atoms, 3), 0.7, dtype=np.float32)

    def _build_mesh(self, coords):
        self.mesh = pv.PolyData(np.asarray(coords, dtype=np.float32))
        self.mesh.point_data["colors"] = self._residue_colors()
        self.plotter.add_mesh(
            self.mesh, scalars="colors", rgb=True, style="points",
            point_size=4, render_points_as_spheres=True)

    def _show_frame(self, i: int):
        self.frame = i
        coords = self.adapter.get_frame(i)
        # 零拷贝快速更新点集
        self.mesh.points = np.asarray(coords, dtype=np.float32)
        self.plotter.render()

        if self.slider.value() != i:
            self.slider.blockSignals(True)
            self.slider.setValue(i)
            self.slider.blockSignals(False)

        self._update_label()
        self._update_live_metrics(coords)

        # 异步预取后续帧
        self.adapter.prefetch_async(
            [(i + k) % self.adapter.n_frames for k in range(1, 21)])

    def _update_live_metrics(self, current_coords: np.ndarray):
        try:
            _, rmsd, _ = kabsch_align(current_coords, self.ref_coords)
            rg = calculate_radius_of_gyration(current_coords)
            self.lbl_live_rmsd.setText(f"Kabsch RMSD: {rmsd:.3f} Å")
            self.lbl_live_rg.setText(f"回旋半径 Rg: {rg:.3f} Å")
        except Exception:
            pass

    def _tick(self):
        nxt = self.frame + 1
        if nxt >= self.adapter.n_frames:
            nxt = 0
        self._show_frame(nxt)

    def toggle_play(self):
        self.playing = not self.playing
        if self.playing:
            self.timer.start(self.speed.currentData())
            self.btn_play.setText("⏸ 暂停")
        else:
            self.timer.stop()
            self.btn_play.setText("▶ 播放")

    def _restart_timer(self):
        if self.playing:
            self.timer.start(self.speed.currentData())

    def next_frame(self):
        self._show_frame(min(self.frame + 1, self.adapter.n_frames - 1))

    def prev_frame(self):
        self._show_frame(max(self.frame - 1, 0))

    def _slider_frame(self, i: int):
        if i != self.frame:
            self._show_frame(i)

    def _update_label(self):
        t = self.adapter.frame_time_ps(self.frame)
        self.time_label.setText(
            f"帧 {self.frame}/{self.adapter.n_frames-1}  ·  {t:.1f} ps")

    def _toggle_panel(self, checked: bool):
        self.side_panel.setVisible(checked)

    # ---------------- 后台批处理动力学指标 ----------------

    def _run_batch_analysis(self):
        self.analysis_progress.setVisible(True)
        self.lbl_stats_summary.setText("正在后台进行流式 Kabsch RMSD 与 Welford RMSF 分析...")

        stride = max(1, self.adapter.n_frames // 500) # 若帧数过多，自动步进抽样
        self.worker = _AnalysisWorker(self.adapter, stride=stride)
        self.thread = threading.Thread(target=self._worker_wrapper, args=(stride,), daemon=True)
        self.thread.start()

    def _worker_wrapper(self, stride: int):
        try:
            res = calculate_trajectory_metrics(self.adapter, ref_frame=0, stride=stride)
            QTimer.singleShot(0, lambda: self._on_analysis_finished(res))
        except Exception as e:
            err = str(e)
            QTimer.singleShot(0, lambda: self._on_analysis_error(err))

    def _on_analysis_finished(self, res: dict):
        self.analysis_progress.setVisible(False)
        self.analysis_data = res

        mean_rmsd = res.get("mean_rmsd", 0.0)
        max_rmsd = res.get("max_rmsd", 0.0)
        mean_rg = res.get("mean_rg", 0.0)

        self.lbl_stats_summary.setText(
            f"✅ 分析完成 (采样帧数: {len(res['frame_indices'])})\n"
            f"平均 RMSD: {mean_rmsd:.3f} Å  |  最大 RMSD: {max_rmsd:.3f} Å\n"
            f"平均回旋半径 Rg: {mean_rg:.3f} Å"
        )
        self.lbl_stats_summary.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")

        # 填充高 RMSF 原子前 20 名
        rmsf = res.get("rmsf", np.zeros(0))
        if len(rmsf) > 0:
            top_indices = np.argsort(rmsf)[::-1][:20]
            self.table_rmsf.setRowCount(len(top_indices))
            for row, aidx in enumerate(top_indices):
                val = rmsf[aidx]
                elem = self.adapter.elements[aidx] if aidx < len(self.adapter.elements) else "X"
                self.table_rmsf.setItem(row, 0, QTableWidgetItem(str(aidx + 1)))
                self.table_rmsf.setItem(row, 1, QTableWidgetItem(str(elem)))
                self.table_rmsf.setItem(row, 2, QTableWidgetItem(f"{val:.3f}"))

    def _on_analysis_error(self, err_msg: str):
        self.analysis_progress.setVisible(False)
        self.lbl_stats_summary.setText(f"❌ 分析失败: {err_msg}")
        self.lbl_stats_summary.setStyleSheet("color: #F44336; font-size: 11px;")

    def _export_analysis_csv(self):
        if not self.analysis_data:
            QMessageBox.information(self, "提示", "请先运行全轨迹分析以生成数据。")
            return

        path, _ = QFileDialog.getSaveFileName(self, "导出轨迹分析 CSV", "trajectory_metrics.csv", "CSV Files (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Frame", "Time_ps", "Kabsch_RMSD_A", "Radius_of_Gyration_A"])
                indices = self.analysis_data["frame_indices"]
                times = self.analysis_data["times_ps"]
                rmsds = self.analysis_data["rmsd"]
                rgs = self.analysis_data["rg"]
                for i in range(len(indices)):
                    writer.writerow([indices[i], f"{times[i]:.2f}", f"{rmsds[i]:.4f}", f"{rgs[i]:.4f}"])

            QMessageBox.information(self, "成功", f"轨迹时序数据已成功导出至:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
