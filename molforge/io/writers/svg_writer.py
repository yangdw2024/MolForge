"""
svg_writer.py - 2D 结构图导出 SVG
===================================
用 RDKit 的 MolToFile 直接写 SVG。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem, Draw
from rdkit.Chem.Draw import rdMolDraw2D

from ..registry import FormatHandler, register
from ...core.molecule import Molecule


def write_svg_2d(doc: Any, path: str | Path, width: int = 800, height: int = 560) -> None:
    """将 MoleculeDocument 或 Molecule 导出为高清晰度 2D SVG 矢量图。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(doc, Molecule) and getattr(doc, "rdkit_mol", None) is not None:
        Draw.MolToFile(doc.rdkit_mol, str(out), size=(width, height), kekulize=True)
        return

    from ..rdkit_adapter import doc_to_rdkit

    try:
        rdmol, aid_to_idx, _ = doc_to_rdkit(doc, sanitize=True, strict=False)
        if rdmol.GetNumAtoms() > 0:
            coords_2d = getattr(doc, "coords_2d", {}) or {}
            if len(coords_2d) >= rdmol.GetNumAtoms():
                conf = Chem.Conformer(rdmol.GetNumAtoms())
                conf.Set3D(False)
                for aid, idx in aid_to_idx.items():
                    x, y = coords_2d.get(aid, (0.0, 0.0))
                    conf.SetAtomPosition(idx, (float(x), float(-y), 0.0))
                rdmol.RemoveAllConformers()
                rdmol.AddConformer(conf, assignId=True)
            else:
                AllChem.Compute2DCoords(rdmol)
            drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
            try:
                drawer.DrawMolecule(rdmol)
            except Exception:
                rdMolDraw2D.PrepareAndDrawMolecule(drawer, rdmol, kekulize=False)
            drawer.FinishDrawing()
            out.write_text(drawer.GetDrawingText(), encoding="utf-8")
            return
    except Exception:
        pass

    # 纯 Python 回退 SVG（避免超非常规价态/异常结构导出失败）
    from ...domain.elements import get_element
    coords_2d = getattr(doc, "coords_2d", {}) or {}
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    if hasattr(doc, "topology") and doc.topology.num_atoms > 0:
        xs = [coords_2d.get(aid, (0.0, 0.0))[0] for aid in doc.topology.atom_ids]
        ys = [coords_2d.get(aid, (0.0, 0.0))[1] for aid in doc.topology.atom_ids]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span = max(max_x - min_x, max_y - min_y, 1.0)
        pad = 48.0
        scale = min(width - 2 * pad, height - 2 * pad) / span

        def _tx(x: float, y: float) -> tuple[float, float]:
            return (
                width * 0.5 + (x - (min_x + max_x) * 0.5) * scale,
                height * 0.5 + (y - (min_y + max_y) * 0.5) * scale,
            )

        for bid in doc.topology.bond_ids:
            b = doc.topology.get_bond(bid)
            x1, y1 = _tx(*coords_2d.get(b.begin, (0.0, 0.0)))
            x2, y2 = _tx(*coords_2d.get(b.end, (0.0, 0.0)))
            lines.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#222" stroke-width="2"/>')
        for aid in doc.topology.atom_ids:
            atom = doc.topology.get_atom(aid)
            if atom.atomic_num == 6:
                continue
            x, y = _tx(*coords_2d.get(aid, (0.0, 0.0)))
            elem = get_element(atom.atomic_num)
            sym = elem.symbol if elem else "?"
            lines.append(
                f'<text x="{x:.1f}" y="{y + 4:.1f}" font-family="sans-serif" font-size="13" '
                f'text-anchor="middle" fill="#111">{sym}</text>'
            )
    lines.append("</svg>")
    out.write_text("\n".join(lines), encoding="utf-8")


@register
class SvgWriter(FormatHandler):
    name = "SVG"
    extensions = [".svg"]
    description = "SVG 矢量图"
    can_read = False
    can_write = True

    def write(self, mol: Molecule, path: Path) -> None:
        Draw.MolToFile(
            mol.rdkit_mol,
            str(path),
            size=(600, 400),
            kekulize=True,
        )
