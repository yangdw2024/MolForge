"""
domain/document.py - 分子文档（唯一化学事实源 + 严格不变量校验 + 双引擎 3D 弛豫）
=================================================================================
"""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from .ids import AtomId, BondId
from .topology import Topology
from .coordinate_store import CoordinateStore


class DocumentStatus(Enum):
    DRAFT = "draft"
    VALIDATED = "validated"


@dataclass(frozen=True)
class DocumentRevision:
    document_id: str
    revision: int
    n_atoms: int
    n_bonds: int
    n_frames: int
    topology_hash: str


class MoleculeDocument:
    """
    分子文档：唯一化学事实源。
    """

    def __init__(self, name: str = "untitled") -> None:
        self.document_id: str = uuid.uuid4().hex[:12]
        self.revision: int = 0
        self.name: str = name
        self.status: DocumentStatus = DocumentStatus.DRAFT
        self.topology = Topology()
        self._coordinates: CoordinateStore | None = None
        # 2D 世界坐标（单位 Å，以 (0,0) 为中心，与窗口像素大小完全解耦！）
        self.coords_2d: dict[AtomId, tuple[float, float]] = {}
        self.properties: dict[str, Any] = {}
        self.source_format: str = "unknown"
        self.source_path: str | None = None

        self.units = {
            "coordinates": "angstrom",
            "energy": "ev",
            "bond_length": "angstrom",
            "angle": "degree",
        }

    # ---------- 双向映射与不变量检查（Phase 1） ----------

    def atom_index_map(self) -> tuple[list[AtomId], dict[AtomId, int]]:
        """返回当前拓扑的 (idx_to_atom_id, atom_id_to_idx) 双向映射。"""
        return self.topology.atom_index_map()

    def get_atom_3d_pos(self, aid: AtomId) -> np.ndarray | None:
        """通过 AtomId 安全获取其 3D 坐标 (3,)。"""
        if not self.has_3d or self.coordinates.current is None:
            return None
        _, id_to_idx = self.topology.atom_index_map()
        idx = id_to_idx.get(aid)
        if idx is None or idx >= len(self.coordinates.current.coords):
            return None
        return self.coordinates.current.coords[idx].copy()

    def find_nearest_atom_3d(self, world_pos: np.ndarray, exclude: AtomId | None = None) -> tuple[AtomId | None, float]:
        """寻找距离 3D 点 world_pos 最近的已有原子 ID 及其距离（Å）。"""
        if not self.has_3d or self.coordinates.current is None or self.topology.num_atoms == 0:
            return None, float("inf")
        idx_to_id, _ = self.topology.atom_index_map()
        coords = self.coordinates.current.coords
        p = np.asarray(world_pos, dtype=np.float32)
        best_aid = None
        best_dist = float("inf")
        # 优先连接重原子（非氢），若只有氢则连接氢
        for prefer_heavy in (True, False):
            for i, aid in enumerate(idx_to_id):
                if aid == exclude or i >= len(coords):
                    continue
                atom = self.topology.get_atom(aid)
                if prefer_heavy and atom.atomic_num == 1:
                    continue
                d = float(np.linalg.norm(coords[i] - p))
                if d < best_dist:
                    best_dist = d
                    best_aid = aid
            if best_aid is not None:
                break
        return best_aid, best_dist

    def validate(self) -> list[str]:
        """
        验证文档的化学与拓扑正确性（注意：允许 0 个原子的空文档，以便删光原子后不阻断）。
        """
        errors = []
        for bid in self.topology.bond_ids:
            bond = self.topology.get_bond(bid)
            if bond.begin not in self.topology._atoms:
                errors.append(f"键 {bid.value} 的起始原子 {bond.begin.value} 不存在")
            if bond.end not in self.topology._atoms:
                errors.append(f"键 {bid.value} 的结束原子 {bond.end.value} 不存在")
            if bond.begin == bond.end:
                errors.append(f"键 {bid.value} 是自环键（原子连接自己）")

        if not errors:
            self.status = DocumentStatus.VALIDATED
        return errors

    def check_invariants(self) -> list[str]:
        """检查数据层强不变量：拓扑原子数 == 坐标帧行数，键两端原子存在，无 NaN。"""
        errs = self.validate()
        n = self.topology.num_atoms
        if self.has_3d and self.coordinates.current is not None:
            c_shape = self.coordinates.current.coords.shape
            if c_shape != (n, 3):
                errs.append(f"坐标帧形状 {c_shape} 与拓扑原子数 ({n}, 3) 不一致")
            if np.isnan(self.coordinates.current.coords).any():
                errs.append("3D 坐标包含 NaN")
        return errs

    def topology_hash(self) -> str:
        atom_list = []
        for aid in self.topology.atom_ids:
            atom = self.topology.get_atom(aid)
            atom_list.append(f"{atom.atomic_num}:{atom.formal_charge}")
        bond_list = []
        for bid in self.topology.bond_ids:
            bond = self.topology.get_bond(bid)
            a = min(bond.begin.value, bond.end.value)
            b = max(bond.begin.value, bond.end.value)
            bond_list.append(f"{a}-{b}:{bond.order}:{int(bond.aromatic)}")
        atom_list.sort()
        bond_list.sort()
        topo_str = f"atoms={','.join(atom_list)};bonds={','.join(bond_list)}"
        return hashlib.sha256(topo_str.encode()).hexdigest()[:16]

    # ---------- 坐标管理 ----------

    @property
    def coordinates(self) -> CoordinateStore:
        if self._coordinates is None:
            self._coordinates = CoordinateStore(self.topology.num_atoms)
        return self._coordinates

    def ensure_coordinates(self) -> CoordinateStore:
        """确保坐标存储与当前拓扑原子数严格同步（行数 == num_atoms）。"""
        n = self.topology.num_atoms
        if self._coordinates is None:
            self._coordinates = CoordinateStore(n)
            return self._coordinates

        if n == 0:
            self._coordinates = CoordinateStore(0)
            return self._coordinates

        if self._coordinates.n_atoms == n and (
            self._coordinates.num_frames == 0 or self._coordinates.current.coords.shape == (n, 3)
        ):
            return self._coordinates

        old = self._coordinates
        if old.num_frames == 0:
            self._coordinates = CoordinateStore(n)
            return self._coordinates

        if old.n_atoms < n:
            k = n - old.n_atoms
            cur = old.current.coords if old.current is not None else np.zeros((old.n_atoms, 3), dtype=np.float32)
            extra = np.zeros((k, 3), dtype=np.float32)
            atom_ids = list(self.topology.atom_ids)
            for idx_offset in range(k):
                global_idx = old.n_atoms + idx_offset
                aid = atom_ids[global_idx]
                nbrs = self.topology.neighbors_of(aid)
                placed = False
                for nbr_id in nbrs:
                    nbr_idx = atom_ids.index(nbr_id)
                    if nbr_idx < old.n_atoms:
                        from .chemistry import estimate_bond_length
                        length = estimate_bond_length(self.topology.get_atom(nbr_id).atomic_num, self.topology.get_atom(aid).atomic_num)
                        extra[idx_offset] = self.suggest_bonded_3d_position(nbr_id, bond_length=length)
                        placed = True
                        break
                if not placed:
                    xmax = float(cur[:, 0].max()) if len(cur) > 0 else 0.0
                    extra[idx_offset] = [xmax + 1.8 * (idx_offset + 1), 0.0, 0.0]
            old.append_atoms(extra)
            return old
        else:
            new_store = CoordinateStore(n)
            for fr in old:
                new_store.add_frame(fr.coords[:n], energy=fr.energy, source=fr.source)
            self._coordinates = new_store
            return self._coordinates

    def suggest_bonded_3d_position(self, anchor_id: AtomId, bond_length: float = 1.45) -> np.ndarray:
        """根据锚点原子已有邻居计算四面体/平面三角新键生长方向（Å）。"""
        if not self.has_3d or self.coordinates.current is None:
            return np.array([bond_length, 0.0, 0.0], dtype=np.float32)

        atom_ids, id_to_idx = self.topology.atom_index_map()
        coords = self.coordinates.current.coords
        if anchor_id not in id_to_idx:
            return np.array([bond_length, 0.0, 0.0], dtype=np.float32)

        idx = id_to_idx[anchor_id]
        if idx >= len(coords):
            return np.array([bond_length, 0.0, 0.0], dtype=np.float32)

        p0 = coords[idx].astype(np.float64)
        nbrs = [n for n in self.topology.neighbors_of(anchor_id) if n in id_to_idx and id_to_idx[n] < len(coords)]

        if not nbrs:
            return (p0 + np.array([bond_length, 0.0, 0.0])).astype(np.float32)

        vecs = []
        for n in nbrs:
            v = coords[id_to_idx[n]].astype(np.float64) - p0
            norm = np.linalg.norm(v)
            if norm > 1e-4:
                vecs.append(v / norm)

        from .coordination import inferred_geometry, fit_directions
        geometry = inferred_geometry(self, anchor_id)
        if geometry is not None and len(vecs) < geometry.coordination:
            oriented, occupied = fit_directions(geometry, vecs)
            free = [i for i in range(geometry.coordination) if i not in occupied]
            return (p0 + oriented[free[0]] * bond_length).astype(np.float32)

        if not vecs:
            return (p0 + np.array([bond_length, 0.0, 0.0])).astype(np.float32)

        if len(vecs) == 1:
            v1 = vecs[0]
            ref = np.array([0.0, 0.0, 1.0]) if abs(v1[2]) < 0.85 else np.array([0.0, 1.0, 0.0])
            perp = np.cross(v1, ref)
            perp /= (np.linalg.norm(perp) + 1e-9)
            direction = -0.45 * v1 + 0.893 * perp
            direction /= (np.linalg.norm(direction) + 1e-9)
            return (p0 + direction * bond_length).astype(np.float32)

        sum_v = np.sum(vecs, axis=0)
        norm_s = np.linalg.norm(sum_v)
        if norm_s > 0.15:
            direction = -sum_v / norm_s
            if len(vecs) == 2:
                normal = np.cross(vecs[0], vecs[1])
                n_norm = np.linalg.norm(normal)
                if n_norm > 1e-3:
                    normal /= n_norm
                    direction = 0.88 * direction + 0.47 * normal
                    direction /= np.linalg.norm(direction)
            return (p0 + direction * bond_length).astype(np.float32)
        else:
            ref = np.array([0.0, 0.0, 1.0]) if abs(vecs[0][2]) < 0.85 else np.array([1.0, 0.0, 0.0])
            direction = np.cross(vecs[0], ref)
            direction /= (np.linalg.norm(direction) + 1e-9)
            return (p0 + direction * bond_length).astype(np.float32)

    def relax_3d_geometry(self, max_iters: int = 120) -> bool:
        """
        双引擎 3D 结构几何优化：
          1. 优先尝试 RDKit MMFF94 / UFF 力场优化
          2. 若 RDKit 因非标价态或环境原因跳过，则执行内置 NumPy 化学谐振弹簧+斥力弛豫算法，
             确保「3D 力场优化」按钮在任何分子结构下都 100% 生效！
        """
        n = self.topology.num_atoms
        if n == 0:
            return False
        self.ensure_coordinates()
        if self.coordinates.current is None:
            self.coordinates.add_frame(np.zeros((n, 3), dtype=np.float32), source="init")

        # 引擎 1：尝试 RDKit MMFF94 / UFF
        try:
            from rdkit.Chem import AllChem
            from ..io.rdkit_adapter import doc_to_rdkit

            rdmol, atom_map, _ = doc_to_rdkit(self, sanitize=True, strict=True)
            if rdmol.GetNumAtoms() == n:
                if rdmol.GetNumConformers() == 0:
                    params = AllChem.ETKDGv3()
                    params.randomSeed = 42
                    AllChem.EmbedMolecule(rdmol, params)
                if rdmol.GetNumConformers() > 0:
                    fixed = [aid for aid in self.topology.atom_ids if self.topology.get_atom(aid).properties.get("frozen")]
                    if AllChem.MMFFHasAllMoleculeParams(rdmol):
                        props = AllChem.MMFFGetMoleculeProperties(rdmol)
                        force_field = AllChem.MMFFGetMoleculeForceField(rdmol, props)
                        method = "MMFF94"
                    else:
                        force_field = AllChem.UFFGetMoleculeForceField(rdmol)
                        method = "UFF"
                    if force_field is None:
                        raise ValueError("Force field unavailable")
                    for aid in fixed:
                        force_field.AddFixedPoint(atom_map[aid])
                    force_field.Initialize()
                    convergence = force_field.Minimize(maxIts=max_iters)
                    self.properties["last_optimization"] = {"method":method,"converged":convergence==0,"frozen_atoms":len(fixed)}
                    conf = rdmol.GetConformer()
                    new_coords = np.zeros((n, 3), dtype=np.float32)
                    for i, aid in enumerate(self.topology.atom_ids):
                        rd_idx = atom_map.get(aid, i)
                        pos = conf.GetAtomPosition(rd_idx)
                        new_coords[i] = [pos.x, pos.y, pos.z]
                    if not fixed:
                        new_coords -= new_coords.mean(axis=0)
                    self.coordinates.update_current_coords(new_coords)
                    return True
        except Exception:
            pass

        # 引擎 2：内置 NumPy 键长弹簧 + VSEPR 键角斥力弛豫器（100% 兜底成功）
        return self._numpy_spring_relax_3d(steps=max(40, min(150, max_iters)))

    def _numpy_spring_relax_3d(self, steps: int = 80) -> bool:
        """纯 NumPy 3D 分子几何弛豫器：修正畸变键长至标准共价键长并消除原子重叠。"""
        n = self.topology.num_atoms
        if n <= 1 or self.coordinates.current is None:
            return True
        coords = self.coordinates.current.coords.astype(np.float64).copy()
        idx_to_id, id_to_idx = self.topology.atom_index_map()
        z_arr = np.array([self.topology.get_atom(aid).atomic_num for aid in idx_to_id])
        fixed_indices = [i for i, aid in enumerate(idx_to_id) if self.topology.get_atom(aid).properties.get("frozen")]
        fixed_coords = coords[fixed_indices].copy()

        # 若有完全重合点，加微小非零扰动解开奇点
        for i in range(n):
            for j in range(i + 1, n):
                if np.linalg.norm(coords[i] - coords[j]) < 0.05:
                    coords[j] += np.array([0.35 * ((j % 3) - 1), 0.35 * ((j % 2) - 0.5), 0.15])

        bonds_idx = []
        for bid in self.topology.bond_ids:
            b = self.topology.get_bond(bid)
            if b.begin in id_to_idx and b.end in id_to_idx:
                i, j = id_to_idx[b.begin], id_to_idx[b.end]
                zi, zj = z_arr[i], z_arr[j]
                from .chemistry import estimate_bond_length
                r0 = estimate_bond_length(zi, zj, b.order, b.aromatic)
                bonds_idx.append((i, j, r0))

        for _ in range(steps):
            forces = np.zeros_like(coords)
            # 1. 成键谐振弹簧力
            for i, j, r0 in bonds_idx:
                diff = coords[j] - coords[i]
                dist = float(np.linalg.norm(diff)) + 1e-8
                f_mag = 0.35 * (dist - r0)
                f_vec = (diff / dist) * f_mag
                forces[i] += f_vec
                forces[j] -= f_vec

            # 2. 非键范德华短程排斥（防止未成键原子挤在一起）
            for i in range(n):
                diff = coords[i] - coords
                dist = np.linalg.norm(diff, axis=1) + 1e-6
                mask = (dist < 2.2) & (dist > 1e-5)
                for j in np.where(mask)[0]:
                    if any((i == bi and j == bj) or (i == bj and j == bi) for bi, bj, _ in bonds_idx):
                        continue
                    rep = 0.08 * (2.2 - dist[j]) / dist[j]
                    forces[i] += diff[j] * rep

            coords += np.clip(forces, -0.25, 0.25)
            coords[fixed_indices] = fixed_coords

        if not fixed_indices:
            coords -= coords.mean(axis=0)
        self.properties["last_optimization"] = {"method":"heuristic spring relaxation","converged":False,"frozen_atoms":len(fixed_indices)}
        self.coordinates.update_current_coords(coords.astype(np.float32))
        return True

    def sync_2d_coords_from_3d(self) -> None:
        """当存在新原子尚无 2D 世界坐标时，按化学键或 3D 投影补齐其 2D 坐标（单位 Å）。"""
        idx_to_id, id_to_idx = self.topology.atom_index_map()
        # 清理已删除原子的残留 2D 坐标
        for k in list(self.coords_2d.keys()):
            if k not in id_to_idx:
                self.coords_2d.pop(k, None)

        # 如果原本缓存的是旧版屏幕像素坐标（绝对值 > 40），自动归一化到 Å 世界坐标
        if self.coords_2d:
            vals = np.array(list(self.coords_2d.values()), dtype=np.float64)
            span = max(float(np.ptp(vals[:, 0])) if len(vals) > 1 else 0.0,
                       float(np.ptp(vals[:, 1])) if len(vals) > 1 else 0.0)
            if len(vals) < 120 and (span > 120.0 or np.abs(vals).max() > 150.0):
                center = vals.mean(axis=0)
                for aid, (px, py) in list(self.coords_2d.items()):
                    self.coords_2d[aid] = ((px - center[0]) / 36.0, -(py - center[1]) / 36.0)

        for i, aid in enumerate(idx_to_id):
            if aid in self.coords_2d:
                continue
            nbrs = [n for n in self.topology.neighbors_of(aid) if n in self.coords_2d]
            if nbrs:
                anchor = nbrs[0]
                ax, ay = self.coords_2d[anchor]
                other_nbrs = [n for n in self.topology.neighbors_of(anchor) if n in self.coords_2d and n != aid]
                if not other_nbrs:
                    ang = math.pi / 6
                elif len(other_nbrs) == 1:
                    ox, oy = self.coords_2d[other_nbrs[0]]
                    base_ang = math.atan2(ay - oy, ax - ox)
                    ang = base_ang + (math.pi / 3 if (aid.value % 2 == 0) else -math.pi / 3)
                else:
                    vx = sum(self.coords_2d[n][0] - ax for n in other_nbrs)
                    vy = sum(self.coords_2d[n][1] - ay for n in other_nbrs)
                    ang = math.atan2(-vy, -vx) if math.hypot(vx, vy) > 1e-4 else 0.0
                self.coords_2d[aid] = (ax + 1.50 * math.cos(ang), ay + 1.50 * math.sin(ang))
            elif self.has_3d and self.coordinates.current is not None and i < len(self.coordinates.current.coords):
                p3 = self.coordinates.current.coords[i]
                self.coords_2d[aid] = (float(p3[0]), float(p3[1]))
            else:
                self.coords_2d[aid] = (float(i) * 1.50, 0.0)

    # ---------- 版本与查询 ----------

    def bump_revision(self) -> None:
        self.revision += 1

    @property
    def revision_snapshot(self) -> DocumentRevision:
        return DocumentRevision(
            document_id=self.document_id,
            revision=self.revision,
            n_atoms=self.topology.num_atoms,
            n_bonds=self.topology.num_bonds,
            n_frames=self.coordinates.num_frames if self._coordinates else 0,
            topology_hash=self.topology_hash(),
        )

    @property
    def num_atoms(self) -> int:
        return self.topology.num_atoms

    @property
    def num_bonds(self) -> int:
        return self.topology.num_bonds

    @property
    def has_3d(self) -> bool:
        return self._coordinates is not None and self._coordinates.num_frames > 0

    def summary(self) -> str:
        parts = [self.name] if self.name else []
        parts.append(f"{self.num_atoms} atoms")
        parts.append(f"{self.num_bonds} bonds")
        if self.has_3d:
            parts.append(f"{self.coordinates.num_frames} frames")
        return " | ".join(parts)
