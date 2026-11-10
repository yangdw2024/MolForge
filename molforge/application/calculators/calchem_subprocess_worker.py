"""
molforge/application/calculators/calchem_subprocess_worker.py
============================================================
在独立子进程中运行 CalChem 纯 Rust 密集计算（单点自洽场 / BFGS 几何优化），
彻底避免底层 C/Rust 扩展因未释放 GIL 而导致 PyQt6 GUI 主线程未响应或卡死。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 确保 Trae_Gaussian / calchem 可被加载
TRAE_GAUSSIAN = Path(r"E:\YDW\Trae_Gaussian")
if TRAE_GAUSSIAN.exists() and str(TRAE_GAUSSIAN) not in sys.path:
    sys.path.insert(0, str(TRAE_GAUSSIAN))

ANGSTROM_TO_BOHR = 1.8897261245650618
BOHR_TO_ANGSTROM = 0.529177210903


def main():
    parser = argparse.ArgumentParser(description="CalChem Subprocess Worker")
    parser.add_argument("--task", choices=["sp", "opt"], required=True)
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        symbols = data["symbols"]
        geom_ang = data["geometry_angstrom"]
        geom_bohr = [[float(c * ANGSTROM_TO_BOHR) for c in pos] for pos in geom_ang]
        charge = int(data.get("charge", 0))
        multiplicity = int(data.get("multiplicity", 1))
        basis = data.get("basis", "sto-3g").lower()
        max_steps = int(data.get("max_steps", 40))

        from calchem import _core

        t0 = time.time()
        if args.task == "sp":
            wf = _core.run_single_point(
                symbols=symbols,
                geometry_bohr=geom_bohr,
                charge=charge,
                multiplicity=multiplicity,
                method="rhf",
                basis=basis,
            )
            elapsed = time.time() - t0
            homo_e = wf.homo_energy_hartree
            lumo_e = wf.lumo_energy_hartree
            gap_ev = (lumo_e - homo_e) * 27.211386245988 if (homo_e is not None and lumo_e is not None) else None
            res = {
                "success": True,
                "converged": wf.converged,
                "total_energy_hartree": wf.total_energy_hartree,
                "homo_energy_hartree": homo_e,
                "lumo_energy_hartree": lumo_e,
                "gap_ev": gap_ev,
                "elapsed_seconds": elapsed,
            }
        elif args.task == "opt":
            opt_res = _core.run_optimize(
                symbols,
                geom_bohr,
                basis=basis,
                max_steps=max_steps,
                charge=charge,
                multiplicity=multiplicity,
            )
            elapsed = time.time() - t0
            import numpy as np
            n_atoms = len(symbols)
            coords_bohr = np.array(opt_res.coords, dtype=np.float64).reshape(n_atoms, 3)
            coords_ang = (coords_bohr * BOHR_TO_ANGSTROM).tolist()

            res = {
                "success": True,
                "converged": opt_res.converged,
                "energy_hartree": opt_res.energy,
                "steps": opt_res.steps,
                "coords": coords_ang,
                "elapsed_seconds": elapsed,
            }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)

    except Exception as exc:
        err_res = {"success": False, "error": str(exc)}
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(err_res, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
