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

    def test_mcp_rich_molecule_building_and_editing_tools(self):
        import json
        from molforge.ai.mcp.mcp_server import MolForgeMCPServer
        from molforge.ai.mcp_bridge import MolForgeMCPBridge
        from molforge.application.command_bus import CommandBus

        doc = MoleculeDocument(name="empty_mcp")
        bus = CommandBus(doc)
        srv = MolForgeMCPServer(doc, bus)
        self.assertGreaterEqual(len(srv.get_tool_definitions()), 18)

        # Build benzene from SMILES -> 12 atoms
        r1 = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "build_from_smiles", "arguments": {"smiles": "c1ccccc1"}}})
        d1 = json.loads(r1["result"]["content"][0]["text"])
        self.assertTrue(d1["success"])
        self.assertEqual(doc.num_atoms, 12)

        # Change atom 1 (C) -> N (atomic_num=7)
        r2 = srv.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "change_element", "arguments": {"atom_index": 1, "new_atomic_num": 7}}})
        self.assertTrue(json.loads(r2["result"]["content"][0]["text"])["success"])
        self.assertEqual(doc.topology.get_atom(list(doc.topology.atom_ids)[0]).atomic_num, 7)

        # Undo via MCP
        r3 = srv.handle_request({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "undo_last", "arguments": {}}})
        self.assertTrue(json.loads(r3["result"]["content"][0]["text"])["success"])
        self.assertEqual(doc.topology.get_atom(list(doc.topology.atom_ids)[0]).atomic_num, 6)

        # Bridge also exposes matching tools
        bridge = MolForgeMCPBridge(doc, bus)
        tool_names = {d["function"]["name"] for d in bridge.tool_definitions()}
        for expected in ("build_from_smiles", "add_ring", "change_element", "change_bond_order", "clean_geometry_3d", "set_atom_charge", "undo_last", "redo_last"):
            self.assertIn(expected, tool_names)

    def test_deepseek_harness_bundle_and_custom_icon(self):
        from molforge.ai.deepseek_harness import prepare_deepseek_harness_bundle, get_custom_icon_path
        self.assertIsNotNone(get_custom_icon_path())
        with tempfile.TemporaryDirectory() as td:
            bundle = prepare_deepseek_harness_bundle(dsh_home=Path(td))
            self.assertTrue(Path(bundle["skill_path"]).is_file())
            self.assertTrue(Path(bundle["mcp_config_path"]).is_file())
            skill_txt = Path(bundle["skill_path"]).read_text(encoding="utf-8")
            self.assertIn("build_from_smiles", skill_txt)
            self.assertIn("molforge.ai.mcp.mcp_server", skill_txt)

    def test_move_single_and_fragment_undo_redo_2d_and_3d(self):
        import numpy as np
        from molforge.application.builtin_commands import MoveAtom3DCommand, MoveMultiAtoms3DCommand
        from molforge.application.command_bus import CommandBus

        doc = create_sample_molecule("咖啡因")
        bus = CommandBus(doc)
        aids = list(doc.topology.atom_ids)
        a0 = aids[0]

        # 1. Simulate 2D live single-atom drag where doc.coords_2d was mutated before execute()
        old_3d = doc.get_atom_3d_pos(a0).copy()
        old_2d = tuple(doc.coords_2d[a0])
        new_2d = (old_2d[0] + 2.5, old_2d[1] - 1.5)
        doc.coords_2d[a0] = new_2d
        res = bus.execute(MoveAtom3DCommand(a0, (new_2d[0], new_2d[1], float(old_3d[2])), old_pos=old_3d, new_pos_2d=new_2d, old_pos_2d=old_2d))
        self.assertTrue(res.success)
        self.assertAlmostEqual(doc.coords_2d[a0][0], new_2d[0], places=4)

        self.assertTrue(bus.undo().success)
        self.assertAlmostEqual(doc.coords_2d[a0][0], old_2d[0], places=4)
        self.assertAlmostEqual(doc.coords_2d[a0][1], old_2d[1], places=4)
        self.assertTrue(np.allclose(doc.get_atom_3d_pos(a0), old_3d, atol=1e-4))

        self.assertTrue(bus.redo().success)
        self.assertAlmostEqual(doc.coords_2d[a0][0], new_2d[0], places=4)

        # 2. Simulate batch/fragment move & undo/redo across all atoms
        bus.undo()
        old_3d_map = {aid: doc.get_atom_3d_pos(aid).copy() for aid in aids}
        old_2d_map = {aid: tuple(doc.coords_2d[aid]) for aid in aids}
        new_3d_map = {aid: old_3d_map[aid] + np.array([3.0, -2.0, 1.0], dtype=np.float32) for aid in aids}
        new_2d_map = {aid: (old_2d_map[aid][0] + 3.0, old_2d_map[aid][1] - 2.0) for aid in aids}
        doc.coords_2d.update(new_2d_map)

        res2 = bus.execute(MoveMultiAtoms3DCommand(old_3d_map, new_3d_map, old_coords_2d=old_2d_map, new_coords_2d=new_2d_map))
        self.assertTrue(res2.success)
        self.assertAlmostEqual(doc.coords_2d[a0][0], new_2d_map[a0][0], places=4)

        self.assertTrue(bus.undo().success)
        for aid in aids:
            self.assertAlmostEqual(doc.coords_2d[aid][0], old_2d_map[aid][0], places=4)
            self.assertTrue(np.allclose(doc.get_atom_3d_pos(aid), old_3d_map[aid], atol=1e-4))

        self.assertTrue(bus.redo().success)
        for aid in aids:
            self.assertAlmostEqual(doc.coords_2d[aid][0], new_2d_map[aid][0], places=4)
            self.assertTrue(np.allclose(doc.get_atom_3d_pos(aid), new_3d_map[aid], atol=1e-4))

    def test_stick_vs_wireframe_representation_distinct_radii_and_ui(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import numpy as np
        import pyvista as pv
        from PyQt6.QtWidgets import QApplication
        from molforge.rendering.contracts import RenderSnapshot, RepresentationMode
        from molforge.rendering.vtk_backend import VtkRendererBackend
        from molforge.ui.panels import RightPanel

        app = QApplication.instance() or QApplication(["molforge_test"])
        doc = create_sample_molecule("咖啡因")
        pl = pv.Plotter(off_screen=True, window_size=(400, 300))
        be = VtkRendererBackend()
        be.attach(pl)
        aids, id2idx = doc.topology.atom_index_map()
        z_arr = np.array([doc.topology.get_atom(a).atomic_num for a in aids], dtype=np.int32)
        bonds = [(id2idx[b.begin], id2idx[b.end], int(b.order)) for b in (doc.topology.get_bond(bid) for bid in doc.topology.bond_ids)]
        be.set_snapshot(RenderSnapshot(atom_ids=aids, atomic_numbers=z_arr, bonds=bonds, coordinates=doc.coordinates.current.coords))

        be.set_mode(RepresentationMode.STICK)
        stick_atom_r = be.get_effective_atom_radius(0)
        stick_bond_r = be.get_effective_bond_radius(0)
        be.set_mode(RepresentationMode.LINE)
        line_atom_r = be.get_effective_atom_radius(0)
        line_bond_r = be.get_effective_bond_radius(0)
        self.assertGreater(stick_bond_r, line_bond_r * 3.0)
        self.assertGreater(stick_atom_r, line_atom_r * 1.5)

        panel = RightPanel()
        codes = [code for code, _ in panel.repr_buttons]
        self.assertIn("stick", codes)
        self.assertIn("wireframe", codes)

    def test_pdb_centered_box_origin_wraps_atoms_and_massive_gpu_path(self):
        import numpy as np
        import pyvista as pv
        from molforge.domain.periodic import UnitCell
        from molforge.io.rdkit_adapter import build_document_from_3d_atoms
        from molforge.rendering.contracts import RenderSnapshot, RepresentationMode
        from molforge.rendering.vtk_backend import VtkRendererBackend

        # Simulate Packmol [0, 50]^3 coordinates with CRYST1 52x52x52
        n = 2500
        rng = np.random.default_rng(7)
        raw_coords = rng.uniform(1.0, 50.0, size=(n, 3))
        z_arr = np.full(n, 6, dtype=np.int32)
        cryst1 = {"a": 52.0, "b": 52.0, "c": 52.0, "alpha": 90.0, "beta": 90.0, "gamma": 90.0}
        doc = build_document_from_3d_atoms(
            "pack_box", z_arr.tolist(), raw_coords, explicit_bonds=[], properties={"cryst1": cryst1}
        )
        box_origin = np.asarray(doc.properties["box_origin"], dtype=np.float64)
        coords = doc.coordinates.current.coords
        self.assertTrue(np.all(coords >= box_origin - 1e-4))
        self.assertTrue(np.all(coords <= box_origin + np.array([52.0, 52.0, 52.0]) + 1e-4))

        bonds = [(i, i + 1, 1) for i in range(0, n - 1, 2)]
        bonds.extend((i, i + 1, 1) for i in range(1, n - 1, 2))  # > 2000 bonds triggers GPU massive path
        pl = pv.Plotter(off_screen=True, window_size=(400, 300))
        be = VtkRendererBackend()
        be.attach(pl)
        uc = UnitCell(**cryst1)
        aids, _ = doc.topology.atom_index_map()
        snap = RenderSnapshot(atom_ids=aids, atomic_numbers=z_arr, bonds=bonds, coordinates=coords, cell_matrix=uc.matrix, cell_origin=box_origin)
        be.set_snapshot(snap, reset_cam=True)
        corners = np.array([be._cell_points.GetPoint(i) for i in range(8)])
        self.assertTrue(np.allclose(corners.min(axis=0), box_origin, atol=1e-3))

        be.set_mode(RepresentationMode.STICK)
        self.assertEqual(type(be._atom_actor.GetMapper()).__name__, "vtkOpenGLSphereMapper")
        self.assertEqual(type(be._bond_actor.GetMapper()).__name__, "vtkOpenGLStickMapper")
        be.set_mode(RepresentationMode.LINE)
        self.assertEqual(be._atom_actor.GetVisibility(), 0)
        self.assertEqual(be._bond_actor.GetVisibility(), 1)

    def test_qc_result_dialog_computes_real_mos_without_hardcoded_constants(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from molforge.io.calculators import compute_tight_binding_mos
        from molforge.ui.qc_result_dialog import QcResultDialog

        app = QApplication.instance() or QApplication(["molforge_test"])
        doc = create_sample_molecule("咖啡因")
        expected = compute_tight_binding_mos(doc)
        dlg = QcResultDialog(document=doc, initial_tab=2)
        self.assertAlmostEqual(dlg.cur_homo_spin.value(), float(expected["homo_ev"]), places=2)
        self.assertAlmostEqual(dlg.cur_lumo_spin.value(), float(expected["lumo_ev"]), places=2)
        self.assertNotAlmostEqual(dlg.cur_homo_spin.value(), -5.58, places=2)
        self.assertTrue(hasattr(dlg, "tab3_tb_btn"))
        self.assertTrue(hasattr(dlg, "tab3_calchem_btn"))
        dlg.close()


if __name__ == "__main__":
    unittest.main()
