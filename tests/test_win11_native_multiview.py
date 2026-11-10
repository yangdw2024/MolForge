"""
tests/test_win11_native_multiview.py - Windows 11 诊断契约、1/2/4 视口命中与 100 次窗口开关耐久测试
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

from molforge.application.workspace_registry import WorkspaceRegistry
from molforge.domain.document import MoleculeDocument
from molforge.ui.shells import Studio3DShell
from molforge.ui.vtk_multiview_widget import compute_viewport_rects, hit_test_pane
from molforge.ui.welcome_window import ShellFactory

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("windows11_diagnostics", ROOT / "scripts/windows11_diagnostics.py")
w11_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w11_mod)


class TestWin11AndMultiviewEndurance(unittest.TestCase):
    def test_windows11_diagnostics_contract(self):
        self.assertTrue(w11_mod.win11_supported("Windows", 10, 0, 22631, 64)[0])
        self.assertFalse(w11_mod.win11_supported("Windows", 10, 0, 19045, 64)[0])
        self.assertFalse(w11_mod.win11_supported("Windows", 10, 0, 22631, 32)[0])
        self.assertFalse(w11_mod.win11_supported("Linux", 10, 0, 22631, 64)[0])

    def test_multiview_1_2_4_viewport_geometry_and_hit_testing(self):
        r1 = compute_viewport_rects(1)
        self.assertEqual(set(r1.keys()), {"P1"})
        r2 = compute_viewport_rects(2)
        self.assertEqual(set(r2.keys()), {"P1", "P2"})
        r4 = compute_viewport_rects(4)
        self.assertEqual(set(r4.keys()), {"P1", "P2", "P3", "P4"})

        self.assertEqual(hit_test_pane(0.25, 0.75, 4), "P1")  # Top-Left
        self.assertEqual(hit_test_pane(0.75, 0.75, 4), "P2")  # Top-Right
        self.assertEqual(hit_test_pane(0.25, 0.25, 4), "P3")  # Bottom-Left
        self.assertEqual(hit_test_pane(0.75, 0.25, 4), "P4")  # Bottom-Right

    def test_100_cycles_shell_create_switch_and_destroy_no_leak(self):
        reg = WorkspaceRegistry.instance()
        reg.reset_for_testing()

        for i in range(100):
            doc = MoleculeDocument(f"stress_{i}")
            sh = ShellFactory.create_shell("3d", doc)
            self.assertIsInstance(sh, Studio3DShell)
            sh.set_pane_layout(2)
            sh.set_pane_layout(4)
            sh.set_pane_layout(1)
            clone = sh.spawn_clone_view(pane_count=2)
            clone.close_shell()
            sh.close_shell()

        # 全部关闭后，活跃视图与会话字典必须 100% 回收，零内存泄漏
        self.assertEqual(len(reg.active_views), 0)
        self.assertEqual(len(reg._documents), 0)
