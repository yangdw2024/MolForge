"""
ui/element_picker.py - 元素周期表选择器
==========================================
完整 118 种元素，按真实周期表布局（含镧系/锕系），
按钮三行信息（原子序数 / 符号 / 原子量），CPK 着色，
顶部搜索框按符号/中文名过滤，深色仪器风格。
"""
from PyQt6.QtCore import Qt, pyqtSignal, QSortFilterProxyModel, QAbstractListModel, QModelIndex
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLabel,
    QWidget, QLineEdit, QScrollArea, QFrame, QLayout
)
from ..domain.elements import ELEMENTS, Element


def _cpk_qcolor(elem: Element) -> str:
    """把元素的 CPK 颜色转成十六进制（适当提亮，深色背景下更清楚）。"""
    r, g, b = elem.cpk_color
    r = min(1.0, r * 1.15 + 0.08)
    g = min(1.0, g * 1.15 + 0.08)
    b = min(1.0, b * 1.15 + 0.08)
    return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"


def _text_color(elem: Element) -> str:
    """根据元素底色亮度决定文字用黑还是白。"""
    r, g, b = elem.cpk_color
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return "#101820" if lum > 0.6 else "#FFFFFF"


class ElementPickerDialog(QDialog):
    """完整元素周期表选择器。"""

    element_selected = pyqtSignal(Element)

    def __init__(self, parent=None, compact=False):
        super().__init__(parent)
        self.setWindowTitle("元素周期表")
        self.compact = bool(compact)
        self.selected_element: Element | None = None
        self.setMinimumSize(600, 420)
        self.resize(780, 560) if self.compact else self.resize(1100, 700)

        self.setStyleSheet("""
            QDialog { background: #0F1A29; }
            QLabel { color: #EAF2F6; }
            QLineEdit {
                background: #172B3C; color: #EAF2F6;
                border: 1px solid #365165; border-radius: 8px;
                padding: 8px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #66DEC9; }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # 标题行
        header = QHBoxLayout()
        title = QLabel("元素周期表 · 选择当前元素")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        header.addWidget(title)
        header.addStretch()
        # 搜索框
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索符号或中文名（如 C / 碳 / carbon）")
        self.search.setMaximumWidth(320)
        self.search.textChanged.connect(self._filter_elements)
        header.addWidget(self.search)
        outer.addLayout(header)

        # 周期表滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        self.table_scroll = scroll
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        table_widget = QWidget()
        self.grid = QGridLayout(table_widget)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(table_widget)
        outer.addWidget(scroll, 1)

        # 信息栏
        self.info_label = QLabel("请选择一个元素；横向/纵向滚动查看完整周期表。半径来自 RDKit 参考表，重元素可能含估计值。")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            "color:#EAF2F6; background:#152435; border:1px solid #2A3B4A;"
            "border-radius:8px; padding:10px; font-size:13px;"
        )
        outer.addWidget(self.info_label)

        # 存储所有按钮，便于过滤
        self._buttons: list[tuple[QPushButton, Element]] = []
        self._build_table()

    def _make_button(self, elem: Element) -> QPushButton:
        """生成三行信息的元素按钮。"""
        bg = _cpk_qcolor(elem)
        fg = _text_color(elem)
        # 原子量简写
        aw = f"{elem.atomic_weight:g}"
        btn = QPushButton(f"{elem.symbol}\n{elem.atomic_number}" if self.compact else f"{elem.atomic_number}\n{elem.symbol}\n{aw}")
        btn.setFixedSize(36, 36) if self.compact else btn.setFixedSize(66, 66)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {fg};
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 6px;
                text-align: center;
                font-weight: bold;
                padding: 2px;
            }}
            QPushButton:hover {{
                border: 2px solid #66DEC9;
            }}
            QPushButton:pressed {{
                background: #2A4A5A;
            }}
        """)
        btn.setToolTip(
            f"{elem.name_cn} ({elem.name})\n"
            f"原子序数: {elem.atomic_number}\n"
            f"原子量: {elem.atomic_weight}\n"
            f"电负性: {elem.electronegativity or 'N/A'}\n"
            f"范德华半径: {elem.vdw_radius} Å\n"
            f"共价半径: {elem.covalent_radius} Å（RDKit 参考值，非唯一实测半径）\n"
            f"分类: {elem.category}\n"
            f"电子构型: {elem.electron_config}"
        )
        btn.clicked.connect(lambda checked=False, e=elem: self._on_clicked(e))
        btn.installEventFilter(self)
        return btn

    def _build_table(self):
        """按真实周期表布局摆放按钮。"""
        for z, elem in ELEMENTS.items():
            if 57 <= z <= 71 or 89 <= z <= 103:
                continue
            row = elem.period - 1
            col = elem.group - 1
            btn = self._make_button(elem)
            self.grid.addWidget(btn, row, col)
            self._buttons.append((btn, elem))

        for row, text in ((5, "57–71"), (6, "89–103")):
            self.grid.addWidget(QLabel(text), row, 2)

        # f 区标签
        f_base_row = 8  # 主表 7 行 + 1 空行
        lan_lbl = QLabel("镧系")
        lan_lbl.setStyleSheet("color:#95A9B8; font-size:11px;")
        self.grid.addWidget(lan_lbl, f_base_row, 0, 1, 2)
        act_lbl = QLabel("锕系")
        act_lbl.setStyleSheet("color:#95A9B8; font-size:11px;")
        self.grid.addWidget(act_lbl, f_base_row + 1, 0, 1, 2)

        for z in range(57, 72):
            elem = ELEMENTS[z]
            btn = self._make_button(elem)
            self.grid.addWidget(btn, f_base_row, z - 57 + 2)
            self._buttons.append((btn, elem))
        for z in range(89, 104):
            elem = ELEMENTS[z]
            btn = self._make_button(elem)
            self.grid.addWidget(btn, f_base_row + 1, z - 89 + 2)
            self._buttons.append((btn, elem))

    def _filter_elements(self, text: str):
        """按搜索文本过滤按钮可见性。"""
        text = text.strip().lower()
        if not text:
            for btn, _ in self._buttons:
                btn.setVisible(True)
            return
        for btn, elem in self._buttons:
            match = (text in elem.symbol.lower()
                     or text in elem.name_cn
                     or text in elem.name.lower()
                     or str(elem.atomic_number) == text)
            btn.setVisible(match)

    def eventFilter(self, obj, event):
        """悬停时显示元素详情；右键点击元素按钮时弹出 ElementFragmentsDialog 基团面板。"""
        if event.type() == event.Type.Enter and isinstance(obj, QPushButton):
            for btn, elem in self._buttons:
                if btn is obj:
                    self._show_info(elem)
                    break
        elif event.type() == event.Type.MouseButtonPress and isinstance(obj, QPushButton):
            if hasattr(event, "button") and event.button() == Qt.MouseButton.RightButton:
                for btn, elem in self._buttons:
                    if btn is obj:
                        from .dialogs.element_fragments import ElementFragmentsDialog
                        dlg = ElementFragmentsDialog(self, initial_category=elem.symbol)
                        if dlg.exec() and dlg.selected_fragment is not None:
                            self.selected_fragment = dlg.selected_fragment
                            self.selected_element = elem
                            self.accept()
                        return True
        return super().eventFilter(obj, event)

    def _show_info(self, elem: Element):
        self.info_label.setText(
            f"{elem.name_cn} ({elem.symbol})  ·  序数 {elem.atomic_number}  ·  "
            f"原子量 {elem.atomic_weight}  ·  电负性 {elem.electronegativity or 'N/A'}  ·  "
            f"vdW半径 {elem.vdw_radius} Å / 共价半径 {elem.covalent_radius} Å（RDKit参考，可能含估计值）  ·  {elem.category}  ·  {elem.electron_config}"
        )

    def _on_clicked(self, elem: Element):
        self.selected_element = elem
        self._show_info(elem)
        self.element_selected.emit(elem)
        self.accept()
