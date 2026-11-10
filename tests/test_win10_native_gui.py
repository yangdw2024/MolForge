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
        from PyQt6.QtWidgets import QApplication,QFileDialog
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

if __name__=="__main__":
    unittest.main()
