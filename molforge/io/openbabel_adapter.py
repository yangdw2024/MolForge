"""
openbabel_adapter.py - OpenBabel 通用格式适配器
=================================================
通过 subprocess 调用 obabel.exe，把 OpenBabel 支持的 183 种格式
统一接入 MolForge 的 Molecule 体系。

策略：
  - 读：任意格式 → obabel 转 SDF 临时文件 → RDKit 读取
  - 写：Molecule → RDKit 写 SDF 临时文件 → obabel 转目标格式
  - 专门 reader（Gaussian log / cube / gjf 等）优先级高于此适配器，
    因为那些格式里有轨道、能量、性质等丰富信息，OpenBabel 读不出来。

obabel 路径探测顺序：
  1. PATH 环境变量里的 obabel
  2. E:\\openbabel-install-msvc\\bin\\obabel.exe
  3. 其他常见安装路径
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem

from ..core.molecule import Molecule
from ..core.conformer import Conformer

# ---------- obabel 路径定位 ----------

_CACHED_OBABEL: Path | None = None
_CACHE_FAILED = False


def _find_obabel() -> Path | None:
    """探测 obabel.exe 路径，结果缓存。"""
    global _CACHED_OBABEL, _CACHE_FAILED
    if _CACHED_OBABEL is not None:
        return _CACHED_OBABEL
    if _CACHE_FAILED:
        return None

    # 1. PATH 里找
    from shutil import which
    found = which("obabel")
    if found:
        _CACHED_OBABEL = Path(found)
        return _CACHED_OBABEL

    # 2. 本机已知安装路径
    candidates = [
        r"E:\openbabel-install-msvc\bin\obabel.exe",
        r"E:\openbabel-openbabel-3-2-1\build-msvc\bin\obabel.exe",
        r"C:\Program Files\OpenBabel\obabel.exe",
        r"D:\Program Files\OpenBabel\obabel.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            _CACHED_OBABEL = Path(c)
            return _CACHED_OBABEL

    _CACHE_FAILED = True
    return None


def is_available() -> bool:
    """OpenBabel 是否可用。"""
    return _find_obabel() is not None


# ---------- 格式列表缓存 ----------

_READ_EXT_CACHE: list[str] | None = None
_WRITE_EXT_CACHE: list[str] | None = None


def _parse_formats_output() -> tuple[list[str], list[str]]:
    """
    解析 `obabel -L formats` 输出，提取可读和可写的扩展名列表。

    输出格式示例：
        cif -- Crystallographic Information File
        cdxml -- ChemDraw CDXML format
        cdx -- ChemDraw binary format [Read-only]
        com -- Gaussian Input [Write-only]
    """
    ob = _find_obabel()
    if ob is None:
        return [], []

    try:
        result = subprocess.run(
            [str(ob), "-L", "formats"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return [], []

    readable: list[str] = []
    writable: list[str] = []

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or "--" not in line:
            continue
        # 第一列是格式名
        fmt_name = line.split("--")[0].strip()
        if not fmt_name:
            continue

        # 跳过一些非文件格式的伪格式
        if fmt_name.lower() in {"copy", "ascii", "fastsearch", "fps", "fpt", "feat", "fix", "can"}:
            continue

        ext = "." + fmt_name.lower()

        # 判断读写能力
        if "[Read-only]" in line:
            readable.append(ext)
        elif "[Write-only]" in line:
            writable.append(ext)
        else:
            readable.append(ext)
            writable.append(ext)

    return readable, writable


def get_readable_extensions() -> list[str]:
    """返回 OpenBabel 可读的所有扩展名列表（小写，带点）。"""
    global _READ_EXT_CACHE
    if _READ_EXT_CACHE is None:
        r, _ = _parse_formats_output()
        _READ_EXT_CACHE = r
    return _READ_EXT_CACHE


def get_writable_extensions() -> list[str]:
    """返回 OpenBabel 可写的所有扩展名列表（小写，带点）。"""
    global _WRITE_EXT_CACHE
    if _WRITE_EXT_CACHE is None:
        _, w = _parse_formats_output()
        _WRITE_EXT_CACHE = w
    return _WRITE_EXT_CACHE


# ---------- 核心转换 ----------

def read_as_rdkit_mol(path: Path) -> Chem.Mol:
    """
    用 OpenBabel 把任意支持的格式读成 RDKit Mol。

    流程：obabel input.xxx -O temp.sdf → RDKit SDMolSupplier 读
    """
    ob = _find_obabel()
    if ob is None:
        raise RuntimeError("OpenBabel 未安装或未找到 obabel.exe")

    with tempfile.NamedTemporaryFile(
        suffix=".sdf", delete=False, mode="w"
    ) as tmp:
        tmp_sdf = Path(tmp.name)

    try:
        cmd = [str(ob), str(path), "-O", str(tmp_sdf)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise ValueError(
                f"OpenBabel 转换失败: {path.name}\n"
                f"命令: {' '.join(cmd)}\n"
                f"错误: {result.stderr.strip() or result.stdout.strip()}"
            )

        suppl = Chem.SDMolSupplier(str(tmp_sdf), sanitize=True, removeHs=False)
        mol = None
        for m in suppl:
            if m is not None:
                mol = m
                break
        if mol is None:
            raise ValueError(f"OpenBabel 转换后无法解析分子: {path.name}")

        return mol
    finally:
        # Windows 上文件句柄可能延迟释放，删除失败不影响主流程
        try:
            if tmp_sdf.exists():
                tmp_sdf.unlink()
        except OSError:
            pass


def write_from_rdkit_mol(mol: Chem.Mol, path: Path) -> None:
    """
    用 OpenBabel 把 RDKit Mol 写成任意支持的格式。

    流程：RDKit 写 temp.sdf → obabel temp.sdf -O output.xxx
    """
    ob = _find_obabel()
    if ob is None:
        raise RuntimeError("OpenBabel 未安装或未找到 obabel.exe")

    with tempfile.NamedTemporaryFile(
        suffix=".sdf", delete=False, mode="w"
    ) as tmp:
        tmp_sdf = Path(tmp.name)

    try:
        # RDKit 先写 SDF
        writer = Chem.SDWriter(str(tmp_sdf))
        writer.write(mol)
        writer.close()

        # obabel 转成目标格式
        cmd = [str(ob), str(tmp_sdf), "-O", str(path)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise ValueError(
                f"OpenBabel 写出失败: {path.name}\n"
                f"错误: {result.stderr.strip() or result.stdout.strip()}"
            )
    finally:
        try:
            if tmp_sdf.exists():
                tmp_sdf.unlink()
        except OSError:
            pass


# ---------- MolForge Molecule 封装 ----------

def read_molecule(path: Path) -> Molecule:
    """用 OpenBabel 读取文件，返回 MolForge Molecule。"""
    rmol = read_as_rdkit_mol(path)
    m = Molecule.from_rdkit(rmol, name=path.stem)
    m.source_format = f"openbabel:{path.suffix.lstrip('.')}"
    m.source_path = path

    # 提取 3D 坐标
    if rmol.GetNumConformers() > 0:
        conf = rmol.GetConformer()
        coords = []
        import numpy as np
        for i in range(rmol.GetNumAtoms()):
            p = conf.GetAtomPosition(i)
            coords.append([p.x, p.y, p.z])
        m.conformers.append(Conformer(
            coords=np.array(coords),
            source=f"openbabel:{path.suffix.lstrip('.')}"
        ))

    return m


def write_molecule(mol: Molecule, path: Path) -> None:
    """用 OpenBabel 把 MolForge Molecule 写成文件。"""
    rmol = mol.rdkit_mol
    write_from_rdkit_mol(rmol, path)
