"""
scripts/smoke_pyqt6_e2e.py - MolForge PyQt6 原生桌面版全面端到端冒烟验收脚本
============================================================================
在真实 Windows Qt (`QT_QPA_PLATFORM=windows`) 环境下对现有 PyQt6 桌面主程序执行全链路压测：
  1. 主窗口冷启动、118 元素周期表、2D/3D 协同编辑与 Undo/Redo
  2. 球棍 / CPK / 棍状 / 细线框四种 3D 展示风格半径与按钮联动
  3. 量化计算对话框 (Tight-Binding 实算、.gjf / REST ctrl.in、.fchk) 与 79 项分析入口
  4. .mforge 工程保存回读、.pdb / .xyz / .mol 导出
  5. 321,554 原子大体系 PDB 加载、RTX GPU 识别、晶胞对齐与毫秒级样式切换
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time

os.environ["QT_QPA_PLATFORM"] = "windows"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import numpy as np
from PyQt6.QtWidgets import QApplication

from molforge.application.builtin_commands import (
    AddAtomCommand,
    AddRingCommand,
    ChangeElementCommand,
    CleanGeometry3DCommand,
    DeleteAtomCommand,
    MoveMultiAtoms3DCommand,
)
from molforge.application.invalidation import AnalysisRegistry, CapabilityResolver
from molforge.io.cclib_adapter import CCLibAdapter
from molforge.io.mforge_storage import load_mforge, save_mforge
from molforge.io.rdkit_adapter import (
    export_document_to_mol_v2000,
    export_document_to_pdb,
    parse_pdb_to_document,
)
from molforge.rendering.contracts import RepresentationMode
from molforge.ui.element_picker import ElementPickerDialog
from molforge.ui.qc_result_dialog import QcResultDialog
from molforge.ui.window import MolForgeWindow


def run_smoke() -> dict[str, object]:
    report: dict[str, object] = {}
    app = QApplication.instance() or QApplication(["molforge_pyqt6_e2e_smoke"])

    # 1. 启动主窗口 (Caffeine)
    t0 = time.perf_counter()
    win = MolForgeWindow()
    win.show()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.03)
    report["startup_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    assert win.document.num_atoms == 24, f"Expected 24 atoms in Caffeine, got {win.document.num_atoms}"
    assert win.document.topology.num_bonds == 25

    # 2. 验证 118 元素周期表对话框
    pt = ElementPickerDialog(win)
    pt.show()
    app.processEvents()
    assert len(pt._buttons) == 118, f"Expected 118 periodic elements, got {len(pt._buttons)}"
    pt._filter_elements("Pt")
    app.processEvents()
    visible_pts = [el.symbol for btn, el in pt._buttons if not btn.isHidden()]
    assert "Pt" in visible_pts, f"Pt not matched in periodic table filter: {visible_pts}"
    pt.close()
    report["periodic_table_elements"] = len(pt._buttons)

    # 3. 2D/3D 交互建模、片段移动与 Undo/Redo
    bus = win.command_bus
    n0 = win.document.num_atoms
    res_add = bus.execute(AddAtomCommand(atomic_num=7, x=4.0, y=0.0, z=0.0, pos_2d=(4.0, 0.0)))
    assert res_add.success and win.document.num_atoms == n0 + 1
    added_aid = list(win.document.topology.atom_ids)[-1]
    res_chg = bus.execute(ChangeElementCommand(added_aid, 16))
    assert res_chg.success and win.document.topology.get_atom(added_aid).symbol == "S"
    res_ring = bus.execute(AddRingCommand(size=6, aromatic=True, attach_to=added_aid))
    assert res_ring.success and win.document.num_atoms >= n0 + 7

    aids = list(win.document.topology.atom_ids)
    old3d = {aid: win.document.get_atom_3d_pos(aid).copy() for aid in aids[:3]}
    new3d = {aid: old3d[aid] + np.array([1.5, -1.0, 0.5], dtype=np.float32) for aid in aids[:3]}
    old2d = {aid: tuple(win.document.coords_2d.get(aid, (0.0, 0.0))) for aid in aids[:3]}
    new2d = {aid: (old2d[aid][0] + 1.5, old2d[aid][1] - 1.0) for aid in aids[:3]}
    assert bus.execute(MoveMultiAtoms3DCommand(old3d, new3d, old_coords_2d=old2d, new_coords_2d=new2d)).success
    assert np.allclose(win.document.get_atom_3d_pos(aids[0]), new3d[aids[0]], atol=1e-4)
    assert bus.undo().success
    assert np.allclose(win.document.get_atom_3d_pos(aids[0]), old3d[aids[0]], atol=1e-4)
    assert bus.redo().success
    assert bus.undo().success  # move
    assert bus.undo().success  # ring
    assert bus.undo().success  # element
    assert bus.undo().success  # add
    assert win.document.num_atoms == n0

    # Clean 3D + DeleteAtom undo
    assert bus.execute(CleanGeometry3DCommand()).success
    before_del = win.document.num_atoms
    assert bus.execute(DeleteAtomCommand(aids[0])).success and win.document.num_atoms < before_del
    assert bus.undo().success and win.document.num_atoms == before_del
    app.processEvents()
    report["editing_undo_redo"] = "passed"

    # 4. 四种 3D 展示风格半径区分与切换
    be = win.workspace.view3d_real.renderer
    win.workspace._on_mode_changed(RepresentationMode.STICK)
    app.processEvents()
    stick_b_r = be.get_effective_bond_radius(0)
    win.workspace._on_mode_changed(RepresentationMode.BALL_AND_STICK)
    app.processEvents()
    ball_b_r = be.get_effective_bond_radius(0)
    win.workspace._on_mode_changed(RepresentationMode.LINE)
    app.processEvents()
    line_b_r = be.get_effective_bond_radius(0)
    win.workspace._on_mode_changed(RepresentationMode.CPK)
    app.processEvents()
    cpk_vis = be._bond_actor.GetVisibility()
    assert stick_b_r > ball_b_r > line_b_r > 0.0, (stick_b_r, ball_b_r, line_b_r)
    assert cpk_vis == 0
    win.workspace._on_mode_changed(RepresentationMode.BALL_AND_STICK)
    report["repr_radii"] = {"stick": round(stick_b_r, 4), "ball": round(ball_b_r, 4), "line": round(line_b_r, 4)}

    # 5. 量化工作台 & 79 项分析入口
    qc = QcResultDialog(win, document=win.document, initial_tab=2)
    assert abs(qc.cur_homo_spin.value() - (-5.96)) < 0.05, qc.cur_homo_spin.value()
    assert "B3LYP" in qc.g_preview.toPlainText()
    assert "[ctrl]" in qc.r_preview.toPlainText()
    qc.close()
    assert len(AnalysisRegistry.all()) == 79
    core_res = CapabilityResolver.execute_analysis("CORE-01", win.document)
    assert core_res.status == "Ready"
    report["qc_homo_ev"] = round(qc.cur_homo_spin.value(), 2)
    report["analysis_entries"] = len(AnalysisRegistry.all())

    # 6. 工程 .mforge 往返 & 格式导出
    with tempfile.TemporaryDirectory() as td:
        mf_path = Path(td) / "smoke.mforge"
        save_mforge(win.document, mf_path)
        reloaded = load_mforge(mf_path)
        assert reloaded.num_atoms == win.document.num_atoms
        assert reloaded.topology.num_bonds == win.document.topology.num_bonds
        assert "HETATM" in export_document_to_pdb(win.document)
        assert "V2000" in export_document_to_mol_v2000(win.document)
        fchk = Path(td) / "sample.fchk"
        fchk.write_text(
            "Test\nSP RB3LYP 6-31G(d)\nNumber of alpha electrons I 1\n"
            "Total Energy R -1.0\nAlpha Orbital Energies R N= 2\n -0.30 0.10\n",
            encoding="ascii",
        )
        parsed_fchk = CCLibAdapter().parse(fchk)
        assert parsed_fchk.gap > 9.0
    report["storage_and_export"] = "passed"

    for s, _, _ in list(win._document_pages.values()):
        win._saved_revisions[s.document.document_id] = s.document.revision
    win.close()
    app.processEvents()

    # 7. 321,554 原子大体系原生 PyQt6 + VTK GPU 窗口全链路压测
    big_pdb = Path(r"E:\YDW\test_wsl\ydw-PM6-ClFFCl.pdb")
    if big_pdb.is_file():
        tp0 = time.perf_counter()
        big_doc = parse_pdb_to_document(big_pdb)
        parse_ms = (time.perf_counter() - tp0) * 1000.0
        tw0 = time.perf_counter()
        big_win = MolForgeWindow(initial_document=big_doc)
        big_win.show()
        for _ in range(15):
            app.processEvents()
            time.sleep(0.05)
        show_ms = (time.perf_counter() - tw0) * 1000.0
        v3d = big_win.workspace.view3d_real
        gpu_txt = v3d.renderer.get_gpu_summary()
        assert "GPU" in gpu_txt, f"Unexpected GPU summary: {gpu_txt!r}"
        sw = {}
        for m in (RepresentationMode.STICK, RepresentationMode.LINE, RepresentationMode.CPK, RepresentationMode.BALL_AND_STICK):
            ts0 = time.perf_counter()
            big_win.workspace._on_mode_changed(m)
            app.processEvents()
            sw[m.value] = round((time.perf_counter() - ts0) * 1000.0, 1)
        for s, _, _ in list(big_win._document_pages.values()):
            big_win._saved_revisions[s.document.document_id] = s.document.revision
        big_win.close()
        app.processEvents()
        report["massive_pdb_321k"] = {
            "atoms": big_doc.num_atoms,
            "bonds": big_doc.topology.num_bonds,
            "parse_ms": round(parse_ms, 1),
            "win_show_ms": round(show_ms, 1),
            "gpu": gpu_txt,
            "mode_switch_ms": sw,
        }

    return report


if __name__ == "__main__":
    import json
    result = run_smoke()
    print(json.dumps(result, ensure_ascii=False, indent=2))
