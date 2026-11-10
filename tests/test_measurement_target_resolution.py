"""
tests/test_measurement_target_resolution.py - P0 测量顺序、双邻键测角与冻结记录失效测试
"""
from __future__ import annotations

import itertools
import math
import unittest
import numpy as np

from molforge.domain.document import MoleculeDocument
from molforge.application.measurement import angle, MeasurementService
from molforge.application.measurement_targets import MeasurementTargetResolver
from molforge.application.selection import SelectionService


class TestMeasurementTargetResolution(unittest.TestCase):
    def _make_110_deg_chain_doc(self) -> tuple[MoleculeDocument, list]:
        doc = MoleculeDocument("chain_110")
        a_i = doc.topology.add_atom(6)
        a_j = doc.topology.add_atom(6)  # 中心顶点 j
        a_k = doc.topology.add_atom(6)
        b1 = doc.topology.add_bond(a_i, a_j, 1)
        b2 = doc.topology.add_bond(a_j, a_k, 1)

        rad = math.radians(110.0)
        coords = np.array([
            [1.50, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [1.50 * math.cos(rad), 1.50 * math.sin(rad), 0.0],
        ], dtype=np.float32)
        store = doc.ensure_coordinates()
        store._frames.clear()
        store._current_index = -1
        store.add_frame(coords, source="init")
        return doc, [a_i, a_j, a_k, b1, b2]

    def test_any_selection_order_of_three_bonded_atoms_finds_true_110_vertex(self):
        """无论用户以 3! = 6 种顺序中的哪一种点击 i, j, k，拓扑解析器都必须识别 j 为中心顶点并得出 110°，绝不出现 35°！"""
        doc, (a_i, a_j, a_k, _, _) = self._make_110_deg_chain_doc()
        coords = doc.coordinates.current.coords
        _, id2idx = doc.topology.atom_index_map()

        for perm in itertools.permutations([a_i, a_j, a_k], 3):
            sel = SelectionService()
            for aid in perm:
                sel.select_atom(aid, add=True)
            target = MeasurementTargetResolver.resolve(doc, sel)
            self.assertEqual(target.kind, "angle")
            self.assertEqual(target.atoms[1], a_j)
            val, ok, _ = angle(coords, id2idx[target.atoms[0]], id2idx[target.atoms[1]], id2idx[target.atoms[2]])
            self.assertTrue(ok)
            self.assertAlmostEqual(val, 110.0, places=3)

    def test_two_adjacent_bonds_resolve_angle_correctly(self):
        """选中两条共享一个顶点的相邻化学键时，自动以公共原子为顶点测出 110°（修复 ISSUES_AND_TODO 36.93° 缺陷）。"""
        doc, (a_i, a_j, a_k, b1, b2) = self._make_110_deg_chain_doc()
        coords = doc.coordinates.current.coords
        _, id2idx = doc.topology.atom_index_map()

        sel = SelectionService()
        sel.select_bond(b1, add=False)
        sel.select_bond(b2, add=True)
        target = MeasurementTargetResolver.resolve(doc, sel)
        self.assertEqual(target.kind, "angle")
        self.assertEqual(target.atoms[1], a_j)
        val, ok, _ = angle(coords, id2idx[target.atoms[0]], id2idx[target.atoms[1]], id2idx[target.atoms[2]])
        self.assertTrue(ok)
        self.assertAlmostEqual(val, 110.0, places=3)

    def test_three_membered_ring_detects_vertex_ambiguity(self):
        """三元环的三个顶点两两成键，选中三个原子时必须返回 ambiguous 提示，不隐式乱猜顶点。"""
        doc = MoleculeDocument("cyclopropane_ring")
        a1 = doc.topology.add_atom(6)
        a2 = doc.topology.add_atom(6)
        a3 = doc.topology.add_atom(6)
        doc.topology.add_bond(a1, a2, 1)
        doc.topology.add_bond(a2, a3, 1)
        doc.topology.add_bond(a3, a1, 1)

        sel = SelectionService()
        for a in (a1, a2, a3):
            sel.select_atom(a, add=True)
        target = MeasurementTargetResolver.resolve(doc, sel)
        self.assertEqual(target.kind, "ambiguous")
        self.assertIn("三元环存在顶点歧义", target.diagnostic)

    def test_frozen_measurement_cleanup_after_delete_no_exception(self):
        """修复 S03：MeasurementService.cleanup_after_delete 替换不可变记录而不触发 FrozenInstanceError。"""
        doc, (a_i, a_j, a_k, _, _) = self._make_110_deg_chain_doc()
        coords = doc.coordinates.current.coords
        _, id2idx = doc.topology.atom_index_map()

        svc = MeasurementService()
        m = svc.measure_angle(coords, (a_i, a_j, a_k), id2idx)
        self.assertTrue(m.valid)

        # 删除其中一个原子，不得抛出 FrozenInstanceError
        svc.cleanup_after_delete({a_k})
        self.assertFalse(svc.measurements[0].valid)
        self.assertIn("已删除", svc.measurements[0].diagnostic)

    def test_single_bond_selection_resolves_canonical_dihedral(self):
        """选中一条中心化学键时，自动推导主二面角原子链 i-j-k-l 并支持直接读取与修改。"""
        doc = MoleculeDocument("butane_chain")
        a0 = doc.topology.add_atom(6)
        a1 = doc.topology.add_atom(6)
        a2 = doc.topology.add_atom(6)
        a3 = doc.topology.add_atom(6)
        b01 = doc.topology.add_bond(a0, a1, 1)
        b12 = doc.topology.add_bond(a1, a2, 1) # 中心单键
        b23 = doc.topology.add_bond(a2, a3, 1)

        sel = SelectionService()
        sel.select_bond(b12, add=False)
        target = MeasurementTargetResolver.resolve(doc, sel)
        self.assertEqual(target.kind, "distance")
        self.assertIsNotNone(target.canonical_dihedral_atoms)
        self.assertEqual(target.canonical_dihedral_atoms, (a0, a1, a2, a3))
        # 验证 1-based 显示标签
        self.assertEqual(target.label, f"#{a1.value + 1}–#{a2.value + 1}")

    def test_four_atom_dihedral_permutations_resolve_to_contiguous_bonded_chain(self):
        """无论用户以 4! = 24 种顺序中的哪一种点击二面角 4 原子，解析器都必须将其排列为相邻成键的连通链，绝不允许对角线跳跃。"""
        doc = MoleculeDocument("butane_chain")
        a0 = doc.topology.add_atom(6)
        a1 = doc.topology.add_atom(6)
        a2 = doc.topology.add_atom(6)
        a3 = doc.topology.add_atom(6)
        doc.topology.add_bond(a0, a1, 1)
        doc.topology.add_bond(a1, a2, 1)
        doc.topology.add_bond(a2, a3, 1)

        for perm in itertools.permutations([a0, a1, a2, a3]):
            sel = SelectionService()
            for aid in perm:
                sel.select_atom(aid, add=True)
            target = MeasurementTargetResolver.resolve(doc, sel)
            self.assertEqual(target.kind, "dihedral")
            chain = target.atoms
            self.assertEqual(len(chain), 4)
            # 验证相邻两两必须在拓扑中真实成键
            for k in range(3):
                self.assertTrue(
                    MeasurementTargetResolver._are_bonded(doc, chain[k], chain[k + 1]),
                    f"原子 {chain[k]} 与 {chain[k+1]} 未成键，发生了空间斜穿跳跃！",
                )

    def test_vtk_backend_recovers_topological_chain_and_avoids_diagonal_chords(self):
        """验证 VtkRendererBackend 在接收乱序原子列表时，能根据拓扑关系自动恢复连通路径，不产生对角线连线。"""
        from molforge.rendering.vtk_backend import VtkRendererBackend
        backend = VtkRendererBackend()
        # 构筑 4 个原子的连通链 0 - 1 - 2 - 3
        backend._bonds = [(0, 1, 1), (1, 2, 1), (2, 3, 1)]
        scrambled = [1, 3, 0, 2] # 乱序排列
        resolved = backend._resolve_topological_chain(scrambled)
        self.assertEqual(len(resolved), 4)
        for k in range(3):
            u, v = resolved[k], resolved[k + 1]
            is_bonded = any((u == b[0] and v == b[1]) or (u == b[1] and v == b[0]) for b in backend._bonds)
            self.assertTrue(is_bonded, f"VTK 测量线在索引 {u} 与 {v} 之间斜穿空间！")
