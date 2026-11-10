"""
molforge/infrastructure/hpc/slurm_generator.py - Slurm / PBS 生产级提交脚本生成器
=============================================================================
支持一键渲染生成标准工业级量子化学与动力学提交脚本：
  1. Gaussian 16 (.gjf -> slurm.sh)
  2. ORCA 6 (.inp -> slurm.sh)
  3. GROMACS (grompp -> mdrun -> slurm.sh)
  4. xTB / CREST
  5. CalChem CLI (无头纯 Rust 高性能超算执行器)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from .cluster_config import ClusterProfile


@dataclass
class JobSpec:
    job_name: str
    engine: str                        # "g16", "orca", "gromacs", "xtb", "calchem"
    input_file: str                    # 如 "opt_freq.gjf"
    output_file: str                   # 如 "opt_freq.log"
    n_cores: int = 16
    memory_mb: int = 32000
    walltime: str = "24:00:00"
    partition: Optional[str] = None
    extra_commands: Optional[List[str]] = None


class SlurmScriptGenerator:
    """标准 Slurm sbatch 脚本生成器。"""

    @staticmethod
    def generate(job: JobSpec, profile: ClusterProfile) -> str:
        lines: list[str] = [
            "#!/bin/bash",
            f"#SBATCH --job-name={job.job_name}",
            f"#SBATCH --nodes={profile.default_nodes}",
            f"#SBATCH --ntasks={job.n_cores}",
            f"#SBATCH --mem={job.memory_mb}M",
            f"#SBATCH --time={job.walltime}",
            f"#SBATCH --output={job.job_name}_%j.out",
            f"#SBATCH --error={job.job_name}_%j.err",
        ]
        part = job.partition or profile.default_partition
        if part:
            lines.append(f"#SBATCH --partition={part}")

        lines.append("")
        lines.append("# ========== 1. 运行环境初始化 ==========")
        for env_cmd in profile.env_preamble:
            lines.append(env_cmd)

        lines.append("")
        lines.append("echo \"[MolForge HPC Job] Starting on node $(hostname) at $(date)\"")
        lines.append("echo \"[MolForge HPC Job] Working directory: $(pwd)\"")
        lines.append("")
        lines.append("# ========== 2. 计算软件主体调用 ==========")

        eng = job.engine.lower()
        if eng == "g16":
            bin_path = profile.app_paths.get("g16", "g16")
            lines.append(f"{bin_path} < {job.input_file} > {job.output_file}")
            lines.append(f"formchk {job.job_name}.chk {job.job_name}.fchk 2>/dev/null || true")
        elif eng == "orca":
            bin_path = profile.app_paths.get("orca", "orca")
            lines.append(f"{bin_path} {job.input_file} > {job.output_file}")
        elif eng == "xtb":
            bin_path = profile.app_paths.get("xtb", "xtb")
            lines.append(f"{bin_path} {job.input_file} --opt > {job.output_file}")
        elif eng == "gromacs":
            bin_path = profile.app_paths.get("gromacs", "gmx")
            lines.append(f"{bin_path} mdrun -ntmpi 1 -ntomp {job.n_cores} -v -deffnm {job.job_name}")
        elif eng == "calchem":
            bin_path = profile.app_paths.get("calchem", "calchem-cli")
            lines.append(f"{bin_path} run --input {job.input_file} --threads {job.n_cores} --output {job.output_file}")
        elif eng == "rest":
            bin_path = profile.app_paths.get("rest", "/home/administrator/miniforge3/envs/rest-py311/bin/rest")
            lines.append(f"{bin_path} -i {job.input_file} > {job.output_file}")
        else:
            lines.append(f"./{job.input_file}")

        if job.extra_commands:
            lines.append("")
            lines.append("# ========== 3. 用户附加后处理指令 ==========")
            for c in job.extra_commands:
                lines.append(c)

        lines.append("")
        lines.append("echo \"[MolForge HPC Job] Finished at $(date) with exit code $?\"")
        return "\n".join(lines) + "\n"
