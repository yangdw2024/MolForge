---
name: dipole-visualization
description: 从 Gaussian 计算好的 fchk/xyz 出发，用 Multiwfn 计算分子整体及各片段的偶极矩矢量，然后用 VMD 在分子结构上绘制不同颜色的偶极矩箭头（片段偶极+总偶极），用于 OSC 给受体分子内电荷转移方向可视化。
---

# 偶极矩可视化工作流 (Multiwfn + VMD 箭头绘制)

## 工具依赖
- Multiwfn 3.8: `<MULTIWFN_DIR>/Multiwfn.exe`
- VMD 1.9+: `<VMD_DIR>/vmd.exe`

## 输入
- Gaussian 优化好的 fchk 或 xyz 文件
- 片段定义（原子序号范围）

## 输出
- atom_moment.txt：每个原子的偶极矩贡献
- multipole.txt：多极矩展开结果
- BMP 渲染图：分子结构 + 彩色偶极箭头

## 步骤

### Step 1: Multiwfn 偶极矩计算
在 Multiwfn 主菜单输入：
```
14          # 分子属性和波函数分析
1           # 偶极矩和多极矩
```

输出：
- 分子总偶极矩矢量 (x, y, z)，单位 a.u.
- 各原子偶极矩贡献
- 多极矩展开

### Step 2: 分片段偶极矩计算
对每个片段（如 IC1、BTP、IC2 端基）：
1. 在 Multiwfn 里选择片段原子
2. 计算该片段的偶极矩矢量
3. 记录 (dx, dy, dz) 值

### Step 3: VMD 绘制偶极箭头
1. 把 xyz 结构文件拖进 VMD
2. 编辑 `scripts/render_dipole.tcl`，填入：
   - 各片段的原子选择（serial 范围）
   - 各片段的偶极矩矢量 (dx, dy, dz)
   - 箭头颜色
3. 在 VMD Tcl console 运行：`source scripts/render_dipole.tcl`

## 渲染效果
- CPK 分子模型
- 白色背景，正交投影
- 片段偶极箭头：不同颜色（如 IC1=绿，BTP=红，IC2=黄）
- 总偶极箭头：蓝色，更粗

## 关键参数
- 箭头长度缩放因子 scl=1.2
- 箭头半径 rad=0.12
- 箭头头部半径 = rad × 2.5
- 偶极矩单位：a.u.（1 a.u. = 2.54 D）

## 示例
参考 ClFFCl 体系（三片段：IC1-BTP-IC2）：
- IC1 偶极：(-3.62, 0.01, 0.38) a.u.
- BTP 偶极：(0.00, -0.96, 0.00) a.u.
- IC2 偶极：(3.62, 0.01, -0.38) a.u.
- 总偶极：(~0, -0.94, ~0) a.u.
