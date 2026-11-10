"""
glog_reader.py - Gaussian log 解析器（支持 Standard / Input / Z-Matrix orientation 与全 118 元素）
"""
from __future__ import annotations

import re
from pathlib import Path
import numpy as np
from rdkit import Chem

from ..registry import FormatHandler, register
from ...core.molecule import Molecule
from ...core.conformer import Conformer
from ...core.orbital import Orbital
from ..rdkit_adapter import doc_to_rdkit, parse_gaussian_log_to_document


@register
class GaussianLogReader(FormatHandler):
    name = "Gaussian Log"
    extensions = [".log", ".out"]
    description = "Gaussian / ORCA / REST 输出文件"
    can_read = True
    can_write = False

    def read(self, path: Path) -> Molecule:
        doc, props = parse_gaussian_log_to_document(path)
        rdmol, _, _ = doc_to_rdkit(doc, sanitize=True)
        m = Molecule.from_rdkit(rdmol, name=path.stem, attach_conformers=False)
        m.source_format = "gaussian_log"
        m.source_path = path
        m.energy = (props.get("energy_ev") / 27.211386) if props.get("energy_ev") else None
        m.properties.update(props)
        if doc.has_3d and doc.coordinates.current is not None:
            m.conformers.append(Conformer(
                coords=doc.coordinates.current.coords.copy(),
                energy=m.energy,
                source="gaussian_optimized",
            ))
        if props.get("homo_ev") and props.get("lumo_ev"):
            m.orbitals = [
                Orbital(index=1, energy_ev=float(props["homo_ev"]), occupation=2.0),
                Orbital(index=2, energy_ev=float(props["lumo_ev"]), occupation=0.0),
            ]
        return m
