"""
ui/settings_panel.py - Blender / DaVinci 风格模块化渲染与主题设置面板
=====================================================================
修复：
  - 移除旧版默认 Windows 95 风格 QGroupBox 与白底看不清字的按钮
  - 每个滑块配备实时百分比/数值读数标签（#66DEC9 等宽字体）
  - 所有滑块与下拉框安装滚轮防误触过滤器（WheelGuard），使面板上下滚动极其顺滑
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QObject, QEvent, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QColorDialog, QSlider, QComboBox
)
from PyQt6.QtGui import QColor


class WheelGuardFilter(QObject):
    """防止在 QScrollArea 中滚动鼠标滚轮时误触未聚焦的控件，同时将滚轮事件无缝转发给外层滚动区域，彻底消除滚轮卡死。"""

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Wheel and not obj.hasFocus():
            event.ignore()
            from PyQt6.QtWidgets import QScrollArea
            parent = obj.parent()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    parent.wheelEvent(event)
                    break
                parent = parent.parent()
            return True
        return super().eventFilter(obj, event)


def install_wheel_guard(widget: QWidget, guard: WheelGuardFilter) -> None:
    widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    widget.installEventFilter(guard)


class SettingsCard(QFrame):
    """带精致标题栏的设置模块卡片。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CollapsibleCard")
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        self.header_btn = QPushButton(f"▾  {title}")
        self.header_btn.setObjectName("CardHeaderBtn")
        self.header_btn.setCheckable(True)
        self.header_btn.setChecked(True)
        self.header_btn.clicked.connect(self._toggle)
        self._root.addWidget(self.header_btn)
        self._title = title

        self.body = QWidget()
        self.body.setObjectName("ScrollPage")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(11, 10, 11, 11)
        self.body_layout.setSpacing(8)
        self._root.addWidget(self.body)

    def _toggle(self, checked: bool):
        self.body.setVisible(checked)
        arrow = "▾" if checked else "▸"
        self.header_btn.setText(f"{arrow}  {self._title}")


class SettingsPanel(QWidget):
    """
    模块化渲染与外观设置面板。
    """

    canvas_color_changed = pyqtSignal(QColor)
    material_changed = pyqtSignal(str)
    theme_changed = pyqtSignal(str)
    atom_size_changed = pyqtSignal(float)
    bond_width_changed = pyqtSignal(float)
    background_3d_changed = pyqtSignal(QColor)
    roughness_changed = pyqtSignal(float)
    metallic_changed = pyqtSignal(float)
    accent_picked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ScrollPage")
        self._wheel_guard = WheelGuardFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 6, 12)
        layout.setSpacing(10)

        # 1. 3D 球棍与几何比例模块
        geom_card = SettingsCard("3D 球棍比例与尺寸 (GEOMETRY SCALE)")
        b_lay = geom_card.body_layout

        # 原子大小滑块 + 实时读数
        row_a_top = QHBoxLayout()
        row_a_top.addWidget(QLabel("原子球半径缩放"))
        row_a_top.addStretch()
        self.atom_val_label = QLabel("100%")
        self.atom_val_label.setProperty("role", "value")
        row_a_top.addWidget(self.atom_val_label)
        b_lay.addLayout(row_a_top)

        self.atom_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.atom_size_slider.setRange(40, 220)
        self.atom_size_slider.setValue(100)
        install_wheel_guard(self.atom_size_slider, self._wheel_guard)
        self.atom_size_slider.valueChanged.connect(self._on_atom_slider)
        b_lay.addWidget(self.atom_size_slider)

        # 键粗细滑块 + 实时读数
        row_b_top = QHBoxLayout()
        row_b_top.addWidget(QLabel("化学键圆柱半径"))
        row_b_top.addStretch()
        self.bond_val_label = QLabel("100%")
        self.bond_val_label.setProperty("role", "value")
        row_b_top.addWidget(self.bond_val_label)
        b_lay.addLayout(row_b_top)

        self.bond_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.bond_width_slider.setRange(40, 220)
        self.bond_width_slider.setValue(100)
        install_wheel_guard(self.bond_width_slider, self._wheel_guard)
        self.bond_width_slider.valueChanged.connect(self._on_bond_slider)
        b_lay.addWidget(self.bond_width_slider)

        layout.addWidget(geom_card)

        # 2. Studio 材质与光照模块
        mat_card = SettingsCard("3D 棚拍材质与高光 (STUDIO SHADING)")
        m_lay = mat_card.body_layout

        row_preset = QHBoxLayout()
        row_preset.addWidget(QLabel("光学预设"))
        self.material_combo = QComboBox()
        self.material_combo.addItems(["Studio", "Scientific", "Analysis"])
        install_wheel_guard(self.material_combo, self._wheel_guard)
        self.material_combo.currentTextChanged.connect(self.material_changed.emit)
        row_preset.addWidget(self.material_combo, 1)
        m_lay.addLayout(row_preset)

        row_r_top = QHBoxLayout()
        row_r_top.addWidget(QLabel("表面粗糙度 (Roughness)"))
        row_r_top.addStretch()
        self.rough_val_label = QLabel("0.35")
        self.rough_val_label.setProperty("role", "value")
        row_r_top.addWidget(self.rough_val_label)
        m_lay.addLayout(row_r_top)

        self.roughness_slider = QSlider(Qt.Orientation.Horizontal)
        self.roughness_slider.setRange(5, 95)
        self.roughness_slider.setValue(35)
        install_wheel_guard(self.roughness_slider, self._wheel_guard)
        self.roughness_slider.valueChanged.connect(self._on_rough_slider)
        m_lay.addWidget(self.roughness_slider)

        row_m_top = QHBoxLayout()
        row_m_top.addWidget(QLabel("环境反射强度 (Ambient)"))
        row_m_top.addStretch()
        self.metal_val_label = QLabel("0.10")
        self.metal_val_label.setProperty("role", "value")
        row_m_top.addWidget(self.metal_val_label)
        m_lay.addLayout(row_m_top)

        self.metallic_slider = QSlider(Qt.Orientation.Horizontal)
        self.metallic_slider.setRange(0, 100)
        self.metallic_slider.setValue(10)
        install_wheel_guard(self.metallic_slider, self._wheel_guard)
        self.metallic_slider.valueChanged.connect(self._on_metal_slider)
        m_lay.addWidget(self.metallic_slider)

        layout.addWidget(mat_card)

        # 3. 主题与视口背景色模块
        theme_card = SettingsCard("界面主题与视口背景 (THEME & CANVAS)")
        t_lay = theme_card.body_layout

        row_theme = QHBoxLayout()
        row_theme.addWidget(QLabel("全局主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Professional", "Light Clean", "High Contrast"])
        install_wheel_guard(self.theme_combo, self._wheel_guard)
        self.theme_combo.currentTextChanged.connect(self.theme_changed.emit)
        row_theme.addWidget(self.theme_combo, 1)
        t_lay.addLayout(row_theme)

        row_colors = QHBoxLayout()
        self.canvas_bg_btn = QPushButton("2D 画布底色...")
        self.canvas_bg_btn.clicked.connect(self._pick_canvas_color)
        row_colors.addWidget(self.canvas_bg_btn)

        self.canvas_3d_btn = QPushButton("3D 视口底色...")
        self.canvas_3d_btn.clicked.connect(self._pick_3d_color)
        row_colors.addWidget(self.canvas_3d_btn)
        t_lay.addLayout(row_colors)

        self.accent_btn = QPushButton("自定义主题强调色 (#66DEC9)...")
        self.accent_btn.clicked.connect(self._pick_accent)
        t_lay.addWidget(self.accent_btn)

        layout.addWidget(theme_card)

        # 4. 界面字体与排版定制 (UI TYPOGRAPHY)
        font_card = SettingsCard("🔤 界面字体与排版定制 (UI TYPOGRAPHY)")
        f_lay = font_card.body_layout

        row_f_family = QHBoxLayout()
        row_f_family.addWidget(QLabel("中英文字体系列"))
        self.font_family_combo = QComboBox()
        self.font_family_combo.addItems([
            "Microsoft YaHei UI",
            "PingFang SC",
            "SimHei",
            "Segoe UI",
            "Arial",
            "System Default",
        ])
        install_wheel_guard(self.font_family_combo, self._wheel_guard)
        row_f_family.addWidget(self.font_family_combo, 1)
        f_lay.addLayout(row_f_family)

        row_f_size = QHBoxLayout()
        row_f_size.addWidget(QLabel("UI 基础字号"))
        self.font_size_combo = QComboBox()
        for sz, lbl in [
            (12, "12px · 紧凑小号"),
            (13, "13px · 标准学术"),
            (14, "14px · 舒适现代 (默认推荐)"),
            (15, "15px · 清晰易读"),
            (16, "16px · 大字号"),
            (18, "18px · 高分屏 4K 宽屏"),
        ]:
            self.font_size_combo.addItem(lbl, sz)
        self.font_size_combo.setCurrentIndex(2)
        install_wheel_guard(self.font_size_combo, self._wheel_guard)
        row_f_size.addWidget(self.font_size_combo, 1)
        f_lay.addLayout(row_f_size)

        btn_apply_font = QPushButton("💾 保存并应用全局字体设置")
        btn_apply_font.setStyleSheet("QPushButton { font-weight:700; font-size:13px; min-height:30px; background:#0D9488; color:#FFFFFF; border:1px solid #5EEAD4; }")
        btn_apply_font.clicked.connect(self._apply_and_save_fonts)
        f_lay.addWidget(btn_apply_font)

        layout.addWidget(font_card)
        layout.addStretch(1)

    def _apply_and_save_fonts(self):
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from PyQt6.QtGui import QFont
        from PyQt6.QtCore import QSettings
        from .theme import build_style
        store = QSettings("MolForge", "Typography")
        family = self.font_family_combo.currentText()
        if family == "System Default":
            family = "Microsoft YaHei UI"
        size = self.font_size_combo.currentData() or 14

        store.setValue("font_family", family)
        store.setValue("font_size", size)

        app = QApplication.instance()
        if app:
            font = QFont(family)
            font.setPixelSize(int(size))
            font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            app.setFont(font)
            new_css = build_style("Dark Professional", font_family=family, font_size=size)
            app.setStyleSheet(new_css)
            # 遍历所有顶级窗口强制刷新布局与样式重绘
            for top_widget in app.topLevelWidgets():
                top_widget.setFont(font)
                from PyQt6.QtWidgets import QWidget
                for child in top_widget.findChildren(QWidget):
                    child.setFont(font)
                top_widget.style().unpolish(top_widget)
                top_widget.style().polish(top_widget)
                top_widget.update()
            app.processEvents()
        QMessageBox.information(self, "字体已更新", f"界面字体已更新为：{family}，基准字号：{size}px！全界面及左右侧边栏已即时同步生效。")

    def _on_atom_slider(self, v: int):
        self.atom_val_label.setText(f"{v}%")
        self.atom_size_changed.emit(v / 100.0)

    def _on_bond_slider(self, v: int):
        self.bond_val_label.setText(f"{v}%")
        self.bond_width_changed.emit(v / 100.0)

    def _on_rough_slider(self, v: int):
        self.rough_val_label.setText(f"{v / 100.0:.2f}")
        self.roughness_changed.emit(v / 100.0)

    def _on_metal_slider(self, v: int):
        self.metal_val_label.setText(f"{v / 100.0:.2f}")
        self.metallic_changed.emit(v / 100.0)

    def _pick_accent(self):
        c = QColorDialog.getColor(QColor("#66DEC9"), self, "选择主题强调色")
        if c.isValid():
            hexc = c.name()
            self.accent_btn.setText(f"强调色: {hexc}")
            self.accent_picked.emit(hexc)

    def _pick_canvas_color(self):
        color = QColorDialog.getColor(QColor("#F4F3EE"), self, "选择 2D 画布颜色")
        if color.isValid():
            self.canvas_color_changed.emit(color)

    def _pick_3d_color(self):
        color = QColorDialog.getColor(QColor("#111D2C"), self, "选择 3D 背景颜色")
        if color.isValid():
            self.background_3d_changed.emit(color)
