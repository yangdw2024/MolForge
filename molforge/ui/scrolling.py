"""Natural-size tool strips: controls keep their text; the viewport scrolls."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QScrollArea, QFrame, QLayout, QPushButton, QLabel, QSizePolicy

class HorizontalWheelScrollArea(QScrollArea):
    height_changed = pyqtSignal(int)
    def __init__(self, content_widget, height=42, parent=None):
        super().__init__(parent)
        if not content_widget.objectName():
            content_widget.setObjectName("ToolbarStrip")
        content_widget.ensurePolished()
        for child in content_widget.findChildren(QPushButton) + content_widget.findChildren(QLabel):
            child.ensurePolished()
            child.setMinimumWidth(min(child.maximumWidth(), max(child.minimumWidth(), child.sizeHint().width())))
        content_widget.setMinimumHeight(max(height, content_widget.sizeHint().height()))
        content_widget.layout().setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.setWidget(content_widget)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(content_widget.minimumHeight() + self.horizontalScrollBar().sizeHint().height())
        self.horizontalScrollBar().rangeChanged.connect(self._fit_height)

    def _fit_height(self, minimum, maximum):
        content_height = max(self.widget().minimumHeight(), self.widget().sizeHint().height())
        self.setFixedHeight(content_height + (self.horizontalScrollBar().sizeHint().height() if maximum > 0 else 0))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.height_changed.emit(self.height())

    def wheelEvent(self, event):
        bar = self.horizontalScrollBar()
        # 若水平滚动条存在且有可滚动余量，则响应水平滚轮
        if bar and bar.maximum() > 0:
            delta = event.angleDelta().y() or event.angleDelta().x()
            old_val = bar.value()
            bar.setValue(old_val - int(delta * .6))
            if bar.value() != old_val:
                event.accept()
                return
        event.ignore()
        # 否则将纵向滚轮事件透传给外层父级垂直滚动容器
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                parent.wheelEvent(event)
                break
            parent = parent.parent()
