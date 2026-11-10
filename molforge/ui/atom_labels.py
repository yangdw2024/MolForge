"""Qt screen labels above the VTK surface, with no molecular coordinate changes."""
from PyQt6.QtCore import Qt, QPoint, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget
from ..domain.elements import get_element
import math


class AtomLabelOverlay(QWidget):
    def __init__(self, owner, parent):
        super().__init__(parent)
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.scope = "heavy"
        self.last_labels = []
        self.last_label_rects = []

    def labels(self):
        backend = self.owner.renderer
        if not (backend.show_labels or backend.show_symbols):
            return []
        coords = backend._coordinates
        ren = getattr(self.owner.plotter, 'renderer', None)
        if coords is None or ren is None:
            return []
        width, height = ren.GetRenderWindow().GetSize()
        if width <= 0 or height <= 0:
            return []
        viewport = ren.GetViewport()
        left, right = viewport[0]*self.width(), viewport[2]*self.width()
        top, bottom = (1-viewport[3])*self.height(), (1-viewport[1])*self.height()
        result = []
        for i, (pos, aid) in enumerate(zip(coords, backend._atom_ids)):
            z = int(backend._atomic_numbers[i])
            if self.scope == "selected" and aid not in backend._selected:
                continue
            if self.scope == "heavy" and z == 1 and aid not in backend._selected:
                continue
            if z == 1 and not backend.show_hydrogens:
                continue
            ren.SetWorldPoint(float(pos[0]), float(pos[1]), float(pos[2]), 1.)
            ren.WorldToDisplay()
            x, y, depth = ren.GetDisplayPoint()
            x, y = x*self.width()/width, (height-y)*self.height()/height
            if not (0 <= depth <= 1 and left <= x <= right and top <= y <= bottom):
                continue
            element = get_element(z)
            text = element.symbol if backend.show_symbols and element else ''
            if backend.show_labels:
                text += str(aid.value + 1)
            result.append((x, y, text))
        return result

    def paintEvent(self, event):
        self.last_labels = self.labels()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont('Arial', 9, QFont.Weight.Normal))
        placed = []
        for x, y, text in self.last_labels:
            base = painter.fontMetrics().boundingRect(text).adjusted(-4, -2, 4, 2)
            candidates = []
            for radius in (18, 34, 52, 74, 100):
                for angle in (-45, 45, -135, 135, 0, 90, 180, -90):
                    rect = type(base)(base)
                    rect.moveCenter(QPoint(int(x+radius*math.cos(math.radians(angle))),
                                           int(y+radius*math.sin(math.radians(angle)))))
                    rect.moveLeft(max(0, min(rect.left(), self.width()-rect.width())))
                    rect.moveTop(max(0, min(rect.top(), self.height()-rect.height())))
                    overlap = sum(rect.adjusted(-2,-2,2,2).intersected(r).width() *
                                  rect.adjusted(-2,-2,2,2).intersected(r).height()
                                  for r, *_ in placed if rect.adjusted(-2,-2,2,2).intersects(r))
                    candidates.append((overlap, radius, rect))
            rect = min(candidates, key=lambda item: (item[0], item[1]))[2]
            placed.append((rect, x, y, text))
        self.last_label_rects = [rect for rect, *_ in placed]
        painter.setPen(QColor(170, 200, 220, 170))
        for rect, x, y, text in placed:
            if math.hypot(rect.center().x()-x,rect.center().y()-y)>28:
                painter.drawLine(QPointF(x, y), QPointF(rect.center()))
        for rect, x, y, text in placed:
            path = QPainterPath()
            fm = painter.fontMetrics()
            path.addText(rect.center().x()-fm.horizontalAdvance(text)/2,
                         rect.center().y()+(fm.ascent()-fm.descent())/2, painter.font(), text)
            painter.setBrush(QColor('#F3F7FA'))
            painter.setPen(QPen(QColor(12,24,38,210),1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            painter.strokePath(path,painter.pen())
            painter.fillPath(path,QColor('#F3F7FA'))
        painter.end()
