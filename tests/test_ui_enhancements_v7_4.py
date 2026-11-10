"""
tests/test_ui_enhancements_v7_4.py - 验收测试：UI 排版、自定义砌块、交互时间线、选区序号与缩放适配
========================================================================================
"""
try:
    import pytest
except ImportError:
    pytest = None
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from molforge.domain.custom_fragments import (
    load_custom_fragments, add_custom_fragment, remove_custom_fragment
)
from molforge.domain.document import MoleculeDocument
from molforge.domain.ids import AtomId, BondId
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import AddAtomCommand, AddBondCommand, DeleteAtomCommand
from molforge.ui.theme import build_style


def test_custom_fragments_crud(tmp_path, monkeypatch):
    """测试自定义结构砌块的持久化增删改查。"""
    monkeypatch.setattr("molforge.domain.custom_fragments.data_dir", lambda: tmp_path)

    frags = load_custom_fragments()
    assert len(frags) >= 1  # 初始含有默认砌块

    # 添加新砌块
    ok = add_custom_fragment("测试咔唑", "c1ccc2c(c1)[nH]c1ccccc12", "测试描述")
    assert ok is True

    frags_after = load_custom_fragments()
    names = [f["name"] for f in frags_after]
    assert "测试咔唑" in names

    # 删除新砌块
    del_ok = remove_custom_fragment("测试咔唑")
    assert del_ok is True
    assert "测试咔唑" not in [f["name"] for f in load_custom_fragments()]


def test_command_bus_interactive_timeline():
    """测试命令总线历史栈与时间线回退/重做状态一致性。"""
    doc = MoleculeDocument(name="TestDoc")
    bus = CommandBus(doc)

    assert bus.history.can_undo is False
    assert bus.history.can_redo is False

    # 执行 3 个操作
    res1 = bus.execute(AddAtomCommand(6, 0.0, 0.0, 0.0))
    assert res1.success
    a1 = res1.data["atom_id"]

    res2 = bus.execute(AddAtomCommand(6, 1.5, 0.0, 0.0))
    assert res2.success
    a2 = res2.data["atom_id"]

    res3 = bus.execute(AddBondCommand(AtomId(a1), AtomId(a2), 1))
    assert res3.success

    assert bus.history.can_undo is True
    assert bus.history.undo_count == 3
    assert bus.history.can_redo is False

    # 模拟在时间线上点击跳回到第 1 步 (撤销 2 步)
    bus.undo()
    bus.undo()
    assert bus.history.undo_count == 1
    assert bus.history.can_redo is True
    assert bus.history.redo_count == 2
    assert doc.num_atoms == 1

    # 模拟在时间线上点击重做回第 3 步
    bus.redo()
    bus.redo()
    assert bus.history.undo_count == 3
    assert bus.history.can_redo is False
    assert doc.num_atoms == 2
    assert doc.num_bonds == 1


def test_theme_typography_customization():
    """测试主题样式表支持动态注入字体家族与字号。"""
    css_default = build_style("Dark Professional")
    assert "Microsoft YaHei UI" in css_default
    assert "font-size: 14px;" in css_default
    assert "QTableWidget" in css_default

    css_custom = build_style("Dark Professional", font_family="PingFang SC", font_size=16)
    assert "font-family: PingFang SC;" in css_custom
    assert "font-size: 16px;" in css_custom


def test_selected_atom_summary_math():
    """测试多原子选区序号排序与质心计算准确性。"""
    import numpy as np
    from molforge.domain.ids import AtomId

    doc = MoleculeDocument(name="CentroidTest")
    a1 = doc.topology.add_atom(6)
    a2 = doc.topology.add_atom(6)
    a3 = doc.topology.add_atom(8)
    coords = np.array([
        [0.0, 0.0, 0.0],
        [2.0, 0.0, 0.0],
        [1.0, 2.0, 0.0]
    ], dtype=np.float32)
    doc.coordinates.update_current_coords(coords)

    selected = [a3, a1, a2]  # 无序传入
    sorted_ids = sorted(selected, key=lambda a: a.value)
    assert [a.value + 1 for a in sorted_ids] == [1, 2, 3]

    selected_coords = [coords[a.value] for a in sorted_ids]
    centroid = np.mean(selected_coords, axis=0)
    assert np.allclose(centroid, [1.0, 2.0 / 3.0, 0.0])


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        class DummyMonkey:
            def setattr(self, target, val):
                parts = target.split('.')
                m = sys.modules[parts[0]]
                for p in parts[1:-1]:
                    m = getattr(m, p)
                setattr(m, parts[-1], val)
        test_custom_fragments_crud(Path(td), DummyMonkey())
    test_command_bus_interactive_timeline()
    test_theme_typography_customization()
    test_selected_atom_summary_math()
    print("All UI enhancements tests passed successfully!")

