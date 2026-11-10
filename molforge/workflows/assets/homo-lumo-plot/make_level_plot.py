# -*- coding: utf-8 -*-
"""拼合 HOMO-LUMO 能级骨架 + 分子轨道等值面图"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import os, argparse

matplotlib.rcParams['font.family'] = 'Arial'
matplotlib.rcParams['font.size'] = 12

def make_plot(data, orb_dir, output_path, y_min=-6.5, y_max=-2.5, show_orbs=True):
    """
    data: list of dicts with keys: name, homo_ev, lumo_ev, gap_ev
    orb_dir: directory containing {name}_HOMO.bmp and {name}_LUMO.bmp
    """
    n = len(data)
    fig, ax = plt.subplots(figsize=(max(8, n * 1.8), 6))

    x = range(n)
    w = 0.35

    for i, d in enumerate(data):
        h, l = d['homo_ev'], d['lumo_ev']
        g = d['gap_ev']
        # HOMO line
        ax.plot([i - w/2, i + w/2], [h, h], 'k-', linewidth=3)
        # LUMO line
        ax.plot([i - w/2, i + w/2], [l, l], 'k-', linewidth=3)
        # Double arrow
        ax.annotate('', xy=(i, l), xytext=(i, h),
                    arrowprops=dict(arrowstyle='<->', color='#2c3e50', lw=1.5))
        # Gap label
        ax.text(i, (h + l) / 2, f'{g:.2f} eV', ha='center', va='center',
                fontsize=11, fontweight='bold', color='#2c3e50',
                bbox=dict(boxstyle='round,pad=0.3', fc='white', ec='none', alpha=0.85))
        # HOMO/LUMO text labels
        ax.text(i, h - 0.1, 'HOMO', ha='center', va='top', fontsize=10, color='#333')
        ax.text(i, l + 0.1, 'LUMO', ha='center', va='bottom', fontsize=10, color='#333')

        # Insert orbital images
        if show_orbs:
            homo_img = os.path.join(orb_dir, f"{d['name']}_HOMO.bmp")
            lumo_img = os.path.join(orb_dir, f"{d['name']}_LUMO.bmp")
            if os.path.exists(homo_img):
                img = mpimg.imread(homo_img)
                ax.imshow(img, extent=[i-0.3, i+0.3, h-0.6, h-0.15], aspect='auto', zorder=5)
            if os.path.exists(lumo_img):
                img = mpimg.imread(lumo_img)
                ax.imshow(img, extent=[i-0.3, i+0.3, l+0.15, l+0.6], aspect='auto', zorder=5)

    ax.set_xticks(list(x))
    ax.set_xticklabels([d['name'] for d in data], fontsize=12)
    ax.set_ylabel('Energy Level (eV)', fontsize=13, fontweight='bold')
    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-0.6, n - 0.4)
    ax.grid(axis='y', linestyle='--', alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.title('HOMO-LUMO Energy Levels', fontsize=14, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-json', required=True)
    parser.add_argument('--orb-dir', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    import json
    with open(args.data_json) as f:
        data = json.load(f)
    make_plot(data, args.orb_dir, args.output)
