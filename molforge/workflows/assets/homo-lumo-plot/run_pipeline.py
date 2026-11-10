# -*- coding: utf-8 -*-
"""一键流水线：fchk → cube → VMD渲染 → 能级图"""
import os, sys, subprocess, json, argparse

MULTIWFN = r"<MULTIWFN_DIR>\Multiwfn_3.8_bin_Win64\Multiwfn.exe"
VMD = r"<VMD_DIR>\vmd.exe"
TREND = os.path.dirname(os.path.abspath(__file__))

def gen_cube(fchk_path, orb_num, out_dir):
    """用 Multiwfn 生成指定轨道的 cube 文件"""
    inp = os.path.join(out_dir, "_in.txt")
    # Multiwfn 命令序列: 200 (其他功能) -> 3 (生成cube) -> orb_num -> 3 -> 1
    with open(inp, 'w') as f:
        f.write(f"200\n3\n{orb_num}\n3\n1\n")
    os.chdir(out_dir)
    subprocess.run([MULTIWFN, fchk_path], stdin=open(inp), capture_output=True)
    # Multiwfn 输出 orb000XXX.cub
    cub = os.path.join(out_dir, f"orb{orb_num:07d}.cub")
    return cub if os.path.exists(cub) else None

def render_cube(cub_path, out_name, out_dir, isoval=0.005):
    """用 VMD + Tachyon 渲染 cube 为 bmp"""
    tcl = os.path.join(TREND, "render_one.tcl")
    out_base = os.path.join(out_dir, out_name)
    cmd = [VMD, "-dispdev", "text", "-e", tcl, "-args", cub_path, out_base, str(isoval)]
    subprocess.run(cmd, capture_output=True)
    bmp = out_base + ".bmp"
    return bmp if os.path.exists(bmp) else None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir', required=True, help='fchk 文件所在目录')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--molecules', required=True, help='逗号分隔的分子名列表')
    parser.add_argument('--homo-orbitals', required=True, help='逗号分隔的 HOMO 轨道号(1-based)')
    args = parser.parse_args()

    mols = args.molecules.split(',')
    homos = [int(x) for x in args.homo_orbitals.split(',')]
    assert len(mols) == len(homos), "分子数和轨道号数不匹配"

    os.makedirs(args.output_dir, exist_ok=True)
    data = []

    from extract_orb_energy import extract_molecule

    for name, hnum in zip(mols, homos):
        print(f"\n=== Processing {name} ===")
        fchk = os.path.join(args.input_dir, f"{name}.fchk")
        if not os.path.exists(fchk):
            print(f"  SKIP: {fchk} not found")
            continue

        # 1. 提取能量
        d = extract_molecule(name, fchk, hnum)
        data.append(d)
        print(f"  HOMO={d['homo_ev']} eV, LUMO={d['lumo_ev']} eV, Gap={d['gap_ev']} eV")

        # 2. 生成 cube
        mol_dir = os.path.join(args.output_dir, name)
        os.makedirs(mol_dir, exist_ok=True)
        cub_homo = gen_cube(fchk, hnum, mol_dir)
        cub_lumo = gen_cube(fchk, hnum + 1, mol_dir)
        print(f"  cube files generated")

        # 3. VMD 渲染
        if cub_homo:
            render_cube(cub_homo, f"{name}_HOMO", mol_dir)
            print(f"  HOMO rendered")
        if cub_lumo:
            render_cube(cub_lumo, f"{name}_LUMO", mol_dir)
            print(f"  LUMO rendered")

    # 4. 拼合能级图
    data_json = os.path.join(args.output_dir, "data.json")
    with open(data_json, 'w') as f:
        json.dump(data, f, indent=2)

    from make_level_plot import make_plot
    make_plot(data, args.output_dir, os.path.join(args.output_dir, "homo_lumo_levels.png"))
    print(f"\n=== ALL DONE ===")

if __name__ == '__main__':
    main()
