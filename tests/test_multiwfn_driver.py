"""
Unit tests for Multiwfn headless driver: QTAIM CP parsing, bond path parsing, Mayer & ADCH parsing.
"""
import unittest
import numpy as np
from pathlib import Path
from molforge.io.multiwfn_driver import (
    MultiwfnDriver,
    CriticalPoint,
    BondPath,
    QTAIMResult,
    MayerBondOrderResult,
    PopulationResult,
    BOHR_TO_ANGSTROM,
)


SAMPLE_CPPROP_TEXT = """
 -------------------- CP    1, Type (3,-3) --------------------
 Position (Bohr):     0.00000000     0.00000000     0.00000000
 Position (Angstrom): 0.00000000     0.00000000     0.00000000
 Density of all electrons:   2.85192039E+02
 Laplacian of electron density: -1.24058291E+05
 Lagrangian kinetic energy G(r):  3.10145728E+04
 Potential energy density V(r):  -6.20291456E+04
 Energy density E(r) or H(r):    -3.10145728E+04
 Ellipticity of electron density: 0.00000000
 Electron localization function (ELF):  0.99982104

 -------------------- CP    2, Type (3,-1) --------------------
 Position (Bohr):     1.13383600     0.00000000     0.00000000
 Position (Angstrom): 0.60000000     0.00000000     0.00000000
 Density of all electrons:   2.67182910E-01
 Laplacian of electron density: -5.81920192E-01
 Lagrangian kinetic energy G(r):  4.51203910E-02
 Potential energy density V(r):  -1.90600438E-01
 Energy density E(r) or H(r):    -1.45480047E-01
 Ellipticity of electron density: 0.04519201
 Electron localization function (ELF):  0.88192010
"""

SAMPLE_PATHS_TEXT = """
 Path index: 1
 3
    0.000000    0.000000    0.000000
    0.566918    0.000000    0.000000
    1.133836    0.000000    0.000000
 Path index: 2
 3
    1.133836    0.000000    0.000000
    1.700754    0.000000    0.000000
    2.267672    0.000000    0.000000
"""

SAMPLE_MAYER_TEXT = """
 Bond orders with absolute value >= 0.050000
    #    1:         1(C )    2(O )    1.85210000
    #    2:         1(C )    3(H )    0.98520100

 Total valences and free valences defined by Mayer:
 Atom     1(C ) :    3.98520100    0.00000000
 Atom     2(O ) :    2.01429000    0.00000000
 Atom     3(H ) :    0.99812000    0.00000000
 ========================================================
"""


class TestMultiwfnDriver(unittest.TestCase):

    def setUp(self):
        self.driver = MultiwfnDriver()

    def test_parse_cpprop(self):
        cps = self.driver._parse_cpprop(SAMPLE_CPPROP_TEXT)
        self.assertEqual(len(cps), 2)

        # CP 1: (3,-3)
        cp1 = cps[0]
        self.assertEqual(cp1.index, 1)
        self.assertEqual(cp1.cp_type, "(3,-3)")
        self.assertAlmostEqual(cp1.rho, 285.192039, places=3)
        self.assertAlmostEqual(cp1.laplacian, -124058.291, places=1)
        self.assertAlmostEqual(cp1.elf, 0.999821, places=4)

        # CP 2: (3,-1) BCP
        cp2 = cps[1]
        self.assertEqual(cp2.index, 2)
        self.assertEqual(cp2.cp_type, "(3,-1)")
        self.assertAlmostEqual(cp2.rho, 0.26718291, places=5)
        self.assertAlmostEqual(cp2.ellipticity, 0.045192, places=4)
        np.testing.assert_allclose(cp2.coords_angstrom, [0.6, 0.0, 0.0], atol=1e-5)

    def test_parse_paths(self):
        paths = self.driver._parse_paths(SAMPLE_PATHS_TEXT)
        self.assertEqual(len(paths), 2)
        p1 = paths[0]
        self.assertEqual(p1.path_index, 1)
        self.assertEqual(len(p1.points_angstrom), 3)
        # Check conversion to angstrom: 0.566918 Bohr * 0.52917721 ~ 0.3000 Å
        self.assertAlmostEqual(p1.points_angstrom[1, 0], 0.3000, places=3)

    def test_parse_mayer(self):
        res = self.driver._parse_mayer_output(SAMPLE_MAYER_TEXT)
        self.assertEqual(len(res.atom_labels), 3)
        self.assertAlmostEqual(res.total_valences[1], 3.985201, places=4)
        self.assertAlmostEqual(res.total_valences[2], 2.014290, places=4)

        # Mayer matrix: C-O bond order ~ 1.8521
        self.assertAlmostEqual(res.bond_orders[(1, 2)], 1.8521, places=3)
        # C-H bond order ~ 0.9852
        self.assertAlmostEqual(res.bond_orders[(1, 3)], 0.9852, places=3)

    def test_driver_missing_file_safe_handling(self):
        with self.assertRaises(FileNotFoundError):
            self.driver.run_qtaim_analysis("nonexistent_mol_12345.wfn")


if __name__ == "__main__":
    unittest.main()
