"""
Unit tests for Direction 2: 2D ⇄ 3D Bidirectional Live Synchronization & Projection.
Tests:
  1. GenerateConformation3DCommand (ETKDGv3 + UFF/MMFF94 + NumPy fallback + Undo/Redo)
  2. Project3DTo2DCommand (Camera view projection + SVD principal plane + CoordGen + 1.50 Å normalization + Undo/Redo)
  3. Physical plausibility checks (bond lengths, planarity, centering)
"""
import unittest
import numpy as np
from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import (
    GenerateConformation3DCommand,
    Project3DTo2DCommand,
    AddAtomCommand,
    AddBondCommand,
)


class TestBidirectionalSync(unittest.TestCase):

    def setUp(self):
        self.doc = create_instant_caffeine_document()
        self.bus = CommandBus(self.doc)

    def test_generate_3d_conformation_etkdg(self):
        # 1. Zero out 3D coordinates to simulate a purely 2D drawn structure
        n = self.doc.num_atoms
        self.doc.coordinates.update_current_coords(np.zeros((n, 3), dtype=np.float32))

        # 2. Run ETKDG conformation generation
        cmd = GenerateConformation3DCommand(optimize_iters=100)
        res = self.bus.execute(cmd)
        self.assertTrue(res.success)
        self.assertTrue(res.changed)

        coords_3d = self.doc.coordinates.current.coords
        # Check that coordinates are non-trivial and centered near (0,0,0)
        self.assertGreater(float(np.ptp(coords_3d)), 1.5)
        np.testing.assert_allclose(coords_3d.mean(axis=0), [0.0, 0.0, 0.0], atol=1e-3)

        # 3. Check bond lengths: all connected bonds should be reasonable (1.0 ~ 2.0 Å)
        atom_ids, id_to_idx = self.doc.topology.atom_index_map()
        for bid in self.doc.topology.bond_ids:
            b = self.doc.topology.get_bond(bid)
            i, j = id_to_idx[b.begin], id_to_idx[b.end]
            dist = float(np.linalg.norm(coords_3d[i] - coords_3d[j]))
            self.assertGreater(dist, 1.0, f"Bond {bid} too short: {dist}")
            self.assertLess(dist, 2.0, f"Bond {bid} too long: {dist}")

        # 4. Test Undo & Redo
        undo_res = self.bus.undo()
        self.assertTrue(undo_res.success)
        np.testing.assert_allclose(self.doc.coordinates.current.coords, np.zeros((n, 3)), atol=1e-5)

        redo_res = self.bus.redo()
        self.assertTrue(redo_res.success)
        np.testing.assert_allclose(self.doc.coordinates.current.coords, coords_3d, atol=1e-5)

    def test_project_3d_to_2d_svd(self):
        # 1. Clear 2D coords
        old_2d = dict(self.doc.coords_2d)
        self.doc.coords_2d = {}

        # 2. Project from 3D to 2D
        cmd = Project3DTo2DCommand()
        res = self.bus.execute(cmd)
        self.assertTrue(res.success)
        self.assertTrue(res.changed)

        self.assertEqual(len(self.doc.coords_2d), self.doc.num_atoms)

        # 3. Verify bond lengths in 2D are normalized near ~1.50 Å (ChemDraw standard)
        atom_ids, id_to_idx = self.doc.topology.atom_index_map()
        lengths = []
        for bid in self.doc.topology.bond_ids:
            b = self.doc.topology.get_bond(bid)
            p1 = np.array(self.doc.coords_2d[b.begin])
            p2 = np.array(self.doc.coords_2d[b.end])
            lengths.append(float(np.linalg.norm(p1 - p2)))

        median_len = float(np.median(lengths))
        self.assertAlmostEqual(median_len, 1.50, delta=0.25)

        # 4. Test Undo
        self.bus.undo()
        self.assertEqual(len(self.doc.coords_2d), 0)

    def test_project_3d_to_2d_camera_basis(self):
        # Project using a custom camera basis: looking along Z, X is right, Y is up
        cam_right = np.array([1.0, 0.0, 0.0])
        cam_up = np.array([0.0, 1.0, 0.0])

        cmd = Project3DTo2DCommand(camera_right=cam_right, camera_up=cam_up)
        res = self.bus.execute(cmd)
        self.assertTrue(res.success)

        # Atoms should be populated
        self.assertEqual(len(self.doc.coords_2d), self.doc.num_atoms)
        atom_ids, _ = self.doc.topology.atom_index_map()
        c2d_arr = np.array([self.doc.coords_2d[a] for a in atom_ids])
        # Centered around (0,0)
        np.testing.assert_allclose(c2d_arr.mean(axis=0), [0.0, 0.0], atol=1e-3)

    def test_project_3d_to_2d_coordgen(self):
        cmd = Project3DTo2DCommand(use_coordgen=True)
        res = self.bus.execute(cmd)
        self.assertTrue(res.success)
        self.assertEqual(len(self.doc.coords_2d), self.doc.num_atoms)


if __name__ == "__main__":
    unittest.main()
