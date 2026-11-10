"""Offscreen modeling regression checks. No real xTB engine is invoked by this script."""
from pathlib import Path
import os,sys,json,ast
from unittest.mock import patch
P=Path(__file__).resolve().parents[1];R=P/'qa_evidence'/'modeling_polish';(R/'evidence').mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(P))
os.environ.update(QT_QPA_PLATFORM='offscreen',MOLFORGE_DATA_DIR=str(R/'runtime'))
from molforge.runtime import configure_runtime
configure_runtime()
import numpy as np
from PyQt6.QtWidgets import QApplication,QMenu,QLabel
from PyQt6.QtGui import QFontDatabase,QFont
from PyQt6.QtCore import QPointF
from molforge.ui.theme import STYLE
app=QApplication([])
for name in ('arial.ttf','msyh.ttc'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/'+name)
app.setFont(QFont('Microsoft YaHei',10));app.setStyleSheet(STYLE)
checks=[]
def check(value,name):
    checks.append({'check':name,'pass':bool(value)});print(name,bool(value),flush=True);assert value,name
for f in (P/'molforge').rglob('*.py'):ast.parse(f.read_text(encoding='utf-8-sig'))
check(True,'syntax')
from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.application.selection import SelectionService
from molforge.application.modeling_commands import SetAtomPropertiesCommand,connected_atoms
from molforge.application.builtin_commands import MoveAtom3DCommand,CleanGeometry3DCommand,AddAtomCommand
from molforge.domain.document import MoleculeDocument
doc=create_instant_caffeine_document();bus=CommandBus(doc);ids=list(doc.topology.atom_ids);aid=ids[0]
initial=doc.get_atom_3d_pos(aid).copy()
check(bus.execute(SetAtomPropertiesCommand([aid],frozen=True)).success,'freeze executes')
check(not bus.execute(MoveAtom3DCommand(aid,initial+[1,0,0])).success,'frozen coordinate move rejected')
np.testing.assert_array_equal(initial,doc.get_atom_3d_pos(aid));check(True,'failed move leaves coordinates exact')
result=bus.execute(CleanGeometry3DCommand(20));check(result.success,'optimization accepts fixed points')
np.testing.assert_array_equal(initial,doc.get_atom_3d_pos(aid));check(True,'MMFF fixed point remains exact')
check(doc.properties['last_optimization']['method'] in ('MMFF94','UFF'),'real force field ran with fixed point')
bus.undo();bus.undo();check(not doc.topology.get_atom(aid).properties.get('frozen'),'undo restores freeze state')
bus.redo();check(doc.topology.get_atom(aid).properties.get('frozen'),'redo restores freeze state')
check(len(connected_atoms(doc,aid))==24,'connected component selection')
cut_doc=MoleculeDocument('branch');cut_bus=CommandBus(cut_doc)
for i in range(4):cut_bus.execute(AddAtomCommand(6,i*1.5,0,0))
from molforge.application.builtin_commands import AddBondCommand
branch_ids=list(cut_doc.topology.atom_ids)
for a,b in zip(branch_ids,branch_ids[1:]):cut_bus.execute(AddBondCommand(a,b))
cut=cut_doc.topology.bond_between(branch_ids[1],branch_ids[2])
check(connected_atoms(cut_doc,branch_ids[0],{cut})==set(branch_ids[:2]),'bond-side fragment selection stops at chosen bond')
from molforge.io.custom_fragments import fragment_from_selection,save_fragment,load_fragment
spec=fragment_from_selection(doc,ids[:3],'测试片段',root=ids[1]);path=save_fragment(spec,R/'evidence'/'fragments');loaded=load_fragment(path)
check(loaded.atoms==spec.atoms and loaded.bonds==spec.bonds,'custom fragment JSON roundtrip')
check(loaded.atoms[0].atomic_num==doc.topology.get_atom(ids[1]).atomic_num,'clicked attachment root preserved')
from molforge.application.fragment_commands import InsertFragmentCommand
target=MoleculeDocument('fragment');tb=CommandBus(target)
check(tb.execute(InsertFragmentCommand(loaded)).success and target.num_atoms==3,'custom fragment insertion')
new_ids=list(target.topology.atom_ids);tb.undo();check(target.num_atoms==0,'fragment one undo removes entire insertion')
tb.redo();check(list(target.topology.atom_ids)==new_ids,'fragment redo stable IDs')
from molforge.io.rdkit_adapter import create_molecule_from_smiles,doc_to_rdkit
benzene=create_molecule_from_smiles('c1ccccc1','benzene')
aromatic=fragment_from_selection(benzene,list(benzene.topology.atom_ids),'benzene')
aromatic=load_fragment(save_fragment(aromatic,R/'evidence/fragments'))
isolated=MoleculeDocument('isolated');ib=CommandBus(isolated);ib.execute(AddAtomCommand(6,0,0,0))
old_id=next(iter(isolated.topology.atom_ids))
check(ib.execute(InsertFragmentCommand(aromatic,attach_to_existing=False)).success,'aromatic custom fragment append')
check(not isolated.topology.neighbors_of(old_id),'blank-context append creates no unwanted attachment bond')
check(sum(isolated.topology.get_atom(a).aromatic for a in isolated.topology.atom_ids)==6,'custom fragment preserves aromatic atom flags')
from rdkit import Chem
check('c1ccccc1' in Chem.MolToSmiles(Chem.RemoveHs(doc_to_rdkit(isolated,sanitize=True,strict=True)[0])),'aromatic custom fragment passes strict chemistry conversion')
check(bus.execute(SetAtomPropertiesCommand(ids[:3],opacity=.35,glow_color=(1.,.1,.4),glow=.7)).success,'effects command executes')
from molforge.io.mforge_storage import save_mforge,load_mforge
save_mforge(doc,R/'evidence/effects.mforge');restored=load_mforge(R/'evidence/effects.mforge')
check(restored.topology.get_atom(aid).properties==doc.topology.get_atom(aid).properties,'freeze opacity glow project roundtrip')
from molforge.ui.editor2d_widget import Editor2DWidget
view2=Editor2DWidget();view2.resize(780,640);view2.set_document(doc);sel=SelectionService();view2.set_selection_service(sel);view2.set_command_bus(bus);view2.show();app.processEvents()
view2._zoom=1.;size1=view2._get_label_font().pointSizeF();view2.grab().save(str(R/'evidence/2d_zoom_100.png'))
view2._zoom=.25;size2=view2._get_label_font().pointSizeF();view2.grab().save(str(R/'evidence/2d_zoom_25.png'))
check(abs(size2/size1-.25)<1e-10,'2D font follows zoom ratio')
captured=[]
def inspect(menu,*args):
    def visit(m):
        for a in m.actions():
            captured.append(a.text())
            if a.menu():visit(a.menu())
    visit(menu)
with patch.object(QMenu,'exec',inspect):view2._show_atom_context_menu(QPointF(200,200),aid)
check('完整118元素周期表…' in captured,'2D context includes full periodic table')
check(any('冻结选中' in t for t in captured) and '自定义片段' in captured,'shared modeling context actions exist')
from molforge.ui.element_picker import ElementPickerDialog
picker=ElementPickerDialog(compact=True);picker.show();app.processEvents()
check(len(picker._buttons)==118 and all(b.width()==36 for b,_ in picker._buttons),'compact complete periodic table')
picker.grab().save(str(R/'evidence/compact_periodic.png'))
from molforge.ui.render3d_widget import Render3DWidget
view=Render3DWidget();view.resize(900,700);view.show();view.set_document(doc);view.set_selection_service(sel);view.set_command_bus(bus);app.processEvents()
view.plotter.renderer.GetRenderWindow().SetSize(900,640);view.reset_camera();view.set_view_options(show_labels=True,show_symbols=False);view._refresh_atom_labels();app.processEvents()
native=view.renderer._native_labels
check(native.strings.GetNumberOfValues()==24,'all atoms numbered by default, including H')
view.renderer.label_scope='heavy';view._refresh_atom_labels()
check(native.strings.GetNumberOfValues()==14,'heavy atom scope remains available')
view.renderer.label_scope='all';view._refresh_atom_labels()
check(view.renderer._atom_colors.GetNumberOfComponents()==4,'renderer uses RGBA atom colors')
check(abs(view.renderer._atom_colors.GetTuple4(0)[3]-89)<1,'selected atom alpha reaches VTK')
check(view.renderer._bond_colors.GetNumberOfComponents()==4,'internal bond transparency uses RGBA')
check(len(view.renderer._glow_layers)==1 and all(layer[3].GetVisibility() for layer in view.renderer._glow_layers),'shared Gaussian colored halo visible')
check(view.renderer._glow_layers[0][2].GetTuple4(0)[0]==255,'chosen glow RGB reaches VTK')
sel.select_atoms([aid]);view._capture_multi_drag_origins();check(aid not in view._multi_drag_start,'frozen atom excluded from drag preview')
from molforge.ui.shells.workflow_inputs import ToolPathConfigDialog
tools=ToolPathConfigDialog();tools.show();app.processEvents();tools.grab().save(str(R/'evidence/tool_paths.png'))
check(all('Ready' not in tools.table.item(i,1).text() for i in range(tools.table.rowCount())),'engine path detection does not claim calculation ready')
from molforge.application.invalidation import CapabilityResolver,CapabilityState
for key in ('DRUG-03','WFN-07','OSC-04','INTER-03'):
    result=CapabilityResolver.execute_analysis(key,doc)
    check(result.status!='Ready' and not result.metrics,key+' never returns mislabeled common estimate')
empty=MoleculeDocument('empty');result=CapabilityResolver.execute_analysis('PROP-01',empty)
check(result.status=='Missing Data' and empty.num_atoms==0,'empty analysis is side-effect free')
from molforge.ui.window import MolForgeWindow
window=MolForgeWindow();window.resize(1400,900);window.show();app.processEvents();window.grab().save(str(R/'evidence/workbench_offscreen.png'))
from threading import get_ident,Event
from PyQt6.QtTest import QTest
main_thread=get_ident();worker_threads=[]
old_coords=window.document.coordinates.current.coords.copy()
def fake_opt(snapshot,**kwargs):
    worker_threads.append(get_ident())
    return {'success':True,'coords':snapshot.coordinates.current.coords+.1,'engine':'test adapter','message':'test output'}
with patch('molforge.io.calculators.run_xtb_optimization',side_effect=fake_opt):
    window._on_run_xtb_optimization()
    for _ in range(200):
        app.processEvents();QTest.qWait(5)
        if not window._xtb_busy:break
check(bool(worker_threads) and worker_threads[0]!=main_thread,'xTB adapter runs off GUI thread')
check(not window._xtb_busy and window.command_bus.can_undo,'xTB result applied through undoable command')
window.command_bus.undo();np.testing.assert_array_equal(old_coords,window.document.coordinates.current.coords)
check(True,'one undo restores pre-xTB geometry')
gate=Event();started=Event()
def slow_opt(snapshot,**kwargs):
    started.set();gate.wait(2)
    return {'success':True,'coords':snapshot.coordinates.current.coords+.2,'engine':'test adapter'}
with patch('molforge.io.calculators.run_xtb_optimization',side_effect=slow_opt),patch('PyQt6.QtWidgets.QMessageBox.information'):
    window._on_run_xtb_optimization();started.wait(1)
    window.command_bus.execute(AddAtomCommand(6,10,0,0));revision=window.document.revision
    gate.set()
    for _ in range(200):
        app.processEvents();QTest.qWait(5)
        if not window._xtb_busy:break
    check(window.document.revision==revision,'stale xTB output cannot overwrite later edits')
from unittest.mock import Mock
with patch('molforge.io.calculators.find_xtb_executable',return_value='mock-xtb.exe'),patch('molforge.io.calculators.subprocess.run',return_value=Mock(returncode=7,stdout='',stderr='engine failed')):
    from molforge.io.calculators import run_xtb_optimization
    failed=run_xtb_optimization(doc,xtb_exe=r'E:\ORCA\software\ORCA6.1.1\xtb-6.7.1pre\xtb.EXE')
check(not failed['success'] and failed['returncode']==7,'xTB engine failure is not converted to fallback success')
invalid=MoleculeDocument('invalid valence')
carbon=invalid.topology.add_atom(6)
for _ in range(6):invalid.topology.add_bond(carbon,invalid.topology.add_atom(1))
invalid.ensure_coordinates().add_frame(np.zeros((7,3),dtype=np.float32),source='invalid test fixture')
check(CapabilityResolver.resolve_status('PROP-06',invalid)[0]==CapabilityState.MISSING_DATA,'invalid valence cannot be presented as ready descriptors')
(R/'modeling_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS',len(checks),flush=True)
os._exit(0)
