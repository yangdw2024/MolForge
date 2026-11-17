"""
MolForge/molforge/server/api_bridge.py - Python 化学与量子计算后台引擎 HTTP/二进制桥接服务
===================================================================================
为新一代 Tauri 2 + React + WebGPU 前端提供：
  - 零第三方 Web 依赖（基于 Python 标准库 ThreadingHTTPServer）
  - 32 万原子级全矢量化二进制传输协议 (`/api/document/binary`, ~8.8 MB)
  - 完整 CommandBus 原子/化学键/芳香环/元素/几何编辑与 Undo/Redo 栈
  - 真实 Tight-Binding MO + 79 项 CapabilityResolver 科研分析 + .gjf/.ctrl.in/.pdb/.xyz/.mol 导出
  - Windows 原生资源管理器文件选择框 (`/api/dialog/open_file`)
  - Google A2UI (Agent-to-UI) 声明式卡片输出
"""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import struct
import sys
import threading
import time
import traceback
from typing import Any
from urllib.parse import urlparse

import numpy as np

from ..application.builtin_commands import (
    AddAtomCommand,
    AddBondCommand,
    AddRingCommand,
    ChangeBondOrderCommand,
    ChangeElementCommand,
    CleanGeometry3DCommand,
    DeleteAtomCommand,
    DeleteBondCommand,
    MoveAtom3DCommand,
)
from ..application.calculators.qc_input_generator import (
    export_document_to_xyz,
    generate_gaussian_gjf,
    generate_rest_ctrl_in,
)
from ..application.command_bus import CommandBus
from ..application.invalidation import AnalysisRegistry, CapabilityResolver
from ..domain.chemical_summary import analyze_geometry_shape, resolve_spin_state
from ..domain.document import MoleculeDocument
from ..domain.elements import ELEMENTS
from ..domain.ids import AtomId, BondId
from ..domain.periodic import cell_from_document
from ..io.calculators import compute_tight_binding_mos
from ..io.rdkit_adapter import (
    create_instant_caffeine_document,
    create_molecule_from_smiles,
    create_sample_molecule,
    export_document_to_mol_v2000,
    export_document_to_pdb,
    load_molecule_document,
)
from ..rendering.vtk_backend import DEFAULT_VDW, STUDIO_CPK_COLORS

MAGIC_MOLF = 0x4D4F4C46  # "MOLF"

OSC_REFERENCE_MATERIALS: dict[str, tuple[float, float, str]] = {
    "PM6 (经典给体)": (-5.50, -3.61, "#60A5FA"),
    "Y6 (经典 A-DAD-A 受体)": (-5.65, -4.10, "#FB923C"),
    "ITIC (经典非富勒烯受体)": (-5.48, -3.78, "#C084FC"),
    "P3HT (标准聚噻吩给体)": (-4.85, -2.95, "#34D399"),
}

PRESET_MOLECULES: list[dict[str, str]] = [
    {"id": "caffeine", "name": "咖啡因", "label": "Caffeine · 咖啡因", "category": "小分子参考", "smiles": "Cn1cnc2c1c(=O)n(C)c(=O)n2C"},
    {"id": "benzene", "name": "苯", "label": "Benzene · 苯环", "category": "芳香体系", "smiles": "c1ccccc1"},
    {"id": "pentacene", "name": "五并苯", "label": "Pentacene · 五并苯半导体", "category": "有机半导体", "smiles": "c1ccc2cc3cc4cc5ccccc5cc4cc3cc2c1"},
    {"id": "thiophene_trimer", "name": "三聚噻吩", "label": "Terthiophene · 3T 寡聚物", "category": "有机半导体", "smiles": "s1cccc1-c2cccs2-c3cccs3"},
    {"id": "aspirin", "name": "阿司匹林", "label": "Aspirin · 乙酰水杨酸", "category": "药物分子", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
    {"id": "porphyrin", "name": "卟啉核", "label": "Porphyrin · 四吡咯大环", "category": "功能大环", "smiles": "c1cc2cc3ccc(cc4ccc(cc5ccc(cc1n2)[nH]5)n4)[nH]3"},
    {"id": "bdt_core", "name": "PM6 核心单元", "label": "BDT-F 核心给体单元", "category": "OSC 给体", "smiles": "Fc1ccc(c2sc3cc(c4scc(F)c4)sc3c2)cc1"},
    {"id": "triplet_o2", "name": "三线态氧 (O2)", "label": "O₂ (Triplet)", "category": "电子态验证", "smiles": "O=O"},
]


def _pick_native_open_file_windows() -> str | None:
    """使用 Windows 原生 Explorer 对话框选择分子文件（零额外依赖）。"""
    if sys.platform != "win32":
        return None
    try:
        from ctypes import wintypes

        class OPENFILENAMEW(ctypes.Structure):
            _fields_ = [
                ("lStructSize", wintypes.DWORD),
                ("hwndOwner", wintypes.HWND),
                ("hInstance", wintypes.HINSTANCE),
                ("lpstrFilter", wintypes.LPCWSTR),
                ("lpstrCustomFilter", wintypes.LPWSTR),
                ("nMaxCustFilter", wintypes.DWORD),
                ("nFilterIndex", wintypes.DWORD),
                ("lpstrFile", wintypes.LPWSTR),
                ("nMaxFile", wintypes.DWORD),
                ("lpstrFileTitle", wintypes.LPWSTR),
                ("nMaxFileTitle", wintypes.DWORD),
                ("lpstrInitialDir", wintypes.LPCWSTR),
                ("lpstrTitle", wintypes.LPCWSTR),
                ("Flags", wintypes.DWORD),
                ("nFileOffset", wintypes.WORD),
                ("nFileExtension", wintypes.WORD),
                ("lpstrDefExt", wintypes.LPCWSTR),
                ("lCustData", wintypes.LPARAM),
                ("lpfnHook", ctypes.c_void_p),
                ("lpTemplateName", wintypes.LPCWSTR),
                ("pvReserved", ctypes.c_void_p),
                ("dwReserved", wintypes.DWORD),
                ("FlagsEx", wintypes.DWORD),
            ]

        buf = ctypes.create_unicode_buffer(4096)
        flt = "分子结构文件 (*.pdb;*.xyz;*.mol;*.sdf;*.cif;*.mol2;*.mforge)\0*.pdb;*.xyz;*.mol;*.sdf;*.cif;*.mol2;*.mforge\0所有文件 (*.*)\0*.*\0\0"
        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.lpstrFilter = flt
        ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
        ofn.nMaxFile = 4096
        ofn.lpstrTitle = "选择分子结构或晶体工程文件"
        ofn.Flags = 0x00080000 | 0x00001000 | 0x00000800 | 0x00000008  # EXPLORER | FILEMUSTEXIST | PATHMUSTEXIST | NOCHANGEDIR
        if ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return buf.value
    except Exception:
        return None
    return None


def _build_luts() -> tuple[np.ndarray, np.ndarray]:
    color_lut = np.full((120, 4), [140, 158, 178, 255], dtype=np.uint8)
    vdw_lut = np.full(120, float(DEFAULT_VDW), dtype=np.float32)
    for z, elem in ELEMENTS.items():
        if 0 <= z < 120:
            c = elem.cpk_color
            color_lut[z, :3] = [int(round(c[0] * 255)), int(round(c[1] * 255)), int(round(c[2] * 255))]
            vdw_lut[z] = float(elem.vdw_radius)
    for z, c in STUDIO_CPK_COLORS.items():
        if 0 <= z < 120:
            color_lut[z, :3] = [int(round(c[0] * 255)), int(round(c[1] * 255)), int(round(c[2] * 255))]
    return color_lut, vdw_lut


_COLOR_LUT, _VDW_LUT = _build_luts()


def _chemical_formula(doc: MoleculeDocument) -> str:
    counts: Counter[str] = Counter()
    for aid in doc.topology.atom_ids:
        counts[doc.topology.get_atom(aid).symbol] += 1
    if not counts:
        return "Empty"
    order = ["C", "H"] + sorted(k for k in counts if k not in ("C", "H"))
    parts = []
    for sym in order:
        n = counts.get(sym, 0)
        if n == 1:
            parts.append(sym)
        elif n > 1:
            parts.append(f"{sym}{n}")
    return "".join(parts)


class MolForgeBridgeState:
    """线程安全的 MolForge 后台状态容器，负责管理当前活动文档与撤销栈。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.document: MoleculeDocument = create_instant_caffeine_document()
        self.command_bus: CommandBus = CommandBus(self.document)
        self._last_binary_rev: int = -1
        self._cached_binary: bytes = b""
        self._source_path: str | None = None

    def set_document(self, doc: MoleculeDocument, source_path: str | None = None) -> None:
        with self._lock:
            self.document = doc
            self.command_bus = CommandBus(self.document)
            self._last_binary_rev = -1
            self._cached_binary = b""
            self._source_path = source_path

    def _invalidate_cache(self) -> None:
        self._last_binary_rev = -1
        self._cached_binary = b""

    def summary_dict(self) -> dict[str, Any]:
        with self._lock:
            doc = self.document
            n_atoms = doc.topology.num_atoms
            n_bonds = doc.topology.num_bonds
            coords = (
                doc.coordinates.current.coords
                if doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) == n_atoms
                else None
            )
            spin = resolve_spin_state(doc)
            if n_atoms <= 3000 and coords is not None and len(coords) > 0:
                geom = analyze_geometry_shape(coords)
                geom_label = geom.label
                point_group = geom.point_group
            elif n_atoms > 3000:
                geom_label = f"大体系 ({n_atoms:,} 原子 · GPU 管线)"
                point_group = "Periodic / Bulk"
            else:
                geom_label = "2D / 未计算"
                point_group = "未计算"

            total_charge = 0
            for aid in doc.topology.atom_ids:
                total_charge += int(getattr(doc.topology.get_atom(aid), "formal_charge", 0))
            if "charge" in doc.properties:
                try:
                    total_charge = int(doc.properties["charge"])
                except Exception:
                    pass

            cell = cell_from_document(doc)
            box_origin = doc.properties.get("box_origin")
            return {
                "name": doc.name or "Untitled",
                "formula": _chemical_formula(doc) if n_atoms <= 50000 else f"{n_atoms:,} atoms",
                "num_atoms": n_atoms,
                "num_bonds": n_bonds,
                "charge": total_charge,
                "multiplicity": spin.multiplicity,
                "spin_label": spin.label,
                "geometry_label": geom_label,
                "point_group": point_group,
                "revision": doc.revision,
                "can_undo": self.command_bus.can_undo,
                "can_redo": self.command_bus.can_redo,
                "has_2d": bool(doc.coords_2d),
                "has_3d": bool(doc.has_3d),
                "source_path": self._source_path or doc.source_path,
                "cell": cell.to_dict() if cell is not None else None,
                "box_origin": list(box_origin) if box_origin is not None else None,
                "presets": PRESET_MOLECULES,
            }

    def binary_payload(self) -> bytes:
        with self._lock:
            doc = self.document
            if self._last_binary_rev == doc.revision and self._cached_binary:
                return self._cached_binary

            aids, id2idx = doc.topology.atom_index_map()
            n = len(aids)
            b_ids = list(doc.topology.bond_ids)
            b_cnt = len(b_ids)

            if n > 0 and doc.has_3d and doc.coordinates.current is not None and len(doc.coordinates.current.coords) == n:
                coords = np.ascontiguousarray(doc.coordinates.current.coords, dtype=np.float32)
            elif n > 0 and doc.coords_2d:
                coords = np.zeros((n, 3), dtype=np.float32)
                for idx, aid in enumerate(aids):
                    p = doc.coords_2d.get(aid)
                    if p is not None:
                        coords[idx, 0] = float(p[0])
                        coords[idx, 1] = float(p[1])
            else:
                coords = np.zeros((0, 3), dtype=np.float32)

            z_arr = np.fromiter((doc.topology.get_atom(aid).atomic_num for aid in aids), dtype=np.int32, count=n)
            z_clip = np.clip(z_arr, 0, 119)
            z_u8 = z_clip.astype(np.uint8)
            vdw = _VDW_LUT[z_clip].astype(np.float32)
            rgba = _COLOR_LUT[z_clip].copy()

            for idx, aid in enumerate(aids):
                atom = doc.topology.get_atom(aid)
                col = getattr(atom, "color", None)
                if col is not None:
                    rgba[idx, 0] = max(0, min(255, int(round(float(col[0]) * 255.0))))
                    rgba[idx, 1] = max(0, min(255, int(round(float(col[1]) * 255.0))))
                    rgba[idx, 2] = max(0, min(255, int(round(float(col[2]) * 255.0))))
                op = atom.properties.get("opacity", 1.0)
                if op != 1.0:
                    rgba[idx, 3] = max(0, min(255, int(round(float(op) * 255.0))))
                sc = getattr(atom, "scale", 1.0)
                if sc != 1.0:
                    vdw[idx] *= float(sc)

            if b_cnt > 0:
                bond_pairs = np.empty((b_cnt, 2), dtype=np.uint32)
                bond_orders = np.empty(b_cnt, dtype=np.uint8)
                valid_count = 0
                for bid in b_ids:
                    bond = doc.topology.get_bond(bid)
                    i = id2idx.get(bond.begin, -1)
                    j = id2idx.get(bond.end, -1)
                    if 0 <= i < n and 0 <= j < n and i != j:
                        bond_pairs[valid_count, 0] = i
                        bond_pairs[valid_count, 1] = j
                        bond_orders[valid_count] = max(1, min(4, int(bond.order)))
                        valid_count += 1
                bond_pairs = np.ascontiguousarray(bond_pairs[:valid_count])
                bond_orders = np.ascontiguousarray(bond_orders[:valid_count])
            else:
                bond_pairs = np.zeros((0, 2), dtype=np.uint32)
                bond_orders = np.zeros(0, dtype=np.uint8)
                valid_count = 0

            cell = cell_from_document(doc)
            has_cell = 1 if cell is not None else 0
            box_origin = np.asarray(doc.properties.get("box_origin") or [0.0, 0.0, 0.0], dtype=np.float32).reshape(3)

            header = struct.pack("<8I", MAGIC_MOLF, 1, n, valid_count, int(doc.revision), has_cell, 0, 0)
            z_pad = (-len(z_u8)) % 4
            bo_pad = (-len(bond_orders)) % 4

            chunks = [
                header,
                coords.tobytes(),
                z_u8.tobytes(),
                b"\x00" * z_pad,
                vdw.tobytes(),
                rgba.tobytes(),
                bond_pairs.tobytes(),
                bond_orders.tobytes(),
                b"\x00" * bo_pad,
            ]
            if has_cell:
                cell_mat = np.ascontiguousarray(cell.matrix, dtype=np.float32).reshape(9)
                chunks.append(np.ascontiguousarray(box_origin, dtype=np.float32).tobytes())
                chunks.append(cell_mat.tobytes())

            payload = b"".join(chunks)
            self._last_binary_rev = doc.revision
            self._cached_binary = payload
            return payload

    def atoms_2d_dict(self, limit: int = 1500) -> dict[str, Any]:
        with self._lock:
            doc = self.document
            aids, id2idx = doc.topology.atom_index_map()
            n = len(aids)
            if n > limit:
                return {"truncated": True, "num_atoms": n, "atoms": [], "bonds": []}

            coords_3d = doc.coordinates.current.coords if doc.has_3d and doc.coordinates.current is not None else None
            atoms_out = []
            for idx, aid in enumerate(aids):
                atom = doc.topology.get_atom(aid)
                p2 = doc.coords_2d.get(aid)
                p3 = coords_3d[idx] if coords_3d is not None and idx < len(coords_3d) else (0.0, 0.0, 0.0)
                col = getattr(atom, "color", None) or STUDIO_CPK_COLORS.get(atom.atomic_num, (0.55, 0.62, 0.70))
                atoms_out.append({
                    "index": idx,
                    "atom_id": aid.value,
                    "display_id": aid.value + 1,
                    "symbol": atom.symbol,
                    "atomic_num": atom.atomic_num,
                    "x2": float(p2[0]) if p2 is not None else float(p3[0]),
                    "y2": float(p2[1]) if p2 is not None else float(p3[1]),
                    "x": float(p3[0]),
                    "y": float(p3[1]),
                    "z": float(p3[2]),
                    "formal_charge": int(getattr(atom, "formal_charge", 0)),
                    "color": [int(round(col[0] * 255)), int(round(col[1] * 255)), int(round(col[2] * 255))],
                })
            bonds_out = []
            for bid in doc.topology.bond_ids:
                bond = doc.topology.get_bond(bid)
                i = id2idx.get(bond.begin, -1)
                j = id2idx.get(bond.end, -1)
                if 0 <= i < n and 0 <= j < n:
                    bonds_out.append({
                        "bond_id": bid.value,
                        "i": i,
                        "j": j,
                        "order": int(bond.order),
                        "aromatic": bool(getattr(bond, "aromatic", False)),
                    })
            return {"truncated": False, "num_atoms": n, "atoms": atoms_out, "bonds": bonds_out}

    def compute_qc_tb(self) -> dict[str, Any]:
        with self._lock:
            doc = self.document
            if doc.topology.num_atoms == 0:
                return {"error": "当前分子为空"}
            if doc.topology.num_atoms > 350:
                return {
                    "skipped": True,
                    "reason": f"体系含 {doc.topology.num_atoms:,} 个原子，已跳过实时 O(N³) Tight-Binding 对角化；可导出 PDB/GJF 或切换小分子。",
                    "references": [
                        {"name": k, "homo_ev": v[0], "lumo_ev": v[1], "color": v[2]}
                        for k, v in OSC_REFERENCE_MATERIALS.items()
                    ],
                }
            tb = compute_tight_binding_mos(doc)
            tb["molecule_name"] = doc.name or "当前分子"
            tb["formula"] = _chemical_formula(doc)
            tb["references"] = [
                {"name": k, "homo_ev": v[0], "lumo_ev": v[1], "color": v[2]}
                for k, v in OSC_REFERENCE_MATERIALS.items()
            ]
            return tb

    def analysis_catalog(self) -> list[dict[str, Any]]:
        with self._lock:
            doc = self.document
            out = []
            for defn in AnalysisRegistry.all():
                st, msg = CapabilityResolver.resolve_status(defn.analysis_id, doc)
                out.append({
                    "id": defn.analysis_id,
                    "category": defn.category,
                    "title": defn.title,
                    "engine": defn.backend_engine,
                    "state": st.value,
                    "note": msg,
                })
            return out

    def run_analysis(self, analysis_id: str) -> dict[str, Any]:
        with self._lock:
            res = CapabilityResolver.execute_analysis(analysis_id, self.document)
            lines = []
            if res.warnings:
                lines.extend(res.warnings)
            prov_note = getattr(res.provenance, "notes", "") if res.provenance else ""
            if prov_note:
                lines.append(prov_note)
            if not lines and res.metrics:
                lines.append(f"已完成 {res.title} ({res.status})")
            return {
                "analysis_id": res.analysis_id,
                "title": res.title,
                "status": res.status,
                "summary": "\n".join(lines) or res.title,
                "metrics": dict(res.metrics or {}),
                "plot_x": list(res.plot_x or []),
                "plot_y": list(res.plot_y or []),
                "x_label": getattr(res, "plot_xlabel", ""),
                "y_label": getattr(res, "plot_ylabel", ""),
            }

    def export_text(self, fmt: str) -> tuple[str, str]:
        with self._lock:
            doc = self.document
            stem = (doc.name or "molecule").replace(" ", "_")
            f = fmt.lower().strip()
            if f == "pdb":
                return f"{stem}.pdb", export_document_to_pdb(doc)
            if f == "mol":
                return f"{stem}.mol", export_document_to_mol_v2000(doc)
            if f == "gjf":
                return f"{stem}.gjf", generate_gaussian_gjf(doc)
            if f == "rest":
                return "ctrl.in", generate_rest_ctrl_in(doc)
            xyz_lines = []
            from ..application.calculators.qc_input_generator import extract_xyz_lines
            body = extract_xyz_lines(doc)
            xyz_lines.append(str(len(body)))
            xyz_lines.append(f"{doc.name or 'MolForge'} | {_chemical_formula(doc)}")
            xyz_lines.extend(body)
            return f"{stem}.xyz", "\n".join(xyz_lines) + "\n"

    def handle_ai_prompt(self, prompt: str) -> dict[str, Any]:
        text = prompt.strip()
        lower = text.lower()
        blocks: list[dict[str, Any]] = []
        reply_parts: list[str] = []

        if any(k in lower for k in ("构建", "生成", "画", "build", "smiles")) and any(
            k in lower for k in ("苯", "咖啡因", "阿司匹林", "噻吩", "pentacene", "caffeine", "aspirin", "smiles:")
        ):
            target_preset = None
            if "阿司匹林" in text or "aspirin" in lower:
                target_preset = PRESET_MOLECULES[4]
            elif "五并苯" in text or "pentacene" in lower:
                target_preset = PRESET_MOLECULES[2]
            elif "噻吩" in text:
                target_preset = PRESET_MOLECULES[3]
            elif "苯" in text:
                target_preset = PRESET_MOLECULES[1]
            elif "咖啡因" in text or "caffeine" in lower:
                target_preset = PRESET_MOLECULES[0]

            if target_preset is not None:
                doc = create_molecule_from_smiles(target_preset["smiles"], target_preset["name"])
                self.set_document(doc)
                reply_parts.append(
                    f"已调用 MolForge RDKit ETKDG 引擎为您构建 **{target_preset['name']}**（`{target_preset['smiles']}`），并同步生成 2D 矢量图与 3D 构象。"
                )
                blocks.append({
                    "type": "action_row",
                    "title": "结构已更新",
                    "actions": [
                        {"label": "打开 OSC 能级图", "action": "open_qc_modal"},
                        {"label": "3D 几何优化", "action": "clean_3d"},
                    ],
                })

        summary = self.summary_dict()
        reply_parts.append(
            f"当前工作区活动分子为 **{summary['name']}**（`{summary['formula']}`，{summary['num_atoms']:,} 原子，{summary['num_bonds']:,} 键）。"
        )
        blocks.append({
            "type": "metrics_card",
            "title": f"{summary['name']} · 结构与化学态",
            "items": [
                {"label": "化学式", "value": summary["formula"]},
                {"label": "原子 / 键", "value": f"{summary['num_atoms']:,} / {summary['num_bonds']:,}"},
                {"label": "电荷 / 自旋", "value": f"{summary['charge']} / {summary['spin_label']}"},
                {"label": "几何形态", "value": summary["geometry_label"]},
            ],
        })

        qc = self.compute_qc_tb()
        if not qc.get("skipped") and not qc.get("error"):
            homo = float(qc.get("homo_ev", 0.0))
            lumo = float(qc.get("lumo_ev", 0.0))
            gap = float(qc.get("gap_ev", abs(lumo - homo)))
            trans = qc.get("transitions") or []
            s1_text = f"{trans[0]['wavelength_nm']:.1f} nm (f={trans[0]['oscillator_f']:.3f})" if trans else "—"
            blocks.append({
                "type": "orbital_card",
                "title": f"Tight-Binding 前线轨道实算 ({summary['name']})",
                "homo_ev": round(homo, 3),
                "lumo_ev": round(lumo, 3),
                "gap_ev": round(gap, 3),
                "s1_text": s1_text,
                "pm6_match": abs(lumo - (-3.61)) > 0.25 and abs(homo - (-5.50)) < 0.8,
            })
            reply_parts.append(
                f"实时紧束缚求解得到 **HOMO = {homo:.3f} eV**、**LUMO = {lumo:.3f} eV**、能隙 **E_g = {gap:.3f} eV**。"
            )
        else:
            reply_parts.append(qc.get("reason", ""))

        try:
            import urllib.request
            from ..ai.mcp_bridge import get_llm_config
            cfg = get_llm_config()
            base_url = (cfg.get("base_url") or "").rstrip("/")
            if base_url and "127.0.0.1" in base_url:
                req = urllib.request.Request(
                    f"{base_url}/chat/completions",
                    data=json.dumps({
                        "model": cfg.get("model") or "gemini-3.8-flash",
                        "messages": [
                            {"role": "system", "content": "你是 MolForge 计算化学 AI 副驾驶，用简练严谨的中文回答科研建议（不超过120字）。"},
                            {"role": "user", "content": f"当前分子: {summary['name']} ({summary['formula']}, {summary['num_atoms']} atoms)。用户提问: {text}"},
                        ],
                        "max_tokens": 220,
                    }).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        **({"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {}),
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    ai_msg = payload["choices"][0]["message"]["content"].strip()
                    if ai_msg:
                        reply_parts.append(ai_msg)
        except Exception:
            pass

        return {
            "reply": "\n\n".join(p for p in reply_parts if p),
            "a2ui_blocks": blocks,
            "document": summary,
        }


def _elements_catalog() -> list[dict[str, Any]]:
    items = []
    for z in sorted(ELEMENTS.keys()):
        el = ELEMENTS[z]
        r, g, b = el.cpk_color
        br = min(1.0, r * 1.15 + 0.08)
        bg_g = min(1.0, g * 1.15 + 0.08)
        bb = min(1.0, b * 1.15 + 0.08)
        hex_bg = f"#{int(br * 255):02X}{int(bg_g * 255):02X}{int(bb * 255):02X}"
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        fg = "#0F172A" if lum > 0.6 else "#F8FAFC"
        items.append({
            "atomic_number": el.atomic_number,
            "symbol": el.symbol,
            "name": el.name,
            "name_cn": el.name_cn,
            "atomic_weight": float(el.atomic_weight),
            "electronegativity": float(el.electronegativity) if el.electronegativity is not None else None,
            "vdw_radius": float(el.vdw_radius),
            "covalent_radius": float(el.covalent_radius),
            "electron_config": el.electron_config,
            "group": int(el.group),
            "period": int(el.period),
            "block": el.block,
            "category": el.category,
            "hex_color": hex_bg,
            "text_color": fg,
        })
    return items


def make_handler(state: MolForgeBridgeState):
    class BridgeHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def _send_json(self, obj: Any, status: int = 200) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._send_cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_bytes(self, data: bytes, status: int = 200) -> None:
            self.send_response(status)
            self._send_cors()
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def do_OPTIONS(self) -> None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            try:
                if path == "/api/health":
                    self._send_json({
                        "ok": True,
                        "service": "MolForge Chemical Engine Bridge",
                        "version": "8.0.0-alpha.2",
                        "document": state.summary_dict(),
                    })
                elif path == "/api/document":
                    self._send_json(state.summary_dict())
                elif path == "/api/document/binary":
                    self._send_bytes(state.binary_payload())
                elif path == "/api/atoms":
                    self._send_json(state.atoms_2d_dict())
                elif path == "/api/elements":
                    self._send_json({"elements": _elements_catalog()})
                elif path == "/api/analysis/catalog":
                    self._send_json({"items": state.analysis_catalog()})
                else:
                    self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
            except Exception as exc:
                self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                body = self._read_json()
                if path == "/api/build/smiles":
                    smiles = str(body.get("smiles", "")).strip()
                    name = str(body.get("name", "")).strip() or smiles
                    if not smiles:
                        return self._send_json({"error": "SMILES 不能为空"}, status=400)
                    doc = create_molecule_from_smiles(smiles, name)
                    state.set_document(doc)
                    return self._send_json({"ok": True, "document": state.summary_dict()})

                if path == "/api/build/preset":
                    preset_id = str(body.get("id", "caffeine")).strip().lower()
                    item = next((p for p in PRESET_MOLECULES if p["id"] == preset_id or p["name"] == preset_id), None)
                    if preset_id == "caffeine" or (item and item["id"] == "caffeine"):
                        doc = create_instant_caffeine_document()
                    elif preset_id == "triplet_o2":
                        doc = MoleculeDocument(name="Triplet O₂ (³Σg⁻)")
                        a0 = doc.topology.add_atom(8)
                        a1 = doc.topology.add_atom(8)
                        doc.topology.add_bond(a0, a1, order=2)
                        doc.ensure_coordinates()
                        doc.coordinates.current.coords[0] = [-0.604, 0.0, 0.0]
                        doc.coordinates.current.coords[1] = [0.604, 0.0, 0.0]
                        doc.coords_2d = {a0: (-0.604, 0.0), a1: (0.604, 0.0)}
                        doc.properties["multiplicity"] = 3
                    elif item is not None:
                        doc = create_molecule_from_smiles(item["smiles"], item["name"])
                    else:
                        doc = create_sample_molecule(str(body.get("name", "咖啡因")))
                    state.set_document(doc)
                    return self._send_json({"ok": True, "document": state.summary_dict()})

                if path == "/api/open":
                    fpath = Path(str(body.get("path", "")).strip())
                    if not fpath.is_file():
                        return self._send_json({"error": f"文件不存在: {fpath}"}, status=404)
                    t0 = time.perf_counter()
                    doc, meta = load_molecule_document(fpath)
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    state.set_document(doc, source_path=str(fpath))
                    return self._send_json({"ok": True, "parse_ms": round(dt_ms, 1), "meta": meta, "document": state.summary_dict()})

                if path == "/api/dialog/open_file":
                    chosen = _pick_native_open_file_windows()
                    if not chosen:
                        return self._send_json({"ok": False, "cancelled": True})
                    fpath = Path(chosen)
                    t0 = time.perf_counter()
                    doc, meta = load_molecule_document(fpath)
                    dt_ms = (time.perf_counter() - t0) * 1000.0
                    state.set_document(doc, source_path=str(fpath))
                    return self._send_json({
                        "ok": True,
                        "cancelled": False,
                        "path": str(fpath),
                        "parse_ms": round(dt_ms, 1),
                        "document": state.summary_dict(),
                    })

                if path == "/api/edit/undo":
                    with state._lock:
                        ok = state.command_bus.undo().success
                        state._invalidate_cache()
                    return self._send_json({"ok": ok, "document": state.summary_dict()})

                if path == "/api/edit/redo":
                    with state._lock:
                        ok = state.command_bus.redo().success
                        state._invalidate_cache()
                    return self._send_json({"ok": ok, "document": state.summary_dict()})

                if path == "/api/edit/clean_3d":
                    with state._lock:
                        res = state.command_bus.execute(CleanGeometry3DCommand())
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "message": res.message, "document": state.summary_dict()})

                if path == "/api/edit/delete_atoms":
                    ids = [AtomId(int(x)) for x in body.get("atom_ids", [])]
                    with state._lock:
                        ok = True
                        for aid in ids:
                            r = state.command_bus.execute(DeleteAtomCommand(aid))
                            ok = ok and r.success
                        state._invalidate_cache()
                    return self._send_json({"ok": ok, "document": state.summary_dict()})

                if path == "/api/edit/delete_indices":
                    indices = [int(x) for x in body.get("indices", [])]
                    with state._lock:
                        aids, _ = state.document.topology.atom_index_map()
                        targets = [aids[i] for i in indices if 0 <= i < len(aids)]
                        ok = bool(targets)
                        for aid in targets:
                            r = state.command_bus.execute(DeleteAtomCommand(aid))
                            ok = ok and r.success
                        state._invalidate_cache()
                    return self._send_json({"ok": ok, "document": state.summary_dict()})

                if path == "/api/edit/add_atom":
                    atomic_num = int(body.get("atomic_num", 6))
                    pos_2d_raw = body.get("pos_2d")
                    pos_3d_raw = body.get("pos")
                    bond_to = body.get("bond_to")
                    with state._lock:
                        if pos_3d_raw is not None:
                            x, y, z = float(pos_3d_raw[0]), float(pos_3d_raw[1]), float(pos_3d_raw[2])
                        elif pos_2d_raw is not None:
                            x, y, z = float(pos_2d_raw[0]), float(pos_2d_raw[1]), 0.0
                        else:
                            x, y, z = None, None, None
                        cmd = AddAtomCommand(
                            atomic_num=atomic_num,
                            x=x,
                            y=y,
                            z=z,
                            bond_to=AtomId(int(bond_to)) if bond_to is not None else None,
                            pos_2d=(float(pos_2d_raw[0]), float(pos_2d_raw[1])) if pos_2d_raw is not None else None,
                        )
                        res = state.command_bus.execute(cmd)
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/add_bond":
                    a = int(body["atom_a"])
                    b = int(body["atom_b"])
                    order = int(body.get("order", 1))
                    with state._lock:
                        res = state.command_bus.execute(AddBondCommand(AtomId(a), AtomId(b), order=order))
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/delete_bond":
                    bid = int(body["bond_id"])
                    with state._lock:
                        res = state.command_bus.execute(DeleteBondCommand(BondId(bid)))
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/cycle_bond_order":
                    bid = BondId(int(body["bond_id"]))
                    with state._lock:
                        bond = state.document.topology.get_bond(bid)
                        nxt = {1: 2, 2: 3, 3: 4, 4: 1}.get(int(bond.order), 1)
                        res = state.command_bus.execute(ChangeBondOrderCommand(bid, nxt))
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/change_element":
                    aid = AtomId(int(body["atom_id"]))
                    z = int(body["atomic_num"])
                    with state._lock:
                        res = state.command_bus.execute(ChangeElementCommand(aid, z))
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/add_ring":
                    size = int(body.get("size", 6))
                    aromatic = bool(body.get("aromatic", True))
                    hetero_raw = body.get("hetero") or {}
                    hetero = {int(k): int(v) for k, v in hetero_raw.items()}
                    attach_to = body.get("attach_to")
                    c2d = body.get("center_2d")
                    with state._lock:
                        cmd = AddRingCommand(
                            size=size,
                            aromatic=aromatic,
                            hetero_atoms=hetero,
                            center_2d=(float(c2d[0]), float(c2d[1])) if c2d is not None else None,
                            attach_to=AtomId(int(attach_to)) if attach_to is not None else None,
                        )
                        res = state.command_bus.execute(cmd)
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/move_atom":
                    aid = AtomId(int(body["atom_id"]))
                    p2 = body.get("pos_2d")
                    with state._lock:
                        old_3d = state.document.get_atom_3d_pos(aid).copy()
                        old_2d = state.document.coords_2d.get(aid)
                        new_x = float(p2[0]) if p2 is not None else float(old_3d[0])
                        new_y = float(p2[1]) if p2 is not None else float(old_3d[1])
                        cmd = MoveAtom3DCommand(
                            aid,
                            (new_x, new_y, float(old_3d[2])),
                            old_pos=old_3d,
                            new_pos_2d=(new_x, new_y),
                            old_pos_2d=old_2d,
                        )
                        res = state.command_bus.execute(cmd)
                        state._invalidate_cache()
                    return self._send_json({"ok": res.success, "document": state.summary_dict()})

                if path == "/api/edit/set_charge_spin":
                    with state._lock:
                        if "charge" in body:
                            state.document.properties["charge"] = int(body["charge"])
                        if "multiplicity" in body:
                            state.document.properties["multiplicity"] = max(1, int(body["multiplicity"]))
                        state._invalidate_cache()
                    return self._send_json({"ok": True, "document": state.summary_dict()})

                if path == "/api/export":
                    fmt = str(body.get("format", "xyz"))
                    fname, content = state.export_text(fmt)
                    return self._send_json({"ok": True, "filename": fname, "content": content})

                if path == "/api/qc/tight_binding":
                    return self._send_json(state.compute_qc_tb())

                if path == "/api/qc/export_input":
                    kind = str(body.get("kind", "gaussian")).lower()
                    route = str(body.get("route", "#p B3LYP/6-31G(d) EmpiricalDispersion=GD3BJ opt freq"))
                    charge = int(body.get("charge", state.document.properties.get("charge", 0)))
                    spin = int(body.get("multiplicity", resolve_spin_state(state.document).multiplicity))
                    if kind == "rest":
                        txt = generate_rest_ctrl_in(
                            state.document,
                            xc=str(body.get("xc", "b3lyp")),
                            basis=str(body.get("basis", "def2-SVP")),
                            charge=float(charge),
                            spin=spin,
                        )
                    else:
                        txt = generate_gaussian_gjf(state.document, route=route, charge=charge, multiplicity=spin)
                    return self._send_json({"ok": True, "kind": kind, "content": txt})

                if path == "/api/analysis/run":
                    aid = str(body.get("analysis_id", "")).strip()
                    if not aid:
                        return self._send_json({"error": "analysis_id 不能为空"}, status=400)
                    return self._send_json({"ok": True, "result": state.run_analysis(aid)})

                if path == "/api/ai/chat":
                    prompt = str(body.get("prompt", "")).strip()
                    if not prompt:
                        return self._send_json({"error": "提问内容不能为空"}, status=400)
                    return self._send_json(state.handle_ai_prompt(prompt))

                return self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
            except Exception as exc:
                return self._send_json({"error": str(exc), "trace": traceback.format_exc()}, status=500)

    return BridgeHandler


def start_bridge_server(host: str = "127.0.0.1", port: int = 18765) -> tuple[ThreadingHTTPServer, MolForgeBridgeState]:
    state = MolForgeBridgeState()
    server = ThreadingHTTPServer((host, port), make_handler(state))
    return server, state


def main() -> None:
    parser = argparse.ArgumentParser(description="MolForge Next-Gen Chemical Engine HTTP/Binary Bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18765)
    args = parser.parse_args()
    server, _ = start_bridge_server(args.host, args.port)
    print(f"[MolForge Bridge] listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
