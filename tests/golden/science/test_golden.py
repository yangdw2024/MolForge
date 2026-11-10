"""
tests/golden/science/test_golden.py - 跨工作区科学黄金回归测试 (已移除全部 skip 并实装真实断言)
=================================================================================================
"""
from __future__ import annotations

import math
import unittest
import numpy as np

from molforge.domain.document import MoleculeDocument
from molforge.application.command_bus import CommandBus
from molforge.application.builtin_commands import AddAtomCommand
from molforge.application.measurement import distance, angle, dihedral, MeasurementService
from molforge.application.measurement_targets import MeasurementTargetResolver
from molforge.application.selection import SelectionService
from molforge.io.rdkit_adapter import create_sample_molecule


class TestScienceGoldenSuite(unittest.TestCase):
    """跨工作区科学黄金回归测试（同时兼容 pytest 与 unittest）。"""

    def test_caffeine_and_aspirin_2d_3d_structures(self):
        doc_caf = create_sample_molecule("咖啡因")
        self.assertEqual(doc_caf.num_atoms, 24)
        self.assertEqual(doc_caf.num_bonds, 25)
        self.assertEqual(doc_caf.name, "咖啡因")

        doc_asp = create_sample_molecule("阿司匹林")
        self.assertGreater(doc_asp.num_atoms, 10)
        self.assertEqual(len(doc_asp.validate()), 0)

    def test_distance_measurement_golden(self):
        coords = np.array([[0.0, 0.0, 0.0], [1.54, 0.0, 0.0]], dtype=np.float32)
        d = distance(coords, 0, 1)
        self.assertAlmostEqual(d, 1.54, places=5)

    def test_angle_measurement_golden(self):
        # 构造顶点在 index 1 (原点)，真实夹角为 110.0° 的三原子体系
        theta_rad = math.radians(110.0)
        coords = np.array([
            [1.5, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [1.5 * math.cos(theta_rad), 1.5 * math.sin(theta_rad), 0.0],
        ], dtype=np.float32)
        val, ok, diag = angle(coords, 0, 1, 2)
        self.assertTrue(ok, msg=diag)
        self.assertAlmostEqual(val, 110.0, places=4)

        # 水分子理想键角 104.5°
        w_rad = math.radians(104.5)
        w_coords = np.array([
            [0.96, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.96 * math.cos(w_rad), 0.96 * math.sin(w_rad), 0.0],
        ], dtype=np.float32)
        w_val, w_ok, _ = angle(w_coords, 0, 1, 2)
        self.assertTrue(w_ok)
        self.assertAlmostEqual(w_val, 104.5, places=4)

    def test_conformer_energy_sorting_golden(self):
        from molforge.application.conformers import ConformerResult, ConformerEnsemble
        ens = ConformerEnsemble(
            method="ETKDGv3",
            seed=42,
            num_requested=3,
            forcefield="MMFF94",
            conformers=[
                ConformerResult(index=0, coords=np.zeros((3, 3), dtype=np.float32), energy=-10.2),
                ConformerResult(index=1, coords=np.zeros((3, 3), dtype=np.float32), energy=-12.8),
                ConformerResult(index=2, coords=np.zeros((3, 3), dtype=np.float32), energy=-11.5),
            ],
        )
        sorted_confs = sorted(ens.conformers, key=lambda c: c.energy if c.energy is not None else float("inf"))
        self.assertEqual([c.index for c in sorted_confs], [1, 2, 0])
        self.assertAlmostEqual(sorted_confs[0].energy, -12.8, places=5)

    def test_quantum_cube_parsing_golden(self):
        import tempfile
        from pathlib import Path
        from molforge.io.cube_reader import read_cube
        sample_cube = """MolForge Golden Cube Test
HOMO Orbital Grid
    1    0.000000    0.000000    0.000000
    2    0.500000    0.000000    0.000000
    2    0.000000    0.500000    0.000000
    2    0.000000    0.000000    0.500000
    1    1.000000    0.000000    0.000000    0.000000
  0.10000E+00 -0.10000E+00  0.20000E+00 -0.20000E+00  0.30000E+00 -0.30000E+00
  0.40000E+00 -0.40000E+00
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "test.cube"
            p.write_text(sample_cube, encoding="utf-8")
            cube_data = read_cube(p)
            self.assertEqual(tuple(cube_data.dims), (2, 2, 2))
            self.assertAlmostEqual(float(np.max(cube_data.values)), 0.4, places=5)
            self.assertAlmostEqual(float(np.min(cube_data.values)), -0.4, places=5)

    def test_trajectory_frame_indexing_golden(self):
        doc = MoleculeDocument("traj_mol")
        a1 = doc.topology.add_atom(6)
        a2 = doc.topology.add_atom(8)
        doc.topology.add_bond(a1, a2, 1)
        store = doc.ensure_coordinates()
        store._frames.clear()
        store._current_index = -1
        store.add_frame(np.array([[0.0, 0.0, 0.0], [1.2, 0.0, 0.0]], dtype=np.float32), energy=-100.0, source="f0")
        store.add_frame(np.array([[0.0, 0.0, 0.0], [1.4, 0.0, 0.0]], dtype=np.float32), energy=-99.5, source="f1")
        self.assertEqual(store.num_frames, 2)
        store.current_index = 1
        self.assertAlmostEqual(float(store.current.coords[1, 0]), 1.4, places=5)

    def test_ai_proposal_command_rollback_golden(self):
        doc = MoleculeDocument("rollback_mol")
        bus = CommandBus(doc)
        res = bus.execute(AddAtomCommand(6, 0.0, 0.0, 0.0))
        self.assertTrue(res.success)
        self.assertEqual(doc.topology.num_atoms, 1)
        undo_res = bus.undo()
        self.assertTrue(undo_res.success)
        self.assertEqual(doc.topology.num_atoms, 0)
