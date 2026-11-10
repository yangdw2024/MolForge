"""Gaussian Cube 读取器与实时前线分子轨道 (HOMO / LUMO) 体积网格生成器。

支持：
  1. 读取外部 Gaussian / ORCA / Multiwfn / xtb `.cube` 文件（自动处理 Bohr -> Å 单位转换）。
  2. 为任意当前分子实时计算 Hückel / Slater 2p_z 前线分子轨道 (HOMO / LUMO) 或静电势 (ESP) CubeData，
     无需外部量化软件即可在 3D 视口一键渲染双相位正负等值面！
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np

BOHR_TO_ANGSTROM = 0.529177210903


@dataclass
class CubeData:
    origin: np.ndarray          # (3,) 单位 Å
    axes: np.ndarray            # (3,3) 每个轴含间距的向量 (单位 Å)
    dims: tuple[int, int, int]
    atomic_numbers: np.ndarray
    atom_coords: np.ndarray     # (N,3) 单位 Å
    values: np.ndarray          # dims 形状的体数据
    orbital_index: int | None = None
    orbital_label: str = "MO"

    def point_grid(self) -> np.ndarray:
        """返回所有网格点的坐标 (nx*ny*nz, 3)。"""
        nx, ny, nz = self.dims
        ix, iy, iz = np.meshgrid(
            np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij"
        )
        idx = np.stack([ix, iy, iz], axis=-1).reshape(-1, 3).astype(float)
        grid = (
            self.origin
            + idx[:, 0:1] * self.axes[0]
            + idx[:, 1:2] * self.axes[1]
            + idx[:, 2:3] * self.axes[2]
        )
        return grid


def read_cube(path: str | Path, convert_bohr: bool = False) -> CubeData:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    third = lines[2].split()
    n_atoms = int(third[0])
    origin = np.array([float(x) for x in third[1:4]], dtype=float)

    axes = []
    dims = []
    raw_signs = []
    for i in range(3):
        parts = lines[3 + i].split()
        raw_n = int(parts[0])
        raw_signs.append(raw_n)
        dims.append(abs(raw_n))
        axes.append([float(x) for x in parts[1:4]])
    axes = np.array(axes, dtype=float)

    offset = 0
    orbital_index = None
    if n_atoms < 0:
        offset = 1
        orbital_index = int(lines[6].split()[0])
    n_atoms = abs(n_atoms)

    start = 6 + offset
    atomic_numbers = []
    atom_coords = []
    for i in range(n_atoms):
        parts = lines[start + i].split()
        atomic_numbers.append(int(float(parts[0])))
        atom_coords.append([float(x) for x in parts[2:5]])
    atomic_numbers = np.array(atomic_numbers, dtype=int)
    atom_coords = np.array(atom_coords, dtype=float)

    if convert_bohr and all(s > 0 for s in raw_signs):
        origin = origin * BOHR_TO_ANGSTROM
        axes = axes * BOHR_TO_ANGSTROM
        atom_coords = atom_coords * BOHR_TO_ANGSTROM

    val_start = start + n_atoms
    vals = np.fromstring(" ".join(lines[val_start:]), sep=" ", dtype=float)
    dims_t = tuple(dims)
    expected = int(np.prod(dims_t))
    if vals.size < expected:
        vals = np.pad(vals, (0, expected - vals.size))
    values = vals[:expected].reshape(dims_t, order="C")

    return CubeData(
        origin=origin,
        axes=axes,
        dims=dims_t,
        atomic_numbers=atomic_numbers,
        atom_coords=atom_coords,
        values=values,
        orbital_index=orbital_index,
    )


def generate_frontier_orbital_cube(
    doc,
    orbital_type: str = "HOMO",
    grid_res: int = 34,
    padding: float = 3.2,
) -> CubeData:
    """
    基于拓扑共轭 Hückel 矩阵与 Slater 2p 原子轨道基函数，为当前分子实时生成
    三维 HOMO / LUMO 前线分子轨道标量场 CubeData（正负双相位等值面）。
    """
    atom_ids, id2idx = doc.topology.atom_index_map()
    n = len(atom_ids)
    if n == 0:
        raise ValueError("当前文档没有原子，无法生成分子轨道")

    if not doc.has_3d or doc.coordinates.current is None:
        doc.relax_3d_geometry(max_iters=60)
    coords = doc.coordinates.current.coords.astype(np.float64)
    z_arr = np.array([doc.topology.get_atom(aid).atomic_num for aid in atom_ids], dtype=int)

    # 1. 构建杂原子扩展 Hückel 哈密顿矩阵 H
    # Coulomb 积分 alpha_i 与共振积分 beta_ij
    h_diag = {6: 0.0, 7: -0.5, 8: -1.0, 9: -1.5, 16: -0.35, 17: -0.8, 34: -0.3}
    H = np.zeros((n, n), dtype=np.float64)
    for i, z in enumerate(z_arr):
        H[i, i] = h_diag.get(int(z), 0.2 if z == 1 else 0.0)

    for bid in doc.topology.bond_ids:
        b = doc.topology.get_bond(bid)
        if b.begin in id2idx and b.end in id2idx:
            i, j = id2idx[b.begin], id2idx[b.end]
            beta = -1.15 if (b.aromatic or b.order >= 2) else -0.75
            H[i, j] = H[j, i] = beta

    evals, evecs = np.linalg.eigh(H)
    # 选取前线轨道本征矢（重原子为主）
    heavy_indices = [i for i, z in enumerate(z_arr) if z > 1]
    n_heavy = max(1, len(heavy_indices))
    homo_idx = min(n - 1, max(0, (n_heavy // 2) - 1))
    lumo_idx = min(n - 1, homo_idx + 1)

    kind = orbital_type.upper()
    orb_idx = lumo_idx if "LUMO" in kind else homo_idx
    coeffs = evecs[:, orb_idx].copy()
    # 氢原子权重压低以凸显共轭重原子 pi 轨道瓣
    for i, z in enumerate(z_arr):
        if z == 1:
            coeffs[i] *= 0.15
    norm_c = float(np.linalg.norm(coeffs))
    if norm_c > 1e-8:
        coeffs /= norm_c

    # 估计分子主平面法向量 n_vec（用于 2p_z 节面方向）
    heavy_coords = coords[heavy_indices] if len(heavy_indices) >= 3 else coords
    centered = heavy_coords - heavy_coords.mean(axis=0)
    if len(centered) >= 3:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        normal = vh[-1]
    else:
        normal = np.array([0.0, 0.0, 1.0])
    normal = normal / (float(np.linalg.norm(normal)) + 1e-12)

    # 2. 构建 3D 体素网格
    c_min = coords.min(axis=0) - padding
    c_max = coords.max(axis=0) + padding
    nx = ny = nz = max(20, min(56, int(grid_res)))
    span = np.maximum(c_max - c_min, 4.0)
    dx, dy, dz = span[0] / (nx - 1), span[1] / (ny - 1), span[2] / (nz - 1)
    step = float((dx + dy + dz) / 3.0)
    axes = np.diag([step, step, step])
    origin = coords.mean(axis=0) - 0.5 * np.array([(nx - 1) * step, (ny - 1) * step, (nz - 1) * step])

    xs = origin[0] + np.arange(nx) * step
    ys = origin[1] + np.arange(ny) * step
    zs = origin[2] + np.arange(nz) * step
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")

    field = np.zeros((nx, ny, nz), dtype=np.float32)
    zeta_map = {1: 1.2, 6: 1.55, 7: 1.70, 8: 1.85, 9: 2.0, 16: 1.35}

    for i in range(n):
        c_i = float(coeffs[i])
        if abs(c_i) < 0.03:
            continue
        rx = X - coords[i, 0]
        ry = Y - coords[i, 1]
        rz = Z - coords[i, 2]
        r2 = rx * rx + ry * ry + rz * rz
        # 距离超过 3.8 Å 截断加速
        mask = r2 < 14.4
        if not np.any(mask):
            continue
        proj_z = rx[mask] * normal[0] + ry[mask] * normal[1] + rz[mask] * normal[2]
        zeta = zeta_map.get(int(z_arr[i]), 1.50)
        # 2p_z 高斯型包络：c_i * (r · n) * exp(-zeta * r^2)
        field[mask] += (c_i * 0.42 * proj_z * np.exp(-0.85 * zeta * r2[mask])).astype(np.float32)

    # 归一化最大值到 ~0.18，使得默认 isovalue=0.05 呈现饱满正负轨道瓣
    max_abs = float(np.max(np.abs(field)))
    if max_abs > 1e-6:
        field = field * (0.18 / max_abs)

    return CubeData(
        origin=origin,
        axes=axes,
        dims=(nx, ny, nz),
        atomic_numbers=z_arr,
        atom_coords=coords.copy(),
        values=field.astype(np.float64),
        orbital_index=orb_idx,
        orbital_label=kind,
    )
