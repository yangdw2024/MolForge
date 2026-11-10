"""
tests/test_internal_coordinate_commands.py - P0 键角与二面角刚体旋转事务命令与环约束测试
"""
from __future__ import annotations

import math
import unittest
import numpy as np

from molforge.domain.document import MoleculeDocument
from molforge.application.command_bus import CommandBus
from molforge.application.internal_coordinates import ModifyAngle3DCommand, ModifyDihedral3DCommand
from molforge.application.measurement import distance, angle, dihedral


class TestInternalCoordinateCommands(unittest.TestCase):
    def _make_butane_like_chain(self) -> tuple[MoleculeDocument, list]:
        """构造 5 原子链 C0 - C1 - C2 - C3 - C4 以验证随动基团刚体旋转与键长保持。"""
        doc = MoleculeDocument("pentane_backbone")
        atoms = [doc.topology.add_atom(6) for _ in range(5)]
        for i in range(4):
            doc.topology.add_bond(atoms[i], atoms[i + 1], 1)

        coords = np.array([
            [-1.50,  0.80,  0.00],
            [ 0.00,  0.00,  0.00],
            [ 1.54,  0.00,  0.00],
            [ 2.10,  1.42,  0.00],
            [ 3.62,  1.50,  0.50],
        ], dtype=np.float32)
        store = doc.ensure_coordinates()
        store._frames.clear()
        store._current_index = -1
        store.add_frame(coords, source="init")
        return doc, atoms

    def test_modify_angle_rotates_entire_subgraph_and_undoes_cleanly(self):
        doc, atoms = self._make_butane_like_chain()
        bus = CommandBus(doc)
        coords_before = doc.coordinates.current.coords.copy()
        d_23_before = distance(coords_before, 2, 3)
        d_34_before = distance(coords_before, 3, 4)

        cmd = ModifyAngle3DCommand(atoms[1], atoms[2], atoms[3], target_angle_deg=115.0)
        res = bus.execute(cmd)
        self.assertTrue(res.success, msg=res.message)

        coords_after = doc.coordinates.current.coords
        ang_after, ok, _ = angle(coords_after, 1, 2, 3)
        self.assertTrue(ok)
        self.assertAlmostEqual(ang_after, 115.0, places=2)

        # 随动基团 C2-C3 与 C3-C4 的键长必须严格保持不变！
        self.assertAlmostEqual(distance(coords_after, 2, 3), d_23_before, places=4)
        self.assertAlmostEqual(distance(coords_after, 3, 4), d_34_before, places=4)

        # 单次 Ctrl+Z 撤销恢复原始坐标
        bus.undo()
        np.testing.assert_allclose(doc.coordinates.current.coords, coords_before, atol=1e-6)

    def test_modify_dihedral_positive_negative_and_180_and_undo(self):
        doc, atoms = self._make_butane_like_chain()
        bus = CommandBus(doc)
        coords_before = doc.coordinates.current.coords.copy()
        d_34_before = distance(coords_before, 3, 4)

        for target_dih in (60.0, -60.0, 179.0):
            cmd = ModifyDihedral3DCommand(atoms[0], atoms[1], atoms[2], atoms[3], target_dihedral_deg=target_dih)
            res = bus.execute(cmd)
            self.assertTrue(res.success, msg=res.message)
            coords_now = doc.coordinates.current.coords
            dih_now, ok, _ = dihedral(coords_now, 0, 1, 2, 3)
            self.assertTrue(ok)
            err = ((dih_now - target_dih + 180.0) % 360.0) - 180.0
            self.assertLess(abs(err), 0.05)
            # 远端 C3-C4 随动基团键长严格保持
            self.assertAlmostEqual(distance(coords_now, 3, 4), d_34_before, places=4)

        # 连续三次 undo 回到初始状态
        bus.undo()
        bus.undo()
        bus.undo()
        np.testing.assert_allclose(doc.coordinates.current.coords, coords_before, atol=1e-6)

    def test_ring_bond_dihedral_torsion_is_explicitly_rejected(self):
        doc, atoms = self._make_butane_like_chain()
        # 将首尾相连构成五元闭环
        doc.topology.add_bond(atoms[4], atoms[0], 1)
        bus = CommandBus(doc)

        cmd = ModifyDihedral3DCommand(atoms[0], atoms[1], atoms[2], atoms[3], target_dihedral_deg=45.0)
        res = bus.execute(cmd)
        self.assertFalse(res.success)
        self.assertIn("环系", res.message)
