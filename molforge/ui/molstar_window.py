"""Mol* 大分子视图窗口：离线渲染蛋白质，链/残基选择，display presets。"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QPushButton)
from PyQt6.QtCore import Qt

from molforge.ui.molstar_widget import MolStarWidget


_PRESETS = [
    ("默认（卡通+配体）", "default"),
    ("卡通 Cartoon", "cartoon"),
    ("球棍 Ball-and-Stick", "ball-and-stick"),
    ("分子表面 Surface", "molecular-surface"),
    ("聚合物与配体", "polymer-and-ligand"),
]


class MolStarWindow(QMainWindow):
    def __init__(self, text: str, fmt: str = "pdb", name: str = "structure", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"大分子视图 - {name}")
        self.resize(1200, 850)

        central = QWidget()
        self.setCentralWidget(central)
        self.setStyleSheet("""
            QWidget { background:#0F1A29; color:#EAF2F6; }
            QComboBox { background:#152435; border:1px solid #2A3B4A;
                border-radius:4px; padding:4px 8px; min-width:180px; }
            QComboBox QAbstractItemView { background:#152435;
                selection-background-color:#1A2C40; border:1px solid #2A3B4A; }
            QPushButton { background:#152435; border:1px solid #2A3B4A;
                border-radius:4px; padding:5px 12px; }
            QPushButton:hover { background:#1A2C40; }
            QLabel { background:transparent; }
        """)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 工具栏：表示预设 + 重置相机
        bar = QHBoxLayout()
        bar.addWidget(QLabel("表示："))
        self.preset_box = QComboBox()
        for label, key in _PRESETS:
            self.preset_box.addItem(label, key)
        self.preset_box.currentIndexChanged.connect(self._apply_preset)
        bar.addWidget(self.preset_box)
        bar.addStretch()
        reset_btn = QPushButton("重置相机")
        reset_btn.clicked.connect(self._reset_camera)
        bar.addWidget(reset_btn)
        layout.addLayout(bar)

        # Mol* 视图
        self.viewer = MolStarWidget()
        self.viewer.on_picked = self._on_picked
        layout.addWidget(self.viewer, 1)

        # 选中信息
        self.pick_label = QLabel("点击分子可选中链 / 残基 / 原子")
        self.pick_label.setStyleSheet(
            "color:#95A9B8; padding:4px 6px; background:#152435; border-radius:4px;")
        layout.addWidget(self.pick_label)

        # 加载
        self.viewer.load_pdb(text, name, fmt)

    def _apply_preset(self):
        key = self.preset_box.currentData()
        self.viewer.apply_preset(key)

    def _reset_camera(self):
        self.viewer.reset_camera()

    def _on_picked(self, loc: str):
        parts = loc.split("|")
        if len(parts) == 4:
            chain, seq, res, atom = parts
            text = f"链 {chain}  ·  残基 {res} {seq}  ·  原子 {atom}"
        else:
            text = loc
        self.pick_label.setText(text)
