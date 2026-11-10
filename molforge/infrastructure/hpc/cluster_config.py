"""
molforge/infrastructure/hpc/cluster_config.py - Linux 超算/服务器连接与调度配置模型
=============================================================================
支持配置多台 Linux 计算节点/超算集群：
  - 协议: SSH (密钥或密码) / 本地 WSL2 (Windows Subsystem for Linux)
  - 调度系统: Slurm (sbatch/squeue/scancel), PBS/Torque (qsub/qstat), 直接后台 nohup
  - 环境初始化: module load, conda activate, 环境变量预置
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


@dataclass
class ClusterProfile:
    """Linux 计算主机档案。"""
    name: str = "Default_Linux_Cluster"
    host_type: Literal["ssh", "wsl", "local"] = "ssh"
    hostname: str = "hpc.university.edu"
    port: int = 22
    username: str = "chem_user"
    key_path: str = ""                         # 推荐: ~/.ssh/id_rsa
    password: str = ""                         # 可选或交互输入
    remote_workdir: str = "~/molforge_jobs"   # 远程临时计算基目录
    scheduler: Literal["slurm", "pbs", "nohup"] = "slurm"
    default_partition: str = "compute"
    default_nodes: int = 1
    default_ntasks: int = 16
    default_memory_mb: int = 32000
    default_walltime: str = "24:00:00"
    env_preamble: List[str] = field(default_factory=lambda: [
        "module purge",
        "module load gaussian/g16-c01",
        "module load orca/6.0.0",
        "module load openmpi/4.1.4",
    ])
    app_paths: Dict[str, str] = field(default_factory=lambda: {
        "g16": "g16",
        "orca": "orca",
        "xtb": "xtb",
        "gromacs": "gmx",
        "calchem": "calchem-cli",
        "rest": "/home/administrator/miniforge3/envs/rest-py311/bin/rest",
    })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ClusterProfile:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ClusterConfigManager:
    """集群配置持久化管理器。"""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            from ...runtime import data_dir
            config_dir = data_dir() / "settings"
        self.config_file = Path(config_dir) / "clusters.json"
        self.profiles: Dict[str, ClusterProfile] = {}
        self.load()

    def load(self) -> None:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.profiles = {
                        name: ClusterProfile.from_dict(prof)
                        for name, prof in data.get("profiles", {}).items()
                    }
            except Exception:
                self._create_default()
        else:
            self._create_default()

    def _create_default(self) -> None:
        default_prof = ClusterProfile()
        wsl_prof = ClusterProfile(
            name="Local_WSL2_Ubuntu",
            host_type="wsl",
            hostname="localhost",
            username="",
            remote_workdir="/tmp/molforge_wsl",
            scheduler="nohup",
            env_preamble=[
                "source /home/administrator/miniforge3/etc/profile.d/conda.sh && conda activate rest-py311",
                "export REST_BASIS_DIR=/mnt/e/YDW/REST/knowledge_base/rest_github/basis-set-pool",
            ],
            app_paths={
                "g16": "g16",
                "orca": "orca",
                "xtb": "xtb",
                "gromacs": "gmx",
                "calchem": "calchem-cli",
                "rest": "/home/administrator/miniforge3/envs/rest-py311/bin/rest",
            },
        )
        self.profiles = {default_prof.name: default_prof, wsl_prof.name: wsl_prof}
        self.save()

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0",
            "profiles": {name: p.to_dict() for name, p in self.profiles.items()},
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get(self, name: str) -> Optional[ClusterProfile]:
        return self.profiles.get(name)

    def set(self, profile: ClusterProfile) -> None:
        self.profiles[profile.name] = profile
        self.save()
