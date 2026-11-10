"""Validated JSON fragment library on the application data drive. No executable content."""
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
import json
import numpy as np
from typing import Iterable
from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId
from ..application.fragment_catalog import FragmentSpec, FragmentAtomTemplate, FragmentBondTemplate
from ..domain.elements import get_element
from ..runtime import data_dir


def fragment_from_selection(document: MoleculeDocument, atom_ids: Iterable[AtomId], name: str, root: AtomId | None = None) -> FragmentSpec:
    chosen = set(atom_ids)
    ids = [aid for aid in document.topology.atom_ids if aid in chosen]
    if not ids or len(ids) > 2000:
        raise ValueError('选择1–2000个原子保存为片段')
    root = root if root in chosen else ids[0]
    ids = [root] + [aid for aid in ids if aid != root]
    positions = [document.get_atom_3d_pos(aid) for aid in ids]
    if any(pos is None for pos in positions):
        raise ValueError('自定义3D片段需要完整三维坐标')
    xyz = np.asarray(positions, dtype=float)
    if not np.isfinite(xyz).all():
        raise ValueError('片段坐标含非有限数')
    xyz -= xyz[0]
    mapping = {aid: i for i, aid in enumerate(ids)}
    atoms = tuple(FragmentAtomTemplate(document.topology.get_atom(aid).atomic_num,
        get_element(document.topology.get_atom(aid).atomic_num).symbol, tuple(xyz[i]),
        document.topology.get_atom(aid).formal_charge, document.topology.get_atom(aid).aromatic) for i, aid in enumerate(ids))
    bonds = tuple(FragmentBondTemplate(mapping[b.begin],mapping[b.end],4 if b.aromatic else b.order)
        for b in document.topology._bonds.values() if b.begin in mapping and b.end in mapping)
    return FragmentSpec('custom-'+uuid4().hex, str(name).strip()[:100] or '自定义片段',
        str(name), '', 'Custom', '', 1, atoms, bonds,
        '选中子结构；入口为第一个原子。插入时需检查连接位点价态/离去氢，不自动补造氢。')


def save_fragment(spec: FragmentSpec, folder: str | Path | None = None) -> Path:
    folder = Path(folder) if folder is not None else data_dir()/'fragments'
    folder = folder.resolve()
    if folder.drive.upper() not in ('D:', 'E:'):
        raise ValueError('片段库必须位于D/E盘')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(uuid4().hex+'.json')
    path.write_text(json.dumps({'format':'molforge-fragment','version':1,'fragment':asdict(spec)},ensure_ascii=False,indent=2),encoding='utf-8')
    return path


def load_fragment(path: str | Path) -> FragmentSpec:
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError('片段文件过大')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('format') != 'molforge-fragment' or data.get('version') != 1:
        raise ValueError('不支持的片段格式')
    value = data['fragment']
    if not 1 <= len(value['atoms']) <= 2000:
        raise ValueError('片段原子数量非法')
    atoms = []
    for atom in value['atoms']:
        z = int(atom['atomic_num']); xyz = np.asarray(atom['local_xyz'],dtype=float)
        if get_element(z) is None or xyz.shape != (3,) or not np.isfinite(xyz).all():
            raise ValueError('元素/坐标非法')
        atoms.append(FragmentAtomTemplate(z,get_element(z).symbol,tuple(xyz),int(atom.get('formal_charge',0)),bool(atom.get('aromatic',False))))
    origin = np.array(atoms[0].local_xyz)
    atoms = tuple(FragmentAtomTemplate(a.atomic_num,a.symbol,tuple(np.array(a.local_xyz)-origin),a.formal_charge,a.aromatic) for a in atoms)
    bonds=[]; pairs=set()
    for b in value['bonds']:
        i,j,o=int(b['begin_idx']),int(b['end_idx']),int(b['order'])
        pair=tuple(sorted((i,j)))
        if not (0<=i<len(atoms) and 0<=j<len(atoms)) or i==j or pair in pairs or o not in (1,2,3,4):
            raise ValueError('片段键非法')
        pairs.add(pair);bonds.append(FragmentBondTemplate(i,j,o))
    order=int(value.get('attachment_bond_order',1))
    if order not in (1,2,3):raise ValueError('连接键级非法')
    return FragmentSpec(str(value['id']),str(value['name_cn']),str(value.get('name_en','')),
        str(value.get('formula','')),'Custom',str(value.get('smiles','')),order,atoms,tuple(bonds),str(value.get('description','')),value.get('geometry_key'))
