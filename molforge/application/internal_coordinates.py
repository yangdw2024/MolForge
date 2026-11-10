"""
application/internal_coordinates.py - 刚体子图键角与二面角精确修改事务命令
===========================================================================
满足 P0 核心要求：
  1. ModifyAngle3DCommand:
     - 自动校验 i-j-k 顶点 j，围绕顶点 j 旋转 k 侧整个连通子图（保持子图内部所有键长与键角不变）
     - 若 j-k 位于闭环内，默认拒绝破坏环系并提示（或仅在显式允许时单点移动）
     - 一次确认对应一条 CommandBus 事务命令，一次 Ctrl+Z 完整恢复 3D 与 2D 坐标
  2. ModifyDihedral3DCommand:
     - 识别中心键 j-k，对 k 侧整个连通子图围绕 j->k 轴实施 Rodrigues 刚体扭转
     - 若中心键 j-k 处于环内，明确拒绝并返回诊断信息，绝不扯坏环结构
     - 彻底替代旧版仅弹出 DihedralChartDialog 而不改坐标的假实现
"""

from __future__ import annotations

import math
import numpy as np

from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId
from .commands import Command, CommandResult
from .measurement import angle as calc_angle, dihedral as calc_dihedral


def rodrigues_rotate(points: np.ndarray, origin: np.ndarray, axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """
    使用 Rodrigues 旋转公式将点集 points (M, 3) 绕通过 origin、方向为单位向量 axis 的轴旋转 angle_rad 弧度。
    """
    norm = float(np.linalg.norm(axis))
    if norm < 1e-12:
        return points.copy()
    u = axis.astype(np.float64) / norm
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)

    shifted = points.astype(np.float64) - origin.astype(np.float64)
    # v_rot = v * cos(theta) + (u x v) * sin(theta) + u * (u . v) * (1 - cos(theta))
    cross_uv = np.cross(u, shifted)
    dot_uv = np.dot(shifted, u)[:, None]
    rotated = shifted * c + cross_uv * s + (u[None, :] * dot_uv) * (1.0 - c)
    return (rotated + origin.astype(np.float64)).astype(np.float32)


def find_connected_subgraph_atoms(
    doc: MoleculeDocument,
    start_atom: AtomId,
    blocked_atom: AtomId,
) -> tuple[set[AtomId], bool]:
    """
    从 start_atom 出发，不经过 blocked_atom 进行 BFS 遍历：
    返回 (连通子图原子集合, 是否通过其他路径重新遇到了 blocked_atom 即是否在环内)。
    """
    visited: set[AtomId] = {start_atom}
    queue: list[AtomId] = [start_atom]
    in_ring = False

    while queue:
        curr = queue.pop(0)
        for bid in doc.topology._adjacency.get(curr, []):
            if bid not in doc.topology._bonds:
                continue
            bond = doc.topology.get_bond(bid)
            nbr = bond.end if bond.begin == curr else bond.begin
            if curr == start_atom and nbr == blocked_atom:
                # 跳过直接连接的 j-k 键
                continue
            if nbr == blocked_atom:
                # 从其他路径回到了 blocked_atom -> 说明 start_atom 与 blocked_atom 在同一个环内！
                in_ring = True
                continue
            if nbr not in visited:
                visited.add(nbr)
                queue.append(nbr)

    return visited, in_ring


class ModifyAngle3DCommand(Command):
    """精确修改键角 (i - j(顶点) - k) 的可撤销事务命令。"""

    description = "精确修改键角"

    def __init__(
        self,
        atom_i: AtomId,
        atom_j: AtomId,
        atom_k: AtomId,
        target_angle_deg: float,
        allow_ring_distortion: bool = False,
    ):
        self.atom_i = atom_i
        self.atom_j = atom_j
        self.atom_k = atom_k
        self.target_angle_deg = float(target_angle_deg)
        self.allow_ring_distortion = bool(allow_ring_distortion)
        self._old_coords: np.ndarray | None = None
        self._old_coords_2d: dict[AtomId, tuple[float, float]] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if not (0.5 <= self.target_angle_deg <= 179.5):
            return CommandResult(
                success=False,
                message=f"目标键角 {self.target_angle_deg:.1f}° 超出物理安全范围 [0.5°, 179.5°]",
            )
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="当前文档缺少 3D 坐标，无法修改键角")

        _, id2idx = doc.topology.atom_index_map()
        for aid in (self.atom_i, self.atom_j, self.atom_k):
            if aid not in id2idx:
                return CommandResult(success=False, message=f"原子 #{aid.value} 不存在于当前分子中")

        if len({self.atom_i, self.atom_j, self.atom_k}) != 3:
            return CommandResult(success=False, message="键角修改必须指定 3 个不同的原子")

        coords = doc.coordinates.current.coords.copy()
        idx_i, idx_j, idx_k = id2idx[self.atom_i], id2idx[self.atom_j], id2idx[self.atom_k]
        cur_deg, ok, diag = calc_angle(coords, idx_i, idx_j, idx_k)
        if not ok:
            return CommandResult(success=False, message=f"当前键角退化无法修改：{diag}")

        sub_k, in_ring = find_connected_subgraph_atoms(doc, self.atom_k, self.atom_j)
        if ( in_ring or self.atom_i in sub_k ) and not self.allow_ring_distortion:
            return CommandResult(
                success=False,
                message=f"原子 #{self.atom_j.value}–#{self.atom_k.value} 位于环系内，直接单侧旋转会破坏成环键长；请使用约束优化",
            )

        if self._old_coords is None:
            self._old_coords = coords.copy()
            self._old_coords_2d = dict(doc.coords_2d)

        p_i = coords[idx_i].astype(np.float64)
        p_j = coords[idx_j].astype(np.float64)
        p_k = coords[idx_k].astype(np.float64)
        v1 = p_i - p_j
        v2 = p_k - p_j
        normal = np.cross(v1, v2)
        n_norm = float(np.linalg.norm(normal))
        if n_norm < 1e-6:
            # 共线时构造任意垂直于 v1 的单位法向量
            u1 = v1 / float(np.linalg.norm(v1))
            trial = np.array([0.0, 0.0, 1.0]) if abs(u1[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
            normal = np.cross(u1, trial)

        delta_rad = math.radians(self.target_angle_deg - cur_deg)
        move_atoms = {self.atom_k} if in_ring else sub_k
        move_indices = [id2idx[a] for a in move_atoms if a in id2idx]

        sub_pts = coords[move_indices]
        coords[move_indices] = rodrigues_rotate(sub_pts, p_j, normal, delta_rad)

        new_deg, ok_after, _ = calc_angle(coords, idx_i, idx_j, idx_k)
        if not ok_after or abs(new_deg - self.target_angle_deg) > 0.05:
            return CommandResult(success=False, message="键角旋转后几何校验未通过，已中止写入")

        doc.coordinates.update_current_coords(coords)
        doc.sync_2d_coords_from_3d()
        return CommandResult(
            success=True,
            changed=True,
            message=(
                f"已将键角 #{self.atom_i.value}–#{self.atom_j.value}–#{self.atom_k.value} "
                f"从 {cur_deg:.2f}° 精确调整为 {new_deg:.2f}°（联动 {len(move_indices)} 个原子）"
            ),
            data={"old_angle": cur_deg, "new_angle": new_deg, "moved_atoms": len(move_indices)},
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords is None or not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="无历史键角坐标可恢复")
        doc.coordinates.update_current_coords(self._old_coords.copy())
        if self._old_coords_2d is not None:
            doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(
            success=True,
            changed=True,
            message=f"已撤销键角 #{self.atom_i.value}–#{self.atom_j.value}–#{self.atom_k.value} 的修改",
        )


class ModifyDihedral3DCommand(Command):
    """精确修改二面角 (i - j - k - l) 的可撤销刚体扭转事务命令。"""

    description = "精确修改二面角"

    def __init__(
        self,
        atom_i: AtomId,
        atom_j: AtomId,
        atom_k: AtomId,
        atom_l: AtomId,
        target_dihedral_deg: float,
    ):
        self.atom_i = atom_i
        self.atom_j = atom_j
        self.atom_k = atom_k
        self.atom_l = atom_l
        # 归一化目标二面角到 (-180, 180]
        val = ((float(target_dihedral_deg) + 180.0) % 360.0) - 180.0
        if val <= -180.0:
            val += 360.0
        self.target_dihedral_deg = val
        self._old_coords: np.ndarray | None = None
        self._old_coords_2d: dict[AtomId, tuple[float, float]] | None = None

    def do(self, doc: MoleculeDocument) -> CommandResult:
        if not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="当前文档缺少 3D 坐标，无法修改二面角")

        _, id2idx = doc.topology.atom_index_map()
        for aid in (self.atom_i, self.atom_j, self.atom_k, self.atom_l):
            if aid not in id2idx:
                return CommandResult(success=False, message=f"原子 #{aid.value} 不存在于当前分子中")

        if len({self.atom_i, self.atom_j, self.atom_k, self.atom_l}) != 4:
            return CommandResult(success=False, message="二面角修改必须指定 4 个不同的原子")

        sub_k, in_ring = find_connected_subgraph_atoms(doc, self.atom_k, self.atom_j)
        if in_ring or self.atom_i in sub_k:
            return CommandResult(
                success=False,
                message=(
                    f"中心键 #{self.atom_j.value}–#{self.atom_k.value} 位于环系内部，"
                    "禁止直接刚体扭转扯断闭环（请使用环系构象搜索或约束优化）"
                ),
            )

        coords = doc.coordinates.current.coords.copy()
        idx_i, idx_j, idx_k, idx_l = (
            id2idx[self.atom_i],
            id2idx[self.atom_j],
            id2idx[self.atom_k],
            id2idx[self.atom_l],
        )
        cur_deg, ok, diag = calc_dihedral(coords, idx_i, idx_j, idx_k, idx_l)
        if not ok:
            return CommandResult(success=False, message=f"当前二面角几何退化无法扭转：{diag}")

        if self._old_coords is None:
            self._old_coords = coords.copy()
            self._old_coords_2d = dict(doc.coords_2d)

        p_j = coords[idx_j].astype(np.float64)
        p_k = coords[idx_k].astype(np.float64)
        axis_jk = p_k - p_j

        # 根据 measurement.dihedral 的法向量右手系定义，绕 b2 = p_k - p_j 旋转 -delta_rad 使二面角精确增加 delta
        diff_deg = self.target_dihedral_deg - cur_deg
        delta_rad = -math.radians(diff_deg)

        move_atoms = sub_k | {self.atom_l}
        move_atoms.discard(self.atom_j)
        move_atoms.discard(self.atom_i)
        move_indices = [id2idx[a] for a in move_atoms if a in id2idx]

        coords[move_indices] = rodrigues_rotate(coords[move_indices], p_k, axis_jk, delta_rad)
        new_deg, ok_after, _ = calc_dihedral(coords, idx_i, idx_j, idx_k, idx_l)

        # 若符号约定相反则自动取反方向旋转一次确保精确命中目标角
        ang_err = ((new_deg - self.target_dihedral_deg + 180.0) % 360.0) - 180.0
        if not ok_after or abs(ang_err) > 0.05:
            coords = self._old_coords.copy()
            coords[move_indices] = rodrigues_rotate(coords[move_indices], p_k, axis_jk, -delta_rad)
            new_deg, ok_after, _ = calc_dihedral(coords, idx_i, idx_j, idx_k, idx_l)

        doc.coordinates.update_current_coords(coords)
        doc.sync_2d_coords_from_3d()
        return CommandResult(
            success=True,
            changed=True,
            message=(
                f"已将二面角 #{self.atom_i.value}–#{self.atom_j.value}–#{self.atom_k.value}–#{self.atom_l.value} "
                f"从 {cur_deg:.2f}° 扭转为 {new_deg:.2f}°（联动 {len(move_indices)} 个原子）"
            ),
            data={"old_dihedral": cur_deg, "new_dihedral": new_deg, "moved_atoms": len(move_indices)},
        )

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        if self._old_coords is None or not doc.has_3d or doc.coordinates.current is None:
            return CommandResult(success=False, message="无历史二面角坐标可恢复")
        doc.coordinates.update_current_coords(self._old_coords.copy())
        if self._old_coords_2d is not None:
            doc.coords_2d = dict(self._old_coords_2d)
        return CommandResult(
            success=True,
            changed=True,
            message=(
                f"已撤销二面角 #{self.atom_i.value}–#{self.atom_j.value}–"
                f"#{self.atom_k.value}–#{self.atom_l.value} 的修改"
            ),
        )
