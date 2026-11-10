"""Trajectory and conformer ensemble mathematical analysis engine.

Adheres strictly to scientific invariants:
  1. Kabsch alignment: All RMSD and RMSF calculations factor out rigid body
     translations and rotations using SVD optimal superposition with reflection parity.
  2. Streaming Welford RMSF: Online mean and variance accumulation over frames,
     achieving O(1) memory and numerical stability without storing entire trajectories.
  3. PBC & NoJump: Designed to accept unwrapped/aligned coordinates.
  4. Conformer Ensemble Clustering: Pairwise Kabsch RMSD distance matrix with
     medoid-based clustering and structural representative identification.
"""
from __future__ import annotations

from typing import List, Dict, Tuple, Optional, Any
import numpy as np


def kabsch_align(P: np.ndarray, Q: np.ndarray) -> Tuple[np.ndarray, float, np.ndarray]:
    """Kabsch 最佳刚体叠合算法。

    将坐标集 P 刚体叠合到参考坐标集 Q 上，最小化均方根偏差 (RMSD)。

    参数
    ----
    P : np.ndarray, shape (N, 3) 待对齐坐标 (单位 Å)
    Q : np.ndarray, shape (N, 3) 参考坐标 (单位 Å)

    返回
    ----
    (P_aligned, rmsd, R)
      - P_aligned: 对齐后的坐标 (N, 3)
      - rmsd: 最小化后的 RMSD 值 (Å)
      - R: 3x3 旋转矩阵
    """
    P_arr = np.asarray(P, dtype=float)
    Q_arr = np.asarray(Q, dtype=float)
    if P_arr.shape != Q_arr.shape or P_arr.ndim != 2 or P_arr.shape[1] != 3:
        raise ValueError(f"Kabsch 输入形状必须一致且为 (N, 3)，收到 {P_arr.shape} 与 {Q_arr.shape}")

    n = len(P_arr)
    if n == 0:
        return P_arr.copy(), 0.0, np.eye(3)

    p_center = np.mean(P_arr, axis=0)
    q_center = np.mean(Q_arr, axis=0)
    P_c = P_arr - p_center
    Q_c = Q_arr - q_center

    # 协方差矩阵 H = P_c^T @ Q_c
    H = P_c.T @ Q_c
    U, S, Vt = np.linalg.svd(H)
    R = U @ Vt

    # 检查手性反转 (反射解)
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt

    P_aligned = P_c @ R + q_center
    rmsd = float(np.sqrt(np.mean(np.sum((P_aligned - Q_arr) ** 2, axis=-1))))
    return P_aligned, rmsd, R


def calculate_radius_of_gyration(coords: np.ndarray) -> float:
    """计算回旋半径 (Radius of Gyration, Rg)。

    Rg = sqrt( (1/N) * sum_i || r_i - r_com ||^2 )
    """
    c = np.asarray(coords, dtype=float)
    if len(c) == 0:
        return 0.0
    com = np.mean(c, axis=0)
    diff = c - com
    return float(np.sqrt(np.mean(np.sum(diff ** 2, axis=-1))))


class StreamingWelfordRMSF:
    """流式 Welford 算法计算逐原子均方根波动 (RMSF)，自动施加 Kabsch 叠合。

    避免将庞大轨迹的所有坐标全部载入内存，且严格过滤由于整体刚体平动/转动导致的虚假涨落。
    """

    def __init__(self, ref_coords: np.ndarray):
        self.ref = np.asarray(ref_coords, dtype=float)
        self.n_atoms = len(self.ref)
        self.count: int = 0
        self.mean = np.zeros_like(self.ref)
        self.M2 = np.zeros_like(self.ref)
        self.rmsd_history: List[float] = []

    def update(self, frame_coords: np.ndarray) -> float:
        """输入新的一帧，自动对齐到参考结构并流式更新统计量。返回当前帧对齐后的 RMSD。"""
        aligned, rmsd, _ = kabsch_align(frame_coords, self.ref)
        self.rmsd_history.append(rmsd)
        self.count += 1
        delta = aligned - self.mean
        self.mean += delta / self.count
        delta2 = aligned - self.mean
        self.M2 += delta * delta2
        return rmsd

    def get_rmsf(self) -> np.ndarray:
        """返回所有原子的 RMSF 数组 (N,)，单位 Å。"""
        if self.count <= 1:
            return np.zeros(self.n_atoms)
        var = self.M2 / self.count
        return np.sqrt(np.sum(var, axis=-1))


def calculate_trajectory_metrics(
    adapter: Any,
    ref_frame: int = 0,
    stride: int = 1,
    max_frames: Optional[int] = None,
) -> Dict[str, Any]:
    """批量/流式计算轨迹的时序物理指标 (RMSD、Rg、RMSF)。

    参数
    ----
    adapter : TrajectoryAdapter 实例
    ref_frame : 参考帧索引 (默认第 0 帧)
    stride : 抽样步长
    max_frames : 最大分析帧数 (防止极端长轨迹耗尽主循环)

    返回
    ----
    包含 frame_indices, times_ps, rmsd, rg, rmsf, mean_rmsd, max_rmsd 的字典。
    """
    total_frames = adapter.n_frames
    indices = list(range(0, total_frames, max(1, stride)))
    if max_frames and len(indices) > max_frames:
        indices = indices[:max_frames]

    ref_coords = adapter.get_frame(ref_frame)
    streamer = StreamingWelfordRMSF(ref_coords)

    times_ps: List[float] = []
    rmsd_list: List[float] = []
    rg_list: List[float] = []

    for fi in indices:
        coords = adapter.get_frame(fi)
        rmsd = streamer.update(coords)
        rg = calculate_radius_of_gyration(coords)
        t = adapter.frame_time_ps(fi)
        times_ps.append(t)
        rmsd_list.append(rmsd)
        rg_list.append(rg)

    rmsf = streamer.get_rmsf()

    return {
        "frame_indices": indices,
        "times_ps": times_ps,
        "rmsd": rmsd_list,
        "rg": rg_list,
        "rmsf": rmsf,
        "mean_rmsd": float(np.mean(rmsd_list)) if rmsd_list else 0.0,
        "max_rmsd": float(np.max(rmsd_list)) if rmsd_list else 0.0,
        "mean_rg": float(np.mean(rg_list)) if rg_list else 0.0,
    }


def cluster_conformer_ensemble(
    coords_list: List[np.ndarray],
    rmsd_threshold: float = 0.5,
) -> Dict[str, Any]:
    """对多构象集合进行全对偶 Kabsch RMSD 矩阵计算与结构聚类。

    参数
    ----
    coords_list : List of (N, 3) 构象坐标
    rmsd_threshold : 聚类截断半径 (单位 Å)

    返回
    ----
    {
      "matrix": np.ndarray (M, M),
      "clusters": Dict[int, List[int]], # cluster_id -> [conformer_indices]
      "medoids": Dict[int, int],        # cluster_id -> center_conformer_index
      "n_clusters": int,
    }
    """
    M = len(coords_list)
    if M == 0:
        return {"matrix": np.zeros((0, 0)), "clusters": {}, "medoids": {}, "n_clusters": 0}

    # 1. 计算对偶 RMSD 距离矩阵
    dist_mat = np.zeros((M, M), dtype=float)
    for i in range(M):
        for j in range(i + 1, M):
            _, d, _ = kabsch_align(coords_list[i], coords_list[j])
            dist_mat[i, j] = d
            dist_mat[j, i] = d

    # 2. 贪心中心聚类 (Greedy Medoids / Leader Algorithm)
    unassigned = set(range(M))
    clusters: Dict[int, List[int]] = {}
    medoids: Dict[int, int] = {}
    cid = 0

    while unassigned:
        # 选择在当前未分配集合中与其它成员平均距离最小的构象作为种子中心 (Medoid)
        best_medoid = -1
        best_avg_dist = float("inf")
        unassigned_list = list(unassigned)

        for cand in unassigned_list:
            dists = [dist_mat[cand, other] for other in unassigned_list]
            avg_d = sum(dists) / len(dists)
            if avg_d < best_avg_dist:
                best_avg_dist = avg_d
                best_medoid = cand

        # 归属到该类中 (距离 <= rmsd_threshold)
        members = [m for m in unassigned_list if dist_mat[best_medoid, m] <= rmsd_threshold]
        if not members:
            members = [best_medoid]

        clusters[cid] = sorted(members)
        medoids[cid] = best_medoid
        for m in members:
            unassigned.remove(m)
        cid += 1

    return {
        "matrix": dist_mat,
        "clusters": clusters,
        "medoids": medoids,
        "n_clusters": len(clusters),
    }
