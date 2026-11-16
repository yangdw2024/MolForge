"""Responsive 22 px layout counterexample from the external smoke audit."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from molforge.ui.theme import apply_global_typography
from molforge.ui.window import MolForgeWindow


class ResponsiveTypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._settings_dir = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls._settings_dir.name)
        cls.app = QApplication.instance() or QApplication(["molforge_typography_test"])

    @classmethod
    def tearDownClass(cls):
        cls._settings_dir.cleanup()

    def setUp(self):
        self.window = MolForgeWindow()
        self.window.show()
        self.window.resize(960, 774)
        apply_global_typography("Microsoft YaHei UI", 22, "Dark Professional")
        for _ in range(5):
            self.app.processEvents()

    def tearDown(self):
        for session, _, _ in self.window._document_pages.values():
            self.window._saved_revisions[session.document.document_id] = session.document.revision
        self.window.close()
        self.app.processEvents()

    def test_22px_compact_layout_has_usable_center_and_controls(self):
        w = self.window
        self.assertFalse(w.left_panel.isVisible(), "left splitter container must release its width")
        self.assertFalse(w.right.isVisible(), "right panel must auto-collapse at 960 px")
        self.assertGreaterEqual(w.workspace.width(), 900)
        self.assertGreaterEqual(w.top_bar.height(), 52)
        self.assertGreaterEqual(w.status_frame.height(), 36)
        self.assertGreaterEqual(w.sidebar.atom_table.verticalHeader().defaultSectionSize(), 40)

        for button in (w.top_bar.open_btn, w.top_bar.qc_btn, w.top_bar.export_btn):
            self.assertTrue(button.isVisible())
            required = button.fontMetrics().horizontalAdvance(button.text()) + 20
            self.assertGreaterEqual(button.width(), required, f"clipped button: {button.text()}")
            self.assertGreaterEqual(button.height(), button.fontMetrics().height() + 8)

        required_status = w.status_right.fontMetrics().horizontalAdvance(w.status_right.text()) + 8
        self.assertGreaterEqual(w.status_right.width(), required_status)

        workspace = w.workspace
        self.assertTrue(workspace.compact_mode_btn.isVisible())
        self.assertTrue(all(not button.isVisible() for button in workspace.mode_buttons.values()))
        toolbar_buttons = list(workspace.tool_buttons.values()) + list(workspace.element_buttons.values()) + [workspace.more_elem_btn, workspace.compact_mode_btn]
        for button in toolbar_buttons:
            if button.isVisible():
                icon_width = button.iconSize().width() + 8 if not button.icon().isNull() else 0
                required = button.fontMetrics().horizontalAdvance(button.text()) + icon_width + 22
                self.assertGreaterEqual(button.width(), required, f"clipped toolbar button: {button.text()}")

    def test_22px_menubar_actions_are_not_clipped(self):
        bar = self.window.menuBar()
        for action in bar.actions():
            if action.isVisible():
                geometry = bar.actionGeometry(action)
                self.assertGreaterEqual(geometry.left(), 0, action.text())
                self.assertLessEqual(geometry.right(), bar.width() - 1, action.text())

    def test_new_document_inherits_compact_typography(self):
        self.window._on_new_blank()
        self.app.processEvents()
        workspace = self.window.workspace
        self.assertEqual(workspace.view_mode_buttons[2].text(), "2D+3D")
        self.assertEqual(workspace.tool_buttons["原子"].text(), "原子")
        self.assertTrue(workspace.compact_mode_btn.isVisible())
        self.assertGreaterEqual(workspace.toolbar_scroll.height(), 42)

    def test_save_22px_evidence_screenshot(self):
        evidence = os.environ.get("MOLFORGE_TEST_EVIDENCE")
        if evidence and QFontDatabase.families():
            target = Path(evidence) / "typography_22_geometry.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(self.window.grab().save(str(target), "PNG"))


if __name__ == "__main__":
    unittest.main()
