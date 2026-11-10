"""Shared 2D/3D selection, fragment and appearance actions."""
from pathlib import Path
from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QColorDialog
from ..application.modeling_commands import SetAtomPropertiesCommand, connected_atoms
from ..application.fragment_commands import InsertFragmentCommand
from ..runtime import data_dir
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6 import sip
from threading import Thread

_pending_loaders = set()


class _Loader(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)


def _background(view, work, done):
    loader = _Loader()
    _pending_loaders.add(loader)
    def finish(value, failed=False):
        try:
            if not sip.isdeleted(view):
                if failed: QMessageBox.warning(view,'片段操作失败',str(value))
                else: done(value)
        finally:
            _pending_loaders.discard(loader)
            loader.deleteLater()
    loader.succeeded.connect(finish)
    loader.failed.connect(lambda message:finish(message,True))
    def run():
        try: loader.succeeded.emit(work())
        except Exception as exc: loader.failed.emit(str(exc))
    Thread(target=run,daemon=True).start()


def _targets(view, seed=None):
    ids = set(view._selection.selected_atoms) if view._selection else set()
    if seed is not None and seed not in ids:
        ids = {seed}
    return ids


def _run(view, command):
    if view._command_bus is None:
        return
    result = view._command_bus.execute(command)
    if not result.success:
        QMessageBox.warning(view,'操作未完成',result.message)


def _save(view, seed):
    from ..io.custom_fragments import fragment_from_selection, save_fragment
    name, ok = QInputDialog.getText(view,'保存选中片段','片段名称（右击原子作为连接入口）：')
    if not ok or not name.strip(): return
    try:
        spec = fragment_from_selection(view._document,_targets(view,seed),name,root=seed)
        path = save_fragment(spec)
    except Exception as exc:
        QMessageBox.warning(view,'保存片段失败',str(exc));return
    QMessageBox.information(view,'片段已保存',f'{spec.name_cn}\n{path}\n插入时检查入口价态；必要时先删除入口端的离去氢。')


def _insert(view, path, seed):
    from ..io.custom_fragments import load_fragment
    original_document=view._document
    def insert(spec):
        if view._document is not original_document:
            QMessageBox.warning(view,'活动分子已改变','片段未插入；请在目标分子上重新操作。');return
        _run(view,InsertFragmentCommand(spec,anchor_atom_id=seed,attach_to_existing=seed is not None))
    _background(view,lambda:load_fragment(path),insert)


def _browse(view, seed):
    path,_ = QFileDialog.getOpenFileName(view,'导入自定义片段',str(data_dir()/'fragments'),'MolForge fragment (*.json)')
    if path: _insert(view,path,seed)


def _from_structure(view):
    from ..io.rdkit_adapter import load_molecule_document
    from ..io.custom_fragments import fragment_from_selection, save_fragment
    path,_ = QFileDialog.getOpenFileName(view,'将分子文件保存为自定义片段','','Structure (*.xyz *.mol *.sdf *.pdb *.mol2 *.gro)')
    if not path:return
    name,ok=QInputDialog.getText(view,'片段名称','名称：',text=Path(path).stem)
    if not ok:return
    def work():
        doc,_=load_molecule_document(path)
        spec=fragment_from_selection(doc,list(doc.topology.atom_ids),name)
        return save_fragment(spec)
    _background(view,work,lambda result:QMessageBox.information(view,'已存入片段库',str(result)))


def _opacity(view, ids):
    value,ok=QInputDialog.getDouble(view,'选中原子/内部键透明度','不透明度（0完全透明，1不透明）：',1.,0.,1.,2)
    if ok:_run(view,SetAtomPropertiesCommand(ids,opacity=value))


def _glow(view, ids):
    color=QColorDialog.getColor(parent=view,title='选择柔光颜色（仅可视化效果）')
    if not color.isValid():return
    strength,ok=QInputDialog.getDouble(view,'柔光强度','强度0–1（不是物理发光模拟）：',.45,0.,1.,2)
    if ok:_run(view,SetAtomPropertiesCommand(ids,glow_color=(color.redF(),color.greenF(),color.blueF()),glow=strength))


def _export_scene(view):
    try:view.export_scene_png()
    except Exception as exc:QMessageBox.warning(view,'图像导出失败',str(exc))


def add_modeling_actions(view, menu, seed=None, bond_id=None):
    if view._document is None:return
    ids=_targets(view,seed)
    if seed is not None:
        menu.addAction('成键 / 配位几何模板…',lambda:_arrange_geometry(view,seed))
    if bond_id is not None:
        torsion=menu.addMenu('绕单键旋转构象')
        bond=view._document.topology.get_bond(bond_id)
        torsion.setEnabled(bond.order==1 and not bond.aromatic)
        for endpoint in (bond.begin,bond.end):
            side=torsion.addMenu(f'旋转 {endpoint.value+1} 号原子一侧')
            for degrees in (-60,60,180):
                side.addAction(f'{degrees:+g}°',lambda checked=False,a=endpoint,d=degrees:_torsion(view,bond_id,a,d))
            side.addAction('自定义角度…',lambda checked=False,a=endpoint:_torsion(view,bond_id,a))
    selection=menu.addMenu('选择与冻结')
    if bond_id is not None and view._selection:
        bond=view._document.topology.get_bond(bond_id)
        for endpoint in (bond.begin,bond.end):
            selection.addAction(f'选中此键 {endpoint.value+1} 号原子一侧片段',
                lambda _=False,a=endpoint:view._selection.select_atoms(connected_atoms(view._document,a,{bond_id}),origin='modeling'))
    if seed is not None and view._selection:
        selection.addAction('只选中此原子',lambda:view._selection.select_atoms([seed],origin='modeling'))
        selection.addAction('选中连通片段',lambda:view._selection.select_atoms(connected_atoms(view._document,seed),origin='modeling'))
    if view._selection:
        selection.addAction('选中全部冻结原子',lambda:view._selection.select_atoms([a for a in view._document.topology.atom_ids if view._document.topology.get_atom(a).properties.get('frozen')],origin='modeling'))
    freeze=selection.addAction(f'冻结选中原子的3D坐标（{len(ids)}）',lambda:_run(view,SetAtomPropertiesCommand(ids,frozen=True)))
    thaw=selection.addAction('解冻选中原子',lambda:_run(view,SetAtomPropertiesCommand(ids,frozen=False)))
    freeze.setEnabled(bool(ids));thaw.setEnabled(bool(ids))
    fragments=menu.addMenu('自定义片段')
    save=fragments.addAction('将选中原子保存为片段…',lambda:_save(view,seed));save.setEnabled(bool(ids))
    fragments.addAction('从分子文件创建片段…',lambda:_from_structure(view))
    fragments.addAction('导入片段JSON并插入…',lambda:_browse(view,seed))
    folder=data_dir()/'fragments'
    if folder.exists():
        from ..io.custom_fragments import load_fragment
        library=fragments.addMenu('插入已保存片段')
        for path in sorted(folder.glob('*.json')):
            try:spec=load_fragment(path)
            except (ValueError,KeyError,TypeError,OSError):continue
            library.addAction(spec.name_cn,lambda _=False,p=path:_insert(view,p,seed))
    appearance=menu.addMenu('颜色、透明度与柔光')
    appearance.setEnabled(bool(ids))
    appearance.addAction('选中原子/内部键不透明度…',lambda:_opacity(view,ids))
    appearance.addAction('选中原子柔光颜色与强度…',lambda:_glow(view,ids))
    appearance.addAction('关闭柔光',lambda:_run(view,SetAtomPropertiesCommand(ids,glow=0.)))
    appearance.addAction('恢复不透明',lambda:_run(view,SetAtomPropertiesCommand(ids,opacity=1.)))
    if hasattr(view,'export_scene_png'):
        menu.addAction('导出纯3D画面PNG（含编号/柔光）…',lambda:_export_scene(view))


def _arrange_geometry(view,seed):
    from .dialogs.element_fragments import ElementFragmentsDialog
    from ..domain.elements import get_element
    from ..application.geometry_commands import ArrangeGeometryCommand
    symbol=get_element(view._document.topology.get_atom(seed).atomic_num).symbol
    dialog=ElementFragmentsDialog(view,symbol,geometry_only=True)
    if dialog.exec() and dialog.selected_geometry:
        _run(view,ArrangeGeometryCommand(seed,dialog.selected_geometry))


def _torsion(view,bond_id,endpoint,degrees=None):
    from ..application.geometry_commands import RotateBondFragmentCommand
    if degrees is None:
        degrees,ok=QInputDialog.getDouble(view,'单键构象旋转','相对转角（度）；冻结原子不移动：',60.,-360.,360.,2)
        if not ok:return
    _run(view,RotateBondFragmentCommand(bond_id,endpoint,degrees))
