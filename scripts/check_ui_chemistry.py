"""UI/chemistry regression checks; writes only project qa_evidence. Offscreen, not native visual acceptance."""
import os, sys, json, ast
from pathlib import Path
P=Path(__file__).resolve().parents[1]
R=P/'qa_evidence'/'ui_chemistry'
(R/'evidence').mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(P))
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['MOLFORGE_DATA_DIR']=str(R/'runtime')
from molforge.runtime import configure_runtime
configure_runtime()
from PyQt6.QtWidgets import QApplication, QWidget, QHBoxLayout, QPushButton, QLabel
from molforge.ui.scrolling import HorizontalWheelScrollArea
from molforge.ui.element_picker import ElementPickerDialog
from molforge.domain.document import MoleculeDocument
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import AddAtomCommand
from molforge.domain.elements import ELEMENTS
from molforge.domain.chemistry import estimate_bond_length
from molforge.io.history_skill import export_history_skill
import numpy as np
app=QApplication([])
from PyQt6.QtGui import QFontDatabase,QFont
QFontDatabase.addApplicationFont("C:/Windows/Fonts/arial.ttf");QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc");app.setFont(QFont("Microsoft YaHei",10))
from molforge.ui.theme import STYLE
app.setStyleSheet(STYLE)
checks=[]
def check(condition, name):
    print(name, bool(condition), flush=True)
    checks.append({'check':name,'pass':bool(condition)})
    assert condition,name
for p in P.rglob('*.py'):
    if 'user_data' not in p.parts: ast.parse(p.read_text(encoding='utf-8-sig'))
check(True,'all Python syntax')
content=QWidget();layout=QHBoxLayout(content)
for i in range(8): layout.addWidget(QPushButton(f'完整标题按钮 {i}'))
strip=HorizontalWheelScrollArea(content);strip.resize(350,strip.height());strip.show();app.processEvents()
check(strip.horizontalScrollBar().maximum()>0,'narrow toolbar scrolls')
check(all(b.width()>=b.sizeHint().width() for b in content.findChildren(QPushButton)),'buttons keep text width')
strip.horizontalScrollBar().setValue(strip.horizontalScrollBar().maximum());app.processEvents()
strip.grab().save(str(R/'evidence'/'toolbar.png'))
picker=ElementPickerDialog();picker.resize(650,450);picker.show();app.processEvents()
check(len(picker._buttons)==118 and len({e.atomic_number for _,e in picker._buttons})==118,'118 unique element cells')
check(picker.table_scroll.horizontalScrollBar().maximum()>0 and picker.table_scroll.verticalScrollBar().maximum()>0,'periodic table scrolls in both directions')
picker.table_scroll.verticalScrollBar().setValue(picker.table_scroll.verticalScrollBar().maximum());app.processEvents()
check(any(b.isVisible() and e.atomic_number==103 for b,e in picker._buttons),'actinide row remains available')
picker.grab().save(str(R/'evidence'/'periodic_table.png'))
from molforge.rendering.vtk_backend import VtkRendererBackend, VDW_RADII
from molforge.rendering.contracts import RepresentationMode
backend=VtkRendererBackend();backend._n_atoms=118;backend._atomic_numbers=np.arange(1,119);backend._per_atom_scales=np.ones(118);backend._mode=RepresentationMode.CPK
check(all(abs(backend.get_effective_atom_radius(z-1)-ELEMENTS[z].vdw_radius)<1e-7 for z in ELEMENTS),'all 118 CPK radii equal reference angstroms')
check(estimate_bond_length(6,9)<estimate_bond_length(6,17)<estimate_bond_length(6,35),'halogen bond construction responds to elements')
check(estimate_bond_length(6,6,3)<estimate_bond_length(6,6,2)<estimate_bond_length(6,6,1),'multiple bond construction contracts')
doc=MoleculeDocument('test');bus=CommandBus(doc);check(bus.execute(AddAtomCommand(6,0,0,0)).success,'initial atom command')
anchor=list(doc.topology.atom_ids)[0]
check(bus.execute(AddAtomCommand(17,bond_to=anchor)).success,'element-aware new bond')
length=np.linalg.norm(doc.coordinates.current.coords[1]-doc.coordinates.current.coords[0])
check(abs(length-estimate_bond_length(6,17))<1e-5,'new C-Cl coordinate distance matches estimate')
bus.undo();bus.redo()
check([e['action'] for e in bus.history.audit_events]==['execute','execute','undo','redo'],'chronological history retains undo and redo')
folder=export_history_skill(doc,bus.history.audit_events,R/'evidence')
check(len(json.loads((folder/'operations.json').read_text(encoding='utf-8'))['events'])==4 and (folder/'SKILL.md').exists(),'workflow skill exports actual events')
(R/'exported_skill_path.txt').write_text(str(folder),encoding='utf-8')
from molforge.ui.render3d_widget import Render3DWidget
from molforge.io.rdkit_adapter import create_instant_caffeine_document
view=Render3DWidget();view.resize(700,600);view.show();view.set_document(create_instant_caffeine_document());app.processEvents()
view.plotter.renderer.GetRenderWindow().SetSize(700,560);view.reset_camera();app.processEvents()
before=view._document.coordinates.current.coords.copy()
view.renderer.label_scope='all';view.set_view_options(show_labels=True,show_symbols=True);app.processEvents();view._refresh_atom_labels();app.processEvents()
native=view.renderer._native_labels
check(native.strings.GetNumberOfValues()==24,'24 native world anchored label strings')
check(native.actor.GetVisibility() and native.mapper.GetInput() is not None,'native label actor has data')
check(not hasattr(view,'_label_timer'),'no timer-driven Qt label overlay')
mtime=native.data.GetMTime();view.plotter.renderer.GetActiveCamera().Azimuth(30)
check(native.data.GetMTime()==mtime,'camera rotation leaves label geometry unchanged')
view.set_view_options(show_hydrogens=False)
check(native.strings.GetNumberOfValues()==14,'numbering respects hidden hydrogen option')
view.set_mode(RepresentationMode.CPK);view.set_document(view._document);app.processEvents()
np.testing.assert_array_equal(before,view._document.coordinates.current.coords)
check(view.renderer.show_labels and view.lbl_toggle_btn.isChecked(),'numbering persists after document refresh')
check(True,'representation preserves imported coordinates exactly')
view.set_view_options(show_labels=False,show_symbols=False);check(not view.lbl_toggle_btn.isChecked() and not native.actor.GetVisibility(),'numbering off synchronizes button and native actor')
from molforge.ui.window import MolForgeWindow
window=MolForgeWindow();window.resize(1200,800);window.show();app.processEvents()
window.right.switch_tab(3);window.command_bus.execute(AddAtomCommand(8,5,0,0));app.processEvents()
texts=[q.text() for q in window.right.history_page.findChildren(QLabel)]
check(any('添加原子' in t for t in texts),'open history page updates after command')
window.grab().save(str(R/'evidence'/'workbench_qt_offscreen.png'))
(R/'feature_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS',len(checks),flush=True)
os._exit(0)



