from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from molforge.application.calculators.orca_engine import OrcaEngine, find_mpiexec
from molforge.application.invalidation import CapabilityResolver, CapabilityState
from molforge.domain.document import MoleculeDocument
from molforge.io.cclib_adapter import CCLibAdapter
from molforge.io.rdkit_adapter import create_sample_molecule
from molforge.workflows.gromacs_submit import resolve_default_gmx


class V76EnhancementTests(unittest.TestCase):
    def test_fchk_parsing_extracts_homo_lumo_and_dipole(self):
        sample_fchk = (
            "Caffeine test\n"
            "SP        RB3LYP                                                      6-31G(d)\n"
            "Charge                                     I                0\n"
            "Multiplicity                               I                1\n"
            "Number of alpha electrons                  I                2\n"
            "Total Energy                               R     -7.640000000000000E+01\n"
            "Alpha Orbital Energies                     R   N=           4\n"
            " -1.00000000E+00 -3.00000000E-01  5.00000000E-02  2.00000000E-01\n"
            "Dipole Moment                              R   N=           3\n"
            "  0.00000000E+00  0.00000000E+00  1.00000000E+00\n"
        )
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test.fchk"
            p.write_text(sample_fchk, encoding="ascii")
            res = CCLibAdapter().parse(p)
            self.assertEqual(res.software, "gaussian_fchk")
            self.assertEqual(res.method, "RB3LYP")
            self.assertAlmostEqual(res.homo, -0.3 * 27.211386245988, places=2)
            self.assertAlmostEqual(res.lumo, 0.05 * 27.211386245988, places=2)
            self.assertGreater(res.gap, 9.0)
            self.assertAlmostEqual(res.dipole_debye, 2.5417, places=3)

    def test_spec_and_wfn02_become_ready_with_real_external_file(self):
        doc = create_sample_molecule("咖啡因")
        with tempfile.TemporaryDirectory() as td:
            fchk = Path(td) / "mock.fchk"
            fchk.write_text(
                "Test\nSP RB3LYP 6-31G(d)\n"
                "Number of alpha electrons                  I                1\n"
                "Total Energy                               R     -1.000000000000000E+00\n"
                "Alpha Orbital Energies                     R   N=           2\n"
                " -3.00000000E-01  1.00000000E-01\n",
                encoding="ascii",
            )
            st_spec, _ = CapabilityResolver.resolve_status("SPEC-03", doc, external_file=str(fchk))
            st_wfn, _ = CapabilityResolver.resolve_status("WFN-02", doc, external_file=str(fchk))
            self.assertEqual(st_spec, CapabilityState.READY)
            self.assertEqual(st_wfn, CapabilityState.READY)

    def test_spectrum_lineshape_options_produce_distinct_curves(self):
        doc = create_sample_molecule("咖啡因")
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "freq.log"
            log.write_text(
                " Entering Gaussian System\n"
                " Frequencies --   1700.0   2950.0   3100.0\n"
                " Normal termination of Gaussian 16\n",
                encoding="ascii",
            )
            res_lor = CapabilityResolver.execute_analysis(
                "SPEC-01", doc, external_file=str(log), options={"fwhm": 18.0, "lineshape": "lorentzian"}
            )
            res_gau = CapabilityResolver.execute_analysis(
                "SPEC-01", doc, external_file=str(log), options={"fwhm": 18.0, "lineshape": "gaussian"}
            )
            self.assertEqual(res_lor.status, "Ready")
            self.assertGreater(len(res_lor.plot_y), 10)
            self.assertEqual(len(res_lor.plot_y), len(res_gau.plot_y))
            self.assertNotEqual(res_lor.plot_y, res_gau.plot_y)

    def test_engine_helpers_resolve_valid_paths(self):
        gmx = resolve_default_gmx()
        self.assertTrue(bool(gmx))
        engine = OrcaEngine()
        if find_mpiexec():
            self.assertTrue(engine.has_mpi())
            self.assertIn("PATH", engine.mpi_env())

    def test_workspace_2d_hard_fuse_for_large_systems(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from molforge.application.command_bus import CommandBus
        from molforge.application.selection import SelectionService
        from molforge.ui.window import Workspace

        app = QApplication.instance() or QApplication(["molforge_test"])
        doc = MoleculeDocument(name="large_stub")
        for i in range(3005):
            doc.topology.add_atom(6)
        doc.ensure_coordinates()
        ws = Workspace(doc, SelectionService(), CommandBus(doc))
        ws.set_mode(0)  # Attempt to switch to 2D-only mode
        self.assertFalse(ws.view_mode_buttons[0].isEnabled())
        self.assertFalse(ws.view_mode_buttons[2].isEnabled())
        self.assertTrue(ws.view_mode_buttons[1].isChecked())
        if hasattr(ws, "view3d_real"):
            ws.view3d_real.close()
        ws.close()
        ws.deleteLater()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
