"""
application/calculators/qc_input_generator.py - Gaussian (.gjf) 与 REST (ctrl.in) 输入卡生成器
==================================================================================================
专为有机光伏 (OSC) 给体/受体分子计算工作流打造：
1. Gaussian 16 / 09 输入卡 (.gjf)：
   - 内置 OSC 常用预设（B3LYP-D3(BJ)/6-31G(d) 预优化、wB97XD/def2SVP、CAM-B3LYP TD-DFT 激发态、ESP 静电势）
   - 支持 PCM/SMD 溶剂模型（氯仿 Chloroform、氯苯 Chlorobenzene、甲苯 Toluene 等）
2. 复旦大学张颖/徐昕团队 REST (Rust-based Electronic Structure Toolkit) 输入卡 (ctrl.in)：
   - 严格遵循官方 TOML 规范，仅包含 [ctrl] 与 [geom] 两个控制区
   - 支持杂化泛函 (b3lyp, pbe0, cam-b3lyp, wb97xd) 与旗舰第五阶双杂化泛函 (xyg3, xygjos, r-xdh7 + scc15, scsrpa)
   - 自动拆分经验色散 (empirical_dispersion = "d3bj")、自动匹配 basis_path 与 auxbas_path、
     自动设置 spin_polarization 与 outputs (["fchk", "cube_orb", "molden", "dipole"])
"""
from __future__ import annotations

from dataclasses import dataclass, field
from ..selection import SelectionService
from ...domain.document import MoleculeDocument
from ...domain.elements import get_element


@dataclass
class GaussianPreset:
    label: str
    route: str
    description: str


OSC_GAUSSIAN_PRESETS: list[GaussianPreset] = [
    GaussianPreset(
        label="OSC 基态几何优化 · B3LYP-D3(BJ)/6-31G(d)",
        route="#p B3LYP/6-31G(d) EmpiricalDispersion=GD3BJ opt freq",
        description="有机光伏给体/受体骨架标准基态构型优化与无虚频验证",
    ),
    GaussianPreset(
        label="OSC 前线轨道与偶极 · B3LYP-D3(BJ)/6-311G(d,p)",
        route="#p B3LYP/6-311G(d,p) EmpiricalDispersion=GD3BJ opt pop=full gfinput",
        description="计算精确 HOMO/LUMO 能级、偶极矩并输出轨道系数用于 Cube 渲染",
    ),
    GaussianPreset(
        label="OSC 长程校正几何与轨道 · wB97XD/def2SVP",
        route="#p wB97XD/def2SVP opt pop=full",
        description="适合 A-D-A 型非富勒烯受体（如 Y6/ITIC）的长程校正泛函优化",
    ),
    GaussianPreset(
        label="OSC 激发态吸收光谱 (TD-DFT) · CAM-B3LYP/6-311+G(d,p)",
        route="#p CAM-B3LYP/6-311+G(d,p) TD=(NStates=10) pop=full",
        description="计算前 10 个激发态 (S1~S10) 激发能、振子强度 f 与电荷转移特征",
    ),
    GaussianPreset(
        label="OSC 激发态吸收光谱 (TD-DFT) · wB97XD/def2SVP",
        route="#p wB97XD/def2SVP TD=(NStates=10) pop=full",
        description="大体系给体/受体寡聚物快速 TD-DFT 激发态计算",
    ),
    GaussianPreset(
        label="OSC 分子表面静电势 (ESP) · B3LYP/def2TZVP",
        route="#p B3LYP/def2TZVP pop=chelpg out=wfn",
        description="计算静电势电荷并输出 .wfn 波函数文件供 Multiwfn / MolForge 绘制 ESP",
    ),
]


@dataclass
class RestPreset:
    label: str
    xc: str
    basis: str
    auxbas: str = "def2-SV(P)-JKFIT"
    empirical_dispersion: str = ""
    post_ai_correction: str = ""
    job_type: str = "energy"
    eri_type: str = "ri-v"
    description: str = ""


OSC_REST_PRESETS: list[RestPreset] = [
    RestPreset(
        label="REST 杂化泛函单点与轨道 · B3LYP-D3BJ / def2-TZVPP",
        xc="b3lyp",
        basis="def2-TZVPP",
        empirical_dispersion="d3bj",
        job_type="energy",
        description="RI-V 加速 B3LYP-D3BJ 单点能与前线分子轨道输出",
    ),
    RestPreset(
        label="REST 几何结构优化 · PBE0-D3BJ / def2-SVP (opt)",
        xc="pbe0",
        basis="def2-SVP",
        empirical_dispersion="d3bj",
        job_type="opt",
        description="使用 LBFGS / geometric-pyo3 引擎做快速 DFT 结构优化",
    ),
    RestPreset(
        label="REST 旗舰双杂化泛函 · XYG3 / def2-QZVPP",
        xc="xyg3",
        basis="def2-QZVPP",
        empirical_dispersion="",
        job_type="energy",
        description="徐昕/张颖团队 XYG3 第五阶双杂化泛函高精度电子结构计算（无需额外色散校正）",
    ),
    RestPreset(
        label="REST 高效双杂化泛函 · XYGJOS / def2-TZVPP",
        xc="xygjos",
        basis="def2-TZVPP",
        empirical_dispersion="",
        job_type="energy",
        description="OS 异自旋标度双杂化泛函，兼顾大分子计算效率与高精度",
    ),
    RestPreset(
        label="REST AI 增强重整化双杂化 · R-xDH7-SCC15 / def2-QZVPP",
        xc="r-xdh7",
        basis="def2-QZVPP",
        post_ai_correction="scc15",
        job_type="energy",
        description="结合 SCC15 机器学习强关联校正的 R-xDH7 重整化双杂化泛函",
    ),
    RestPreset(
        label="REST 随机相位近似 · scsRPA / def2-QZVPP",
        xc="scsrpa",
        basis="def2-QZVPP",
        job_type="energy",
        description="自旋分量标度随机相位近似 (scs-RPA)，适合非共价相互作用与受体堆积体系",
    ),
]


def extract_xyz_lines(doc: MoleculeDocument) -> list[str]:
    """从 MoleculeDocument 提取标准元素符号与 3D 坐标行。"""
    doc.ensure_coordinates()
    atom_ids = list(doc.topology.atom_ids)
    n = len(atom_ids)
    if n == 0:
        return ["C    0.000000    0.000000    0.000000"]

    coords = doc.coordinates.current.coords if (doc.has_3d and doc.coordinates.current is not None) else None
    lines = []
    for i, aid in enumerate(atom_ids):
        atom = doc.topology.get_atom(aid)
        elem = get_element(atom.atomic_num)
        sym = elem.symbol if elem else "C"
        if coords is not None and i < len(coords):
            x, y, z = float(coords[i, 0]), float(coords[i, 1]), float(coords[i, 2])
        else:
            x2, y2 = doc.coords_2d.get(aid, (float(i * 1.4), 0.0))
            x, y, z = float(x2), float(y2), 0.0
        lines.append(f"{sym:<3s} {x:>14.8f} {y:>14.8f} {z:>14.8f}")
    return lines


def export_document_to_xyz(doc: MoleculeDocument, path: str | Any) -> str:
    """把当前 MoleculeDocument 导出为标准 XYZ 文件（纯计算/数据层，零 GUI 依赖）。"""
    from pathlib import Path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    atom_ids = list(doc.topology.atom_ids)
    lines = extract_xyz_lines(doc)
    text = f"{len(atom_ids)}\nMolForge canvas export · {doc.name}\n" + "\n".join(lines) + "\n"
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return str(p)


def generate_gaussian_gjf(
    doc: MoleculeDocument,
    route: str = "#p B3LYP/6-31G(d) EmpiricalDispersion=GD3BJ opt freq",
    charge: int = 0,
    multiplicity: int = 1,
    nproc: int = 16,
    mem_gb: int = 16,
    solvent: str = "",
    chk_name: str = "",
) -> str:
    """生成可直接提交给 Gaussian 09/16 的 .gjf 输入文件文本。"""
    stem = (doc.name or "molecule").replace(" ", "_")
    chk = chk_name.strip() or f"{stem}.chk"
    full_route = route.strip()
    if not full_route.startswith("#"):
        full_route = "#p " + full_route
    if solvent and solvent.lower() not in ("none", "gas", "气相", "") and "scrf" not in full_route.lower():
        full_route += f" SCRF=(PCM,Solvent={solvent})"

    xyz_lines = extract_xyz_lines(doc)
    lines = [
        f"%chk={chk}",
        f"%nprocshared={max(1, int(nproc))}",
        f"%mem={max(1, int(mem_gb))}GB",
        full_route,
        "",
        f"{doc.name or 'MolForge Structure'} | Generated by MolForge OSC Workbench",
        "",
        f"{int(charge)} {int(multiplicity)}",
        *xyz_lines,
        "",
    ]
    if "out=wfn" in full_route.lower():
        lines.append(f"{stem}.wfn")
        lines.append("")
    lines.append("")
    return "\n".join(lines)


def generate_rest_ctrl_in(
    doc: MoleculeDocument,
    xc: str = "b3lyp",
    basis: str = "def2-TZVPP",
    auxbas: str = "def2-SV(P)-JKFIT",
    empirical_dispersion: str = "d3bj",
    post_ai_correction: str = "",
    job_type: str = "energy",
    opt_engine: str = "lbfgs",
    eri_type: str = "ri-v",
    charge: float = 0.0,
    spin: int = 1,
    num_threads: int = 16,
    print_level: int = 1,
    basis_pool: str = "/mnt/e/YDW/REST/knowledge_base/rest_github/basis-set-pool",
    outputs: list[str] | None = None,
) -> str:
    """
    生成符合复旦大学 REST (Rust-based Electronic Structure Toolkit) 规范的 TOML 输入卡 (ctrl.in)。
    严格满足：
      - 仅含 [ctrl] 与 [geom] 两个 TOML 区块
      - 方法关键词使用 xc，色散校正单独使用 empirical_dispersion
      - 基组路径使用 basis_path 与 auxbas_path（根目录默认 /opt/rest_workspace/rest/basis-set-pool）
      - charge 与 spin 位于 [ctrl] 区，分子结构位于 [geom] 区的 position 多行双引号字符串
    """
    xc_clean = xc.strip().lower()
    disp_clean = empirical_dispersion.strip().lower()

    # 若用户传入了如 "b3lyp-d3bj"，自动拆分为 xc 与 empirical_dispersion
    for suffix in ("-d3bj", "-d3", "-d4"):
        if xc_clean.endswith(suffix):
            xc_clean = xc_clean[: -len(suffix)]
            disp_clean = suffix[1:]
            break

    # XYG3 型双杂化/RPA 泛函不额外加经验色散
    no_disp_methods = {"xyg3", "xyg7", "xygjos", "scsrpa", "r-xdh7", "rpa", "zrps", "sbge2"}
    if xc_clean in no_disp_methods:
        disp_clean = ""

    threads = max(10, int(num_threads))
    spin_int = max(1, int(spin))
    spin_pol = "true" if spin_int > 1 else "false"
    pool = basis_pool.rstrip("/")
    basis_path = f"{pool}/{basis.strip()}"
    auxbas_path = f"{pool}/{auxbas.strip()}"
    out_list = outputs if outputs is not None else ["fchk", "dipole"]
    out_toml = "[" + ", ".join(f'"{o}"' for o in out_list) + "]"

    ctrl_lines = [
        "[ctrl]",
        f'print_level = {int(print_level)}',
        f'num_threads = {threads}',
        f'job_type = "{job_type.strip()}"',
        f'xc = "{xc_clean}"',
    ]
    if disp_clean:
        ctrl_lines.append(f'empirical_dispersion = "{disp_clean}"')
    if post_ai_correction.strip():
        ctrl_lines.append(f'post_ai_correction = "{post_ai_correction.strip().lower()}"')
    if job_type.strip() == "opt":
        ctrl_lines.append(f'opt_engine = "{opt_engine.strip()}"')

    ctrl_lines.extend([
        f'eri_type = "{eri_type.strip()}"',
        f'basis_path = "{basis_path}"',
    ])
    if eri_type.strip().lower() != "analytic":
        ctrl_lines.append(f'auxbas_path = "{auxbas_path}"')

    ctrl_lines.extend([
        'basis_type = "spheric"',
        f'charge = {float(charge):.1f}',
        f'spin = {float(spin_int):.1f}',
        f'spin_polarization = {spin_pol}',
        'initial_guess = "sad"',
        'mixer = "diis"',
        'max_scf_cycle = 100',
        f'outputs = {out_toml}',
    ])
    if xc_clean in ("rpa", "scsrpa", "r-xdh7"):
        ctrl_lines.append("frequency_points = 20")

    xyz_lines = extract_xyz_lines(doc)
    xyz_block = "\n".join(xyz_lines)
    safe_name = "".join(c if (c.isalnum() or c in "_-") and ord(c) < 128 else "_" for c in (doc.name or "molforge"))
    clean_name = safe_name.strip("_") or "molforge_mol"

    geom_lines = [
        "",
        "[geom]",
        f'name = "{clean_name}"',
        'unit = "angstrom"',
        'position = """',
        xyz_block,
        '"""',
        "",
    ]
    return "\n".join(ctrl_lines + geom_lines)
