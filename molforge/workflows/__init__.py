from __future__ import annotations
import importlib.util as _ilu
import sys as _sys
from pathlib import Path as _Path

_PKG_DIR = _Path(__file__).resolve().parent
for _mod_name in (
    "esp_surface",
    "homo_lumo_plot",
    "osc_energy_diagram",
    "reorganization_energy",
    "dipole_analysis",
    "planarity_analysis",
    "md_rdf_analysis",
    "igmh_interaction",
):
    _full = f"{__name__}.{_mod_name}"
    _fp = _PKG_DIR / f"{_mod_name}.py"
    if _full not in _sys.modules and _fp.is_file():
        _spec = _ilu.spec_from_file_location(_full, str(_fp))
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _sys.modules[_full] = _mod
            _spec.loader.exec_module(_mod)
            globals()[_mod_name] = _mod
