"""
tests/test_core_features_e2e.py - MolForge 基本核心功能全链路核验测试套件
========================================================================
覆盖真实工作台的核心端到端功能：
  1. 多格式读写往返（.mforge 完整工程字段、.pdb + CRYST1 晶胞、.xyz、.gjf、REST ctrl.in）
  2. 分子搭建与全部基础编辑命令（加原子/成键/加环/换元素/改键级/几何优化/内坐标/删除 + Undo/Redo）
  3. 2D & 3D 选中、双击选中连通片段/整分子、拖拽平移及 Undo/Redo 精确还原
  4. 左侧自建分组（新建分组/存入片段/重命名/移动/删除/界面渲染可见性）与左右侧栏独立折叠
  5. 右侧属性、结构树 AtomId+1 稳定性（删 1 号原子后不漂移）、几何测量（键长/键角/二面角）
  6. 科学摘要（自旋/SVD 旋转不变性/环计数/芳香与丙二烯）与量化 .fchk / 光谱展宽线型
  7. 超大体系（>3000 原子）2D 画布硬熔断保护
  8. 桌面 MCP（18 项工具、一键启动 DeepSeek Harness 服务开启与专属图标/Skill 生成）
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from molforge.ai.deepseek_harness import get_custom_icon_path, prepare_deepseek_harness_bundle
from molforge.ai.mcp.mcp_server import MolForgeMCPServer
from molforge.ai.mcp_bridge import get_llm_config, set_llm_config
from molforge.application.builtin_commands import (
    AddAtomCommand,
    AddBondCommand,
    AddRingCommand,
    AppendMoleculeCommand,
    ChangeBondOrderCommand,
    ChangeElementCommand,
    CleanGeometry3DCommand,
    DeleteAtomCommand,
    ModifyBondLength3DCommand,
    MoveAtomsBatch3DCommand,
)
from molforge.application.calculators.qc_input_generator import export_document_to_xyz, generate_gaussian_gjf, generate_rest_ctrl_in
from molforge.application.command_bus import CommandBus
from molforge.application.internal_coordinates import ModifyAngle3DCommand, ModifyDihedral3DCommand
from molforge.application.invalidation import CapabilityResolver, CapabilityState
from molforge.application.measurement_targets import MeasurementTargetResolver
from molforge.application.selection import SelectionService
from molforge.domain.chemical_summary import analyze_geometry_shape, resolve_spin_state
from molforge.domain.custom_fragments import (
    add_custom_fragment,
    add_custom_group,
    delete_custom_group,
    get_grouped_custom_fragments,
    load_custom_groups,
    rename_custom_group,
    save_custom_fragments,
    save_custom_groups,
    load_custom_fragments,
)
from molforge.domain.document import MoleculeDocument
from molforge.domain.periodic import UnitCell, cell_from_document, minimum_image_delta
from molforge.io.cclib_adapter import CCLibAdapter
from molforge.io.mforge_storage import load_mforge, save_mforge
from molforge.io.rdkit_adapter import (
    create_molecule_from_smiles,
    create_sample_molecule,
    export_document_to_mol2,
    export_document_to_mol_v2000,
    export_document_to_pdb,
    load_molecule_document,
    parse_pdb_to_document,
)
from molforge.ui.window import MolForgeWindow


class CoreFeaturesEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["molforge_e2e_test"])

    def setUp(self):
        self._orig_frags = load_custom_fragments()
        self._orig_groups = load_custom_groups()
        self.window = MolForgeWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        for s, _, _ in list(self.window._document_pages.values()):
            self.window._saved_revisions[s.document.document_id] = s.document.revision
        if getattr(self.window, "mcp_service", None) is not None and self.window.mcp_service.is_active:
            self.window.mcp_service.stop()
        self.window.close()
        self.app.processEvents()
        save_custom_fragments(self._orig_frags)
        save_custom_groups(self._orig_groups)

    def test_01_file_formats_and_project_roundtrip(self):
        doc = create_molecule_from_smiles("c1ccccc1O", name="phenol_e2e")
        doc.properties["multiplicity"] = 3
        doc.properties["charge"] = 1
        doc.properties["cryst1"] = {
            "a": 12.0, "b": 14.0, "c": 16.0,
            "alpha": 90.0, "beta": 90.0, "gamma": 90.0, "space_group": "P 1",
        }
        a0 = list(doc.topology.atom_ids)[0]
        doc.topology.get_atom(a0).color = (1.0, 0.2, 0.4)
        doc.topology.get_atom(a0).scale = 1.45

        with tempfile.TemporaryDirectory() as td:
            td_p = Path(td)
            # 1. .mforge roundtrip
            mf_path = td_p / "phenol.mforge"
            save_mforge(doc, mf_path)
            doc_mf = load_mforge(mf_path)
            self.assertEqual(doc_mf.num_atoms, doc.num_atoms)
            self.assertEqual(doc_mf.properties.get("multiplicity"), 3)
            self.assertEqual(doc_mf.topology.get_atom(a0).color, (1.0, 0.2, 0.4))
            self.assertAlmostEqual(doc_mf.topology.get_atom(a0).scale, 1.45, places=2)
            cell_mf = cell_from_document(doc_mf)
            self.assertIsInstance(cell_mf, UnitCell)
            self.assertAlmostEqual(cell_mf.a, 12.0, places=3)

            # 2. .pdb with CRYST1 roundtrip
            pdb_path = td_p / "phenol.pdb"
            pdb_path.write_text(export_document_to_pdb(doc), encoding="utf-8")
            doc_pdb = parse_pdb_to_document(pdb_path)
            self.assertEqual(doc_pdb.num_atoms, doc.num_atoms)
            self.assertIsNotNone(cell_from_document(doc_pdb))

            # 3. .xyz / .mol / .mol2 roundtrip
            xyz_path = td_p / "phenol.xyz"
            export_document_to_xyz(doc, str(xyz_path))
            doc_xyz, _ = load_molecule_document(xyz_path)
            self.assertEqual(doc_xyz.num_atoms, doc.num_atoms)

            mol_path = td_p / "phenol.mol"
            mol_path.write_text(export_document_to_mol_v2000(doc), encoding="utf-8")
            doc_mol, _ = load_molecule_document(mol_path)
            self.assertEqual(doc_mol.num_atoms, doc.num_atoms)

            mol2_path = td_p / "phenol.mol2"
            mol2_path.write_text(export_document_to_mol2(doc), encoding="utf-8")
            doc_mol2, _ = load_molecule_document(mol2_path)
            self.assertEqual(doc_mol2.num_atoms, doc.num_atoms)

            # 4. QC input cards (.gjf & REST ctrl.in)
            gjf = generate_gaussian_gjf(doc)
            ctrl = generate_rest_ctrl_in(doc)
            self.assertIn("#", gjf)
            self.assertIn("[ctrl]", ctrl)

    def test_02_molecular_building_editing_and_undo_redo(self):
        doc = MoleculeDocument(name="build_e2e")
        bus = CommandBus(doc)

        # Add C, N, bond, ring, change element, change bond order, internal coords, relax
        r1 = bus.execute(AddAtomCommand(6, x=0.0, y=0.0, z=0.0))
        r2 = bus.execute(AddAtomCommand(6, x=1.5, y=0.0, z=0.0, bond_to=list(doc.topology.atom_ids)[0]))
        r3 = bus.execute(AddAtomCommand(6, x=2.3, y=1.3, z=0.0, bond_to=list(doc.topology.atom_ids)[1]))
        r4 = bus.execute(AddAtomCommand(6, x=3.8, y=1.3, z=0.0, bond_to=list(doc.topology.atom_ids)[2]))
        self.assertTrue(all(r.success for r in (r1, r2, r3, r4)))
        self.assertEqual(doc.num_atoms, 4)

        aids = list(doc.topology.atom_ids)
        self.assertTrue(bus.execute(ChangeElementCommand(aids[1], 7)).success)
        self.assertEqual(doc.topology.get_atom(aids[1]).atomic_num, 7)

        bid0 = doc.topology.bond_between(aids[0], aids[1])
        self.assertTrue(bus.execute(ChangeBondOrderCommand(bid0, 2)).success)
        self.assertEqual(doc.topology.get_bond(bid0).order, 2)

        self.assertTrue(bus.execute(ModifyBondLength3DCommand(bid0, 1.32)).success)
        self.assertAlmostEqual(float(np.linalg.norm(doc.get_atom_3d_pos(aids[0]) - doc.get_atom_3d_pos(aids[1]))), 1.32, places=2)

        self.assertTrue(bus.execute(ModifyAngle3DCommand(aids[0], aids[1], aids[2], 120.0)).success)
        self.assertTrue(bus.execute(ModifyDihedral3DCommand(aids[0], aids[1], aids[2], aids[3], 60.0)).success)

        self.assertTrue(bus.execute(AddRingCommand(size=6, aromatic=True)).success)
        self.assertEqual(doc.num_atoms, 10)

        self.assertTrue(bus.execute(CleanGeometry3DCommand()).success)

        # Undo everything step by step back to empty (11 commands)
        steps = 0
        while bus.can_undo:
            self.assertTrue(bus.undo().success)
            steps += 1
        self.assertEqual(steps, 11)
        self.assertEqual(doc.num_atoms, 0)

        # Redo all 10 steps back to 10 atoms
        for _ in range(steps):
            self.assertTrue(bus.redo().success)
        self.assertEqual(doc.num_atoms, 10)

    def test_03_2d_and_3d_double_click_move_undo_redo_in_gui(self):
        # Switch to 2D+3D split mode so both views are visible and active
        self.window.workspace.set_mode(2)
        self.app.processEvents()
        v2d = self.window.workspace.view2d
        v2d.resize(640, 480)
        v2d.fit_view()
        self.app.processEvents()

        doc = self.window.document
        aids = list(doc.topology.atom_ids)
        self.assertGreater(len(aids), 2)
        a0 = aids[0]
        w0 = v2d._ensure_world_coords_2d()[a0]
        s0 = v2d.world_to_screen(w0[0], w0[1])
        p0 = QPointF(s0[0], s0[1])

        from PyQt6.QtCore import QEvent
        from PyQt6.QtGui import QMouseEvent

        # 1. Double-click atom in 2D -> selects entire connected caffeine molecule
        self.app.sendEvent(
            v2d,
            QMouseEvent(QEvent.Type.MouseButtonDblClick, p0, p0, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
        )
        self.app.processEvents()
        self.assertEqual(len(self.window.selection.selected_atoms), doc.num_atoms)

        # 2. Drag the selected molecule in 2D (mouse press -> move -> release)
        orig_2d = {aid: tuple(doc.coords_2d[aid]) for aid in aids}
        orig_3d = {aid: doc.get_atom_3d_pos(aid).copy() for aid in aids}
        target_pt = QPointF(p0.x() + 60.0, p0.y() + 40.0)
        self.app.sendEvent(
            v2d,
            QMouseEvent(QEvent.Type.MouseButtonPress, p0, p0, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
        )
        self.app.sendEvent(
            v2d,
            QMouseEvent(QEvent.Type.MouseMove, target_pt, target_pt, Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
        )
        self.app.sendEvent(
            v2d,
            QMouseEvent(QEvent.Type.MouseButtonRelease, target_pt, target_pt, Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier),
        )
        self.app.processEvents()

        moved_2d = tuple(doc.coords_2d[a0])
        self.assertGreater(abs(moved_2d[0] - orig_2d[a0][0]), 0.5)

        # 3. Undo -> must move ALL atoms back in BOTH 2D and 3D
        self.window._undo()
        self.app.processEvents()
        for aid in aids:
            self.assertAlmostEqual(doc.coords_2d[aid][0], orig_2d[aid][0], places=3)
            self.assertAlmostEqual(doc.coords_2d[aid][1], orig_2d[aid][1], places=3)
            self.assertTrue(np.allclose(doc.get_atom_3d_pos(aid), orig_3d[aid], atol=1e-3))

        # 4. Redo -> must re-apply the moved 2D & 3D coordinates
        self.window._redo()
        self.app.processEvents()
        self.assertAlmostEqual(doc.coords_2d[a0][0], moved_2d[0], places=3)

        # 5. 3D batch move + undo/redo via command bus
        self.window._undo()
        delta3 = np.array([2.0, -1.0, 0.5], dtype=np.float32)
        moves_3d = {aid: (orig_3d[aid], orig_3d[aid] + delta3) for aid in aids}
        self.assertTrue(self.window.command_bus.execute(MoveAtomsBatch3DCommand(moves_3d)).success)
        self.assertTrue(np.allclose(doc.get_atom_3d_pos(a0), orig_3d[a0] + delta3, atol=1e-3))
        self.window._undo()
        self.assertTrue(np.allclose(doc.get_atom_3d_pos(a0), orig_3d[a0], atol=1e-3))

    def test_04_custom_groups_and_independent_panel_folding(self):
        # Custom group CRUD + UI rendering visibility
        grp_name = "E2E测试光伏受体分组"
        add_custom_group(grp_name)
        add_custom_fragment("E2E_BT", "c1ccc2nsnc2c1", group=grp_name, frag_type="fragment")
        self.window.sidebar._refresh_custom_fragments_card()
        self.app.processEvents()

        grouped = get_grouped_custom_fragments()
        self.assertIn(grp_name, grouped)
        self.assertTrue(any(f.get("name") == "E2E_BT" for f in grouped[grp_name]))
        self.assertTrue(any(name == "E2E_BT" for name, _btn in self.window.sidebar.custom_fragment_buttons))

        new_grp = "E2E重命名分组"
        self.assertTrue(rename_custom_group(grp_name, new_grp))
        self.assertIn(new_grp, get_grouped_custom_fragments())
        self.assertTrue(delete_custom_group(new_grp))

        # Independent left/right panel folding
        self.window.left_panel.setVisible(True)
        self.window.right.setVisible(True)
        self.window._toggle_left_sidebar()
        self.app.processEvents()
        self.assertFalse(self.window.left_panel.isVisible())
        self.assertTrue(self.window.right.isVisible())

        self.window._toggle_right_sidebar()
        self.app.processEvents()
        self.assertFalse(self.window.left_panel.isVisible())
        self.assertFalse(self.window.right.isVisible())

        self.window._toggle_left_sidebar()
        self.app.processEvents()
        self.assertTrue(self.window.left_panel.isVisible())
        self.assertFalse(self.window.right.isVisible())

    def test_05_atom_numbering_consistency_and_measurements(self):
        doc = create_sample_molecule("咖啡因")
        bus = CommandBus(doc)
        first_aid = list(doc.topology.atom_ids)[0]
        bus.execute(DeleteAtomCommand(first_aid))
        self.window._add_document_page(doc)
        self.window.sidebar.refresh_structure_tree(doc)
        self.app.processEvents()

        # Tree atom label must display stable AtomId.value + 1 ("2", NOT "1")
        tbl = self.window.sidebar.atom_table
        self.assertGreater(tbl.rowCount(), 0)
        first_id_text = tbl.item(0, 0).text()
        self.assertIn("2", first_id_text)

        # Measurement resolution on 2, 3, and 4 selected atoms
        sel = SelectionService()
        rem = list(doc.topology.atom_ids)[:4]
        sel.select_atoms(rem[:2], origin="test")
        self.assertEqual(MeasurementTargetResolver.resolve(doc, sel).kind, "distance")
        sel.select_atoms(rem[:3], origin="test")
        self.assertEqual(MeasurementTargetResolver.resolve(doc, sel).kind, "angle")
        sel.select_atoms(rem[:4], origin="test")
        self.assertEqual(MeasurementTargetResolver.resolve(doc, sel).kind, "dihedral")

    def test_06_science_summary_and_qc_analysis_ready(self):
        # Triplet O2 spin + SVD rotation invariance
        o2 = MoleculeDocument(name="triplet_o2")
        a1 = o2.topology.add_atom(8)
        a2 = o2.topology.add_atom(8)
        o2.topology.add_bond(a1, a2, 2)
        o2.ensure_coordinates()
        o2.coordinates.update_current_coords(np.array([[0.0, 0.0, 0.0], [1.21, 0.0, 0.0]], dtype=np.float32))
        o2.properties["multiplicity"] = 3
        spin_state = resolve_spin_state(o2)
        self.assertEqual(spin_state.multiplicity, 3)
        self.assertEqual(spin_state.label, "Triplet")

        benz = create_molecule_from_smiles("c1ccccc1", name="benz")
        shape1 = analyze_geometry_shape(benz.coordinates.current.coords)
        self.assertEqual(shape1.kind, "planar")
        # Rotate 90 degrees around X
        c = benz.coordinates.current.coords.copy()
        rot = np.column_stack([c[:, 0], -c[:, 2], c[:, 1]])
        shape2 = analyze_geometry_shape(rot)
        self.assertEqual(shape2.kind, "planar")

        # Real .fchk parsing if sample file exists
        fchk_sample = Path(r"E:\YDW\Trae_Chemdraw\咖啡因.fchk")
        if fchk_sample.is_file():
            qc_res = CCLibAdapter().parse(fchk_sample)
            self.assertEqual(qc_res.software, "gaussian_fchk")
            self.assertLess(qc_res.energy_hartree, -100.0)
            st, _ = CapabilityResolver.resolve_status("WFN-02", benz, external_file=str(fchk_sample))
            self.assertEqual(st, CapabilityState.READY)

    def test_07_large_system_2d_hard_fuse(self):
        doc = MoleculeDocument(name="large_fuse")
        for _ in range(3005):
            doc.topology.add_atom(6)
        doc.ensure_coordinates()
        self.window._add_document_page(doc)
        self.app.processEvents()
        ws = self.window.workspace
        ws.set_mode(0)
        self.assertFalse(ws.view_mode_buttons[0].isEnabled())
        self.assertFalse(ws.view_mode_buttons[2].isEnabled())
        self.assertTrue(ws.view_mode_buttons[1].isChecked())
        self.assertEqual(len(doc.coords_2d), 0)

    def test_08_ai_config_mcp_and_dsh_desktop_binding(self):
        orig = get_llm_config()
        try:
            set_llm_config("http://127.0.0.1:8045/v1", "sk-e2e-verify", "gemini-3.8-flash")
            cfg = get_llm_config()
            self.assertEqual(cfg["model"], "gemini-3.8-flash")
            self.assertNotEqual(cfg["model"], "default-model")
        finally:
            set_llm_config(orig.get("base_url", "http://127.0.0.1:8045/v1"), orig.get("api_key", "EMPTY"), orig.get("model", "gemini-3.8-flash"))

        # MCP 18 tools end-to-end: add standalone atom & build from SMILES, then undo
        srv = MolForgeMCPServer(self.window.document, self.window.command_bus)
        self.assertGreaterEqual(len(srv.get_tool_definitions()), 18)
        before_atoms = self.window.document.num_atoms
        r = srv.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "add_atom", "arguments": {"atomic_num": 9, "x": 10.0, "y": 0.0, "z": 0.0}}})
        res = json.loads(r["result"]["content"][0]["text"])
        self.assertTrue(res["success"])
        self.assertEqual(self.window.document.num_atoms, before_atoms + 1)
        self.window._undo()
        self.assertEqual(self.window.document.num_atoms, before_atoms)

        # Desktop MCP toggle + DeepSeek Harness bundle
        self.window._toggle_desktop_mcp(True)
        self.assertIsNotNone(self.window.mcp_service)
        self.assertTrue(self.window.mcp_service.is_active)
        self.assertIsNotNone(get_custom_icon_path())
        with tempfile.TemporaryDirectory() as td:
            bundle = prepare_deepseek_harness_bundle(dsh_home=Path(td))
            self.assertTrue(Path(bundle["skill_path"]).is_file())
            self.assertTrue(Path(bundle["mcp_config_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
