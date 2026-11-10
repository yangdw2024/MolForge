# MolForge v6.2 完整问题与改进清单

> 更新时间：2026-10-30
> 基线版本：v6.2 (Gemini Refactored)

---

## 一、前端 UI 集成问题（P0）

### 1. 欢迎界面没有真正的 UI
- **现状**：`welcome_window.py` 只有 ShellFactory 工厂类，没有真正的 QDialog/QMainWindow 欢迎界面
- **期望**：启动时显示欢迎界面，有三个大按钮：2D 设计 / 3D 设计 / 2D-3D 分屏
- **代码位置**：`molforge/ui/welcome_window.py`
- **修复方案**：
  1. 做一个真正的 WelcomeWindow(QDialog) 或 WelcomeWindow(QMainWindow)
  2. 三个大按钮点击后调用 ShellFactory.create_shell() 进入对应系统
  3. 启动脚本先显示欢迎界面，用户选择后再进入主窗口

### 2. 三大 Shell 不是真正的窗口
- **现状**：`Studio2DShell`、`Studio3DShell`、`StudioSplitShell` 只是数据类，不是 QMainWindow，不能显示
- **期望**：每个 Shell 都是一个真正的 QMainWindow，有菜单、画布、状态栏
- **代码位置**：`molforge/ui/shells/`
- **修复方案**：
  1. 让 Studio3DShell 继承 QMainWindow
  2. 顶部菜单：File / Edit / Tools / Builder / View / Calculate / Results / Windows / Help
  3. 中央：VTK 画布
  4. 底部状态栏：原子数、电子数、电荷、自旋

### 3. 启动流程没接入
- **现状**：`scripts/launch.py` 直接创建 `MolForgeWindow`，没有经过欢迎界面
- **期望**：启动时先显示欢迎界面，用户选择进入哪个系统
- **代码位置**：`scripts/launch.py`
- **修复方案**：
  1. launch.py 先显示 WelcomeWindow
  2. 用户选择后再创建对应的 Shell 窗口

---

## 二、Gaussian 集成现状

### 已有功能 ✅
- `gaussian_engine.py` — Gaussian 计算引擎适配器
- `qc_input_generator.py` — Gaussian .gjf 输入卡生成器
- `GaussianCalculationSetupDialog` — 11 页签 + 6 按钮计算设置对话框
- 支持加载 Gaussian .log 输出文件
- 支持加载 Gaussian .cube 轨道文件
- 菜单：计算 → Gaussian 计算输入配置

### 缺失功能 ❌
- 没有真正调用 g16.exe 提交计算任务
- 没有实时监控计算进度
- 没有自动读取计算结果（能量、优化坐标、振动频率）
- 没有振动光谱可视化（IR/Raman 谱图）
- 没有 NMR 谱图可视化
- 没有 HOMO/LUMO 能级图自动生成

---

## 三、Multiwfn 集成（完全缺失）

### 现状 ❌
- 完全没有集成 Multiwfn
- 搜索 `multiwfn` 无结果

### 本机已有工作流（应集成到 MolForge）

#### 1. ESP 表面分析工作流（esp-surface-analysis）
- **工具路径**：`D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe`
- **流程**：
  - Step 1: `Multiwfn.exe xxx.fchk -ESPrhoiso 0.001` → 生成 density.cub + totesp.cub
  - Step 2: `Multiwfn.exe xxx.fchk < ESPext.txt` → 生成 mol.pdb + surfanalysis.pdb + vtx.pdb
- **输出**：
  - sigma2+ / sigma2- / nu / Pi / MPI 等 OSC 关键描述符
  - BWR 配色 ESP 表面图（VMD 渲染）
  - ESP 极大（红）/ 极小（蓝）特征点
- **时间**：~9 min per molecule for ~60 MB fchk
- **集成方式**：菜单 → Results → ESP Surface Analysis...

#### 2. HOMO-LUMO 能级图工作流（homo-lumo-plot）
- **工具路径**：Multiwfn + VMD + Python
- **流程**：
  - Multiwfn 从 fchk 生成轨道 cube 文件
  - VMD 渲染 cube 文件为 BMP 轨道图
  - Python 提取 HOMO/LUMO 能量，matplotlib 拼合能级骨架
- **输出**：带分子轨道等值面图的 HOMO-LUMO 能级图
- **适用场景**：OSC 受体/给体分子 HOMO/LUMO 能级对比，开题答辩、论文配图
- **集成方式**：菜单 → Results → HOMO/LUMO Level Plot...

#### 3. OSC 能级图工作流（osc-energy-level-diagram）
- **工具路径**：同上
- **用途**：OSC 有机太阳能电池分子能级图

### 期望功能（完整 Multiwfn 集成）
- 调用 Multiwfn.exe 做波函数分析
- 电子密度图、静电势图、ELF 图
- 轨道可视化（HOMO/LUMO/NBO）
- 键级分析（Mayer 键级）
- 电荷分析（Hirshfeld / ADCH / NPA）
- 激发态分析（电子空穴分布）
- 光谱模拟（IR / Raman / UV-Vis / CD）

---

## 四、后处理分析模块

### 现状 ❌
- 没有统一的后处理分析模块
- 结果分析功能散落在各个文件里

### 期望架构
- **Results 菜单**：
  - Summary... — 计算结果摘要
  - Charge Distribution... — 电荷分布
  - Atom Properties... — 原子属性
  - Bond Properties... — 键属性
  - Surfaces/Contours... — 表面/等值面
  - Vibrations... — 振动光谱
  - NMR... — NMR 谱图
  - UV-Vis... — 紫外可见光谱
  - ORD... — 旋光色散
  - Vibronic... — 振动电子耦合
  - Scan... — 势能面扫描
  - IRC/Path... — IRC 路径
  - Trajectory... — 分子轨迹
  - Optimization... — 优化轨迹
  - Energy Plot... — 能量图

---

## 五、其他已修复问题

### 已修复 ✅
- v6.0 启动崩溃（render3d_widget __init__ 缺少变量）
- run_molforge.bat 中文注释导致解析错误
- 精确修改对话框默认值硬编码
- 右侧面板缺少键角/二面角调节入口
- Ctrl+A 全选快捷键
- xtb.exe 路径集成
- 测量逻辑错误（measurement_targets.py）
- Element Fragments 基团面板
- Gaussian Calculation Setup 对话框
- calchem_engine.py 补回

---

## 六、待验证功能 🧪

- [ ] xtb 半经验优化（GFN2-xTB）
- [ ] 多构象搜索（ETKDGv3）
- [ ] HOMO/LUMO 轨道渲染
- [ ] 二面角扭转势能曲线
- [ ] 右键菜单完整性
- [ ] 框选 + 套索切换
- [ ] 多选平移
- [ ] 拖拽文件打开
- [ ] 原子半径比例调整效果
