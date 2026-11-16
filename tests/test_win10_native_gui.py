"""REAL Windows 10 Qt GUI acceptance (not a mocked screenshot).

Runs only on Windows 10 with PyQt6, pyvistaqt and VTK installed:
    python -m unittest discover -s tests -p test_win10_native_gui.py -v

Native 0xC0000005 may terminate the entire process; always run this script
in an isolated subprocess and archive its Windows exit code.
"""
from __future__ import annotations
import platform
import sys
import tempfile
import unittest
from pathlib import Path

IS_WIN10 = (sys.platform=="win32" and
            17763 <= sys.getwindowsversion().build < 22000)
if IS_WIN10:
    try:
        from PyQt6.QtWidgets import QApplication,QFileDialog,QMessageBox
        from molforge.ui.window import MolForgeWindow
        from unittest.mock import patch
        READY=True
    except Exception:
        READY=False
else:
    READY=False

@unittest.skipUnless(READY, "Requires a genuine Windows 10 PyQt6/VTK desktop")
class RealWin10GuiAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication(["molforge_gui_test"])

    def setUp(self):
        self.window=MolForgeWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        for s, _, _ in list(self.window._document_pages.values()):
            self.window._saved_revisions[s.document.document_id] = s.document.revision
        self.window.close()
        self.app.processEvents()

    def test_selected_atom_slider_changes_domain_and_undo(self):
        aid=next(iter(self.window.document.topology.atom_ids))
        original=self.window.document.topology.get_atom(aid).scale
        self.window.selection.select_atom(aid, add=False, origin="test")
        self.window._on_selection_changed()
        self.window.right.atom_scale_slider.setValue(180)
        self.app.processEvents()
        self.assertAlmostEqual(self.window.document.topology.get_atom(aid).scale,1.8)
        self.assertTrue(self.window.command_bus.can_undo)
        self.window.command_bus.undo()
        self.assertAlmostEqual(self.window.document.topology.get_atom(aid).scale,original)

    def test_selected_bond_slider_changes_only_selected_bond(self):
        bids=list(self.window.document.topology.bond_ids)
        self.assertGreaterEqual(len(bids),2)
        first=bids[0];other=bids[1]
        original=self.window.document.topology.get_bond(other).width_scale
        self.window.selection.select_bond(first,add=False,origin="test")
        self.window._on_selection_changed()
        self.window.right.selected_bond_width_slider.setValue(190)
        self.app.processEvents()
        self.assertAlmostEqual(self.window.document.topology.get_bond(first).width_scale,1.9)
        self.assertEqual(self.window.document.topology.get_bond(other).width_scale,original)

    def test_native_save_and_open_roundtrip_with_gui(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"gui_roundtrip.mforge"
            with patch.object(QFileDialog,"getSaveFileName",
                              return_value=(str(path),"MolForge 工程 (*.mforge)")):
                self.window._on_save_as_file()
            self.assertTrue(path.exists())
            before=list(self.window.document.topology.atom_ids)
            bonds=list(self.window.document.topology.bond_ids)
            self.assertTrue(self.window.open_molecule_file(path))
            self.assertEqual(list(self.window.document.topology.atom_ids),before)
            self.assertEqual(list(self.window.document.topology.bond_ids),bonds)

    def test_initial_layout_restored_before_first_show(self):
        # The source no longer schedules _finish_layout using singleShot(0);
        # confirm main splitter and widget sizes are already visible.
        self.assertGreater(self.window.workspace.width(),0)
        self.assertTrue(self.window.isVisible())
    def test_periodic_cell_wireframe_follows_document(self):
        w = self.window
        w.document.properties["cryst1"] = {
            "a": 10.0, "b": 11.0, "c": 12.0,
            "alpha": 90.0, "beta": 90.0, "gamma": 90.0,
            "space_group": "P 1",
        }
        w.document.revision += 1
        w.workspace.view3d_real.set_document(w.document)
        self.app.processEvents()
        backend = w.workspace.view3d_real.renderer
        self.assertIsNotNone(backend._cell_actor)
        self.assertEqual(backend._cell_actor.GetVisibility(), 1)
        self.assertEqual(backend._cell_points.GetNumberOfPoints(), 8)
        self.assertEqual(backend._cell_polydata.GetLines().GetNumberOfCells(), 12)

        del w.document.properties["cryst1"]
        w.document.revision += 1
        w.workspace.view3d_real.set_document(w.document)
        self.app.processEvents()
        self.assertEqual(backend._cell_actor.GetVisibility(), 0)

    def test_initial_small_system_camera_fit(self):
        import numpy as np
        from molforge.application.builtin_commands import AddAtomCommand
        w = self.window
        w._on_new_blank()
        self.assertTrue(w.command_bus.execute(AddAtomCommand(6, x=0.0, y=0.0, z=0.0)).success)
        first = list(w.document.topology.atom_ids)[0]
        self.assertTrue(w.command_bus.execute(AddAtomCommand(6, x=1.52, y=0.0, z=0.0, bond_to=first)).success)
        for _ in range(4):
            self.app.processEvents()
        view = w.workspace.view3d_real
        renderer = view.renderer
        cam_pos, focal, _up, _fov = renderer._get_camera_params()
        self.assertGreater(np.linalg.norm(cam_pos - focal), 10.0)
        np.testing.assert_allclose(focal, [0.76, 0.0, 0.0], atol=0.2)
        sx, sy, _z, _ty = renderer._project_points_to_qt_numpy(
            w.document.coordinates.current.coords, view.width(), view.height()
        )
        self.assertTrue(np.all((sx > 0) & (sx < view.width())))
        self.assertTrue(np.all((sy > 0) & (sy < view.height())))
        self.assertGreater(float(np.hypot(sx[1] - sx[0], sy[1] - sy[0])), 20.0)

    def test_unsaved_close_cancel_and_discard(self):
        from molforge.application.builtin_commands import AddAtomCommand
        w = self.window
        original_count = w.document.num_atoms
        self.assertTrue(w.command_bus.execute(AddAtomCommand(8, x=4.0, y=4.0, z=4.0)).success)
        self.assertTrue(w._is_doc_modified(w.document))
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(w.close())
        self.assertEqual(w.document.num_atoms, original_count + 1)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(w.close())

    def test_unsaved_close_save_choice_writes_project(self):
        from molforge.application.builtin_commands import AddAtomCommand
        w = self.window
        self.assertTrue(w.command_bus.execute(AddAtomCommand(7, x=3.0, y=3.0, z=3.0)).success)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "save_on_close.mforge"
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Save), patch.object(
                QFileDialog, "getSaveFileName", return_value=(str(path), "MolForge Project (*.mforge)")
            ):
                self.assertTrue(w.close())
            self.assertTrue(path.is_file())
            self.assertIn("manifest.json", __import__("zipfile").ZipFile(path).namelist())

if __name__=="__main__":
    unittest.main()
