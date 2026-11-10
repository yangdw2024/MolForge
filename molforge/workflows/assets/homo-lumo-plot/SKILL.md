---
name: homo-lumo-plot
description: 从 Gaussian fchk 文件批量生成 HOMO-LUMO 能级图，含分子轨道等值面图。流程：Multiwfn 生成 cube → VMD 渲染轨道图 → Python 拼合能级骨架。用于 OSC/有机分子开题、论文配图。
allow_implicit_invocation: false
---

# HOMO-LUMO 能级图生成技能

从 Gaussian 优化好的 fchk 文件，一键生成带分子轨道等值面图的 HOMO-LUMO 能级图。

## 适用场景

- 有机太阳能电池（OSC）受体/给体分子 HOMO/LUMO 能级对比
- 开题答辩、论文配图的能级图
- 需要同时展示能级数值和轨道分布

## 前置依赖

| 工具 | 路径 | 用途 |
|---|---|---|
| Multiwfn 3.8 | <MULTIWFN_DIR>\Multiwfn_3.8_bin_Win64\Multiwfn.exe | 从 fchk 生成轨道 cube 文件 |
| VMD 1.9+ | <VMD_DIR>\vmd.exe | 渲染 cube 文件为 BMP 轨道图 |
| Tachyon | <VMD_DIR>\tachyon_WIN64.exe | VMD 离线光线追踪渲染器 |
| Python | <PYTHON> | 提取能量、拼合能级图 |

## 使用流程

运行 run_pipeline.py，传入 fchk 目录、分子名列表、HOMO 轨道号列表即可。

## 文件说明

- render_one.tcl：VMD 渲染脚本
- extract_orb_energy.py：从 fchk 提取 HOMO/LUMO 能量
- make_level_plot.py：matplotlib 拼合能级骨架 + 轨道图
- run_pipeline.py：一键运行整个流水线
