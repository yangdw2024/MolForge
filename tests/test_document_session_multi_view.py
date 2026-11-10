"""
tests/test_document_session_multi_view.py - P1 单文档唯一会话、G:M:V 克隆视图同步与跨视图 Ctrl+Z 测试
"""
from __future__ import annotations

import unittest

from molforge.application.builtin_commands import AddAtomCommand
from molforge.application.workspace_registry import WorkspaceRegistry
from molforge.domain.document import MoleculeDocument
from molforge.ui.shells import Studio3DShell


class TestDocumentSessionMultiView(unittest.TestCase):
    def setUp(self) -> None:
        WorkspaceRegistry.instance().reset_for_testing()

    def test_gmv_cloned_views_share_single_command_bus_and_undo_history(self):
        doc = MoleculeDocument("shared_benzene")
        v1 = Studio3DShell(document=doc)
        self.assertEqual(v1.gmv_tag, "G1:M1:V1")

        # 克隆视图 G1:M1:V2
        v2 = v1.spawn_clone_view(pane_count=4)
        self.assertEqual(v2.gmv_tag, "G1:M1:V2")
        self.assertIs(v1.session, v2.session)
        self.assertIs(v1.session.command_bus, v2.session.command_bus)

        # 在 V1 中执行添加碳原子命令 -> V2 立即可见且收到会话事件
        res = v1.session.execute(AddAtomCommand(6, 0.0, 0.0, 0.0), origin="G1:M1:V1")
        self.assertTrue(res.success)
        self.assertEqual(v2.document.topology.num_atoms, 1)
        self.assertIsNotNone(v2.last_event)
        self.assertEqual(v2.last_event.origin, "G1:M1:V1")

        # 在 V2 中执行 Undo (Ctrl+Z) -> 直接撤销 V1 刚才发起的编辑！
        undo_res = v2.session.undo(origin="G1:M1:V2")
        self.assertTrue(undo_res.success)
        self.assertEqual(v1.document.topology.num_atoms, 0)

        # 视图独立性：V2 设为 4 分屏，V1 仍保持 1 分屏
        self.assertEqual(v2.view_session.pane_count, 4)
        self.assertEqual(v1.view_session.pane_count, 1)

    def test_gmv_group_molecule_and_monotonic_id_after_close(self):
        v1 = Studio3DShell(document=MoleculeDocument("mol1"))
        self.assertEqual(v1.gmv_tag, "G1:M1:V1")

        m2 = v1.spawn_group_molecule(MoleculeDocument("mol2"))
        self.assertEqual(m2.gmv_tag, "G1:M2:V1")
        self.assertIsNot(v1.session, m2.session)

        # 关闭 M2 后再新建组内分子，编号单调递增为 G1:M3:V1，绝不复用已关闭的 M2 造成冲突
        m2.close_shell()
        m3 = v1.spawn_group_molecule(MoleculeDocument("mol3"))
        self.assertEqual(m3.gmv_tag, "G1:M3:V1")
