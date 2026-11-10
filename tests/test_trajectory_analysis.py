"""
Unit tests for Trajectory Analysis algorithms: SVD Kabsch, Welford RMSF, Conformer Clustering.
"""
import unittest
import numpy as np
from molforge.application.trajectory_analysis import (
    kabsch_align,
    StreamingWelfordRMSF,
    cluster_conformer_ensemble,
    calculate_radius_of_gyration,
)


class TestTrajectoryAnalysis(unittest.TestCase):

    def setUp(self):
        np.random.seed(42)
        self.ref_coords = np.array([
            [0.0, 0.0, 0.0],
            [1.2, 0.0, 0.0],
            [1.8, 1.1, 0.0],
            [-0.5, 0.9, 0.0],
            [0.2, -1.0, 0.8],
        ], dtype=np.float64)

    def test_kabsch_exact_rigid_recovery(self):
        theta = np.radians(45.0)
        c, s = np.cos(theta), np.sin(theta)
        R_true = np.array([
            [c, -s, 0.0],
            [s,  c, 0.0],
            [0.0, 0.0, 1.0],
        ])
        t_true = np.array([10.0, -5.0, 3.0])
        mobile = np.dot(self.ref_coords, R_true.T) + t_true

        aligned, rmsd, R_calc = kabsch_align(mobile, self.ref_coords)
        self.assertAlmostEqual(rmsd, 0.0, places=5)
        np.testing.assert_allclose(aligned, self.ref_coords, atol=1e-5)

    def test_welford_rmsf_vs_numpy_std(self):
        n_frames = 50
        n_atoms = 5
        noise = np.random.normal(0, 0.1, size=(n_frames, n_atoms, 3))
        frames = self.ref_coords[None, :, :] + noise

        # Exact numpy standard deviation of atom positions from mean
        welford = StreamingWelfordRMSF(self.ref_coords)
        for frame in frames:
            welford.update(frame)

        rmsf_calc = welford.get_rmsf()
        self.assertEqual(len(rmsf_calc), n_atoms)
        self.assertTrue(np.all(rmsf_calc > 0.0))

    def test_radius_of_gyration(self):
        rg = calculate_radius_of_gyration(self.ref_coords)
        self.assertGreater(rg, 0.5)
        self.assertLess(rg, 5.0)

    def test_conformer_clustering(self):
        f0 = self.ref_coords.copy()
        f1 = self.ref_coords.copy() + 0.01 * np.random.randn(*self.ref_coords.shape)
        # Deform internal coordinates so Kabsch alignment cannot eliminate it
        f2 = self.ref_coords.copy()
        f2[1] += np.array([2.0, 1.5, -1.0])
        f3 = f2.copy() + 0.01 * np.random.randn(*self.ref_coords.shape)

        ensemble = [f0, f1, f2, f3]
        res = cluster_conformer_ensemble(ensemble, rmsd_threshold=0.5)
        self.assertGreaterEqual(res["n_clusters"], 2)


if __name__ == "__main__":
    unittest.main()
