"""Input-validated OSC workflow helpers.

All external engines run serially, in a fresh output directory, with captured logs.
The pure parsers and geometry routines do not require Gaussian, Multiwfn, or VMD.
"""
from __future__ import annotations

import csv
import json
import math
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

HARTREE_TO_EV = 27.211386245988
BOHR_TO_ANGSTROM = 0.529177210903
ASSET_DIR = Path(__file__).resolve().parent / "assets"


@dataclass(frozen=True)
class FrontierLevels:
    source: str
    homo_orbital: int
    homo_ev: float
    lumo_ev: float
    gap_ev: float
    validation: str


def _fchk_field(path: str | Path, label: str) -> tuple[int, list[str]]:
    """Read one fixed-width Gaussian formatted-checkpoint array without loading the file."""
    p = Path(path)
    with p.open("r", encoding="ascii", errors="replace") as fh:
        for line in fh:
            if line.startswith(label):
                m = re.search(r"\bN=\s*(\d+)", line)
                if not m:
                    raise ValueError(f"字段 {label} 不包含数组长度")
                n = int(m.group(1))
                vals: list[str] = []
                while len(vals) < n:
                    block = fh.readline()
                    if not block:
                        break
                    vals.extend(block.split())
                if len(vals) < n:
                    raise ValueError(f"{label} 数据不完整：需要 {n} 项，读到 {len(vals)} 项")
                return n, vals[:n]
    raise ValueError(f"fchk 中找不到字段：{label}")


def read_fchk_orbitals(path: str | Path) -> tuple[int, np.ndarray]:
    """Return alpha-electron count and alpha orbital energies in eV."""
    p = Path(path)
    alpha = None
    with p.open("r", encoding="ascii", errors="replace") as fh:
        for line in fh:
            if line.startswith("Number of alpha electrons"):
                try:
                    alpha = int(line.split()[-1])
                except (ValueError, IndexError):
                    pass
                    
    if alpha is None:
        raise ValueError("fchk 缺少 Number of alpha electrons，无法确定 HOMO 轨道号")
    _, vals = _fchk_field(p, "Alpha Orbital Energies")
    energies = np.asarray([float(x.replace("D", "E")) for x in vals], dtype=float) * HARTREE_TO_EV
    if alpha < 1 or alpha >= len(energies):
        raise ValueError(f"alpha 电子数 {alpha} 与轨道数组长度 {len(energies)} 不匹配")
    return alpha, energies


def parse_log_frontier(path: str | Path) -> tuple[float, float]:
    """Return HOMO/LUMO from the last Gaussian alpha occupied/virtual eigenvalue blocks."""
    occ: list[float] = []
    virt: list[float] = []
    occ_re = re.compile(r"Alpha\s+occ\.\s+eigenvalues\s*--\s*(.*)", re.I)
    virt_re = re.compile(r"Alpha\s+virt\.\s+eigenvalues\s*--\s*(.*)", re.I)
    number_re = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[DEde][-+]?\d+)?")
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            om = occ_re.search(line)
            vm = virt_re.search(line)
            if om:
                if virt:
                    occ, virt = [], []
                occ += [float(x.replace("D", "E").replace("d", "e")) for x in number_re.findall(om.group(1))]
            elif vm:
                virt += [float(x.replace("D", "E").replace("d", "e")) for x in number_re.findall(vm.group(1))]
    if not occ or not virt:
        raise ValueError("Gaussian log 中没有完整的 Alpha occupied/virtual eigenvalues")
    return occ[-1] * HARTREE_TO_EV, virt[0] * HARTREE_TO_EV


def extract_frontier(fchk_path: str | Path, log_path: str | Path | None = None,
                     tolerance_ev: float = 0.05) -> FrontierLevels:
    alpha, energies = read_fchk_orbitals(fchk_path)
    homo, lumo = float(energies[alpha - 1]), float(energies[alpha])
    status = "fchk"
    if log_path:
        log_h, log_l = parse_log_frontier(log_path)
        dh, dl = abs(homo - log_h), abs(lumo - log_l)
        if max(dh, dl) > tolerance_ev:
            raise ValueError(f"fchk/log 能级差异超过 {tolerance_ev:.2f} eV（HOMO {dh:.3f}, LUMO {dl:.3f}）；请确认两个文件属于同一次计算")
        status = f"fchk/log 一致（最大差异 {max(dh, dl):.4f} eV）"
    return FrontierLevels(Path(fchk_path).stem, alpha, homo, lumo, lumo - homo, status)


def read_fchk_geometry(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Return atomic numbers and Cartesian coordinates in Angstrom."""
    _, zs = _fchk_field(path, "Atomic numbers")
    _, xyz = _fchk_field(path, "Current cartesian coordinates")
    z = np.asarray([int(x) for x in zs], dtype=int)
    coords = np.asarray([float(x.replace("D", "E")) for x in xyz], dtype=float).reshape(-1, 3)
    if len(z) != len(coords) or not len(z):
        raise ValueError("fchk 原子序数与坐标数不一致或分子为空")
    return z, coords * BOHR_TO_ANGSTROM


def planarity_from_coordinates(atomic_numbers: Iterable[int], coords: Iterable[Iterable[float]]) -> dict:
    z = np.asarray(list(atomic_numbers), dtype=int)
    xyz = np.asarray(list(coords), dtype=float).reshape(-1, 3)
    if len(z) != len(xyz):
        raise ValueError("原子序数和坐标数量不同")
    keep = z != 1
    pts = xyz[keep]
    if len(pts) < 3:
        raise ValueError("平面性分析至少需要 3 个重原子")
    center = pts.mean(axis=0)
    _u, _s, vt = np.linalg.svd(pts - center, full_matrices=False)
    normal = vt[-1]
    signed = (pts - center) @ normal
    abs_dev = np.abs(signed)
    return {
        "heavy_atom_count": int(len(pts)),
        "rmsd_angstrom": float(np.sqrt(np.mean(signed**2))),
        "max_deviation_angstrom": float(abs_dev.max()),
        "span_angstrom": float(signed.max() - signed.min()),
        "normal": [float(x) for x in normal],
        "center_angstrom": [float(x) for x in center],
    }


def new_output_dir(base: str | Path, prefix: str) -> Path:
    base = Path(base).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    stem = f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}"
    out = base / stem
    i = 2
    while out.exists():
        out = base / f"{stem}_{i}"
        i += 1
    out.mkdir()
    return out


def _engine(tool_id: str) -> str:
    from ..io.calculators import EngineToolRegistry
    status = EngineToolRegistry.detect_tool(tool_id)
    if not status.available or not status.executable_path:
        raise RuntimeError(status.diagnostic)
    return status.executable_path


def _run(argv: list[str], cwd: Path, stdin: str = "", timeout: int = 3600,
         allow_nonzero: bool = False) -> str:
    proc = subprocess.run(argv, input=stdin, cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, shell=False)
    log = proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
    (cwd / f"{Path(argv[0]).stem}_last.log").write_text(log, encoding="utf-8")
    if proc.returncode and not allow_nonzero:
        raise RuntimeError(f"外部程序退出码 {proc.returncode}；查看 {Path(argv[0]).stem}_last.log")
    return log


def _patched_vmd_script(source: Path, destination: Path, tachyon: str | None = None) -> Path:
    text = source.read_text(encoding="utf-8", errors="replace")
    # These user scripts pin Tachyon to a previous workstation; resolve beside the detected VMD.
    text = re.sub(r'"D:/VMD/tachyon_WIN64\.exe"', lambda _m: f'"{(Path(tachyon).as_posix() if tachyon else "tachyon_WIN64.exe")}"', text)
    destination.write_text(text, encoding="utf-8")
    return destination


def run_esp_surface(fchk: str | Path, output_parent: str | Path, isovalue: float = 0.001) -> Path:
    fchk = Path(fchk).resolve()
    if not fchk.is_file() or fchk.suffix.lower() != ".fchk":
        raise ValueError("ESP 表面分析需要存在的 Gaussian .fchk 文件")
    mwfn, vmd = _engine("multiwfn"), _engine("vmd")
    out = new_output_dir(output_parent, f"ESP_{fchk.stem}")
    assets = ASSET_DIR / "esp-surface-analysis" / "scripts"
    (out / "ESPiso_input.txt").write_text((assets / "ESPiso_input.txt").read_text(encoding="utf-8"), encoding="utf-8")
    # Workflow specifies separate commands because ESPrhoiso creates cubes while menu 12 exports surface PDBs.
    log1 = _run([mwfn, str(fchk), "-ESPrhoiso", str(isovalue)], out,
                stdin=(out / "ESPiso_input.txt").read_text(encoding="utf-8"), timeout=3600, allow_nonzero=True)
    esp_menu = "12\n3\n0.15\n0\n5\nmol.pdb\n6\n2\nq\n"
    log2 = _run([mwfn, str(fchk)], out, stdin=esp_menu, timeout=3600, allow_nonzero=True)
    (out / "multiwfn_esp.log").write_text(log1 + "\n--- surface analysis ---\n" + log2, encoding="utf-8")
    for target, patterns in (("density.cub", ["*_density.cub", "density.cub"]),
                             ("totesp.cub", ["*_totesp.cub", "totesp.cub"])):
        dest=out/target
        if not dest.exists():
            candidate=next((q for pattern in patterns for q in out.glob(pattern) if q.is_file()),None)
            if candidate is not None and candidate != dest: candidate.replace(dest)
    needed = ["density.cub", "totesp.cub", "mol.pdb", "surfanalysis.pdb", "vtx.pdb"]
    missing = [n for n in needed if not (out / n).is_file()]
    if missing:
        raise RuntimeError("Multiwfn 未生成所需文件：" + ", ".join(missing) + f"。输出保留在 {out}")
    from ..io.calculators import EngineToolRegistry, MultiwfnAdapter
    metrics=MultiwfnAdapter.parse_esp_summary_text(log1+"\n"+log2)
    (out/"esp_descriptors.json").write_text(json.dumps(metrics,indent=2,ensure_ascii=False),encoding="utf-8")
    if not metrics:
        (out/"esp_descriptor_status.txt").write_text("没有从本次 Multiwfn 文本中识别到描述符字段；请核对 Multiwfn 日志与版本。\n",encoding="utf-8")
    vmd_status = EngineToolRegistry.detect_tool("vmd")
    tachyon = str(Path(vmd_status.executable_path).parent / "tachyon_WIN64.exe")
    tcl = _patched_vmd_script(assets / "draw_ESP.tcl", out / "draw_ESP.tcl", tachyon)
    vsurf = _read_extrema(out / "surfanalysis.pdb")
    low, high = vsurf if vsurf else (-35.0, 35.0)
    # Skill requires per-molecule extrema with a 20% margin; do not reuse fixed ranges.
    margin = max(abs(low), abs(high)) * 0.2
    colorlow, colorhigh = (low - margin) / 627.51, (high + margin) / 627.51
    bmp = out / f"{fchk.stem}_esp.bmp"
    _run([vmd, "-dispdev", "text", "-e", str(tcl), "-args",
          "mol.pdb", "surfanalysis.pdb", "density.cub", "totesp.cub", str(bmp),
          str(isovalue), f"{colorlow:.6f}", f"{colorhigh:.6f}"], out, timeout=3600)
    if not bmp.is_file():
        raise RuntimeError(f"VMD 未生成 ESP 图像：{bmp}；请查看 VMD 日志")
    return out


def _read_extrema(path: Path) -> tuple[float, float] | None:
    maxima, minima = [], []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("HETATM"):
            continue
        try:
            atom = line[12:16].strip()
            value = float(line[60:66])
            if atom == "C": maxima.append(value)
            elif atom == "O": minima.append(value)
        except (ValueError, IndexError):
            continue
    if not maxima or not minima:
        return None
    return min(minima), max(maxima)


def export_osc_levels(inputs: Iterable[tuple[str | Path, str | Path | None]], output_parent: str | Path) -> Path:
    records = [asdict(extract_frontier(fchk, log)) for fchk, log in inputs]
    if len(records) < 2:
        raise ValueError("OSC 能级比较至少需要两个分子")
    out = new_output_dir(output_parent, "OSC_energy")
    (out / "levels.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out / "levels.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(records[0]))
        w.writeheader(); w.writerows(records)
    write_levels_svg(records, out / "osc_energy_levels.svg")
    _write_rectangle_svg(records, out / "osc_rectangle_levels.svg")
    _write_grid_svg(records, out / "osc_2xN_levels.svg")
    _write_energy_workbook(records, out / "osc_energy_levels.xlsx")
    _write_editable_pptx(records, out / "osc_energy_levels.pptx")
    return out


def write_levels_svg(records: list[dict], output: str | Path) -> None:
    width, height = 1000, 620
    left, right, top, bottom = 100, 35, 45, 95
    emin = min(-6.5, min(x["homo_ev"] for x in records) - .4)
    emax = max(-2.2, max(x["lumo_ev"] for x in records) + .4)
    def y(e): return top + (emax - e) / (emax - emin) * (height - top - bottom)
    step = (width-left-right) / len(records)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>', '<g font-family="Arial,sans-serif" fill="#263746">']
    for tick_i in range(math.ceil(emin*2), math.floor(emax*2)+1):
        e=tick_i/2; yy=y(e)
        parts += [f'<path d="M{left} {yy:.1f}H{width-right}" stroke="#e3e9ee"/>',
                  f'<text x="{left-12}" y="{yy+5:.1f}" text-anchor="end" font-size="14">{e:.1f} eV</text>']
    parts.append(f'<path d="M{left} {top}V{height-bottom}" stroke="#314555" stroke-width="2"/>')
    colors=['#198c8c','#dd7a35','#5679bb','#6a9b65','#aa6594','#bc9b36']
    for i, rec in enumerate(records):
        cx=left+(i+.5)*step; col=colors[i%len(colors)]
        yh, yl=y(rec['homo_ev']), y(rec['lumo_ev'])
        parts += [f'<path d="M{cx-35} {yh:.1f}H{cx+35}" stroke="#163246" stroke-width="4"/>',
                  f'<path d="M{cx-35} {yl:.1f}H{cx+35}" stroke="{col}" stroke-width="4"/>',
                  f'<text x="{cx}" y="{yh+20:.1f}" text-anchor="middle" font-size="13">{rec["homo_ev"]:.2f}</text>',
                  f'<text x="{cx}" y="{yl-9:.1f}" text-anchor="middle" font-size="13">{rec["lumo_ev"]:.2f}</text>',
                  f'<text x="{cx}" y="{height-bottom+25}" text-anchor="middle" font-size="13">{_xml(rec["source"])}</text>',
                  f'<text x="{cx}" y="{height-bottom+47}" text-anchor="middle" font-size="12" fill="#697987">Gap {rec["gap_ev"]:.2f} eV</text>']
    parts += ['</g></svg>']
    Path(output).write_text('\n'.join(parts), encoding='utf-8')


def _xml(text: str) -> str:
    return str(text).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')


def analyze_fchk_planarity(fchk: str | Path, output_parent: str | Path) -> Path:
    fchk = Path(fchk).resolve()
    result = planarity_from_coordinates(*read_fchk_geometry(fchk))
    result.update(source=str(fchk), metric="重原子最佳拟合平面 RMSD")
    out = new_output_dir(output_parent, f"Planarity_{fchk.stem}")
    (out / "planarity.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    with (out / "planarity.csv").open("w", newline="", encoding="utf-8-sig") as fh:
        w=csv.writer(fh); w.writerow(["metric","value","unit"])
        for k,v in result.items():
            if isinstance(v,(int,float)): w.writerow([k,v,"Å" if "angstrom" in k else ""])
    return out


def analyze_fchk_dipole(fchk: str | Path, output_parent: str | Path) -> Path:
    fchk = Path(fchk).resolve()
    _, values = _fchk_field(fchk, "Dipole Moment")
    vec = np.asarray([float(x.replace("D","E")) for x in values[:3]], dtype=float)
    if vec.size != 3:
        raise ValueError("fchk 偶极矩字段不是三维向量")
    result = {"source": str(fchk), "dipole_au": vec.tolist(),
              "dipole_debye": float(np.linalg.norm(vec) * 2.541746473),
              "note": "总偶极矩取自 fchk；分片段偶极需要用户定义片段并另行运行 Multiwfn。"}
    out = new_output_dir(output_parent, f"Dipole_{fchk.stem}")
    (out / "dipole.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        image=_render_total_dipole(fchk, vec, out)
        result["rendered_image"]=str(image)
        (out/"dipole.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    except Exception as exc:
        (out/"dipole_render_status.txt").write_text(f"总偶极矩数值已导出；3D 箭头未生成：{exc}\n",encoding="utf-8")
    return out



def _render_total_dipole(fchk, dipole, out):
    vmd=_engine("vmd")
    from ..io.calculators import EngineToolRegistry
    status=EngineToolRegistry.detect_tool("vmd")
    tachyon=Path(status.executable_path).parent/"tachyon_WIN64.exe"
    if not tachyon.is_file():raise RuntimeError("VMD 目录中找不到 tachyon_WIN64.exe")
    z,coords=read_fchk_geometry(fchk)
    symbols={1:"H",6:"C",7:"N",8:"O",9:"F",15:"P",16:"S",17:"Cl",35:"Br",53:"I"}
    xyz=out/(Path(fchk).stem+".xyz")
    with xyz.open("w",encoding="utf-8") as fh:
        fh.write(f"{len(z)}\n{Path(fchk).stem}\n")
        for atom,point in zip(z,coords):fh.write(f"{symbols.get(int(atom), 'C')} {point[0]:.8f} {point[1]:.8f} {point[2]:.8f}\n")
    center=coords.mean(axis=0);vector=np.asarray(dipole,dtype=float)*1.2
    start=center-vector*.5;mid=center+vector*.25;end=center+vector*.5
    image=out/(Path(fchk).stem+"_dipole.bmp");base=out/(Path(fchk).stem+"_dipole.tga")
    def fmt(v):return " ".join(f"{float(x):.8f}" for x in v)
    lines=[f"mol new {{{xyz.as_posix()}}} type xyz waitfor all",
           "mol modstyle 0 top CPK 1.0 0.3 22.0 22.0","color Display Background white",
           "axes location Off","display projection Orthographic",f'set beg "{fmt(start)}"',
           f'set mid "{fmt(mid)}"',f'set end "{fmt(end)}"',"draw color blue",
           "draw cylinder $beg $mid radius 0.12 filled yes resolution 20",
           "draw cone $mid $end radius 0.30 resolution 20","display resetview","scale by 1.15",
           f"render Tachyon {{{base.as_posix()}}} {{{tachyon.as_posix()}}} -aasamples 12 -format BMP -o {{{image.as_posix()}}}","quit"]
    tcl=out/"render_total_dipole.tcl";tcl.write_text("\n".join(lines)+"\n",encoding="utf-8")
    _run([vmd,"-dispdev","text","-e",str(tcl)],out,timeout=1800)
    if not image.is_file():raise RuntimeError("VMD 未生成偶极矩图像")
    return image

def run_homo_lumo(fchks: Iterable[str | Path], output_parent: str | Path,
                  log_by_stem: dict[str, str | Path] | None = None) -> Path:
    files = [Path(p).resolve() for p in fchks]
    if not files or any(not p.is_file() or p.suffix.lower() != ".fchk" for p in files):
        raise ValueError("HOMO/LUMO 流程需要一个或多个有效 .fchk 文件")
    mwfn, vmd = _engine("multiwfn"), _engine("vmd")
    out = new_output_dir(output_parent, "HOMO_LUMO")
    log_by_stem = log_by_stem or {}
    records=[]
    script = ASSET_DIR / "homo-lumo-plot" / "render_one.tcl"
    from ..io.calculators import EngineToolRegistry
    vmd_status=EngineToolRegistry.detect_tool("vmd")
    tcl=_patched_vmd_script(script, out / "render_one.tcl", str(Path(vmd_status.executable_path).parent / "tachyon_WIN64.exe"))
    for fchk in files:
        log = log_by_stem.get(fchk.stem)
        rec=asdict(extract_frontier(fchk, log))
        records.append(rec)
        mol_dir=out / fchk.stem; mol_dir.mkdir()
        for orbital,label in ((rec["homo_orbital"],"HOMO"),(rec["homo_orbital"]+1,"LUMO")):
            _run([mwfn,str(fchk)],mol_dir,stdin=f"200\n3\n{orbital}\n3\n1\n",timeout=1800,allow_nonzero=True)
            cub=mol_dir / f"orb{orbital:07d}.cub"
            if not cub.is_file():
                # Some Multiwfn builds emit a variant with an unpadded orbital number.
                candidates=list(mol_dir.glob("orb*.cub"))
                if len(candidates)==1: cub=candidates[0]
                else: raise RuntimeError(f"Multiwfn 没有生成第 {orbital} 轨道 cube；查看 {mol_dir}")
            base=mol_dir / f"{fchk.stem}_{label}"
            _run([vmd,"-dispdev","text","-e",str(tcl),"-args",str(cub),str(base),"0.005"],mol_dir,timeout=1800)
            if not Path(str(base)+".bmp").is_file():
                raise RuntimeError(f"VMD 未生成 {label} 图；输出保留在 {mol_dir}")
            cub.rename(mol_dir / f"{fchk.stem}_{label}.cub")
    (out/"levels.json").write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding="utf-8")
    if len(records)>=2: write_levels_svg(records,out/"homo_lumo_levels.svg")
    with (out/"levels.csv").open("w",newline="",encoding="utf-8-sig") as fh:
        w=csv.DictWriter(fh,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    return out


def _structure_arrays(doc):
    z=np.asarray([doc.topology.get_atom(a).atomic_num for a in doc.topology.atom_ids],dtype=int)
    if not doc.has_3d or doc.coordinates.current is None:
        raise ValueError(f"{doc.name} 没有 3D 坐标")
    xyz=np.asarray(doc.coordinates.current.coords,dtype=float)
    return z,xyz


def detect_pair_interactions(doc_a, doc_b, output_parent: str | Path) -> Path:
    """Report cross-molecule heavy-atom contacts and geometry-qualified N/O/S hydrogen bonds."""
    za,xa=_structure_arrays(doc_a); zb,xb=_structure_arrays(doc_b)
    symbols={1:'H',6:'C',7:'N',8:'O',9:'F',15:'P',16:'S',17:'Cl',35:'Br',53:'I'}
    radii={1:1.2,6:1.7,7:1.55,8:1.52,9:1.47,15:1.8,16:1.8,17:1.75,35:1.85,53:1.98}
    heavy_a=np.where(za!=1)[0];heavy_b=np.where(zb!=1)[0]
    contacts=[];hbonds=[]
    for i in heavy_a:
        for j in heavy_b:
            d=float(np.linalg.norm(xa[i]-xb[j]))
            cutoff=radii.get(int(za[i]),1.8)+radii.get(int(zb[j]),1.8)+0.5
            if d <= cutoff:
                contacts.append({'atom_a':int(i+1),'element_a':symbols.get(int(za[i]),str(int(za[i]))),
                                 'atom_b':int(j+1),'element_b':symbols.get(int(zb[j]),str(int(zb[j]))),
                                 'distance_angstrom':d,'vdw_overlap_angstrom':cutoff-d})
            # Explicit-H D-H...A test. Donors are N/O/S; acceptors are N/O/S.
            if int(zb[j]) in (7,8,16):
                _check_hbond(doc_a,doc_b,xa,xb,za,zb,i,j,True,hbonds)
            if int(za[i]) in (7,8,16):
                _check_hbond(doc_b,doc_a,xb,xa,zb,za,j,i,False,hbonds)
    result={'molecule_a':doc_a.name,'molecule_b':doc_b.name,
            'contact_count':len(contacts),'hydrogen_bond_count':len(hbonds),
            'contacts':contacts,'hydrogen_bonds':hbonds,
            'pi_stacking':_pi_stack_pairs(doc_a,doc_b,xa,xb),
            'limitations':'范德华接触阈值为元素半径筛查近似；氢键角度和距离采用几何判据，不替代能量分析。'}
    out=new_output_dir(output_parent,'Interactions')
    (out/'interactions.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    with (out/'contacts.csv').open('w',newline='',encoding='utf-8-sig') as f:
        keys=['atom_a','element_a','atom_b','element_b','distance_angstrom','vdw_overlap_angstrom']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(contacts)
    return out


def _check_hbond(donor_doc,acceptor_doc,xd,xa,zd,za,donor_idx,acceptor_idx,acceptor_is_b,out):
    acc=int(za[acceptor_idx])
    if int(zd[donor_idx]) not in (7,8,16): return
    for hidx in np.where(zd==1)[0]:
        if np.linalg.norm(xd[hidx]-xd[donor_idx])>1.25: continue
        da=float(np.linalg.norm(xd[donor_idx]-xa[acceptor_idx]))
        ha=float(np.linalg.norm(xd[hidx]-xa[acceptor_idx]))
        if da>3.6 or ha>2.6: continue
        v1=xd[donor_idx]-xd[hidx];v2=xa[acceptor_idx]-xd[hidx]
        den=float(np.linalg.norm(v1)*np.linalg.norm(v2))
        angle=math.degrees(math.acos(float(np.clip(np.dot(v1,v2)/den,-1,1)))) if den else 0
        if angle>=120:
            out.append({'donor':donor_doc.name,'donor_atom':int(donor_idx+1),'hydrogen_atom':int(hidx+1),
                        'acceptor':acceptor_doc.name,'acceptor_atom':int(acceptor_idx+1),
                        'D_A_angstrom':da,'H_A_angstrom':ha,'D_H_A_degree':angle})



def _pi_stack_pairs(doc_a,doc_b,xa,xb):
    try:
        from ..io.rdkit_adapter import doc_to_rdkit
        ma=doc_to_rdkit(doc_a,sanitize=True)[0]; mb=doc_to_rdkit(doc_b,sanitize=True)[0]
    except Exception:
        return []
    def rings(m,xyz):
        out=[]
        for ids in m.GetRingInfo().AtomRings():
            if len(ids)<5 or not all(m.GetAtomWithIdx(i).GetIsAromatic() for i in ids):continue
            pts=xyz[list(ids)];center=pts.mean(axis=0)
            _u,_s,vt=np.linalg.svd(pts-center,full_matrices=False)
            out.append((tuple(int(i+1) for i in ids),center,vt[-1]))
        return out
    result=[]
    for ia,ca,na in rings(ma,xa):
        for ib,cb,nb in rings(mb,xb):
            delta=cb-ca;dist=float(np.linalg.norm(delta))
            if not 3.0<=dist<=6.0:continue
            angle=math.degrees(math.acos(float(np.clip(abs(np.dot(na,nb)),-1,1))))
            vertical=abs(float(np.dot(delta,na)))
            lateral=math.sqrt(max(0.,dist*dist-vertical*vertical))
            geometry=('parallel' if angle<=30 and vertical<=4.0 and lateral<=4.5
                      else 'T-shaped' if angle>=60 and 3.0<=vertical<=5.0 else None)
            if geometry:
                result.append({'ring_a_atoms':ia,'ring_b_atoms':ib,'centroid_distance_angstrom':dist,
                               'plane_angle_degree':angle,'geometry':geometry})
    return result

def _kabsch_rmsd(reference: np.ndarray, mobile: np.ndarray) -> float:
    a=reference-reference.mean(axis=0);b=mobile-mobile.mean(axis=0)
    u,_s,vt=np.linalg.svd(b.T@a);d=np.linalg.det(u@vt)
    rot=u@np.diag([1.,1.,d])@vt
    delta=b@rot-a
    return float(np.sqrt(np.mean(np.sum(delta*delta,axis=1))))


def run_md_postprocess(topology: str | Path, trajectory: str | Path, output_parent: str | Path) -> Path:
    """Use MDAnalysis to calculate aligned RMSD and radius of gyration per frame."""
    try: import MDAnalysis as mda
    except ImportError as exc: raise RuntimeError('MD 轨迹分析需要安装 MDAnalysis（requirements-md.txt）。') from exc
    top,traj=Path(topology).resolve(),Path(trajectory).resolve()
    if not top.is_file() or not traj.is_file(): raise ValueError('拓扑或轨迹文件不存在')
    universe=mda.Universe(str(top),str(traj))
    if len(universe.atoms)==0: raise ValueError('轨迹中没有原子')
    frames=[];reference=None
    for ts in universe.trajectory:
        coords=np.asarray(universe.atoms.positions,dtype=float).copy()
        if reference is None: reference=coords.copy()
        rg=float(universe.atoms.radius_of_gyration())
        frames.append({'frame':int(ts.frame),'time_ps':float(getattr(ts,'time',ts.frame)),
                       'rmsd_angstrom':_kabsch_rmsd(reference,coords),'rg_angstrom':rg})
    if not frames: raise ValueError('轨迹中没有帧')
    # Deterministic coarse clustering by aligned RMSD and Rg features.
    values=np.asarray([[x['rmsd_angstrom'],x['rg_angstrom']] for x in frames],dtype=float)
    scale=values.std(axis=0);scale[scale<1e-12]=1.0
    feat=(values-values.mean(axis=0))/scale;k=min(3,len(feat))
    centers=feat[np.linspace(0,len(feat)-1,k,dtype=int)].copy()
    for _ in range(40):
        labels=np.argmin(((feat[:,None,:]-centers[None,:,:])**2).sum(axis=2),axis=1)
        updated=np.asarray([feat[labels==j].mean(axis=0) if np.any(labels==j) else centers[j] for j in range(k)])
        if np.allclose(updated,centers):break
        centers=updated
    for row,cluster in zip(frames,labels):row['cluster_id']=int(cluster+1)
    hbonds={'status':'not_run','count':0,'occupancy':[]}
    try:
        from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis
        hba=HydrogenBondAnalysis(universe,d_a_cutoff=3.5,d_h_a_angle_cutoff=150.0)
        hba.run()
        data=np.asarray(hba.results.hbonds)
        hbonds['status']='ok'
        hbonds['count']=int(len(data))
        if data.size:
            pairs={}
            for record in data:
                key=(int(record[1]),int(record[3]));pairs.setdefault(key,set()).add(int(record[0]))
            hbonds['occupancy']=[{'donor_index':a,'acceptor_index':b,'fraction':len(fs)/max(1,len(frames))}
                                 for (a,b),fs in sorted(pairs.items())]
    except Exception as exc:
        hbonds={'status':'unavailable','count':0,'occupancy':[],'diagnostic':str(exc)}
    out=new_output_dir(output_parent,f"MD_{top.stem}")
    with (out/'md_rmsd_rg.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(frames[0]));w.writeheader();w.writerows(frames)
    (out/'md_summary.json').write_text(json.dumps({'topology':str(top),'trajectory':str(traj),
        'frames':len(frames),'atoms':len(universe.atoms),'cluster_count':k,'hbond_analysis':hbonds,
        'warning':'未自动处理周期边界；聚类基于对齐 RMSD/Rg 两个特征，不是全原子自由能聚类。'},
        indent=2,ensure_ascii=False),encoding='utf-8')
    return out


def calculate_pair_energy_components(csv_path: str | Path, output_parent: str | Path) -> Path:
    """Calculate component-wise E(AB)-E(A)-E(B) from exported GROMACS energy means.

    CSV columns: system (AB/A/B), component, mean_kj_mol. This is a classical
    force-field rerun decomposition; it is not a quantum-chemical sobEDA result.
    """
    p=Path(csv_path).resolve();values={}
    with p.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        required={'system','component','mean_kj_mol'}
        if not required.issubset(set(reader.fieldnames or [])):
            raise ValueError('CSV 必须包含 system, component, mean_kj_mol 三列；system 使用 AB、A、B。')
        for row in reader: values.setdefault(row['system'].strip().upper(),{})[row['component'].strip()]=float(row['mean_kj_mol'])
    if not all(x in values for x in ('AB','A','B')): raise ValueError('输入数据必须包含 AB、A、B 三个体系。')
    common=set(values['AB'])&set(values['A'])&set(values['B'])
    if not common: raise ValueError('三个体系没有同名能量分量。')
    result=[{'component':k,'AB_kj_mol':values['AB'][k],'A_kj_mol':values['A'][k],
             'B_kj_mol':values['B'][k],'interaction_kj_mol':values['AB'][k]-values['A'][k]-values['B'][k]}
            for k in sorted(common)]
    out=new_output_dir(output_parent,f"Gromacs_EDA_{p.stem}")
    with (out/'interaction_energy_components.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    (out/'method.txt').write_text('经典力场 rerun 分量差：ΔE(component)=E_AB-E_A-E_B。此结果不是 sobEDA/量子化学能量分解。\n',encoding='utf-8')
    return out


def _write_rectangle_svg(records, output):
    width,height=1050,620;left,right,top,bottom=100,35,40,90
    emin=min(-6.5,min(r['homo_ev'] for r in records)-.4);emax=max(-2.2,max(r['lumo_ev'] for r in records)+.4)
    y=lambda e:top+(emax-e)/(emax-emin)*(height-top-bottom)
    step=(width-left-right)/len(records);parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/>']
    for k in range(math.ceil(emin*2),math.floor(emax*2)+1):
        e=k/2; yy=y(e);parts.append(f'<path d="M{left} {yy:.1f}H{width-right}" stroke="#e2e8ef"/><text x="{left-10}" y="{yy+4:.1f}" text-anchor="end" font-size="13">{e:.1f}</text>')
    colors=['#227c83','#d8793d','#4f73aa','#759452','#a45d91']
    for i,r in enumerate(records):
        cx=left+(i+.5)*step; y1,y2=y(r['lumo_ev']),y(r['homo_ev']); c=colors[i%len(colors)]
        parts += [f'<rect x="{cx-45:.1f}" y="{y1:.1f}" width="90" height="{max(2,y2-y1):.1f}" fill="{c}" fill-opacity=".13" stroke="{c}" stroke-width="3"/>',
                  f'<text x="{cx}" y="{y1-8:.1f}" text-anchor="middle" font-size="13">LUMO {r["lumo_ev"]:.2f}</text>',
                  f'<text x="{cx}" y="{y2+20:.1f}" text-anchor="middle" font-size="13">HOMO {r["homo_ev"]:.2f}</text>',
                  f'<text x="{cx}" y="{height-bottom+24}" text-anchor="middle" font-size="14">{_xml(r["source"])}</text>']
    parts.append('</svg>');Path(output).write_text('\n'.join(parts),encoding='utf-8')


def _write_grid_svg(records, output):
    width=max(800,240*len(records));height=620;gap=width/len(records);parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/>']
    colors=['#267a83','#cf753b','#5175a8','#78954e','#a45e91']
    for row,label,key in ((0,'LUMO','lumo_ev'),(1,'HOMO','homo_ev')):
        ybase=210+row*270
        parts.append(f'<text x="20" y="{ybase+15}" font-family="Arial" font-weight="bold" font-size="20">{label}</text>')
        for i,r in enumerate(records):
            cx=(i+.5)*gap;value=r[key];c=colors[i%len(colors)]
            parts += [f'<path d="M{cx-38} {ybase}H{cx+38}" stroke="{c}" stroke-width="5"/>',
                      f'<text x="{cx}" y="{ybase-12}" text-anchor="middle" font-family="Arial" font-size="18">{value:.2f} eV</text>',
                      f'<text x="{cx}" y="{ybase+40}" text-anchor="middle" font-family="Arial" font-size="13">{_xml(r["source"])}</text>']
    parts.append('</svg>');Path(output).write_text('\n'.join(parts),encoding='utf-8')


def _write_energy_workbook(records, output):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill,Alignment,Border,Side
    except ImportError:
        Path(str(output)+'.missing.txt').write_text('Install openpyxl to export this workbook.\n',encoding='utf-8');return
    wb=Workbook();ws=wb.active;ws.title='HOMO_LUMO'
    headers=['Molecule','HOMO (eV)','LUMO (eV)','Gap (eV)','Source validation']
    ws.append(headers)
    for r in records:ws.append([r['source'],r['homo_ev'],r['lumo_ev'],r['gap_ev'],r['validation']])
    fill=PatternFill('solid',fgColor='D9E1F2');thin=Side(style='thin',color='AAB7C4')
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment=Alignment(horizontal='center',vertical='center');cell.border=Border(left=thin,right=thin,top=thin,bottom=thin)
            if cell.row==1:cell.font=Font(bold=True);cell.fill=fill
    for col,width in {'A':24,'B':16,'C':16,'D':14,'E':34}.items():ws.column_dimensions[col].width=width
    note=wb.create_sheet('Notes');note.append(['Method','HOMO from alpha electron count; energies converted with 27.211386245988 eV/Ha.'])
    note.append(['Validation','fchk and matching Gaussian log must agree within 0.05 eV.'])
    wb.save(output)


def _write_editable_pptx(records, output):
    try:
        from pptx import Presentation
        from pptx.util import Inches,Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from pptx.enum.shapes import MSO_CONNECTOR
    except ImportError:
        Path(str(output)+'.missing.txt').write_text('Install python-pptx to export the editable PowerPoint.\n',encoding='utf-8');return
    prs=Presentation();slide=prs.slides.add_slide(prs.slide_layouts[6]);left=1.1;right=12.3;top=.8;bottom=6.2
    emin=min(-6.5,min(r['homo_ev'] for r in records)-.4);emax=max(-2.2,max(r['lumo_ev'] for r in records)+.4)
    y=lambda e:top+(emax-e)/(emax-emin)*(bottom-top)
    axis=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(left),Inches(top),Inches(left),Inches(bottom));axis.line.color.rgb=RGBColor(45,62,78)
    for i,r in enumerate(records):
        cx=left+.6+(right-left-1.2)*(i/max(1,len(records)-1))
        for key,color in [('lumo_ev',RGBColor(210,88,62)),('homo_ev',RGBColor(38,79,95))]:
            line=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(cx-.42),Inches(y(r[key])),Inches(cx+.42),Inches(y(r[key])))
            line.line.color.rgb=color;line.line.width=Pt(3)
            box=slide.shapes.add_textbox(Inches(cx-.6),Inches(y(r[key])-.25),Inches(1.2),Inches(.22));box.text_frame.text=f'{r[key]:.2f} eV';box.text_frame.paragraphs[0].alignment=PP_ALIGN.CENTER;box.text_frame.paragraphs[0].font.size=Pt(10)
        box=slide.shapes.add_textbox(Inches(cx-.8),Inches(6.35),Inches(1.6),Inches(.35));box.text_frame.text=r['source'];box.text_frame.paragraphs[0].alignment=PP_ALIGN.CENTER;box.text_frame.paragraphs[0].font.size=Pt(10)
    prs.save(output)
