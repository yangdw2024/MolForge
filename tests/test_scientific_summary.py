"""Counterexamples for honest spin, shape and bond summary information."""
import unittest

import numpy as np

from molforge.domain.chemical_summary import (
    analyze_geometry_shape,
    count_non_ring_single_bonds,
    resolve_spin_state,
)
from molforge.domain.document import MoleculeDocument
from molforge.io.rdkit_adapter import create_instant_caffeine_document


class ScientificSummaryTests(unittest.TestCase):
    def test_explicit_triplet_is_respected(self):
        doc = MoleculeDocument("oxygen")
        doc.topology.add_atom(8)
        doc.topology.add_atom(8)
        doc.properties["multiplicity"] = 3
        state = resolve_spin_state(doc)
        self.assertTrue(state.explicit)
        self.assertEqual((state.multiplicity, state.label), (3, "Triplet"))

    def test_unknown_even_electron_spin_is_not_asserted(self):
        doc = MoleculeDocument("oxygen-unknown")
        doc.topology.add_atom(8)
        doc.topology.add_atom(8)
        state = resolve_spin_state(doc)
        self.assertFalse(state.explicit)
        self.assertEqual(state.multiplicity, 1)
        self.assertIn("未指定", state.label)
        self.assertNotEqual(state.label, "Singlet")

    def test_linear_planar_and_nonplanar_are_not_point_groups(self):
        linear = analyze_geometry_shape([[0, 0, 0], [1, 0, 0], [2, 0, 0]])
        planar = analyze_geometry_shape([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]])
        methane = analyze_geometry_shape([
            [0, 0, 0], [1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]
        ])
        self.assertEqual(linear.kind, "linear")
        self.assertEqual(planar.kind, "planar")
        self.assertEqual(methane.kind, "nonplanar")
        for shape in (linear, planar, methane):
            self.assertEqual(shape.point_group, "未计算")

    def test_shape_is_rigid_rotation_invariant(self):
        coords = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0.2, 0.3, 0]], dtype=float)
        theta = np.pi / 2
        rotation = np.array([[1, 0, 0], [0, np.cos(theta), -np.sin(theta)], [0, np.sin(theta), np.cos(theta)]])
        before = analyze_geometry_shape(coords)
        after = analyze_geometry_shape(coords @ rotation.T + np.array([4, -2, 8]))
        self.assertEqual(before.kind, after.kind)
        self.assertAlmostEqual(before.thickness_rms, after.thickness_rms, places=6)

    def test_custom_bond_metric_is_explicit_and_ring_aware(self):
        caffeine = create_instant_caffeine_document()
        self.assertEqual(count_non_ring_single_bonds(caffeine.topology), 3)
        doc = MoleculeDocument("isolated-aromatic-bond")
        a = doc.topology.add_atom(6, aromatic=True)
        b = doc.topology.add_atom(6, aromatic=True)
        bid = doc.topology.add_bond(a, b, order=4, aromatic=True)
        self.assertFalse(doc.topology.is_bond_in_ring(bid))
        self.assertEqual(count_non_ring_single_bonds(doc.topology), 0)


if __name__ == "__main__":
    unittest.main()
