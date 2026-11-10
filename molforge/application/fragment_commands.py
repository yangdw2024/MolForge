"""
application/fragment_commands.py - 官能团片段原子级事务接枝命令 (InsertFragmentCommand)
======================================================================================
严格实现 S04 / P0 要求：
  - 将“离去氢替换（若选中末端 H）+ 批量新增片段原子 + 批量新增片段内化学键 + 空间生长方向旋转对齐 + 2D/3D 坐标同步”
    封装为单条 CommandBus 事务命令；
  - 任一步校验失败立即整体回滚，绝不留下半成品分子；
  - 一次 Ctrl+Z (undo) 100% 恢复接枝前的原子集、键集、3D 坐标帧与 2D 坐标！
"""

from __future__ import annotations

import math
import numpy as np

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId
from ..domain.topology import Atom, Bond
from .commands import Command, CommandResult
from .fragment_catalog import FragmentCatalog, FragmentSpec


def _align_fragment_coords(
    local_coords: np.ndarray,
    anchor_pos: np.ndarray,
    grow_dir: np.ndarray,
    bond_length: float = 1.47,
) -> np.ndarray:
    """
    将入口位于原点 (0,0,0)、主生长方向沿 +X (1,0,0) 的片段局部坐标旋转平移到：
    入口原子位于 anchor_pos + grow_dir * bond_length，且 +X 轴对齐 grow_dir。
    """
    norm = float(np.linalg.norm(grow_dir))
    u = (grow_dir.astype(np.float64) / norm) if norm > 1e-6 else np.array([1.0, 0.0, 0.0], dtype=np.float64)
    ex = np.array([1.0, 0.0, 0.0], dtype=np.float64)

    # 构造从 ex 到 u 的正交旋转矩阵 R
    dot_val = float(np.clip(np.dot(ex, u), -1.0, 1.0))
    if dot_val > 0.999999:
        R = np.eye(3, dtype=np.float64)
    elif dot_val < -0.999999:
        R = np.diag([-1.0, -1.0, 1.0])
    else:
        v = np.cross(ex, u)
        s = float(np.linalg.norm(v))
        vx = np.array([
            [0.0, -v[2], v[1]],
            [v[2], 0.0, -v[0]],
            [-v[1], v[0], 0.0],
        ], dtype=np.float64)
        R = np.eye(3, dtype=np.float64) + vx + (vx @ vx) * ((1.0 - dot_val) / (s * s))

    root_pos = anchor_pos.astype(np.float64) + u * float(bond_length)
    transformed = (local_coords.astype(np.float64) @ R.T) + root_pos[None, :]
    return transformed.astype(np.float32)


class InsertFragmentCommand(Command):
    """原子级官能团片段插入命令（一次接枝、一次撤销）。"""

    description = "插入官能团片段"

    def __init__(
        self,
        fragment: FragmentSpec | str,
        anchor_atom_id: AtomId | None = None,
        attach_to_existing: bool = True,
    ):
        if isinstance(fragment, str):
            spec = FragmentCatalog.get(fragment)
            if spec is None:
                raise ValueError(f"Unknown fragment id: '{fragment}'")
            self.spec = spec
        else:
            self.spec = fragment
        self.anchor_atom_id = anchor_atom_id
        self.attach_to_existing = bool(attach_to_existing)

        # 事务快照（支持完备 undo 与确定性 redo）
        self._snapshot_atoms: dict[AtomId, Atom] | None = None
        self._snapshot_bonds: dict[BondId, Bond] | None = None
        self._snapshot_adj: dict[AtomId, list[BondId]] | None = None
        self._snapshot_coords_3d: np.ndarray | None = None
        self._snapshot_coords_2d: dict[AtomId, tuple[float, float]] | None = None
        self._added_atom_ids: list[AtomId] = []
        self._added_bond_ids: list[BondId] = []

    def do(self, doc: MoleculeDocument) -> CommandResult:
        # 1. 保存完整拓扑与坐标事务快照
        self._snapshot_atoms = {aid: Atom(**vars(a)) for aid, a in doc.topology._atoms.items()}
        self._snapshot_bonds = {bid: Bond(**vars(b)) for bid, b in doc.topology._bonds.items()}
        self._snapshot_adj = {aid: list(bids) for aid, bids in doc.topology._adjacency.items()}
        self._snapshot_coords_3d = (
            doc.coordinates.current.coords.copy()
            if (doc.has_3d and doc.coordinates.current is not None)
            else None
        )
        self._snapshot_coords_2d = dict(doc.coords_2d)

        try:
            anchor_aid = self.anchor_atom_id
            if anchor_aid is not None and anchor_aid not in doc.topology._atoms:
                return CommandResult(success=False, message=f"锚点原子 #{anchor_aid.value} 不存在")

            # 若未显式指定锚点且分子非空，默认取最后一个重原子（或最后一个原子）
            if anchor_aid is None and self.attach_to_existing and doc.topology.num_atoms > 0:
                heavy = [aid for aid in doc.topology.atom_ids if doc.topology.get_atom(aid).atomic_num > 1]
                anchor_aid = heavy[-1] if heavy else list(doc.topology.atom_ids)[-1]

            # 若用户选中的锚点是一个单价末端氢原子 (H)，则自动采用“离去氢替换”策略：
            # 找到与该 H 相连的母原子作为真正锚点，生长方向严格沿着母原子 -> 该 H 的方向，并移除该离去 H！
            anchor_pos = np.zeros(3, dtype=np.float32)
            grow_dir = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            attach_bond_len = 1.47

            if anchor_aid is not None:
                anchor_atom = doc.topology.get_atom(anchor_aid)
                adj_bids = list(doc.topology._adjacency.get(anchor_aid, []))
                if anchor_atom.atomic_num == 1 and len(adj_bids) == 1 and doc.has_3d:
                    h_pos = doc.get_atom_3d_pos(anchor_aid)
                    b_obj = doc.topology.get_bond(adj_bids[0])
                    parent_aid = b_obj.begin if b_obj.end == anchor_aid else b_obj.end
                    parent_pos = doc.get_atom_3d_pos(parent_aid)
                    if h_pos is not None and parent_pos is not None:
                        vec = h_pos - parent_pos
                        norm = float(np.linalg.norm(vec))
                        if norm > 1e-4:
                            grow_dir = (vec / norm).astype(np.float32)
                        anchor_pos = parent_pos
                        # 在事务内移除被替换的离去氢原子及其键
                        _, id2idx_pre = doc.topology.atom_index_map()
                        h_idx = id2idx_pre[anchor_aid]
                        doc.topology.remove_bond(adj_bids[0])
                        doc.topology.remove_atom(anchor_aid)
                        doc.coordinates.remove_atom_at(h_idx)
                        doc.coords_2d.pop(anchor_aid, None)
                        anchor_aid = parent_aid
                else:
                    pos = doc.get_atom_3d_pos(anchor_aid)
                    if pos is not None:
                        anchor_pos = pos
                        sug = doc.suggest_bonded_3d_position(anchor_aid, bond_length=1.47)
                        vec = sug - pos
                        norm = float(np.linalg.norm(vec))
                        if norm > 1e-4:
                            grow_dir = (vec / norm).astype(np.float32)

            if anchor_aid is not None:
                from ..domain.chemistry import estimate_bond_length
                attach_bond_len = estimate_bond_length(doc.topology.get_atom(anchor_aid).atomic_num, self.spec.atoms[0].atomic_num, self.spec.attachment_bond_order)
            if anchor_aid is not None:
                from ..domain.coordination import automatic_bond_error, valence_limit
                error = automatic_bond_error(doc, anchor_aid, self.spec.atoms[0].atomic_num, self.spec.attachment_bond_order)
                root = self.spec.atoms[0]
                limit = valence_limit(root.atomic_num, root.formal_charge)
                root_order = sum(1.5 if b.order == 4 else b.order for b in self.spec.bonds if 0 in (b.begin_idx, b.end_idx))
                if error or (limit is not None and root_order + self.spec.attachment_bond_order > limit):
                    self._restore_snapshot(doc)
                    return CommandResult(False, message=error or '片段入口价态已满；请先移除入口离去氢，或独立插入')
            local_xyz = np.array([t.local_xyz for t in self.spec.atoms], dtype=np.float32)
            if anchor_aid is None:
                world_xyz = local_xyz.copy()
                if doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords):
                    original = doc.coordinates.current.coords
                    world_xyz += np.array([original[:,0].max()+3.-local_xyz[:,0].min(), original[:,1].mean(), original[:,2].mean()],dtype=np.float32)
            else:
                world_xyz = _align_fragment_coords(local_xyz, anchor_pos, grow_dir, bond_length=attach_bond_len)

            # 添加片段原子（若为 redo，则复用已有 ID）
            new_atom_ids: list[AtomId] = []
            for idx, tmpl in enumerate(self.spec.atoms):
                reuse_aid = self._added_atom_ids[idx] if idx < len(self._added_atom_ids) else None
                aid = doc.topology.add_atom(
                    tmpl.atomic_num,
                    formal_charge=tmpl.formal_charge,
                    aromatic=tmpl.aromatic,
                    atom_id=reuse_aid,
                )
                new_atom_ids.append(aid)
            self._added_atom_ids = list(new_atom_ids)
            if self.spec.geometry_key:
                doc.topology.get_atom(new_atom_ids[0]).properties['geometry_template'] = self.spec.geometry_key

            # 添加锚点连接键与片段内部化学键
            new_bond_ids: list[BondId] = []
            b_cursor = 0
            if anchor_aid is not None and anchor_aid in doc.topology._atoms:
                reuse_bid = self._added_bond_ids[b_cursor] if b_cursor < len(self._added_bond_ids) else None
                bid = doc.topology.add_bond(
                    anchor_aid,
                    new_atom_ids[0],
                    order=self.spec.attachment_bond_order,
                    bond_id=reuse_bid,
                )
                new_bond_ids.append(bid)
                b_cursor += 1

            for b_tmpl in self.spec.bonds:
                reuse_bid = self._added_bond_ids[b_cursor] if b_cursor < len(self._added_bond_ids) else None
                bid = doc.topology.add_bond(
                    new_atom_ids[b_tmpl.begin_idx],
                    new_atom_ids[b_tmpl.end_idx],
                    order=b_tmpl.order,
                    aromatic=b_tmpl.order == 4,
                    bond_id=reuse_bid,
                )
                new_bond_ids.append(bid)
                b_cursor += 1
            self._added_bond_ids = list(new_bond_ids)

            # 写入 3D 与 2D 坐标
            store = doc.ensure_coordinates()
            if store.num_frames == 0 or self._snapshot_coords_3d is None or len(self._snapshot_coords_3d) == 0:
                store.n_atoms = doc.topology.num_atoms
                store._frames.clear()
                store._current_index = -1
                store.add_frame(world_xyz, source=f"fragment:{self.spec.id}")
            else:
                doc.coordinates.append_atoms(world_xyz)

            doc.sync_2d_coords_from_3d()

            # 校验拓扑不变量
            errs = doc.validate()
            if errs:
                self._restore_snapshot(doc)
                return CommandResult(success=False, message=f"片段插入校验失败已回滚：{'; '.join(errs)}")

            return CommandResult(
                success=True,
                changed=True,
                message=f"已插入基团 [{self.spec.name_cn}]（新增 {len(new_atom_ids)} 个原子）",
                data={"fragment_id": self.spec.id, "added_atom_ids": [a.value for a in new_atom_ids]},
            )
        except Exception as exc:
            self._restore_snapshot(doc)
            return CommandResult(success=False, message=f"片段插入异常已整体回滚：{exc}")

    def _restore_snapshot(self, doc: MoleculeDocument) -> None:
        if self._snapshot_atoms is not None:
            doc.topology._atoms = {aid: Atom(**vars(a)) for aid, a in self._snapshot_atoms.items()}
        if self._snapshot_bonds is not None:
            doc.topology._bonds = {bid: Bond(**vars(b)) for bid, b in self._snapshot_bonds.items()}
        if self._snapshot_adj is not None:
            doc.topology._adjacency = {aid: list(bids) for aid, bids in self._snapshot_adj.items()}
        if self._snapshot_coords_3d is None:
            doc._coordinates = None
        else:
            store = doc.ensure_coordinates()
            store.n_atoms = len(self._snapshot_coords_3d)
            if store.num_frames == 0:
                store.add_frame(self._snapshot_coords_3d.copy(), source="undo_fragment")
            else:
                store.update_current_coords(self._snapshot_coords_3d.copy())
        if self._snapshot_coords_2d is not None:
            doc.coords_2d = dict(self._snapshot_coords_2d)

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._snapshot_atoms is None:
            return CommandResult(success=False, message="无片段插入快照可撤销")
        self._restore_snapshot(doc)
        return CommandResult(
            success=True,
            changed=True,
            message=f"已撤销插入基团 [{self.spec.name_cn}]",
        )
