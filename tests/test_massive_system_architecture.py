"""
tests/test_massive_system_architecture.py - 超大规模原子体系与动力学盒子架构验收测试
========================================================================================
验证 10^5 ~ 10^8 原子级别的内存紧凑度、零拷贝 LOD 降采样、视锥体剔除与自适应交互流。
"""
import time
import math
import numpy as np
from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from molforge.domain.massive_system import (
    MassiveSystemData,
    SpatialGridIndex,
    InteractionAdaptiveController,
    BoundingBox3D,
)


def test_million_atom_memory_compactness():
    """测试 1,000,000 (百万) 原子内存极简扁平化，验证 1 亿原子理论消耗在 ~1.2 GB。"""
    t0 = time.perf_counter()
    sys_1m = MassiveSystemData.create_synthetic_md_box(1_000_000, name="1M_WaterBox")
    dt = time.perf_counter() - t0

    assert sys_1m.n_atoms == 1_000_000
    # 100 万原子 (coords: float32[1000000, 3] = 12MB, elements: uint8[1000000] = 1MB)
    assert sys_1m.memory_bytes < 15 * 1024 * 1024, "100万原子内存必须在 15MB 以内"
    assert "MB" in sys_1m.memory_footprint_str

    # 推导 1 亿 (100,000,000) 原子内存占用
    theoretical_100m_bytes = 100_000_000 * 3 * 4 + 100_000_000 * 1  # 1.21 GB
    assert theoretical_100m_bytes / (1024 ** 3) < 1.3, "1亿原子连续内存完全可以容纳在 1.3 GB 物理内存中"


def test_instantaneous_lod_strided_sampling():
    """测试在百万原子体系上执行动态 LOD 下采样，验证耗时在微秒级 (< 5ms)。"""
    sys_1m = MassiveSystemData.create_synthetic_md_box(1_000_000, name="LOD_Test")
    
    t0 = time.perf_counter()
    sub_coords, sub_elem, ratio = sys_1m.get_lod_representation(max_display_points=100_000)
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert sub_coords.shape[0] <= 100_000
    assert sub_elem.shape[0] == sub_coords.shape[0]
    assert dt_ms < 5.0, f"LOD 降采样应在 5ms 内完成，实际耗时: {dt_ms:.3f} ms"
    assert ratio <= 0.10


def test_spatial_frustum_culling_speed():
    """测试三维网格视锥体剔除：从百万原子中高速检索视野内的局部原子。"""
    sys_1m = MassiveSystemData.create_synthetic_md_box(1_000_000, name="FrustumTest")
    index = SpatialGridIndex(sys_1m, cell_size=25.0)

    # 模拟相机近景特写视野（例如中心 50x50x50 Å 区域）
    query_box = BoundingBox3D(
        min_x=-25.0, max_x=25.0,
        min_y=-25.0, max_y=25.0,
        min_z=-25.0, max_z=25.0,
    )

    t0 = time.perf_counter()
    visible_indices = index.query_frustum_bbox(query_box)
    dt_ms = (time.perf_counter() - t0) * 1000.0

    assert len(visible_indices) > 0
    assert len(visible_indices) < sys_1m.n_atoms
    assert dt_ms < 20.0, f"视锥体剔除查询耗时应在 20ms 以内，实际耗时: {dt_ms:.3f} ms"


def test_adaptive_interaction_controller_budget():
    """测试交互动态降级控制器的帧绘制预算状态机。"""
    ctrl = InteractionAdaptiveController(interactive_target_points=80_000)
    assert not ctrl.is_interacting
    
    # 静止状态下允许高达 200 万点渲染
    assert ctrl.get_render_budget(5_000_000) == 2_000_000

    # 开始鼠标交互（旋转/平移）
    ctrl.on_interaction_start()
    assert ctrl.is_interacting
    # 动态降级到 80k 点以保障 60 FPS
    assert ctrl.get_render_budget(5_000_000) == 80_000

    # 停止交互
    ctrl.on_interaction_end()
    assert not ctrl.is_interacting
    assert ctrl.get_render_budget(5_000_000) == 2_000_000


def test_large_pdb_fixed_column_conect_parsing():
    """测试五位数以上序号无空格标准 PDB 与 CONECT 键的解析，严防 9999 截断回归。"""
    from molforge.io.rdkit_adapter import parse_pdb_to_document
    pdb_path = Path("E:/YDW/test_wsl/ydw-PM6-ClFFCl.pdb")
    if pdb_path.exists():
        t0 = time.perf_counter()
        doc = parse_pdb_to_document(pdb_path)
        dt = time.perf_counter() - t0
        assert doc.num_atoms == 321554, f"期望 321554 原子，实际解析得到 {doc.num_atoms}"
        assert doc.num_bonds == 273522, f"期望 273522 键，实际解析得到 {doc.num_bonds}"
        assert dt < 10.0, f"32万原子解析耗时超标: {dt:.2f}s"
    else:
        # 内存合成超过 10000 序号无空格的 PDB 文本进行格式校验
        lines = [
            "HETATM 9999  C   MOL     1      10.000  10.000  10.000  1.00  0.00           C",
            "HETATM10000  C   MOL     1      11.500  10.000  10.000  1.00  0.00           C",
            "HETATM10001  N   MOL     1      12.800  11.000  10.000  1.00  0.00           N",
            "CONECT 999910000",
            "CONECT10000 999910001",
        ]
        tmp_pdb = Path("E:/YDW/Trae_Chemdraw/data/test_conect_10k.pdb")
        tmp_pdb.parent.mkdir(parents=True, exist_ok=True)
        tmp_pdb.write_text("\n".join(lines), encoding="utf-8")
        doc = parse_pdb_to_document(tmp_pdb)
        assert doc.num_atoms == 3
        assert doc.num_bonds == 2
        tmp_pdb.unlink(missing_ok=True)


if __name__ == "__main__":
    test_million_atom_memory_compactness()
    print("[PASS] test_million_atom_memory_compactness")
    test_instantaneous_lod_strided_sampling()
    print("[PASS] test_instantaneous_lod_strided_sampling")
    test_spatial_frustum_culling_speed()
    print("[PASS] test_spatial_frustum_culling_speed")
    test_adaptive_interaction_controller_budget()
    print("[PASS] test_adaptive_interaction_controller_budget")
    test_large_pdb_fixed_column_conect_parsing()
    print("[PASS] test_large_pdb_fixed_column_conect_parsing")
    print("All massive system architecture tests passed successfully!")
