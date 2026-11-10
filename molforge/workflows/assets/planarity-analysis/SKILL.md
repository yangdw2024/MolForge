---
name: planarity-analysis
description: 从 Gaussian 优化好的 fchk 出发，用 Multiwfn MPP 功能计算分子平面性参数（重原子平面度 RMSD、最大离面距离 SDP、每个原子的平面偏差 d_s），输出 pqr 文件并用 VMD BWR 蓝-白-红色标渲染平面偏差，用于 OSC 给体/受体分子平面性对比。
---

# 分子平面性分析工作流 (Multiwfn MPP + VMD)

## 工具依赖
- Multiwfn 3.8: `<MULTIWFN_DIR>/Multiwfn.exe`
- VMD 1.9+: `<VMD_DIR>/vmd.exe`
- Python: `<PYTHON>`

## 输入
- Gaussian 优化好的 fchk 文件

## 输出
- pqr 文件：每个原子的 charge 字段存的是 d_s（平面偏差，单位 Å）
- BMP 渲染图：BWR 色标，红色=离面远，蓝色=在平面上

## 步骤

### Step 1: Multiwfn MPP 计算
运行 `scripts/run_mpp.bat <fchk文件>`，自动生成指令流：
```
MPP
h          # 只考虑重原子
y          # 导出 pqr
           # 确认空行
q          # 退出
```

输出：`<fchk文件名>.pqr`

### Step 2: VMD 渲染平面偏差
1. 把 pqr 文件拖进 VMD
2. 在 VMD Tcl console 运行：`source scripts/render_planarity.tcl`

渲染效果：
- CPK 模型
- 按 Charge 字段（即 d_s）着色
- BWR 蓝-白-红色标
- 白色背景，正交投影

## 关键参数
- MPP 只考虑重原子（h 选项），氢原子忽略
- d_s 范围建议 -0.5 ~ 0.5 Å，跨分子对比时保持一致
- 色标：BWR (blue-white-red)

## 示例
参考 ClFFCl 体系：
- MPP 计算后输出 planarity.bmp
- plane.txt 包含最佳拟合平面参数
- 最大离面距离 SDP 约 0.1-0.3 Å（平面性好的体系）
