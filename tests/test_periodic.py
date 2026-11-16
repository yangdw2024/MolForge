"""Unit-cell, minimum-image and CRYST1 persistence counterexamples."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from molforge.application.measurement import angle, dihedral, distance
from molforge.domain.document import MoleculeDocument
from molforge.domain.periodic import UnitCell, cell_from_document, minimum_image_delta
from molforge.io.mforge_storage import load_mforge, save_mforge
from molforge.io.rdkit_adapter import export_document_to_pdb, parse_pdb_to_document


class PeriodicTests(unittest.TestCase):
    def setUp(self):
        self.cell = UnitCell(10, 11, 12, 90, 90, 90, "P 1")

    def test_orthorhombic_minimum_image_distance(self):
        coords = np.array([[0.05, 0, 0], [9.95, 0, 0]], dtype=float)
        self.assertAlmostEqual(distance(coords, 0, 1), 9.9)
        self.assertAlmostEqual(distance(coords, 0, 1, self.cell), 0.1)
        np.testing.assert_allclose(minimum_image_delta(coords[0] - coords[1], self.cell), [0.1, 0, 0], atol=1e-8)

    def test_periodic_angle_and_dihedral(self):
        angular = np.array([[9.9, 0, 0], [0, 0, 0], [0, 1, 0]], dtype=float)
        value, valid, _ = angle(angular, 0, 1, 2, self.cell)
        self.assertTrue(valid)
        self.assertAlmostEqual(value, 90.0)

        base = np.array([[0, 0, 0], [1, 0, 0], [1.5, 1, 0], [2.0, 1, 1]], dtype=float)
        shifted = base.copy()
        shifted[2] += [10, 0, 0]
        shifted[3] += [10, 0, 0]
        expected = dihedral(base, 0, 1, 2, 3)[0]
        actual = dihedral(shifted, 0, 1, 2, 3, self.cell)[0]
        self.assertAlmostEqual(actual, expected)

    def test_triclinic_fractional_roundtrip(self):
        cell = UnitCell(8, 9, 10, 80, 75, 70, "P -1")
        cart = np.array([[1.2, 3.4, 5.6], [-2.0, 0.5, 1.0]])
        np.testing.assert_allclose(cell.to_cartesian(cell.to_fractional(cart)), cart, atol=1e-8)
        self.assertGreater(cell.volume, 0)

    def _document(self):
        doc = MoleculeDocument("periodic-two-atoms")
        doc.topology.add_atom(6)
        doc.topology.add_atom(6)
        doc.ensure_coordinates().add_frame(np.array([[0.05, 0, 0], [9.95, 0, 0]], dtype=np.float32))
        doc.properties["cryst1"] = self.cell.to_dict()
        doc.properties["box_dimensions"] = [10, 11, 12]
        doc.properties["box_angles"] = [90, 90, 90]
        doc.properties["multiplicity"] = 3
        atoms = list(doc.topology.atom_ids)
        doc.topology.get_atom(atoms[0]).formal_charge = 1
        doc.topology.get_atom(atoms[1]).formal_charge = -1
        doc.topology.get_atom(atoms[0]).properties["frozen"] = True
        doc.coords_2d[atoms[0]] = (1.25, -2.5)
        return doc

    def test_cryst1_pdb_and_mforge_roundtrip(self):
        doc = self._document()
        self.assertIsNotNone(cell_from_document(doc))
        text = export_document_to_pdb(doc)
        self.assertIn("CRYST1", text)
        with tempfile.TemporaryDirectory() as td:
            pdb = Path(td) / "cell.pdb"
            pdb.write_text(text, encoding="utf-8")
            restored = parse_pdb_to_document(pdb)
            cell = cell_from_document(restored)
            self.assertEqual((cell.a, cell.b, cell.c, cell.space_group), (10, 11, 12, "P 1"))

            project = Path(td) / "cell.mforge"
            save_mforge(doc, project)
            restored_project = load_mforge(project)
            self.assertEqual(cell_from_document(restored_project).to_dict(), self.cell.to_dict())
            self.assertEqual(restored_project.properties["multiplicity"], 3)
            restored_atoms = list(restored_project.topology.atom_ids)
            self.assertEqual(restored_project.topology.get_atom(restored_atoms[0]).formal_charge, 1)
            self.assertEqual(restored_project.topology.get_atom(restored_atoms[1]).formal_charge, -1)
            self.assertTrue(restored_project.topology.get_atom(restored_atoms[0]).properties["frozen"])
            self.assertEqual(restored_project.coords_2d[restored_atoms[0]], (1.25, -2.5))

    def test_invalid_cell_is_rejected(self):
        with self.assertRaises(ValueError):
            UnitCell(10, 10, 10, 0, 90, 90)
        with self.assertRaises(ValueError):
            UnitCell(10, 10, 10, 120, 120, 120)


if __name__ == "__main__":
    unittest.main()
