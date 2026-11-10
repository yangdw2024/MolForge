"""Element-specific ideal geometry templates and functional fragments."""
from __future__ import annotations
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QPushButton,
    QLabel,QWidget,QScrollArea,QCheckBox,QComboBox,QSpinBox,QMessageBox,QTabWidget)
from ..element_picker import ElementPickerDialog
from ...domain.elements import ELEMENTS
from ...domain.coordination import GEOMETRIES,preferred_geometries,valence_limit
from ...domain.chemistry import estimate_bond_length
from ...application.fragment_catalog import FragmentCatalog,FragmentSpec,FragmentAtomTemplate,FragmentBondTemplate


class _EmbeddedTable(ElementPickerDialog):
    def __init__(self,parent):
        super().__init__(parent,compact=True)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setMinimumSize(0,0)
        self.info_label.hide()
        self.layout().setContentsMargins(6,6,6,6)
        for button,element in self._buttons:
            button.setFixedSize(28,28)
            button.setText(element.symbol)
        self.grid.setSpacing(3)
    def _on_clicked(self,elem):
        self.selected_element=elem;self._show_info(elem);self.element_selected.emit(elem)
    def eventFilter(self,obj,event):
        # This is a builder table; right-click chooses the same element, never nests dialogs.
        if event.type()==event.Type.MouseButtonPress and hasattr(event,'button') and event.button()==Qt.MouseButton.RightButton:
            for button,element in self._buttons:
                if obj is button:self._on_clicked(element);return True
        return QWidget.eventFilter(self,obj,event)


class GeometryTile(QPushButton):
    def __init__(self,geometry,parent=None):
        super().__init__(parent);self.geometry=geometry
        self.setMinimumSize(162,112)
        self.setToolTip(f'{geometry.name} / {geometry.symbol} / {geometry.coordination} 个理想方向')
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center=QPointF(self.width()/2,42)
        painter.setPen(QPen(QColor('#80b9c4'),2))
        # Oblique projection preserves visibility of axial sites.
        for x,y,z in self.geometry.directions:
            end=center+QPointF((x+.38*z)*26,(-y-.45*z)*26)
            painter.drawLine(center,end);painter.setBrush(QColor('#c8e7ef'));painter.drawEllipse(end,3,3)
        painter.setBrush(QColor('#48d6c0'));painter.drawEllipse(center,6,6)
        painter.setPen(QColor('#eaf2f6'))
        painter.drawText(self.rect().adjusted(4,76,-4,-2),Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignTop,
                         f'{self.geometry.name}\n{self.geometry.symbol} · CN {self.geometry.coordination}')


class ElementFragmentsDialog(QDialog):
    fragment_chosen=pyqtSignal(object)
    def __init__(self,parent=None,initial_category='C',geometry_only=False):
        super().__init__(parent)
        self.setWindowTitle('元素片段 · 成键与配位几何')
        self.resize(850,760);self.setMinimumSize(600,520)
        self.selected_fragment=None;self.selected_geometry=None;self.geometry_only=geometry_only
        self.element=next((e for e in ELEMENTS.values() if e.symbol.lower()==initial_category.lower()),ELEMENTS[6])
        frame=QVBoxLayout(self)
        scroller=QScrollArea();scroller.setWidgetResizable(True);frame.addWidget(scroller)
        body=QWidget();scroller.setWidget(body)
        outer=QVBoxLayout(body)
        self.table=_EmbeddedTable(self);self.table.setFixedHeight(365)
        self.table.element_selected.connect(self._choose_element);outer.addWidget(self.table,1)
        self.heading=QLabel();outer.addWidget(self.heading)
        settings=QHBoxLayout()
        self.all_shapes=QCheckBox('浏览全部理想几何');self.all_shapes.toggled.connect(self._rebuild)
        settings.addWidget(self.all_shapes)
        self.charge=QSpinBox();self.charge.setRange(-8,8);self.charge.setPrefix('中心形式电荷 ');settings.addWidget(self.charge)
        self.shell=QCheckBox('生成显式配体壳层');settings.addWidget(self.shell)
        self.ligand=QComboBox()
        for z in (1,9,17,35,53):self.ligand.addItem(ELEMENTS[z].symbol,z)
        settings.addWidget(self.ligand);outer.addLayout(settings)
        self.tabs=QTabWidget();self.tabs.setMinimumHeight(270);outer.addWidget(self.tabs,2)
        self.note=QLabel('默认只插入中心原子并记录生长方向；之后自动成键沿模板生长。壳层为独立分子初值。理想几何不预测氧化态、自旋或热力学稳定性。')
        self.note.setWordWrap(True);outer.addWidget(self.note)
        if geometry_only:
            self.table.hide();self.shell.hide();self.ligand.hide();self.charge.hide()
            self.note.setText('整理已有邻居方向，保持中心键长与各支链内部结构；环/桥联或移动冻结原子时拒绝。')
        close=QPushButton('关闭');close.clicked.connect(self.reject);outer.addWidget(close)
        self._rebuild()
    def _choose_element(self,element):self.element=element;self._rebuild()
    def _rebuild(self,*args):
        self.heading.setText(f'{self.element.name_cn} {self.element.symbol} · 选择构建几何')
        while self.tabs.count():
            widget=self.tabs.widget(0);self.tabs.removeTab(0);widget.deleteLater()
        scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();grid=QGridLayout(page)
        geometries=tuple(GEOMETRIES.values()) if self.all_shapes.isChecked() else preferred_geometries(self.element)
        if not self.geometry_only:
            atom=QPushButton(f'{self.element.symbol}\n单个原子');atom.setMinimumSize(162,112)
            atom.clicked.connect(lambda:self._pick_geometry(None));grid.addWidget(atom,0,0)
        offset=0 if self.geometry_only else 1
        for i,g in enumerate(geometries,offset):
            tile=GeometryTile(g);tile.clicked.connect(lambda checked=False,key=g.key:self._pick_geometry(key))
            grid.addWidget(tile,i//4,i%4)
        if not geometries:
            msg=QLabel('无默认几何推荐。可浏览全部理想几何，不能据此推断该元素的真实配位化学。');msg.setWordWrap(True);grid.addWidget(msg,1,0,1,4)
        grid.setRowStretch(grid.rowCount(),1);scroll.setWidget(page);self.tabs.addTab(scroll,'成键 / 配位方向')
        if not self.geometry_only:
            scroll=QScrollArea();scroll.setWidgetResizable(True);page=QWidget();grid=QGridLayout(page)
            for i,spec in enumerate(FragmentCatalog.for_element_symbol(self.element.symbol)):
                button=QPushButton(f'{spec.name_cn}\n{spec.formula}');button.setMinimumHeight(52);button.setToolTip(spec.description)
                button.clicked.connect(lambda checked=False,s=spec:self._on_pick(s));grid.addWidget(button,i//3,i%3)
            scroll.setWidget(page);self.tabs.addTab(scroll,'官能团 / 环片段')
    def _pick_geometry(self,key):
        self.selected_geometry=key
        if self.geometry_only:
            if key:self.accept()
            return
        geometry=GEOMETRIES.get(key);element=self.element;charge=self.charge.value()
        atoms=[FragmentAtomTemplate(element.atomic_number,element.symbol,(0.,0.,0.),charge)];bonds=[]
        if geometry and self.shell.isChecked():
            limit=valence_limit(element.atomic_number,charge)
            if limit is not None and geometry.coordination>limit:
                QMessageBox.warning(self,'请检查价态','该壳层超过此形式电荷的常用价态；请更换几何/电荷，或只插入中心方向模板。');return
            z=self.ligand.currentData();length=estimate_bond_length(element.atomic_number,z)
            for vector in geometry.directions:
                atoms.append(FragmentAtomTemplate(z,ELEMENTS[z].symbol,tuple(np.asarray(vector)*length)))
                bonds.append(FragmentBondTemplate(0,len(atoms)-1,1))
        name=f'{element.symbol} · {geometry.name if geometry else "单原子"}'
        spec=FragmentSpec('geometry-'+element.symbol+'-'+str(key),name,name,element.symbol,element.symbol,'',1,
                          tuple(atoms),tuple(bonds),'理想构建初值；不代表实测稳定配合物',key)
        self._on_pick(spec)
    def _on_pick(self,spec):
        self.selected_fragment=spec;self.fragment_chosen.emit(spec);self.accept()
