"""
ai/deepseek_harness.py - MolForge <-> DeepSeek Harness 深度联动桥接器
==================================================================
功能：
  1. 自动探测本机 DeepSeek Harness 可执行程序 (E:\\DeepseekHarness\\DeepSeek Harness.exe 等)
  2. 将 MolForge 全部 18 项分子搭建/精细编辑/量化计算 MCP 工具及使用规范自动写入
     ~/.dsh/skills/molforge-workbench/SKILL.md，让 DeepSeek Harness Agent 彻底掌握本软件
  3. 生成带有 MolForge 专属图标 (molforge_logo.ico) 的启动快捷方式与 MCP 配置文件，
     实现在 MolForge AI 面板中一键启动 DeepSeek Harness 并联动当前活动分子
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..runtime import data_dir

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ICON_ICO = _REPO_ROOT / "molforge" / "ui" / "assets" / "molforge_logo.ico"
_ICON_PNG = _REPO_ROOT / "molforge" / "ui" / "assets" / "molforge_logo.png"

_DSH_CANDIDATES = (
    Path(r"E:\DeepseekHarness\DeepSeek Harness.exe"),
    Path(r"D:\DeepseekHarness\DeepSeek Harness.exe"),
    Path.home() / "AppData" / "Local" / "Programs" / "deepseek-harness" / "DeepSeek Harness.exe",
)


def find_deepseek_harness_exe() -> Path | None:
    env_p = os.environ.get("MOLFORGE_DSH_EXE", "").strip()
    if env_p and Path(env_p).is_file():
        return Path(env_p)
    for cand in _DSH_CANDIDATES:
        if cand.is_file():
            return cand
    return None


def get_custom_icon_path() -> Path | None:
    if _ICON_ICO.is_file():
        return _ICON_ICO
    if _ICON_PNG.is_file():
        return _ICON_PNG
    return None


def build_molforge_skill_markdown(python_exe: str, repo_root: Path, mcp_conn_path: Path) -> str:
    return f"""---
name: molforge-workbench
description: 控制正在运行的 MolForge 分子工作台，实时读取、搭建、精细修改当前活动分子并执行量子化学/几何优化计算。
---

# MolForge 分子工作台联动指南 (Desktop MCP)

当用户通过 **MolForge** 启动 DeepSeek Harness 时，MolForge 已在后台开启了**活动文档桌面 MCP 桥接服务**。你可以通过 stdio MCP 服务实时操作用户当前正在编辑的分子标签页（所有修改均走 `CommandBus`，支持视口实时刷新与 `Ctrl+Z` 撤销）。

## 1. MCP 服务启动方式
- **Python**: `{python_exe}`
- **参数**: `["-m", "molforge.ai.mcp.mcp_server"]`
- **工作目录**: `{repo_root}`
- **环境变量**: `PYTHONPATH={repo_root}`, `MOLFORGE_DATA_DIR={data_dir()}`
- **桌面连接凭证**: `{mcp_conn_path}`（自动读取当前活动文档的本机端口与 Token）

## 2. 可用分子搭建与精细编辑工具（共 18 项）
- **结构读取**: `get_molecule_info`（化学式、原子坐标、点群、电荷、自旋）
- **从头搭建 / 拼接**:
  - `build_from_smiles(smiles, name)`：根据 SMILES 一键生成 3D 构象并加入画布
  - `add_ring(size, aromatic, attach_to)`：添加苯环/杂环/脂环，支持接枝到指定 1-based 原子
  - `add_atom(atomic_num, near_atom, x, y, z)`：在指定原子旁或绝对坐标添加原子
  - `add_bond(atom_a, atom_b)`：在两原子间成键
- **精细改分子**:
  - `change_element(atom_index, new_atomic_num)`：替换原子元素（如 C -> N/O/S/F）
  - `change_bond_order(atom_a, atom_b, order)`：修改键级（1单 / 2双 / 3三 / 4芳香）
  - `modify_internal_coordinate(coord_type, atoms, target_value)`：精确修改键长 (Å)、键角 (°)、二面角 (°) 并刚体联动旋转子图
  - `set_atom_charge(atom_index, formal_charge)`：设置形式电荷
  - `delete_atom(atom_index)`：删除原子及相连键
  - `clean_geometry_3d()`：执行 MMFF94/UFF 3D 力场几何弛豫
  - `undo_last()` / `redo_last()`：撤销或重做上一步操作
- **量化与结构分析**:
  - `run_calchem_scf(basis)` / `run_calchem_opt(basis, max_steps)`：CalChem Rust 内核秒级 RHF 与 BFGS 优化
  - `run_rest_scf(xc, basis)`：WSL2 复旦 REST 双杂化/DFT 计算
  - `run_planarity()`：计算重原子最佳拟合平面度 (MPP)
  - `generate_hpc_slurm_script(engine, job_name, n_cores, memory_mb, walltime)`：生成超算 Slurm 脚本
"""


def prepare_deepseek_harness_bundle(dsh_home: Path | None = None) -> dict[str, Any]:
    """同步 MolForge Skill、MCP 配置 JSON 与带 MolForge 专属图标的启动快捷方式。"""
    exe = find_deepseek_harness_exe()
    home = dsh_home or (Path.home() / ".dsh")
    skill_dir = home / "skills" / "molforge-workbench"
    skill_dir.mkdir(parents=True, exist_ok=True)

    python_exe = sys.executable
    conn_path = data_dir() / "mcp" / "desktop.json"
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(build_molforge_skill_markdown(python_exe, _REPO_ROOT, conn_path), encoding="utf-8")

    out_dir = data_dir() / "deepseek_harness"
    out_dir.mkdir(parents=True, exist_ok=True)
    mcp_cfg = {
        "mcpServers": {
            "molforge": {
                "command": python_exe,
                "args": ["-m", "molforge.ai.mcp.mcp_server"],
                "cwd": str(_REPO_ROOT),
                "env": {
                    "PYTHONPATH": str(_REPO_ROOT),
                    "MOLFORGE_DATA_DIR": str(data_dir()),
                },
            }
        }
    }
    cfg_path = out_dir / "molforge_mcp_config.json"
    cfg_path.write_text(json.dumps(mcp_cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    lnk_path = out_dir / "MolForge_DeepSeek_Harness.lnk"
    icon_path = get_custom_icon_path()
    if sys.platform == "win32" and exe is not None:
        _create_windows_shortcut(lnk_path, exe, _REPO_ROOT, icon_path)

    return {
        "exe": str(exe) if exe else None,
        "skill_path": str(skill_path),
        "mcp_config_path": str(cfg_path),
        "shortcut_path": str(lnk_path) if lnk_path.is_file() else None,
        "icon_path": str(icon_path) if icon_path else None,
    }


def _create_windows_shortcut(lnk_path: Path, target_exe: Path, work_dir: Path, icon_path: Path | None) -> None:
    def _ps_quote(val: str) -> str:
        return "'" + val.replace("'", "''") + "'"

    icon_line = f"$s.IconLocation = {_ps_quote(str(icon_path))}" if icon_path and icon_path.suffix.lower() == ".ico" else ""
    script = "\n".join([
        "$ws = New-Object -ComObject WScript.Shell",
        f"$s = $ws.CreateShortcut({_ps_quote(str(lnk_path))})",
        f"$s.TargetPath = {_ps_quote(str(target_exe))}",
        f"$s.WorkingDirectory = {_ps_quote(str(work_dir))}",
        "$s.Description = 'MolForge x DeepSeek Harness AI Workbench'",
        icon_line,
        "$s.Save()",
    ])
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def launch_deepseek_harness(desktop_mcp_service=None) -> dict[str, Any]:
    """确保桌面 MCP 监听开启、写入联动 Skill 与专属图标快捷方式，并拉起 DeepSeek Harness。"""
    mcp_info = None
    if desktop_mcp_service is not None:
        mcp_info = desktop_mcp_service.start()

    bundle = prepare_deepseek_harness_bundle()
    exe = bundle.get("exe")
    if not exe:
        return {
            "ok": False,
            "error": "未找到 DeepSeek Harness（请确认已安装至 E:\\DeepseekHarness\\DeepSeek Harness.exe 或设置 MOLFORGE_DSH_EXE）。",
            **bundle,
            "mcp": mcp_info,
        }

    lnk = bundle.get("shortcut_path")
    if sys.platform == "win32" and lnk and Path(lnk).is_file():
        os.startfile(lnk)
    else:
        subprocess.Popen([exe, str(_REPO_ROOT)], cwd=str(_REPO_ROOT))

    return {
        "ok": True,
        "launched": lnk or exe,
        "mcp": mcp_info,
        **bundle,
    }
