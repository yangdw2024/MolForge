"""
gromacs_submit.py - MolForge 外接 GROMACS 任务生成与 Pueue 队列提交
====================================================================
复用 GromacsAdapter 的标准 .mdp，生成 Windows PowerShell 运行包装脚本（gmx 路径写死），
再通过本机全局 Pueue 调度系统（E:\\YDW\\Scheduling_System，并发=1）串行提交，
避免多个 GPU 任务抢显存。

设计约束：
  - 工作目录与产物落在 D 盘（活跃计算），不写 C 盘；
  - 包装脚本用 CRLF、gmx 绝对路径写死，零命令行转义；
  - 只生成脚本并入队，不在这里直接启动 gmx，保证 GPU 任务统一受队列管控。
"""
from __future__ import annotations

import subprocess
import re
import shutil
from pathlib import Path

from ..io.calculators import GromacsAdapter

# RTX 5060 Ti 为 sm120，默认用 CUDA-sm120 版本
DEFAULT_GMX = r"D:\YDW\Trae_Gromacs\gromacs\gromacs-2026.3-AVX512-CUDA-sm120-final2\bin\gmx.exe"
SUBMIT_WRAPPER = r"E:\YDW\Scheduling_System\scripts\submit-wrapper.ps1"


def build_gromacs_job(
    work_dir: str | Path,
    structure: str | Path,
    topology: str | Path,
    label: str = "molforge_md",
    temp_k: float = 298.15,
    pressure_bar: float = 1.0,
    nsteps_md: int = 500000,
    dt_ps: float = 0.002,
    gmx_path: str = DEFAULT_GMX,
) -> dict[str, str]:
    """在 work_dir 生成 mdp、复制结构/拓扑并写出 run_md.ps1 包装脚本。

    返回 dict：wrapper（包装脚本路径）、work_dir、gmx、mdp 文件清单。
    """
    work = Path(work_dir).resolve()
    if work.exists() and any(work.iterdir()):
        raise FileExistsError("任务目录非空，拒绝覆盖已有计算；请选择新目录")
    work.mkdir(parents=True, exist_ok=True)
    structure, topology = Path(structure).resolve(), Path(topology).resolve()
    if not structure.is_file():
        raise FileNotFoundError(f"结构文件不存在: {structure}")
    if not topology.is_file():
        raise FileNotFoundError(f"拓扑文件 topol.top 不存在: {topology}")
    if not Path(gmx_path).is_file():
        raise FileNotFoundError(f"gmx 可执行文件不存在: {gmx_path}")

    if work.drive.upper() not in ("D:", "E:"):
        raise ValueError("任务目录必须位于D盘或E盘")
    if structure.suffix.lower() not in (".gro", ".pdb"):
        raise ValueError("结构输入仅支持GRO/PDB")

    # 1. 写标准 mdp
    mdp = GromacsAdapter.generate_mdp_files(
        temp_k=temp_k, pressure_bar=pressure_bar, nsteps_md=nsteps_md, dt_ps=dt_ps
    )
    mdp_files = []
    for name in ("minim.mdp", "nvt.mdp", "md.mdp"):
        p = work / name
        # mdp 用 LF 即可，GROMACS 可正常解析
        p.write_text(mdp[name], encoding="utf-8")
        mdp_files.append(str(p))

    # 2. 复制结构与拓扑到工作目录（固定文件名，脚本零歧义）
    input_gro = work / ("input" + structure.suffix.lower())
    input_gro.write_bytes(structure.read_bytes())
    topol = work / "topol.top"
    topol.write_bytes(topology.read_bytes())
    visited = set()
    def copy_includes(source, dest):
        source = source.resolve()
        if source in visited:
            return
        visited.add(source)
        for item in re.findall(r'^\s*#include\s+"([^"\n]+)"', source.read_text(encoding="utf-8-sig", errors="replace"), re.M):
            relative = Path(item)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"请将拓扑include整理为任务目录内的相对路径: {item}")
            local = source.parent / relative
            if not local.is_file():
                raise FileNotFoundError(f"缺少拓扑依赖 {local}；请提供完整力场/itp目录")
            target = dest.parent / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(local.read_bytes())
            copy_includes(local, target)
    copy_includes(topology, topol)

    # 3. 写 Windows 包装脚本（CRLF、gmx 路径写死、用 & 调用运算符）
    runner = work / "run_md.ps1"
    lines = [
        "# MolForge 自动生成的 GROMACS 运行包装脚本（受 Pueue 队列管控）",
        "$ErrorActionPreference = 'Stop'",
        "Set-Location -LiteralPath '" + str(work).replace("'", "''") + "'",
        "$gmx = '" + str(gmx_path).replace("'", "''") + "'",
        # Preserve the supplied periodic box; box preparation is a separate scientific decision.
        f'& $gmx grompp -f minim.mdp -c {input_gro.name} -p topol.top -o em.tpr',
        '& $gmx mdrun -v -deffnm em -nb gpu',
        '& $gmx grompp -f nvt.mdp -c em.gro -r em.gro -p topol.top -o nvt.tpr',
        '& $gmx mdrun -deffnm nvt -nb gpu',
        '& $gmx grompp -f md.mdp -c nvt.gro -p topol.top -o md_0_1.tpr',
        '& $gmx mdrun -deffnm md_0_1 -nb gpu -gpu_id 0',
        'Write-Host "MolForge GROMACS job finished in ' + str(work) + '"',
    ]
    checked = []
    for line in lines:
        checked.append(line)
        if line.startswith('& $gmx '):
            checked.append('if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }')
    runner.write_bytes(("\r\n".join(checked) + "\r\n").encode("utf-8-sig"))

    return {
        "wrapper": str(runner),
        "work_dir": str(work),
        "gmx": gmx_path,
        "mdp_files": mdp_files,
        "label": label,
    }


def enqueue_gromacs_job(job: dict[str, str], priority: int = 5) -> str:
    """通过 submit-wrapper.ps1 把包装脚本送入 Pueue 队列，返回 pueue 输出。"""
    wrapper = job["wrapper"]
    if not Path(wrapper).is_file():
        raise FileNotFoundError(f"包装脚本不存在: {wrapper}")
    if not Path(SUBMIT_WRAPPER).is_file():
        raise FileNotFoundError(f"提交脚本不存在: {SUBMIT_WRAPPER}")

    # 用 Windows PowerShell 调用提交包装（与调度系统约定一致）
    ps_exe = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    def literal(value):
        return "'" + str(value).replace("'", "''") + "'"
    invocation = (
        "$global:LASTEXITCODE = 0; & " + literal(SUBMIT_WRAPPER)
        + " -Wrapper " + literal(wrapper)
        + " -Label " + literal(job.get("label", "molforge_md"))
        + " -WorkDir " + literal(job["work_dir"])
        + " -Priority " + str(int(priority))
        + "; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
    )
    cmd = [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", invocation]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise RuntimeError(f"Pueue 入队失败: {output}")
    return output
