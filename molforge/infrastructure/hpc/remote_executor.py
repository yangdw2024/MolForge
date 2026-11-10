"""
molforge/infrastructure/hpc/remote_executor.py - 远程 Linux 执行与监控器
========================================================================
支持两种模式：
  1. SSH / SCP：调用系统 OpenSSH (ssh.exe / scp.exe) 或 Paramiko
  2. WSL2 (本地 Windows Subsystem for Linux)：调用 wsl.exe 零配置本地仿真
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from .cluster_config import ClusterProfile


@dataclass
class RemoteJobStatus:
    job_id: str
    status: str                         # "PENDING", "RUNNING", "COMPLETED", "FAILED", "UNKNOWN"
    node: str = ""
    elapsed: str = ""
    raw_output: str = ""


def to_wsl_path(path: str | Path) -> str:
    """将 Windows 本地路径转换为 WSL2 /mnt 路径。"""
    p = Path(path).resolve()
    drive = p.drive.replace(":", "").lower()
    return f"/mnt/{drive}" + p.as_posix()[2:]


def parse_squeue_output(out: str, job_id: str) -> RemoteJobStatus:
    """解析 squeue 输出行: '%i %T %R %M' (JobID, State, Reason/Node, Time)"""
    line = out.strip().splitlines()[0].strip() if out.strip() else ""
    if not line:
        return RemoteJobStatus(job_id=job_id, status="UNKNOWN", raw_output=out)
    parts = line.split()
    st = parts[1] if len(parts) > 1 else "UNKNOWN"
    node = parts[2] if len(parts) > 2 else ""
    elapsed = parts[3] if len(parts) > 3 else ""
    # 状态标准化
    st_upper = st.upper()
    if st_upper in ("PD", "PENDING", "CONFIGURING"):
        std_status = "PENDING"
    elif st_upper in ("R", "RUNNING", "COMPLETING"):
        std_status = "RUNNING"
    elif st_upper in ("CD", "COMPLETED"):
        std_status = "COMPLETED"
    elif st_upper in ("F", "FAILED", "NF", "NODE_FAIL", "TO", "TIMEOUT", "BOOT_FAIL"):
        std_status = "FAILED"
    elif st_upper in ("CA", "CANCELLED"):
        std_status = "CANCELLED"
    else:
        std_status = st_upper
    return RemoteJobStatus(job_id=job_id, status=std_status, node=node, elapsed=elapsed, raw_output=out)


class RemoteHPCExecutor:
    """远程 Linux 集群作业调度与状态监控器。"""

    def __init__(self, profile: ClusterProfile, runner: Optional[Callable[[list[str]], Tuple[int, str, str]]] = None):
        self.profile = profile
        self._custom_runner = runner

    def _build_ssh_cmd(self, remote_command: str) -> list[str]:
        if self.profile.host_type == "wsl":
            return ["wsl.exe", "bash", "-c", remote_command]

        cmd = ["ssh.exe", "-p", str(self.profile.port)]
        if self.profile.key_path and os.path.exists(os.path.expanduser(self.profile.key_path)):
            cmd.extend(["-i", os.path.expanduser(self.profile.key_path)])
        cmd.extend(["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"])
        target = f"{self.profile.username}@{self.profile.hostname}"
        cmd.append(target)
        cmd.append(remote_command)
        return cmd

    def run_command(self, remote_cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
        """在远程主机执行命令，返回 (exit_code, stdout, stderr)。"""
        cmd = self._build_ssh_cmd(remote_cmd)
        if self._custom_runner is not None:
            return self._custom_runner(cmd)
        try:
            p = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            return -1, "", f"命令执行超时 (>{timeout}s)"
        except Exception as e:
            return -1, "", str(e)

    def upload_files(self, local_paths: List[Path], remote_dir: str) -> bool:
        """上传本地计算文件到远程目录。"""
        if self.profile.host_type == "wsl":
            code, _, _ = self.run_command(f"mkdir -p '{remote_dir}'")
            if code != 0:
                return False
            for p in local_paths:
                wsl_src = to_wsl_path(p)
                code_cp, _, _ = self.run_command(f"cp '{wsl_src}' '{remote_dir}/'")
                if code_cp != 0:
                    return False
            return True

        # SSH 模式使用 scp.exe
        scp_cmd = ["scp.exe", "-P", str(self.profile.port)]
        if self.profile.key_path and os.path.exists(os.path.expanduser(self.profile.key_path)):
            scp_cmd.extend(["-i", os.path.expanduser(self.profile.key_path)])
        scp_cmd.extend(["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"])
        for p in local_paths:
            scp_cmd.append(str(p.resolve()))
        dest = f"{self.profile.username}@{self.profile.hostname}:{remote_dir}/"
        scp_cmd.append(dest)

        # 确保远程目录存在
        self.run_command(f"mkdir -p {remote_dir}")
        res = subprocess.run(scp_cmd, capture_output=True, text=True)
        return res.returncode == 0

    def download_file(self, remote_file: str, local_dest: Path) -> bool:
        """下载远程结果文件到本地。"""
        local_dest.parent.mkdir(parents=True, exist_ok=True)
        if self.profile.host_type == "wsl":
            wsl_dest = to_wsl_path(local_dest)
            code, _, _ = self.run_command(f"cp '{remote_file}' '{wsl_dest}'")
            return code == 0

        scp_cmd = ["scp.exe", "-P", str(self.profile.port)]
        if self.profile.key_path and os.path.exists(os.path.expanduser(self.profile.key_path)):
            scp_cmd.extend(["-i", os.path.expanduser(self.profile.key_path)])
        scp_cmd.extend(["-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"])
        src = f"{self.profile.username}@{self.profile.hostname}:{remote_file}"
        scp_cmd.extend([src, str(local_dest.resolve())])
        res = subprocess.run(scp_cmd, capture_output=True, text=True)
        return res.returncode == 0

    def submit_job(self, remote_dir: str, script_name: str = "slurm.sh") -> Tuple[bool, str]:
        """在远程提交作业，返回 (是否成功, JobID或错误消息)。"""
        if self.profile.scheduler == "slurm":
            sub_cmd = f"cd {remote_dir} && sbatch {script_name}"
        elif self.profile.scheduler == "pbs":
            sub_cmd = f"cd {remote_dir} && qsub {script_name}"
        else:
            sub_cmd = f"cd {remote_dir} && nohup bash {script_name} > job.log 2>&1 & echo $!"

        code, out, err = self.run_command(sub_cmd)
        if code != 0:
            return False, f"提交失败: {err or out}"

        # 提取 Slurm Job ID, e.g. "Submitted batch job 123456"
        out_strip = out.strip()
        if "Submitted batch job" in out_strip:
            job_id = out_strip.split()[-1]
            return True, job_id
        return True, out_strip

    def query_job(self, job_id: str) -> RemoteJobStatus:
        """查询远程作业运行状态。"""
        if self.profile.scheduler == "slurm":
            cmd = f"squeue -j {job_id} --noheader --format='%i %T %R %M'"
            code, out, err = self.run_command(cmd)
            if code != 0 or not out.strip():
                # 不在队列中，进一步检查 sacct 判断是 COMPLETED 还是 FAILED
                code_acct, out_acct, _ = self.run_command(f"sacct -j {job_id} --format=JobID,State -P -n")
                if code_acct == 0:
                    upper_acct = out_acct.upper()
                    if "COMPLETED" in upper_acct:
                        return RemoteJobStatus(job_id=job_id, status="COMPLETED", raw_output=out_acct)
                    elif "FAILED" in upper_acct or "TIMEOUT" in upper_acct or "CANCELLED" in upper_acct:
                        return RemoteJobStatus(job_id=job_id, status="FAILED", raw_output=out_acct)
                return RemoteJobStatus(job_id=job_id, status="COMPLETED", raw_output="已离开当前队列")
            return parse_squeue_output(out, job_id)

        elif self.profile.scheduler == "pbs":
            cmd = f"qstat -f {job_id}"
            code, out, err = self.run_command(cmd)
            if code != 0 or not out.strip():
                return RemoteJobStatus(job_id=job_id, status="COMPLETED", raw_output="PBS 队列中未查找到该作业")
            # 查找 job_state = Q/R/C/E
            st = "UNKNOWN"
            for line in out.splitlines():
                if "job_state" in line.lower() and "=" in line:
                    val = line.split("=")[-1].strip().upper()
                    if val == "Q":
                        st = "PENDING"
                    elif val in ("R", "E"):
                        st = "RUNNING"
                    elif val == "C":
                        st = "COMPLETED"
                    break
            return RemoteJobStatus(job_id=job_id, status=st, raw_output=out)

        elif self.profile.scheduler == "nohup":
            cmd = f"ps -p {job_id} -o pid,stat,time --no-headers"
            code, out, err = self.run_command(cmd)
            if code == 0 and out.strip():
                parts = out.strip().split()
                elapsed = parts[-1] if len(parts) >= 3 else ""
                return RemoteJobStatus(job_id=job_id, status="RUNNING", elapsed=elapsed, raw_output=out)
            return RemoteJobStatus(job_id=job_id, status="COMPLETED", raw_output="进程已终止")

        return RemoteJobStatus(job_id=job_id, status="UNKNOWN")
