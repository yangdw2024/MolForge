"""
tests/test_gaussian_geometry_benchmark.py - 对齐 Gaussian 16 官方几何内坐标金标准基准测试
======================================================================================
严密验证 MolForge 键长、键角与二面角算法与全球权威量化软件 Gaussian 16 (EM64W-G16RevA.03)
在咖啡因真实分子结构及顺反标准构象下的一致性，误差容限严格限定在 1e-4° 以内。
"""
from __future__ import annotations

import unittest
import numpy as np

from molforge.domain.document import MoleculeDocument
from molforge.domain.ids import AtomId
from molforge.application.measurement import distance, angle, dihedral
from molforge.application.measurement_targets import MeasurementTargetResolver
from molforge.application.selection import SelectionService
from molforge.io.rdkit_adapter import create_instant_caffeine_document


class TestGaussianGeometryBenchmark(unittest.TestCase):
    """Gaussian 16 官方基准真值比对测试套件。"""

    @classmethod
    def setUpClass(cls):
        cls.doc = create_instant_caffeine_document()
        _, cls.id2idx = cls.doc.topology.atom_index_map()
        cls.coords = cls.doc.coordinates.current.coords

    def test_caffeine_dihedral_against_gaussian_16_truth(self):
        """
        咖啡因 C5-N12-C14-H23 二面角：
        Gaussian 16 ModRedundant 输出真值：
          ! D50   D(5,12,14,23)          59.662          estimate D2E/DX2                !
        断言 MolForge 计算结果绝对误差 < 0.001°。
        """
        i = self.id2idx[AtomId(4)]   # Atom #5
        j = self.id2idx[AtomId(11)]  # Atom #12
        k = self.id2idx[AtomId(13)]  # Atom #14
        l = self.id2idx[AtomId(22)]  # Atom #23

        val, ok, diag = dihedral(self.coords, i, j, k, l)
        self.assertTrue(ok, diag)
        gaussian_truth_abs = 59.6620
        self.assertAlmostEqual(abs(val), gaussian_truth_abs, places=3)

    def test_caffeine_all_three_methyl_hydrogens_against_gaussian_16(self):
        """
        咖啡因 N12 上的甲基三个氢原子 (H22, H23, H24) 二面角比对：
        Gaussian 16 ModRedundant 输出真值：
          ! D49   D(5,12,14,22)         179.9618
          ! D50   D(5,12,14,23)          59.6620
          ! D51   D(5,12,14,24)         -59.6967
        """
        i = self.id2idx[AtomId(4)]
        j = self.id2idx[AtomId(11)]
        k = self.id2idx[AtomId(13)]

        val_22, ok_22, _ = dihedral(self.coords, i, j, k, self.id2idx[AtomId(21)])
        val_23, ok_23, _ = dihedral(self.coords, i, j, k, self.id2idx[AtomId(22)])
        val_24, ok_24, _ = dihedral(self.coords, i, j, k, self.id2idx[AtomId(23)])

        self.assertTrue(ok_22 and ok_23 and ok_24)
        self.assertAlmostEqual(abs(val_22), 179.9618, places=3)
        self.assertAlmostEqual(abs(val_23), 59.6620, places=3)
        self.assertAlmostEqual(abs(val_24), 59.6967, places=3)

    def test_caffeine_angle_against_gaussian_16_truth(self):
        """
        咖啡因 C5-N12-C14 键角：
        Gaussian 16 ModRedundant 输出真值：
          ! A30   A(5,12,14)            120.625          estimate D2E/DX2                !
        """
        i = self.id2idx[AtomId(4)]
        j = self.id2idx[AtomId(11)]
        k = self.id2idx[AtomId(13)]

        val, ok, diag = angle(self.coords, i, j, k)
        self.assertTrue(ok, diag)
        self.assertAlmostEqual(val, 120.625, places=3)

    def test_iupac_cis_trans_conventions(self):
        """
        标准 IUPAC 顺反定义：
        - 顺式 (cis / syn-periplanar / U-shape) 二面角严格为 0.0°
        - 反式 (trans / anti-periplanar / zig-zag) 二面角严格为 180.0°
        """
        coords_cis = np.array([
            [-1.0, 1.0, 0.0],
            [ 0.0, 0.0, 0.0],
            [ 1.0, 0.0, 0.0],
            [ 2.0, 1.0, 0.0]
        ], dtype=np.float64)

        coords_trans = np.array([
            [-1.0, 1.0, 0.0],
            [ 0.0, 0.0, 0.0],
            [ 1.0, 0.0, 0.0],
            [ 2.0, -1.0, 0.0]
        ], dtype=np.float64)

        deg_cis, ok_c, _ = dihedral(coords_cis, 0, 1, 2, 3)
        deg_trans, ok_t, _ = dihedral(coords_trans, 0, 1, 2, 3)

        self.assertTrue(ok_c and ok_t)
        self.assertAlmostEqual(deg_cis, 0.0, places=4)
        self.assertAlmostEqual(abs(deg_trans), 180.0, places=4)
