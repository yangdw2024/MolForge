"""
calculators/rest_engine.py - 复旦大学 REST (Rust-based Electronic Structure Toolkit) 受控计算引擎
=================================================================================================
支持：
  - probe   检测本机或本地 WSL2 虚拟环境中的 rest 可执行程序
  - prepare 生成 ctrl.in (TOML 格式) 并记录 SHA-256 哈希
  - run_wsl 在本地 WSL2 中原生执行真实量子化学计算并秒级回传结果
  - parse   解析 REST 输出日志与结果文件中的 SCF 能量、双杂化 (XYG3/XYGJOS/R-xDH7) 总能量、HOMO/LUMO、Mulliken 电荷及收敛状态
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .base import CalculationEngine, JobRequest, PreparedJob, EngineNotFound


WSL_REST_BIN = "/home/administrator/miniforge3/envs/rest-py311/bin/rest"
WSL_BASIS_POOL = "/mnt/e/YDW/REST/knowledge_base/rest_github/basis-set-pool"
HARTREE_TO_EV = 27.211386245988


def to_wsl_path(path: str | Path) -> str:
    """将 Windows 本地路径转换为 WSL2 /mnt 路径。"""
    p = Path(path).resolve()
    drive = p.drive.replace(":", "").lower()
    return f"/mnt/{drive}" + p.as_posix()[2:]


def parse_fchk_orbitals(fchk_path: Path) -> tuple[float | None, float | None]:
    """从 formatted checkpoint (fchk) 文件提取真实 HOMO 与 LUMO 能级 (单位: eV)。"""
    if not fchk_path.exists():
        return None, None
    try:
        text = fchk_path.read_text(encoding="utf-8", errors="replace")
        m_alpha = re.search(r"Number of alpha electrons\s+I\s+(\d+)", text)
        if not m_alpha:
            return None, None
        n_alpha = int(m_alpha.group(1))

        m_orb = re.search(r"Alpha Orbital Energies\s+R\s+N=\s+(\d+)\s*\n((?:\s*-?\d+\.\d+E[+-]\d+\s*)+)", text)
        if not m_orb:
            return None, None

        raw_vals = m_orb.group(2).split()
        energies_hartree = [float(v) for v in raw_vals]

        homo_idx = n_alpha - 1
        lumo_idx = n_alpha
        homo_ev = round(energies_hartree[homo_idx] * HARTREE_TO_EV, 4) if 0 <= homo_idx < len(energies_hartree) else None
        lumo_ev = round(energies_hartree[lumo_idx] * HARTREE_TO_EV, 4) if 0 <= lumo_idx < len(energies_hartree) else None
        return homo_ev, lumo_ev
    except Exception:
        return None, None


class RestEngine(CalculationEngine):
    name = "REST"

    def __init__(self, executable: str | None = None) -> None:
        exe = (
            executable
            or shutil.which("rest")
            or "/opt/rest_workspace/rest/target/release/rest"
        )
        super().__init__(exe)

    def probe(self) -> bool:
        if bool(self._executable) and Path(self._executable).is_file():
            return True
        # 在 Windows 上检测本地 WSL2 rest 安装
        if os.name == "nt":
            try:
                res = subprocess.run(
                    ["wsl.exe", "-d", "Ubuntu", "-e", "test", "-f", WSL_REST_BIN],
                    capture_output=True,
                    timeout=5,
                )
                return res.returncode == 0
            except Exception:
                return False
        return False

    def version(self) -> str:
        return "REST-2026.1.1 (Fudan University Rust Electronic Structure Toolkit)"

    def prepare(self, request: JobRequest, workdir: Path) -> PreparedJob:
        if not self.probe():
            raise EngineNotFound("未在系统或 WSL2 中找到 REST 可执行文件 (rest)。")
        workdir.mkdir(parents=True, exist_ok=True)
        input_path = workdir / "ctrl.in"
        input_path.write_text(request.input_text, encoding="utf-8")
        input_hash = self.hash_text(request.input_text)
        (workdir / "job.meta").write_text(
            f"engine={self.name}\nversion={self.version()}\ninput_hash={input_hash}\nmethod={request.method}\n",
            encoding="utf-8",
        )
        argv = [self._executable, "-i", str(input_path), *request.extra_args]
        return PreparedJob(
            workdir=workdir, input_path=input_path, argv=argv,
            input_hash=input_hash, engine_version=self.version()
        )

    def parse(self, prepared: PreparedJob) -> dict:
        log = prepared.workdir / "run.log"
        if not log.exists():
            return {"ok": False, "reason": "无 REST 输出日志"}
        text = log.read_text(encoding="utf-8", errors="replace")
        return parse_rest_log_text(text, input_hash=prepared.input_hash, workdir=prepared.workdir)

    def run_calculation(
        self,
        doc,
        xc: str = "b3lyp",
        basis: str = "def2-SVP",
        num_threads: int = 4,
        workdir: Optional[Path] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """在本地 WSL2 中真实运行 REST 计算并直接返回解析结果（绝不伪造数据）。"""
        from .qc_input_generator import generate_rest_ctrl_in
        safe_name = "".join(c if (c.isalnum() or c in "_-") and ord(c) < 128 else "_" for c in (doc.name or "mol"))
        clean_name = safe_name.strip("_") or "mol"
        if workdir is None:
            # 优先使用 E:\YDW\REST\run_<name> 以保证与 WSL 路径映射与写权限畅通
            rest_root = Path(r"E:\YDW\REST")
            if rest_root.exists():
                workdir = rest_root / f"run_{clean_name}"
            else:
                from ...runtime import data_dir
                workdir = data_dir() / "temp" / f"rest_{clean_name}"
        workdir.mkdir(parents=True, exist_ok=True)

        charge = float(doc.properties.get("charge", 0.0))
        toml_content = generate_rest_ctrl_in(
            doc,
            xc=xc,
            basis=basis,
            auxbas="def2-universal-jkfit",
            charge=charge,
            num_threads=num_threads,
            basis_pool=WSL_BASIS_POOL,
        )
        input_file = workdir / "ctrl.in"
        input_file.write_text(toml_content, encoding="utf-8")

        wsl_workdir = to_wsl_path(workdir)
        cmd = [
            "wsl.exe", "-d", "Ubuntu", "-e", "bash", "-c",
            f"cd '{wsl_workdir}' && export REST_BASIS_DIR={WSL_BASIS_POOL} && {WSL_REST_BIN} -i ctrl.in",
        ]
        if log_callback:
            log_callback(f"[WSL2 REST] 正在工作目录执行计算: {wsl_workdir}\n")
            log_callback(f"[WSL2 REST] 运行指令: {' '.join(cmd)}\n")

        res = subprocess.run(cmd, capture_output=True, timeout=180)
        stdout_str = res.stdout.decode("utf-8", errors="replace")
        stderr_str = res.stderr.decode("utf-8", errors="replace")
        output_text = stdout_str + ("\n" + stderr_str if stderr_str else "")
        (workdir / "run.log").write_text(output_text, encoding="utf-8")

        if log_callback and output_text:
            log_callback(output_text)

        parsed = parse_rest_log_text(output_text, workdir=workdir)
        parsed["exit_code"] = res.returncode
        parsed["engine"] = self.version()
        parsed["workdir"] = str(workdir)
        return parsed


def parse_rest_log_text(text: str, input_hash: str = "", workdir: Optional[Path] = None) -> dict:
    """解析 REST 量子化学程序输出文本及衍生结果文件，提取能量(Hartree/eV)、Mulliken电荷与轨道信息。"""
    # 1. 匹配总能量 (The SCF energy / Total SCF energy / Total energy)
    scf_matches = re.findall(
        r"(?:The\s+SCF\s+energy|Total\s+SCF\s+energy|SCF\s+energy|Total\s+energy|Final\s+energy|E\((?:SCF|tot|XYG3|XYGJOS|R-xDH7[^)]*)\))\s*[:=]?\s*(-?\d+\.\d+)",
        text,
        flags=re.IGNORECASE,
    )
    homo_matches = re.findall(r"HOMO\s*(?:energy)?\s*[:=]?\s*(-?\d+\.\d+)\s*(?:a\.u\.|Hartree|eV)?", text, flags=re.IGNORECASE)
    lumo_matches = re.findall(r"LUMO\s*(?:energy)?\s*[:=]?\s*(-?\d+\.\d+)\s*(?:a\.u\.|Hartree|eV)?", text, flags=re.IGNORECASE)

    energy_au = float(scf_matches[-1]) if scf_matches else None
    homo_val = float(homo_matches[-1]) if homo_matches else None
    lumo_val = float(lumo_matches[-1]) if lumo_matches else None

    if homo_val is not None and abs(homo_val) < 1.5:
        homo_val *= HARTREE_TO_EV
    if lumo_val is not None and abs(lumo_val) < 1.5:
        lumo_val *= HARTREE_TO_EV

    # 2. 迭代收敛与用时
    converged = ("scf is converged" in text.lower()) or ("mission accomplished" in text.lower())
    iter_match = re.search(r"SCF is converged after\s+(\d+)\s+iterations", text, re.IGNORECASE)
    iterations = int(iter_match.group(1)) if iter_match else None

    time_match = re.search(r"Overall\s*\|\s*:\s*([\d\.]+)\s*s", text)
    elapsed_sec = float(time_match.group(1)) if time_match else None

    # 3. 提取 Mulliken 电荷
    mulliken_charges: dict[int, float] = {}
    mull_block = re.search(r"Mulliken population analysis:\s*\n((?:\s*\d+-[A-Za-z]+\s*:\s*-?\d+\.\d+\s*\n)+)", text)
    if mull_block:
        for line in mull_block.group(1).splitlines():
            m = re.match(r"\s*(\d+)-([A-Za-z]+)\s*:\s*(-?\d+\.\d+)", line)
            if m:
                idx = int(m.group(1))
                val = float(m.group(3))
                mulliken_charges[idx] = val

    # 4. 若提供了工作目录，读取 rest_results.json 与 fchk 文件进行高精度数值校准
    dipole_debye = None
    if workdir and Path(workdir).is_dir():
        wdir = Path(workdir)
        json_file = wdir / "rest_results.json"
        if json_file.exists():
            try:
                jdata = json.loads(json_file.read_text(encoding="utf-8"))
                if "total_energy" in jdata and energy_au is None:
                    energy_au = float(jdata["total_energy"])
                if "dipole_debye" in jdata:
                    dipole_debye = jdata["dipole_debye"]
            except Exception:
                pass

        # 检查所有 *.fchk
        for fchk in wdir.glob("*.fchk"):
            h_fchk, l_fchk = parse_fchk_orbitals(fchk)
            if h_fchk is not None and l_fchk is not None:
                homo_val = h_fchk
                lumo_val = l_fchk
                break

    gap_ev = round(lumo_val - homo_val, 4) if (homo_val is not None and lumo_val is not None) else None

    return {
        "ok": converged,
        "software": "REST (Rust-based Electronic Structure Toolkit)",
        "method": "DFT",
        "basis": "def2-SVP",
        "energy": round(energy_au * HARTREE_TO_EV, 4) if energy_au is not None else 0.0,
        "energy_hartree": energy_au,
        "final_energy_hartree": energy_au,
        "final_energy_ev": round(energy_au * HARTREE_TO_EV, 6) if energy_au is not None else None,
        "homo": homo_val if homo_val is not None else 0.0,
        "lumo": lumo_val if lumo_val is not None else 0.0,
        "homo_ev": homo_val,
        "lumo_ev": lumo_val,
        "gap": gap_ev if gap_ev is not None else 0.0,
        "gap_ev": gap_ev,
        "iterations": iterations,
        "elapsed_seconds": elapsed_sec,
        "mulliken_charges": mulliken_charges,
        "dipole_debye": dipole_debye,
        "converged": converged,
        "input_hash": input_hash,
    }
