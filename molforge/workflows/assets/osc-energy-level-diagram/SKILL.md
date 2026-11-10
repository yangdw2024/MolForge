---
name: osc-energy-level-diagram
description: 从 Gaussian 计算结果（fchk/log）提取 OSC 有机太阳能电池分子的 HOMO/LUMO 能级，用 Multiwfn 生成轨道 cube、VMD 渲染轨道等值面 BMP，最终输出三种论文级能级图（矩形条图、水平线+轨道小图+Gap 标注图、HOMO/LUMO 2xN 排布图）和可编辑 Excel 能级表。当用户需要：(1) 读取/整理 Gaussian 输出的 HOMO/LUMO 数值；(2) 绘制 OSC 分子的前线轨道能级图；(3) 把多个分子的 HOMO/LUMO 对比画出来；(4) 渲染分子轨道等值面（HOMO/LUMO 轨道图）时使用此 skill。
---

# OSC 分子 HOMO/LUMO 能级图工作流

从 Gaussian 输出到论文级能级图的完整流水线。所有输出均为**可编辑 PPT/Excel**，不是死贴位图。

## 硬件与环境约定

- Gaussian 16 Rev A.03 装在 <G16_DIR>，mem=12GB、nprocshared=8，**严格串行**，禁止并行
- Multiwfn 3.8: <MULTIWFN_DIR>\Multiwfn_3.8_bin_Win64\Multiwfn.exe
- VMD: <VMD_DIR>\vmd.exe，Tachyon 渲染器: <VMD_DIR>\tachyon_WIN64.exe
- 物理内存 15.1 GB，fchk 超过 1GB 时必须**流式读取**，禁止 readlines()
- 删除临时文件一律放回收站（Microsoft.VisualBasic.FileIO.FileSystem::DeleteFile），禁止 Remove-Item 永久删除

## 工作流总览

```
fchk/log -> 1. 提取能级 -> levels.json
                |
          2. 生成 Excel 能级表
                |
fchk -> 3. Multiwfn 生成 cube -> 4. VMD 渲染 BMP
                |
          5. 三种 PPT 图（矩形条 / 水平线轨道 / 2xN 排布）
```

## 1. 提取 HOMO/LUMO 能级

**首选 fchk 读取**（scripts/extract_levels.py）：
- 流式扫 Alpha Orbital Energies 行，收集 N 个浮点数（D 科学计数法转 E）
- HOMO 轨道号必须**从 log 最后一次 SCF 块确认**，不要硬编码后不验证
- 换算：E_eV = E_Ha x 27.211386245988

**交叉验证**（scripts/verify_from_log.py）：
- 解析 log 里所有 Alpha occ. eigenvalues -- 和 Alpha virt. eigenvalues -- 行
- 新 occ 块出现时若已有 virt 块，说明是新一轮 SCF，重置
- 最后一组 occ 块的最后一个值 = HOMO，紧接着 virt 块第一个值 = LUMO

**踩坑**：log 里相邻负数连在一起（如 -101.58209-101.58209），解析前必须用 re.sub(r'(?<=\d)(?=-)', ' ', s) 在负号前补空格。

## 2. Excel 能级表

scripts/make_energy_table.py：输出列 = 分子名 / HOMO / LUMO / Gap，第二个 sheet 附数据来源说明。

## 3. Multiwfn 生成轨道 cube

对每个分子建子目录（如 LMO/<分子名>/），写 _in.txt：
```
200
3
<HOMO号>,<LUMO号>
3
1
```
运行：Multiwfn.exe <fchk路径> < _in.txt

**踩坑**：Multiwfn 输入读完会报 forrtl: severe (24): end-of-file during read，这是它还在等下一行输入，**cube 文件已经生成，不影响**，可以直接继续。

## 4. VMD 渲染轨道 BMP

scripts/render_one.tcl 已校准，参数：
```
vmd -dispdev text -e render_one.tcl -args <cube.cub> <输出名> <等值面>
```
- 等值面取 0.005（和论文风格对齐）
- 绿 = 正相位（ColorID 12），蓝 = 负相位（ColorID 22）
- C 原子改为棕褐色 tan
- 输出 1200x1200 BMP，Tachyon 光线追踪

## 5. 三种 PPT 图

所有脚本读 levels.json，改分子列表后直接跑。

### 5a. 矩形条图（make_rectangle_diagram.py）
- 每个分子一个彩色边框矩形，上沿=LUMO，下沿=HOMO
- 纵轴范围按实际数据动态设（LUMO 高于 -3.0 时上界放宽到 -2.5）
- 矩形中间竖排分子名，上下沿标数值

### 5b. 水平线+轨道小图（make_level_lines_diagram.py）
- 红色 LUMO 线（宽 0.8 inch）、黑色 HOMO 线
- 蓝色竖线连两线，右侧标 Gap（紧贴竖线 0.35 inch）
- LUMO 图贴红线上方（间隙 0.05 inch），HOMO 图贴黑线下方
- **踩坑**：python-pptx 文本框居中时 cx_center 是 Emu，宽度参数要包 Inches(w)，不能直接相减

### 5c. HOMO/LUMO 2xN 排布图（make_editable_pptx.py）
- 上排 LUMO、下排 HOMO，N 列均匀分布
- 每张图上方标能级、下方标分子名、左上角大标题

## 交付前自检

1. 用 PowerPoint COM 导出 PPT 为 PNG，Read 预览：
   ```powershell
   $ppt = New-Object -ComObject PowerPoint.Application
   $pres = $ppt.Presentations.Open($src, $true, $false, $false)
   $pres.Slides.Item(1).Export($out, "PNG", 1920, 1080)
   ```
2. 检查：元素不重叠、不超出边界、数值和 levels.json 一致
3. 清理临时预览文件到回收站

## 关键数据校验

HOMO/LUMO 数值必须**fchk 和 log 双源一致**才算通过。若两者差 > 0.05 eV，说明轨道号读错或 fchk/log 不同步，先排查再画图。