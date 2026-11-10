"""
application/builtin_commands.py - 严格保持 AtomId/BondId 与坐标帧一致性的内置命令集
===================================================================================
"""

from __future__ import annotations

import copy
import math
import numpy as np

from ..domain.document import MoleculeDocument
from ..domain.chemistry import estimate_bond_length
from ..domain.ids import AtomId, BondId
from .commands import Command, CommandResult


class AddAtomCommand(Command):
    """
    添加一个原子：
      - 支持显式传入 3D 坐标 (x, y, z)
      - 支持传入 bond_to 自动与指定原子成键并按四面体/三角方向计算合理键长 (元素相关估算键长)
      - 支持 auto_bond_nearest=True（3D 点击空白处时，自动与最近原子按 元素相关估算键长 成键）
      - redo 时严格复用首次分配的 _added_atom_id 与 _added_bond_id，保证 ID 绝不漂移！
    """

    description = "添加原子"

    def __init__(
        self,
        atomic_num: int,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        bond_to: AtomId | None = None,
        bond_order: int = 1,
        pos_2d: tuple[float, float] | None = None,
        auto_bond_nearest: bool = False,
    ):
        self.atomic_num = int(atomic_num)
        self.explicit_pos = (
            (float(x), float(y), float(z))
            if (x is not None and y is not None and z is not None)
            else None
        )
        self.bond_to = bond_to
        self.bond_order = int(bond_order)
        self.pos_2d = pos_2d
        self.auto_bond_nearest = bool(auto_bond_nearest)
        self._added_atom_id: AtomId | None = None
        self._added_bond_id: BondId | None = None
        self._resolved_bond_to: AtomId | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        target_bond_aid = self.bond_to

        # 若开启了 3D 自动连接最近原子，且当前分子非空
        if target_bond_aid is None and self.auto_bond_nearest and doc.topology.num_atoms > 0:
            ref_pt = np.array(self.explicit_pos or (0.0, 0.0, 0.0), dtype=np.float32)
            nearest_aid, dist = doc.find_nearest_atom_3d(ref_pt)
            if nearest_aid is not None:
                target_bond_aid = nearest_aid
                length = estimate_bond_length(doc.topology.get_atom(nearest_aid).atomic_num, self.atomic_num, self.bond_order)
                # 将新原子坐标校准到从 nearest_aid 朝向点击位置的 元素相关估算键长 合理键长处
                anchor_pos = doc.get_atom_3d_pos(nearest_aid)
                if anchor_pos is not None:
                    vec = ref_pt - anchor_pos
                    norm = float(np.linalg.norm(vec))
                    if norm > 0.15:
                        new_coord = (anchor_pos + (vec / norm) * length).astype(np.float32)
                    else:
                        new_coord = doc.suggest_bonded_3d_position(nearest_aid, bond_length=length)
                else:
                    new_coord = ref_pt
            else:
                new_coord = ref_pt
        elif self.explicit_pos is not None:
            new_coord = np.array(self.explicit_pos, dtype=np.float32)
        elif target_bond_aid is not None and doc.has_3d:
            new_coord = doc.suggest_bonded_3d_position(target_bond_aid, bond_length=estimate_bond_length(doc.topology.get_atom(target_bond_aid).atomic_num, self.atomic_num, self.bond_order))
        elif self.pos_2d is not None:
            # 从 2D 世界坐标 (wx, wy) 直接映射为 3D (wx, wy, 0.0)
            z_mean = 0.0
            if doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) > 0:
                z_mean = float(doc.coordinates.current.coords[:, 2].mean())
            new_coord = np.array([float(self.pos_2d[0]), float(self.pos_2d[1]), z_mean], dtype=np.float32)
        elif doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) > 0:
            coords = doc.coordinates.current.coords
            xmax = float(coords[:, 0].max())
            ymid = float(coords[:, 1].mean())
            zmid = float(coords[:, 2].mean())
            new_coord = np.array([xmax + 1.5, ymid, zmid], dtype=np.float32)
        else:
            new_coord = np.zeros(3, dtype=np.float32)

        if target_bond_aid is not None and (self.explicit_pos is None or self.auto_bond_nearest):
            from ..domain.coordination import automatic_bond_error
            error = automatic_bond_error(doc, target_bond_aid, self.atomic_num, self.bond_order)
            if error:
                return CommandResult(False, message=error)
        self._resolved_bond_to = target_bond_aid

        # 复用已有 _added_atom_id（支持 redo 不改变 ID）
        aid = doc.topology.add_atom(self.atomic_num, atom_id=self._added_atom_id)
        self._added_atom_id = aid

        if target_bond_aid is not None and target_bond_aid in doc.topology._atoms:
            self._added_bond_id = doc.topology.add_bond(
                target_bond_aid, aid, order=self.bond_order, bond_id=self._added_bond_id
            )

        doc.coordinates.append_atoms(new_coord.reshape(1, 3))

        if self.pos_2d is not None:
            doc.coords_2d[aid] = (float(self.pos_2d[0]), float(self.pos_2d[1]))
        else:
            doc.coords_2d[aid] = (float(new_coord[0]), float(new_coord[1]))

        return CommandResult(
            success=True,
            changed=True,
            message=f"添加原子 #{aid.value}",
            data={
                "atom_id": aid.value,
                "bond_id": self._added_bond_id.value if self._added_bond_id else None,
            },
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._added_atom_id is None:
            return CommandResult(success=False, message="没有可撤销的原子")
        if self._added_bond_id is not None:
            doc.topology.remove_bond(self._added_bond_id)
        if doc.has_3d:
            doc.coordinates.remove_trailing_atoms(1)
        doc.coords_2d.pop(self._added_atom_id, None)
        doc.topology.remove_atom(self._added_atom_id)
        return CommandResult(
            success=True,
            changed=True,
            message=f"撤销添加原子 #{self._added_atom_id.value}",
        )


class DeleteAtomCommand(Command):
    """删除指定原子（连带删除相连的氢原子，完整备份支持完美撤销）。"""

    description = "删除原子"
    requires_confirmation = True

    def __init__(self, atom_id: AtomId):
        self.atom_id = atom_id
        self._backup_atom = None
        self._backup_index: int = -1
        self._backup_bonds: list = []
        self._backup_coord_3d: np.ndarray | None = None
        self._backup_coord_2d: tuple[float, float] | None = None
        # 连带删除的氢原子
        self._deleted_hydrogens: list = []  # list of (atom, bonds, coord_2d, coord_3d, index)

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if self.atom_id not in doc.topology._atoms:
            return CommandResult(success=False, message=f"原子 {self.atom_id} 不存在")

        self._deleted_hydrogens = []
        # 先找到所有仅与当前原子相连的末端氢原子（若当前删除的就是 H 自身则不递归）
        target_atom = doc.topology.get_atom(self.atom_id)
        hydrogen_ids: list[AtomId] = []
        if target_atom.atomic_num != 1:
            for bid in list(doc.topology._adjacency.get(self.atom_id, [])):
                bond = doc.topology.get_bond(bid)
                other = bond.end if bond.begin == self.atom_id else bond.begin
                if other in doc.topology._atoms and doc.topology.get_atom(other).atomic_num == 1:
                    if len(doc.topology._adjacency.get(other, [])) <= 1:
                        hydrogen_ids.append(other)

        # 按当前拓扑索引从大到小排序并删除氢原子（避免移除坐标帧行时索引偏移）
        hydrogen_ids.sort(key=lambda a: doc.topology.index_of_atom(a), reverse=True)
        for hid in hydrogen_ids:
            h_index = doc.topology.index_of_atom(hid)
            h_atom = copy.deepcopy(doc.topology.get_atom(hid))
            h_bonds = [copy.deepcopy(doc.topology.get_bond(b)) for b in doc.topology._adjacency.get(hid, [])]
            h_coord2d = doc.coords_2d.get(hid)
            h_coord3d = doc.coordinates.remove_atom_at(h_index) if doc.has_3d else None
            doc.coords_2d.pop(hid, None)
            doc.topology.remove_atom(hid)
            self._deleted_hydrogens.append({
                'atom': h_atom,
                'bonds': h_bonds,
                'coord_2d': h_coord2d,
                'coord_3d': h_coord3d,
                'index': h_index,
            })

        # 备份并删除主原子
        self._backup_index = doc.topology.index_of_atom(self.atom_id)
        self._backup_atom = copy.deepcopy(doc.topology.get_atom(self.atom_id))
        self._backup_coord_2d = doc.coords_2d.get(self.atom_id)

        incident_bids = list(doc.topology._adjacency.get(self.atom_id, []))
        self._backup_bonds = [copy.deepcopy(doc.topology.get_bond(bid)) for bid in incident_bids]

        if doc.has_3d:
            self._backup_coord_3d = doc.coordinates.remove_atom_at(self._backup_index)

        doc.coords_2d.pop(self.atom_id, None)
        doc.topology.remove_atom(self.atom_id)
        return CommandResult(
            success=True,
            changed=True,
            message=f"删除原子 #{self.atom_id.value}（连带 {len(hydrogen_ids)} 个氢）",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._backup_atom is None:
            return CommandResult(success=False, message="没有可恢复的原子数据")

        # 先恢复主原子
        doc.topology.restore_atom(copy.deepcopy(self._backup_atom), index=self._backup_index)
        if self._backup_coord_3d is not None:
            doc.coordinates.insert_atom_at(self._backup_index, self._backup_coord_3d)
        if self._backup_coord_2d is not None:
            doc.coords_2d[self.atom_id] = self._backup_coord_2d
        for bond in self._backup_bonds:
            try:
                doc.topology.restore_bond(copy.deepcopy(bond))
            except Exception:
                pass

        # 再恢复被连带删除的氢原子（从后往前恢复）
        for h in reversed(self._deleted_hydrogens):
            doc.topology.restore_atom(copy.deepcopy(h['atom']), index=h['index'])
            if h['coord_3d'] is not None:
                doc.coordinates.insert_atom_at(h['index'], h['coord_3d'])
            if h['coord_2d'] is not None:
                hid = h['atom'].id
                doc.coords_2d[hid] = h['coord_2d']
            for bond in h['bonds']:
                try:
                    doc.topology.restore_bond(copy.deepcopy(bond))
                except Exception:
                    pass

        return CommandResult(
            success=True,
            changed=True,
            message=f"恢复原子 #{self.atom_id.value}（连带 {len(self._deleted_hydrogens)} 个氢）",
            data={"atom_id": self.atom_id.value},
        )


class AddBondCommand(Command):
    """在两个原子之间添加键（若已存在则更新键级，redo 保持 BondId 不变）。"""

    description = "添加键"

    def __init__(self, atom_a: AtomId | int, atom_b: AtomId | int, order: int = 1):
        self.atom_a = AtomId(atom_a) if isinstance(atom_a, int) else atom_a
        self.atom_b = AtomId(atom_b) if isinstance(atom_b, int) else atom_b
        self.order = int(order)
        self._added_bond_id: BondId | None = None
        self._was_existing: bool = False
        self._old_order: int = 1
        self._old_aromatic: bool = False

    def do(self, doc: MoleculeDocument) -> CommandResult:
        existing = doc.topology.bond_between(self.atom_a, self.atom_b)
        if existing is not None:
            self._was_existing = True
            self._added_bond_id = existing
            bond = doc.topology.get_bond(existing)
            self._old_order = bond.order
            self._old_aromatic = bond.aromatic
            bond.order = self.order
            bond.aromatic = (self.order == 4)
            return CommandResult(
                success=True,
                changed=True,
                message=f"更新键 #{existing.value} 键级为 {self.order}",
                data={"bond_id": existing.value},
            )

        self._was_existing = False
        bond_id = doc.topology.add_bond(
            self.atom_a,
            self.atom_b,
            order=self.order,
            aromatic=(self.order == 4),
            bond_id=self._added_bond_id,
        )
        self._added_bond_id = bond_id
        return CommandResult(
            success=True,
            changed=True,
            message=f"添加键 #{bond_id.value}",
            data={"bond_id": bond_id.value},
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._added_bond_id is None:
            return CommandResult(success=False, message="没有可撤销的键")
        if self._was_existing:
            bond = doc.topology.get_bond(self._added_bond_id)
            bond.order = self._old_order
            bond.aromatic = self._old_aromatic
            return CommandResult(success=True, changed=True, message=f"恢复键 #{self._added_bond_id.value}")
        doc.topology.remove_bond(self._added_bond_id)
        return CommandResult(
            success=True,
            changed=True,
            message=f"撤销添加键 #{self._added_bond_id.value}",
        )


class DeleteBondCommand(Command):
    """删除指定的化学键。"""

    description = "删除键"

    def __init__(self, bond_id: BondId):
        self.bond_id = bond_id
        self._backup_bond = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if self.bond_id not in doc.topology._bonds:
            return CommandResult(success=False, message=f"键 {self.bond_id} 不存在")
        self._backup_bond = copy.deepcopy(doc.topology.get_bond(self.bond_id))
        doc.topology.remove_bond(self.bond_id)
        return CommandResult(
            success=True,
            changed=True,
            message=f"删除键 #{self.bond_id.value}",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._backup_bond is None:
            return CommandResult(success=False, message="没有可恢复的键")
        doc.topology.restore_bond(copy.deepcopy(self._backup_bond))
        return CommandResult(
            success=True,
            changed=True,
            message=f"恢复键 #{self.bond_id.value}",
        )


class ChangeElementCommand(Command):
    """修改原子的元素类型。"""

    description = "修改元素"

    def __init__(self, atom_id: AtomId, new_atomic_num: int):
        self.atom_id = atom_id
        self.new_atomic_num = int(new_atomic_num)
        self._old_atomic_num: int | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        atom = doc.topology.get_atom(self.atom_id)
        self._old_atomic_num = atom.atomic_num
        atom.atomic_num = self.new_atomic_num
        return CommandResult(
            success=True,
            changed=True,
            message=f"修改原子 #{self.atom_id.value} 为元素 Z={self.new_atomic_num}",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_atomic_num is None:
            return CommandResult(success=False, message="没有可恢复的数据")
        atom = doc.topology.get_atom(self.atom_id)
        atom.atomic_num = self._old_atomic_num
        return CommandResult(
            success=True,
            changed=True,
            message=f"恢复原子 #{self.atom_id.value} 为元素 Z={self._old_atomic_num}",
        )


class ChangeBondOrderCommand(Command):
    """修改键级。"""

    description = "修改键级"

    def __init__(self, bond_id: BondId, new_order: int):
        self.bond_id = bond_id
        self.new_order = int(new_order)
        self._old_order: int | None = None
        self._old_aromatic: bool = False

    def do(self, doc: MoleculeDocument) -> CommandResult:
        bond = doc.topology.get_bond(self.bond_id)
        self._old_order = bond.order
        self._old_aromatic = bond.aromatic
        bond.order = self.new_order
        bond.aromatic = (self.new_order == 4)
        return CommandResult(
            success=True,
            changed=True,
            message=f"修改键 #{self.bond_id.value} 为 {self.new_order} 级键",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_order is None:
            return CommandResult(success=False, message="没有可恢复的数据")
        bond = doc.topology.get_bond(self.bond_id)
        bond.order = self._old_order
        bond.aromatic = self._old_aromatic
        return CommandResult(
            success=True,
            changed=True,
            message=f"恢复键 #{self.bond_id.value} 为 {self._old_order} 级键",
        )


class MoveAtom3DCommand(Command):
    """移动原子 3D 坐标（同时可选更新 2D 世界坐标）。"""

    description = "移动原子坐标"

    def __init__(
        self,
        atom_id: AtomId,
        new_pos: np.ndarray | tuple[float, float, float],
        old_pos: np.ndarray | tuple[float, float, float] | None = None,
        new_pos_2d: tuple[float, float] | None = None,
    ):
        self.atom_id = atom_id
        self.new_pos = np.asarray(new_pos, dtype=np.float32).copy()
        self._old_pos = np.asarray(old_pos, dtype=np.float32).copy() if old_pos is not None else None
        self.new_pos_2d = new_pos_2d
        self._old_pos_2d: tuple[float, float] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="当前文档无 3D 坐标")
        idx = doc.topology.index_of_atom(self.atom_id)
        if self._old_pos is None:
            self._old_pos = doc.coordinates.current.coords[idx].copy()
        if self._old_pos_2d is None and self.atom_id in doc.coords_2d:
            self._old_pos_2d = doc.coords_2d[self.atom_id]
        doc.coordinates.set_atom_coord(idx, self.new_pos)
        if self.new_pos_2d is not None:
            doc.coords_2d[self.atom_id] = self.new_pos_2d
        else:
            doc.coords_2d[self.atom_id] = (float(self.new_pos[0]), float(self.new_pos[1]))
        return CommandResult(
            success=True,
            changed=True,
            message=f"移动原子 #{self.atom_id.value} -> ({self.new_pos[0]:.2f}, {self.new_pos[1]:.2f}, {self.new_pos[2]:.2f}) Å",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_pos is None or not doc.has_3d:
            return CommandResult(success=False, message="无可恢复的 3D 坐标")
        idx = doc.topology.index_of_atom(self.atom_id)
        doc.coordinates.set_atom_coord(idx, self._old_pos)
        if self._old_pos_2d is not None:
            doc.coords_2d[self.atom_id] = self._old_pos_2d
        return CommandResult(
            success=True,
            changed=True,
            message=f"恢复原子 #{self.atom_id.value} 坐标",
        )


class CleanGeometry3DCommand(Command):
    """对当前分子执行 3D 结构力场弛豫优化（支持一键撤销回优化前构型）。"""

    description = "3D 结构优化清理"

    def __init__(self, max_iters: int = 120):
        self.max_iters = max_iters
        self._old_coords: np.ndarray | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if doc.has_3d and doc.coordinates.current is not None:
            self._old_coords = doc.coordinates.current.coords.copy()
        ok = doc.relax_3d_geometry(max_iters=self.max_iters)
        if not ok:
            return CommandResult(success=False, message="当前分子为空")
        return CommandResult(
            success=True,
            changed=True,
            message="几何优化：" + str(doc.properties.get("last_optimization", {})),
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords is None or not doc.has_3d:
            return CommandResult(success=False, message="无可恢复的旧坐标")
        doc.coordinates.update_current_coords(self._old_coords)
        return CommandResult(
            success=True,
            changed=True,
            message="已恢复优化前的 3D 坐标",
        )


class GenerateConformation3DCommand(Command):
    """
    基于 RDKit ETKDGv3 结合 MMFF94/UFF 力场从 2D 拓扑结构生成高质量 3D 空间立体构象
    （支持纯 NumPy VSEPR 弹簧力场兜底与单次 Ctrl+Z 原位撤销）。
    """

    description = "2D ➜ 3D 构象生成 (ETKDG)"
    affects_geometry = False

    def __init__(self, optimize_iters: int = 150, random_seed: int = 42):
        self.optimize_iters = optimize_iters
        self.random_seed = random_seed
        self._old_coords = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        n = doc.topology.num_atoms
        if n == 0:
            return CommandResult(success=False, message="当前分子为空")

        if doc.has_3d and doc.coordinates.current is not None:
            self._old_coords = doc.coordinates.current.coords.copy()

        embedded = False
        opt_method = "NumPy VSEPR 弹簧力场"
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            from ..io.rdkit_adapter import doc_to_rdkit

            rdmol, atom_map, _ = doc_to_rdkit(doc, sanitize=True, strict=False)
            if rdmol.GetNumAtoms() == n:
                params = AllChem.ETKDGv3() if hasattr(AllChem, "ETKDGv3") else AllChem.ETKDG()
                params.randomSeed = self.random_seed
                params.useRandomCoords = True
                if hasattr(params, 'maxIterations'): params.maxIterations = 50
                res = AllChem.EmbedMolecule(rdmol, params)
                if res != 0 or rdmol.GetNumConformers() == 0:
                    params.enforceChirality = False
                    res = AllChem.EmbedMolecule(rdmol, params)

                if rdmol.GetNumConformers() > 0:
                    if AllChem.MMFFHasAllMoleculeParams(rdmol):
                        AllChem.MMFFOptimizeMolecule(rdmol, maxIters=self.optimize_iters)
                        opt_method = "ETKDGv3 + MMFF94"
                    else:
                        AllChem.UFFOptimizeMolecule(rdmol, maxIters=self.optimize_iters)
                        opt_method = "ETKDGv3 + UFF"

                    conf = rdmol.GetConformer()
                    new_coords = np.zeros((n, 3), dtype=np.float32)
                    for i, aid in enumerate(doc.topology.atom_ids):
                        rd_i = atom_map.get(aid, i)
                        pos = conf.GetAtomPosition(rd_i)
                        new_coords[i] = [pos.x, pos.y, pos.z]
                    new_coords -= new_coords.mean(axis=0)
                    doc.ensure_coordinates()
                    doc.coordinates.update_current_coords(new_coords)
                    doc.properties["last_optimization"] = {"method": opt_method, "converged": True}
                    embedded = True
        except Exception:
            pass

        if not embedded:
            doc.relax_3d_geometry(max_iters=self.optimize_iters)
            opt_method = "NumPy 弹簧力场"

        return CommandResult(
            success=True,
            changed=True,
            message=f"3D 构象生成完成 ({opt_method})",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords is None or not doc.has_3d:
            return CommandResult(success=False, message="无可恢复的旧 3D 坐标")
        doc.coordinates.update_current_coords(self._old_coords)
        return CommandResult(
            success=True,
            changed=True,
            message="已恢复生成前的 3D 构象",
        )


class Project3DTo2DCommand(Command):
    """
    将当前 3D 构象正交投影至当前视平面或生成 ChemDraw 出版级规范二维布局（支持一键撤销）。
    """

    description = "3D ➜ 2D 视角规整投影"
    affects_geometry = False

    def __init__(
        self,
        camera_right = None,
        camera_up = None,
        use_coordgen: bool = False,
    ):
        self.camera_right = np.asarray(camera_right, dtype=np.float64) if camera_right is not None else None
        self.camera_up = np.asarray(camera_up, dtype=np.float64) if camera_up is not None else None
        self.use_coordgen = use_coordgen
        self._old_coords_2d = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        n = doc.topology.num_atoms
        if n == 0:
            return CommandResult(success=False, message="当前分子为空")

        self._old_coords_2d = dict(doc.coords_2d)

        # 模式 1：ChemDraw 规范化学出版重排 (RDKit CoordGen / Compute2DCoords)
        if self.use_coordgen:
            try:
                from rdkit.Chem import AllChem
                from ..io.rdkit_adapter import doc_to_rdkit

                rdmol, atom_map, _ = doc_to_rdkit(doc, sanitize=True, strict=False)
                AllChem.Compute2DCoords(rdmol)
                if rdmol.GetNumConformers() > 0:
                    conf = rdmol.GetConformer()
                    raw = np.array([
                        [conf.GetAtomPosition(i).x, conf.GetAtomPosition(i).y]
                        for i in range(rdmol.GetNumAtoms())
                    ])
                    center = raw.mean(axis=0) if len(raw) > 0 else np.zeros(2)
                    new_2d = {}
                    for aid in doc.topology.atom_ids:
                        rd_i = atom_map.get(aid)
                        if rd_i is not None:
                            new_2d[aid] = (
                                float(raw[rd_i, 0] - center[0]),
                                float(raw[rd_i, 1] - center[1]),
                            )
                    doc.coords_2d = new_2d
                    return CommandResult(
                        success=True,
                        changed=True,
                        message="已生成 ChemDraw 规范出版级 2D 布局",
                    )
            except Exception:
                pass

        # 模式 2：根据当前 3D 观察相机基向量投影或 SVD 主平面正交投影
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="当前分子无 3D 坐标")

        atom_ids, id_to_idx = doc.topology.atom_index_map()
        pts = doc.coordinates.current.coords.astype(np.float64)
        center = pts.mean(axis=0)
        centered = pts - center

        if self.camera_right is not None and self.camera_up is not None:
            rx = self.camera_right.copy()
            uy = self.camera_up.copy()
            r_norm = np.linalg.norm(rx)
            u_norm = np.linalg.norm(uy)
            if r_norm > 1e-6 and u_norm > 1e-6:
                rx /= r_norm
                uy /= u_norm
                px = centered @ rx
                py = centered @ uy
                xy = np.column_stack([px, py])
            else:
                xy = centered[:, :2].copy()
        else:
            # SVD 主平面正交投影
            _, _, vh = np.linalg.svd(centered, full_matrices=False)
            ax_x = vh[0]
            ax_y = vh[1] if len(vh) > 1 else np.array([0.0, 1.0, 0.0])
            px = centered @ ax_x
            py = centered @ ax_y
            xy = np.column_stack([px, py])

        # 键长归一化：将平均/中位数键长缩放到 ~1.50 Å (ChemDraw 标准键长)
        b_lengths = []
        for bid in doc.topology.bond_ids:
            b = doc.topology.get_bond(bid)
            if b.begin in id_to_idx and b.end in id_to_idx:
                i, j = id_to_idx[b.begin], id_to_idx[b.end]
                d = float(np.linalg.norm(xy[i] - xy[j]))
                if d > 0.15:
                    b_lengths.append(d)

        if b_lengths:
            median_d = float(np.median(b_lengths))
            if median_d > 0.05:
                xy *= (1.50 / median_d)

        xy -= xy.mean(axis=0)
        new_2d = {atom_ids[i]: (float(xy[i, 0]), float(xy[i, 1])) for i in range(n)}
        doc.coords_2d = new_2d
        return CommandResult(
            success=True,
            changed=True,
            message="已将当前 3D 构象投影至 2D 画布",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords_2d is None:
            return CommandResult(success=False, message="无可撤销的旧 2D 坐标")
        doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(
            success=True,
            changed=True,
            message="已恢复之前的 2D 布局",
        )


class AddRingCommand(Command):
    """
    添加一个共轭环或饱和环（支持自动与当前选中原子或最近外围原子通过单键相连！）。
    """

    description = "添加环"

    def __init__(
        self,
        size: int = 6,
        aromatic: bool = False,
        hetero_atoms: dict[int, int] | None = None,
        center_2d: tuple[float, float] | None = None,
        center_3d: tuple[float, float, float] | None = None,
        attach_to: AtomId | None = None,
    ):
        self.size = int(size)
        self.aromatic = bool(aromatic)
        self.hetero_atoms = hetero_atoms or {}
        self.center_2d = center_2d
        self.center_3d = center_3d
        self.attach_to = attach_to
        self._atom_ids: list[AtomId] = []
        self._bond_ids: list[BondId] = []
        self._bridge_bond_id: BondId | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        r = 1.42 / (2.0 * math.sin(math.pi / self.size))

        # 计算环中心与连接方向，使新加的环自然接在选中原子（或分子外侧）上
        anchor_id = self.attach_to
        bridge_dir_3d = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        if anchor_id is not None and anchor_id in doc.topology._atoms and doc.has_3d:
            anchor_pos = doc.get_atom_3d_pos(anchor_id)
            bridge_length = estimate_bond_length(doc.topology.get_atom(anchor_id).atomic_num, self.hetero_atoms.get(0, 6))
            sprout_pos = doc.suggest_bonded_3d_position(anchor_id, bond_length=bridge_length)
            if anchor_pos is not None:
                v = sprout_pos - anchor_pos
                vn = float(np.linalg.norm(v))
                if vn > 1e-4:
                    bridge_dir_3d = (v / vn).astype(np.float32)
                c3d = anchor_pos + bridge_dir_3d * (bridge_length + r)
            else:
                c3d = np.zeros(3, dtype=np.float32)
        elif self.center_3d is not None:
            c3d = np.asarray(self.center_3d, dtype=np.float32)
        elif doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) > 0:
            coords = doc.coordinates.current.coords
            xmax = float(coords[:, 0].max())
            ymid = float(coords[:, 1].mean())
            zmid = float(coords[:, 2].mean())
            c3d = np.array([xmax + 2.4 + r, ymid, zmid], dtype=np.float32)
        else:
            c3d = np.zeros(3, dtype=np.float32)

        # 生成正多边形顶点（让第 0 个或第 1 个碳正对 anchor_id 以便成键）
        base_angle = math.atan2(float(-bridge_dir_3d[1]), float(-bridge_dir_3d[0]))
        # 若第 0 号位是杂原子（如噻吩 S、呋喃 O），让第 1 号位（C2 alpha 位）与母核相连！
        connect_ring_idx = 1 if (0 in self.hetero_atoms and self.size >= 5) else 0
        angle_offset = base_angle - (2.0 * math.pi * connect_ring_idx / self.size)

        ring_coords_3d = np.zeros((self.size, 3), dtype=np.float32)
        for i in range(self.size):
            ang = angle_offset + 2.0 * math.pi * i / self.size
            ring_coords_3d[i] = [
                c3d[0] + r * math.cos(ang),
                c3d[1] + r * math.sin(ang),
                c3d[2],
            ]

        reusing_atoms = len(self._atom_ids) == self.size
        new_aids: list[AtomId] = []
        for i in range(self.size):
            z = self.hetero_atoms.get(i, 6)
            preset_aid = self._atom_ids[i] if reusing_atoms else None
            aid = doc.topology.add_atom(z, aromatic=self.aromatic, atom_id=preset_aid)
            new_aids.append(aid)
        self._atom_ids = new_aids

        reusing_bonds = len(self._bond_ids) == self.size
        new_bids: list[BondId] = []
        for i in range(self.size):
            a = self._atom_ids[i]
            b = self._atom_ids[(i + 1) % self.size]
            order = (2 if (i % 2 == 1) else 1) if self.aromatic else 1
            preset_bid = self._bond_ids[i] if reusing_bonds else None
            bid = doc.topology.add_bond(a, b, order=order, aromatic=self.aromatic, bond_id=preset_bid)
            new_bids.append(bid)
        self._bond_ids = new_bids

        # 若指定了连接锚点原子，自动加上环与母核之间的单键
        if anchor_id is not None and anchor_id in doc.topology._atoms:
            target_ring_aid = self._atom_ids[connect_ring_idx]
            self._bridge_bond_id = doc.topology.add_bond(
                anchor_id, target_ring_aid, order=1, bond_id=self._bridge_bond_id
            )

        doc.coordinates.append_atoms(ring_coords_3d)

        # 写入 2D 世界坐标（单位 Å）
        if self.center_2d is not None:
            cx2, cy2 = self.center_2d
        elif anchor_id is not None and anchor_id in doc.coords_2d:
            ax, ay = doc.coords_2d[anchor_id]
            cx2 = ax + float(bridge_dir_3d[0]) * (1.50 + r)
            cy2 = ay + float(bridge_dir_3d[1]) * (1.50 + r)
        else:
            cx2, cy2 = float(c3d[0]), float(c3d[1])

        for i, aid in enumerate(self._atom_ids):
            ang = angle_offset + 2.0 * math.pi * i / self.size
            doc.coords_2d[aid] = (cx2 + r * math.cos(ang), cy2 + r * math.sin(ang))

        return CommandResult(
            success=True,
            changed=True,
            message=f"添加 {self.size} 元环",
            data={"size": self.size, "atom_ids": [a.value for a in self._atom_ids]},
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._bridge_bond_id is not None:
            doc.topology.remove_bond(self._bridge_bond_id)
        for bid in self._bond_ids:
            doc.topology.remove_bond(bid)
        if doc.has_3d:
            doc.coordinates.remove_trailing_atoms(self.size)
        for aid in self._atom_ids:
            doc.coords_2d.pop(aid, None)
            doc.topology.remove_atom(aid)
        return CommandResult(
            success=True,
            changed=True,
            message=f"撤销 {self.size} 元环",
        )



class ChangeAtomStyleCommand(Command):
    affects_geometry = False
    """
    修改单个或多个原子的独立显示半径缩放 (atom.scale)、独立颜色 (atom.color) 或形式电荷 (atom.formal_charge)。
    完整记录修改前状态，100% 支持 Ctrl+Z / Ctrl+Y 撤销重做！
    """

    description = "修改选中原子外观属性"

    def __init__(
        self,
        atom_ids: list[AtomId] | set[AtomId] | AtomId,
        scale: float | None = None,
        color: tuple[float, float, float] | None = None,
        clear_color: bool = False,
        formal_charge: int | None = None,
    ):
        if isinstance(atom_ids, AtomId):
            self.atom_ids = [atom_ids]
        else:
            self.atom_ids = list(atom_ids)
        self.scale = float(scale) if scale is not None else None
        self.color = tuple(float(c) for c in color) if color is not None else None
        self.clear_color = bool(clear_color)
        self.formal_charge = int(formal_charge) if formal_charge is not None else None
        self._old_states: dict[AtomId, tuple[float, tuple | None, int]] = {}

    def do(self, doc: MoleculeDocument) -> CommandResult:
        changed_count = 0
        for aid in self.atom_ids:
            if aid not in doc.topology._atoms:
                continue
            atom = doc.topology.get_atom(aid)
            if aid not in self._old_states:
                self._old_states[aid] = (
                    float(getattr(atom, "scale", 1.0)),
                    getattr(atom, "color", None),
                    int(getattr(atom, "formal_charge", 0)),
                )
            if self.scale is not None:
                atom.scale = max(0.20, min(3.50, self.scale))
            if self.clear_color:
                atom.color = None
            elif self.color is not None:
                atom.color = self.color
            if self.formal_charge is not None:
                atom.formal_charge = self.formal_charge
            changed_count += 1

        if changed_count == 0:
            return CommandResult(success=False, message="未找到目标原子")
        return CommandResult(
            success=True,
            changed=True,
            message=f"已更新 {changed_count} 个原子的独立外观属性",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        for aid, (old_scale, old_color, old_charge) in self._old_states.items():
            if aid in doc.topology._atoms:
                atom = doc.topology.get_atom(aid)
                atom.scale = old_scale
                atom.color = old_color
                atom.formal_charge = old_charge
        return CommandResult(
            success=True,
            changed=True,
            message="已撤销原子外观修改",
        )


class ChangeBondStyleCommand(Command):
    affects_geometry = False
    """
    修改单条或多条化学键的独立粗细缩放 (bond.width_scale) 或独立颜色 (bond.color)。
    完整支持 Ctrl+Z / Ctrl+Y 撤销重做！
    """

    description = "修改选中化学键外观属性"

    def __init__(
        self,
        bond_ids: list[BondId] | set[BondId] | BondId,
        width_scale: float | None = None,
        color: tuple[float, float, float] | None = None,
        clear_color: bool = False,
    ):
        if isinstance(bond_ids, BondId):
            self.bond_ids = [bond_ids]
        else:
            self.bond_ids = list(bond_ids)
        self.width_scale = float(width_scale) if width_scale is not None else None
        self.color = tuple(float(c) for c in color) if color is not None else None
        self.clear_color = bool(clear_color)
        self._old_states: dict[BondId, tuple[float, tuple | None]] = {}

    def do(self, doc: MoleculeDocument) -> CommandResult:
        changed_count = 0
        for bid in self.bond_ids:
            if bid not in doc.topology._bonds:
                continue
            bond = doc.topology.get_bond(bid)
            if bid not in self._old_states:
                self._old_states[bid] = (
                    float(getattr(bond, "width_scale", 1.0)),
                    getattr(bond, "color", None),
                )
            if self.width_scale is not None:
                bond.width_scale = max(0.20, min(3.50, self.width_scale))
            if self.clear_color:
                bond.color = None
            elif self.color is not None:
                bond.color = self.color
            changed_count += 1

        if changed_count == 0:
            return CommandResult(success=False, message="未找到目标化学键")
        return CommandResult(
            success=True,
            changed=True,
            message=f"已更新 {changed_count} 条化学键的独立粗细/颜色",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        for bid, (old_w, old_c) in self._old_states.items():
            if bid in doc.topology._bonds:
                bond = doc.topology.get_bond(bid)
                bond.width_scale = old_w
                bond.color = old_c
        return CommandResult(
            success=True,
            changed=True,
            message="已撤销化学键外观修改",
        )


class TransformCoordinates3DCommand(Command):
    """
    批量变换 3D 坐标（用于镜像反转 Mirror Invert、主轴对齐 Reorient、键角/二面角精确修改等），
    100% 支持 Ctrl+Z / Ctrl+Y 撤销重做！
    """

    def __init__(self, new_coords: np.ndarray, description: str = "三维几何变换"):
        self.new_coords = np.asarray(new_coords, dtype=np.float32).copy()
        self.description = description
        self._old_coords: np.ndarray | None = None
        self._old_coords_2d: dict[AtomId, tuple[float, float]] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="当前分子无 3D 坐标")
        if self._old_coords is None:
            self._old_coords = doc.coordinates.current.coords.copy()
            self._old_coords_2d = dict(doc.coords_2d)
        if self.new_coords.shape != doc.coordinates.current.coords.shape:
            return CommandResult(success=False, message="坐标维度不匹配")
        doc.coordinates.update_current_coords(self.new_coords.copy())
        doc.sync_2d_coords_from_3d()
        return CommandResult(success=True, changed=True, message=f"已执行：{self.description}")

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords is None or not doc.has_3d:
            return CommandResult(success=False, message="无可恢复的 3D 坐标")
        doc.coordinates.update_current_coords(self._old_coords.copy())
        if self._old_coords_2d is not None:
            doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(success=True, changed=True, message=f"已撤销：{self.description}")


# ===========================================================================
# v6 新增核心命令：
# 1. MoveAtomsBatch3DCommand（框选/套索多原子同步平移，单次 Ctrl+Z 全部恢复）
# 2. AppendMoleculeCommand（Ctrl+V 智能追加粘贴分子到当前文档，带自动防重叠偏移与 Ctrl+Z 撤销）
# 3. ModifyBondLength3DCommand（精确修改键长 Å，带动端基基团位移，支持 Ctrl+Z 撤销）
# 4. SetAtomStyleCommand / SetBondStyleCommand / SetAtomChargeCommand（兼容 Win10 严格校验单测）
# ===========================================================================
import math as _math


def _validate_scale_value(val: float | None) -> float | None:
    if val is None:
        return None
    f = float(val)
    if not _math.isfinite(f) or f < 0.15 or f > 6.0:
        raise ValueError(f"Invalid scale {val}: must be finite in [0.15, 6.0]")
    return f


def _validate_rgb_tuple(color: tuple | list | None) -> tuple[float, float, float] | None:
    if color is None:
        return None
    if not isinstance(color, (tuple, list)) or len(color) != 3:
        raise ValueError("RGB color must be a 3-tuple of floats in [0.0, 1.0]")
    rgb = tuple(float(c) for c in color)
    if not all(_math.isfinite(c) and 0.0 <= c <= 1.0 for c in rgb):
        raise ValueError(f"RGB channels out of range [0.0, 1.0]: {rgb}")
    return rgb


class SetAtomStyleCommand(ChangeAtomStyleCommand):
    """严格参数校验版单原子/多原子外观修改命令（100% 兼容 test_v4_true_style_and_storage）。"""

    affects_geometry = False

    def __init__(
        self,
        atom_ids: list[AtomId] | set[AtomId] | AtomId,
        scale: float | None = None,
        color: tuple[float, float, float] | None = None,
        formal_charge: int | None = None,
        clear_color: bool = False,
    ):
        v_scale = _validate_scale_value(scale)
        v_color = _validate_rgb_tuple(color)
        super().__init__(
            atom_ids=atom_ids,
            scale=v_scale,
            color=v_color,
            formal_charge=formal_charge,
            clear_color=clear_color,
        )


class SetBondStyleCommand(ChangeBondStyleCommand):
    """严格参数校验版单键/多键外观修改命令（100% 兼容 test_v4_true_style_and_storage）。"""

    affects_geometry = False

    def __init__(
        self,
        bond_ids: list[BondId] | set[BondId] | BondId,
        width_scale: float | None = None,
        color: tuple[float, float, float] | None = None,
        clear_color: bool = False,
    ):
        v_scale = _validate_scale_value(width_scale)
        v_color = _validate_rgb_tuple(color)
        super().__init__(
            bond_ids=bond_ids,
            width_scale=v_scale,
            color=v_color,
            clear_color=clear_color,
        )


class SetAtomChargeCommand(Command):
    """修改原子形式电荷命令（走 CommandBus 支持 Undo/Redo，不破坏 2D 坐标）。"""

    affects_geometry = False
    description = "修改原子形式电荷"

    def __init__(self, atom_id: AtomId, formal_charge: int):
        if not isinstance(formal_charge, (int, np.integer)) or abs(int(formal_charge)) > 8:
            raise ValueError(f"Invalid formal charge: {formal_charge}")
        self.atom_id = atom_id
        self.formal_charge = int(formal_charge)
        self._old_charge: int | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if self.atom_id not in doc.topology._atoms:
            return CommandResult(success=False, message="未找到目标原子")
        atom = doc.topology.get_atom(self.atom_id)
        if self._old_charge is None:
            self._old_charge = int(getattr(atom, "formal_charge", 0))
        atom.formal_charge = self.formal_charge
        return CommandResult(
            success=True,
            changed=True,
            message=f"已将原子 #{self.atom_id.value} 形式电荷设为 {self.formal_charge:+d}",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self.atom_id in doc.topology._atoms and self._old_charge is not None:
            doc.topology.get_atom(self.atom_id).formal_charge = self._old_charge
        return CommandResult(
            success=True,
            changed=True,
            message=f"已撤销原子 #{self.atom_id.value} 形式电荷修改",
        )


class MoveAtomsBatch3DCommand(Command):
    """
    批量移动多个选中原子的 3D 坐标（框选/套索后一起拖拽平移）。
    一次 Ctrl+Z 即可把所有被拖动的原子同时恢复到拖动前的位置！
    """

    description = "批量平移选中原子"

    def __init__(
        self,
        atom_moves: dict[AtomId, tuple[np.ndarray, np.ndarray]],
        description: str = "批量平移选中原子",
    ):
        # atom_moves: {atom_id: (old_pos_3d, new_pos_3d)}
        self.atom_moves = {
            aid: (
                np.asarray(old_p, dtype=np.float32).copy(),
                np.asarray(new_p, dtype=np.float32).copy(),
            )
            for aid, (old_p, new_p) in atom_moves.items()
        }
        self.description = description
        self._old_coords_2d: dict[AtomId, tuple[float, float]] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None or not self.atom_moves:
            return CommandResult(success=False, message="无有效 3D 坐标可平移")
        if self._old_coords_2d is None:
            self._old_coords_2d = dict(doc.coords_2d)
        _, id_to_idx = doc.topology.atom_index_map()
        coords = doc.coordinates.current.coords.copy()
        moved = 0
        for aid, (_, new_p) in self.atom_moves.items():
            if aid in id_to_idx and id_to_idx[aid] < len(coords):
                coords[id_to_idx[aid]] = new_p
                moved += 1
        if moved == 0:
            return CommandResult(success=False, message="未命中可移动原子")
        doc.coordinates.update_current_coords(coords)
        return CommandResult(
            success=True,
            changed=True,
            message=f"已同步平移 {moved} 个选中原子",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None or not self.atom_moves:
            return CommandResult(success=False, message="无有效 3D 坐标可恢复")
        _, id_to_idx = doc.topology.atom_index_map()
        coords = doc.coordinates.current.coords.copy()
        for aid, (old_p, _) in self.atom_moves.items():
            if aid in id_to_idx and id_to_idx[aid] < len(coords):
                coords[id_to_idx[aid]] = old_p
        doc.coordinates.update_current_coords(coords)
        if self._old_coords_2d is not None:
            doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(
            success=True,
            changed=True,
            message=f"已撤销 {len(self.atom_moves)} 个原子的批量平移",
        )


class AppendMoleculeCommand(Command):
    """
    将另一个 MoleculeDocument（来自 Ctrl+V 粘贴的 SMILES / XYZ / 片段）追加合并到当前文档中，
    自动计算非重叠空间偏移，且支持 Ctrl+Z 一键撤销整个粘贴操作！
    """

    description = "粘贴追加分子结构"

    def __init__(self, source_doc: MoleculeDocument, offset_3d: np.ndarray | None = None):
        self.source_doc = source_doc
        self.offset_3d = np.asarray(offset_3d, dtype=np.float32) if offset_3d is not None else None
        self._added_atom_ids: list[AtomId] = []
        self._added_bond_ids: list[BondId] = []
        self._old_coords_3d: np.ndarray | None = None
        self._old_coords_2d: dict[AtomId, tuple[float, float]] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if self.source_doc is None or self.source_doc.num_atoms == 0:
            return CommandResult(success=False, message="待粘贴分子为空")

        self._old_coords_2d = dict(doc.coords_2d)
        old_n = doc.num_atoms
        if doc.has_3d and doc.coordinates.current is not None and old_n > 0:
            self._old_coords_3d = doc.coordinates.current.coords.copy()
        else:
            self._old_coords_3d = np.zeros((0, 3), dtype=np.float32)

        # 计算 3D 自动防重叠偏移量（置于现有分子右侧 +3.8 Å）
        src_n = self.source_doc.num_atoms
        if self.source_doc.has_3d and self.source_doc.coordinates.current is not None:
            src_coords = self.source_doc.coordinates.current.coords.copy()
        else:
            self.source_doc.relax_3d_geometry(max_iters=60)
            src_coords = (
                self.source_doc.coordinates.current.coords.copy()
                if self.source_doc.coordinates.current is not None
                else np.zeros((src_n, 3), dtype=np.float32)
            )
        src_coords = src_coords - src_coords.mean(axis=0)

        if self.offset_3d is not None:
            shift_3d = self.offset_3d
        elif len(self._old_coords_3d) > 0:
            max_x = float(self._old_coords_3d[:, 0].max())
            min_src_x = float(src_coords[:, 0].min()) if len(src_coords) > 0 else 0.0
            shift_3d = np.array([max_x - min_src_x + 3.5, 0.0, 0.0], dtype=np.float32)
        else:
            shift_3d = np.zeros(3, dtype=np.float32)

        src_coords_shifted = src_coords + shift_3d

        # 添加原子（若 Redo 则复用上次分配的 AtomId）
        src_atom_ids = list(self.source_doc.topology.atom_ids)
        src_to_new_aid: dict[AtomId, AtomId] = {}
        reusing_ids = len(self._added_atom_ids) == len(src_atom_ids)
        new_aids: list[AtomId] = []

        for idx, s_aid in enumerate(src_atom_ids):
            s_atom = self.source_doc.topology.get_atom(s_aid)
            forced_id = self._added_atom_ids[idx] if reusing_ids else None
            new_aid = doc.topology.add_atom(
                atomic_num=s_atom.atomic_num,
                formal_charge=s_atom.formal_charge,
                aromatic=s_atom.aromatic,
                atom_id=forced_id,
            )
            dst_atom = doc.topology.get_atom(new_aid)
            dst_atom.scale = float(getattr(s_atom, "scale", 1.0))
            dst_atom.color = getattr(s_atom, "color", None)
            src_to_new_aid[s_aid] = new_aid
            new_aids.append(new_aid)
        self._added_atom_ids = new_aids

        # 添加化学键
        src_bond_ids = list(self.source_doc.topology.bond_ids)
        reusing_bids = len(self._added_bond_ids) == len(src_bond_ids)
        new_bids: list[BondId] = []
        for idx, s_bid in enumerate(src_bond_ids):
            s_bond = self.source_doc.topology.get_bond(s_bid)
            if s_bond.begin in src_to_new_aid and s_bond.end in src_to_new_aid:
                forced_bid = self._added_bond_ids[idx] if reusing_bids else None
                new_bid = doc.topology.add_bond(
                    src_to_new_aid[s_bond.begin],
                    src_to_new_aid[s_bond.end],
                    order=s_bond.order,
                    aromatic=s_bond.aromatic,
                    bond_id=forced_bid,
                )
                dst_bond = doc.topology.get_bond(new_bid)
                dst_bond.width_scale = float(getattr(s_bond, "width_scale", 1.0))
                dst_bond.color = getattr(s_bond, "color", None)
                new_bids.append(new_bid)
        self._added_bond_ids = new_bids

        # 合并 3D 坐标
        combined_3d = (
            np.vstack([self._old_coords_3d, src_coords_shifted]).astype(np.float32)
            if len(self._old_coords_3d) > 0
            else src_coords_shifted.astype(np.float32)
        )
        store = doc.ensure_coordinates()
        if store.num_frames == 0:
            store.add_frame(combined_3d, source="paste_append")
        else:
            store.update_current_coords(combined_3d)

        doc.sync_2d_coords_from_3d()
        return CommandResult(
            success=True,
            changed=True,
            message=f"已追加粘贴 {len(new_aids)} 个原子、{len(new_bids)} 条化学键",
            data={"added_atom_ids": list(new_aids)},
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        for bid in reversed(self._added_bond_ids):
            if bid in doc.topology._bonds:
                doc.topology.remove_bond(bid)
        for aid in reversed(self._added_atom_ids):
            if aid in doc.topology._atoms:
                doc.topology.remove_atom(aid)
        if self._old_coords_3d is not None:
            if len(self._old_coords_3d) == 0:
                doc._coordinates = None
            elif doc.has_3d and doc.coordinates.current is not None:
                doc.coordinates.update_current_coords(self._old_coords_3d.copy())
        if self._old_coords_2d is not None:
            doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(
            success=True,
            changed=True,
            message=f"已撤销粘贴追加的 {len(self._added_atom_ids)} 个原子",
        )


class ModifyBondLength3DCommand(Command):
    """
    精确修改选中化学键的 3D 键长 (Å)，自动带动远端连接子树平移（若成环则仅移动端点），
    100% 支持 Ctrl+Z / Ctrl+Y 撤销重做！
    """

    description = "精确修改化学键长"

    def __init__(self, bond_id: BondId, target_length: float):
        self.bond_id = bond_id
        self.target_length = max(0.40, min(5.00, float(target_length)))
        self._old_coords: np.ndarray | None = None
        self._old_coords_2d: dict[AtomId, tuple[float, float]] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if self.bond_id not in doc.topology._bonds or not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="无法修改键长：未找到化学键或缺少 3D 坐标")
        if self._old_coords is None:
            self._old_coords = doc.coordinates.current.coords.copy()
            self._old_coords_2d = dict(doc.coords_2d)

        bond = doc.topology.get_bond(self.bond_id)
        _, id2idx = doc.topology.atom_index_map()
        a1, a2 = bond.begin, bond.end
        if a1 not in id2idx or a2 not in id2idx:
            return CommandResult(success=False, message="化学键端点索引无效")

        coords = doc.coordinates.current.coords.copy()
        p1 = coords[id2idx[a1]].astype(np.float64)
        p2 = coords[id2idx[a2]].astype(np.float64)
        vec = p2 - p1
        cur_len = float(np.linalg.norm(vec))
        if cur_len < 1e-6:
            unit_v = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            unit_v = vec / cur_len

        delta = unit_v * (self.target_length - cur_len)

        # BFS 查找 a2 侧子树（不经过 self.bond_id）；若包含 a1（说明在环内）则只移动 a2
        visited = {a2}
        queue = [a2]
        in_ring = False
        while queue:
            curr = queue.pop(0)
            for bid in doc.topology._adjacency.get(curr, []):
                if bid == self.bond_id or bid not in doc.topology._bonds:
                    continue
                b_obj = doc.topology.get_bond(bid)
                nbr = b_obj.end if b_obj.begin == curr else b_obj.begin
                if nbr == a1:
                    in_ring = True
                    break
                if nbr not in visited:
                    visited.add(nbr)
                    queue.append(nbr)
            if in_ring:
                break

        move_atoms = {a2} if in_ring else visited
        for aid in move_atoms:
            if aid in id2idx:
                coords[id2idx[aid]] = (coords[id2idx[aid]] + delta).astype(np.float32)

        doc.coordinates.update_current_coords(coords)
        doc.sync_2d_coords_from_3d()
        return CommandResult(
            success=True,
            changed=True,
            message=f"已将键 #{self.bond_id.value} 键长从 {cur_len:.3f} Å 调整为 {self.target_length:.3f} Å",
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords is None or not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="无历史坐标可恢复")
        doc.coordinates.update_current_coords(self._old_coords.copy())
        if self._old_coords_2d is not None:
            doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(
            success=True,
            changed=True,
            message=f"已撤销键 #{self.bond_id.value} 的键长修改",
        )


from .internal_coordinates import ModifyAngle3DCommand, ModifyDihedral3DCommand
