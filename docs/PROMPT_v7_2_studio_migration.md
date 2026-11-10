# MolForge v7.2 — Chem3D/GaussView 风格简洁多标签窗口系统完整提示词

## 项目背景

MolForge 是一款对标 GaussView / ChemDraw / Chem3D / VMD 的自研分子建模与量化后处理工作台，PyQt6 + VTK + OpenBabel/RDKit 技术栈。

当前版本 v7.1 已完成：
- 欢迎界面（WelcomeWindow）四个卡片入口
- 三大独立 Studio 窗口（Studio2DWindow / Studio3DWindow / StudioSplitWindow）的外壳框架
- 菜单中文化（文件/编辑/构建/视图/计算/结果/窗口/帮助）
- 返回欢迎界面入口
- 79 项 Results 后处理功能注册（AnalysisRegistry）

**核心问题**：Studio 窗口太空了——只有菜单栏 + 中央画布，没有工具栏、没有多标签页、没有多文档管理。用户想要的是 **Chem3D 那种风格**：顶部菜单栏 + 工具栏 + 底部标签页切换多个分子，干净利落，不要侧边栏。

---

## 目标

**一套内核，两种视图，标签页统一管理：**

### 核心设计理念
- **文档模型统一**：所有分子文档共享同一个 DocumentSession / CommandBus / SelectionService
- **视图两种模式**：
  - **主系统标签页模式**：在主窗口里以标签页形式打开，左侧侧边栏 + 右侧属性面板常驻
  - **独立 Studio 窗口模式**：弹出独立简洁窗口，没有侧边栏，像 Chem3D 那样
- **用户自由切换**：在主系统里可以右键标签页 → "弹出为独立窗口"，也可以在 Studio 窗口里 → "合并到主系统标签页"

### 主系统（MolForgeWindow）—— 升级多标签页
- **中央区域改成 QTabWidget**：每个标签页是一个分子文档
- 左侧分子库侧边栏、右侧属性面板保持不变
- 标签页底部显示，像 Chem3D 那样
- `文件 → 新建` 默认在主系统里新建标签页
- `窗口 → 弹出为独立 3D 窗口` 可以把当前标签页弹出成 Studio3DWindow
- `窗口 → 弹出为独立 2D 窗口` 可以把当前标签页弹出成 Studio2DWindow

### 三大独立 Studio 窗口 —— 简洁风格
- **Chem3D / GaussView 风格的简洁布局**：顶部菜单栏 + 工具栏 + 中央画布 + 底部标签页 + 状态栏
- **绝对不要**左侧分子库面板、右侧属性面板——那是主系统的风格
- **但核心功能一个都不能少**：
  - 2D/3D 编辑工具（选择/原子/键/擦除，通过工具栏或菜单访问）
  - 打开/保存/导出文件
  - Gaussian 设置、xTB 优化
  - Results 后处理菜单（79 项 + 新增 ESP/HOMO/OSC）
  - 多标签页、多视口分屏
- 分子库、环模板这些功能通过菜单访问（`构建 → 元素片段库...`、`构建 → 环/R-基团构建器...`），不要做成侧边栏常驻
- `文件 → 合并到主系统` 可以把当前 Studio 窗口合并回主系统的标签页

### 为什么要这样设计？
- 用户想快速画一个分子 → 主系统里新建标签页，侧边栏还在，方便查分子库
- 用户想专注做 3D 建模 → 弹出独立 Studio 窗口，没有干扰，大画布
- 用户想对比两个分子 → 主系统里并排两个标签页，或弹出两个 Studio 窗口平铺
- 两套视图共享同一份文档数据，不会不同步

---

## 技术基线

- **主基线目录**：`E:\YDW\Trae_Chemdraw\MolForge`（v7.1，126 Python 文件）
- **Python 环境**：`D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe`（Py3.13, PyQt6 6.11, VTK 9.7）
- **关键文件**：
  - `molforge/ui/shells/studio_3d.py` — Studio3DWindow 外壳（待增强）
  - `molforge/ui/shells/studio_2d.py` — Studio2DWindow 外壳（待增强）
  - `molforge/ui/shells/studio_split.py` — StudioSplitWindow 外壳（待增强）
  - `molforge/ui/window.py` — 旧 MolForgeWindow（功能参考，不要包装）
  - `molforge/ui/panels.py` — 旧面板组件（参考，不要直接搬过来）
  - `molforge/ui/render3d_widget.py` — 3D 画布组件
  - `molforge/ui/editor2d_widget.py` — 2D 画布组件
  - `molforge/ui/welcome_window.py` — 欢迎界面 + ShellWindowFactory

---

## 具体任务清单

### P0-0. 主系统（MolForgeWindow）多标签页升级

把主系统的中央区域从单个画布改成 **QTabWidget 多标签页**：
- 每个标签页是一个独立的分子文档（2D 或 3D 视图）
- 标签标题显示分子名称
- 底部标签栏（像 Chem3D 那样）
- 左侧分子库侧边栏、右侧属性面板保持不变，作用于当前激活的标签页
- `文件 → 新建` 默认在主系统里新建标签页
- `文件 → 打开...` 在主系统里新建标签页打开
- 标签页右键菜单：关闭、复制、重命名、弹出为独立 Studio 窗口
- `窗口 → 弹出为独立 3D 窗口` 把当前标签页弹出成 Studio3DWindow
- `窗口 → 弹出为独立 2D 窗口` 把当前标签页弹出成 Studio2DWindow
- `窗口 → 合并到主系统` 在 Studio 窗口里可以合并回来

要求：
- 主系统的标签页和 Studio 窗口共享同一个 DocumentSession，数据实时同步
- 关闭主系统最后一个标签页时，弹出"是否返回欢迎界面"

### P0-1. Studio3DWindow 多标签页系统（核心！）
把 Studio3DWindow 的中央区域从单个 Render3DWidget 改成 **QTabWidget**：
- 每个标签页是一个独立的 3D 画布（Render3DWidget 实例）
- 标签标题显示分子名称（如 "Untitled-1"、"咖啡因"、"PM6"）
- 双击标签页可以重命名
- 标签页右键菜单：关闭、复制、新建
- 底部标签栏（像 Chem3D 那样），不是顶部
- 关闭最后一个标签页时，弹出"是否新建空白分子"或"返回欢迎界面"

要求：
- 新建分子：`文件 → 新建 3D 画布 (Ctrl+N)` → 新建一个标签页
- 打开文件：`文件 → 打开... (Ctrl+O)` → 在当前标签页打开，或新建标签页
- 每个标签页有独立的 document / command_bus / selection

#### P0-2. 工具栏
在菜单栏下方添加工具栏（像 Chem3D 那样一排图标按钮）：
- 选择/拖动工具 (V)
- 添加原子工具 (A)
- 绘制键工具 (B)
- 擦除工具 (E)
- 撤销 (Ctrl+Z)
- 重做 (Ctrl+Y)
- 清洁 3D 几何 (Ctrl+M)
- 居中视图
- 重置相机
- 切换显示模式（球棍/CPK/线框/表面）

要求：
- 工具栏按钮用 Unicode 符号或文字（不依赖外部图标文件）
- 工具按钮是可切换的（checkable），当前工具高亮
- 工具栏可以拖拽浮动、可以隐藏

#### P0-3. 多视口并排（同一个分子分屏）
在视图菜单里添加：
- `视图 → 单视口`（默认，全屏一个 3D 视图）
- `视图 → 左右分屏`（左边前视图，右边侧视图）
- `视图 → 四视口`（前/侧/俯/透视，像 GaussView 那样）
- `视图 → 并排对比两个分子`（当前标签页和下一个标签页并排显示）

要求：
- 同一个标签页内可以切换 1/2/4 视口
- 多视口共享同一个分子文档，旋转一个视口其他视口联动（可选）
- 用 vtkRenderer.SetViewport 实现，不要创建多个独立 RenderWindow（避免 VTK 多窗口崩溃）

#### P0-4. 窗口菜单（多文档管理）
升级"窗口"菜单：
- `窗口 → 新建 3D 画布`（新建标签页）
- `窗口 → 关闭当前画布`（关闭当前标签页）
- `窗口 → 平铺所有画布`（多标签页并排显示，像 Windows 平铺窗口）
- `窗口 → 层叠所有画布`（层叠排列）
- `窗口 → 切换到下一个画布` (Ctrl+Tab)
- `窗口 → 切换到上一个画布` (Ctrl+Shift+Tab)
- 下面列出所有打开的标签页，点击切换

#### P0-5. 菜单栏升级
把现有菜单补全，所有功能都通过菜单访问：

**文件(&F)**：
- 新建 3D 画布 (Ctrl+N)
- 打开结构 / 量子输出 (Ctrl+O)
- 保存 MolForge 工程 (Ctrl+S)
- 另存为...
- 导出 XYZ / MOL / SDF / PDB / gjf...
- 导出图像 PNG/SVG...
- 最近打开的文件
- ---
- 返回欢迎界面...
- 退出 (Ctrl+Q)

**编辑(&E)**：
- 撤销 (Ctrl+Z)
- 重做 (Ctrl+Y)
- ---
- 剪切 (Ctrl+X)
- 复制 (Ctrl+C)
- 粘贴 (Ctrl+V)
- 删除选中 (Delete)
- ---
- 清洁 3D 几何 (Ctrl+M)
- 加氢/去氢
- 居中 (Ctrl+Shift+C)

**构建(&B)**：
- 选择模式 (V)
- 添加原子模式 (A)
- 绘制键模式 (B)
- 擦除模式 (E)
- ---
- 元素片段库...
- 环 / R-基团构建器...
- ---
- 修改键长...
- 修改键角...
- 修改二面角...

**视图(&V)**：
- 单视口
- 左右分屏
- 四视口
- ---
- 显示模式：球棍模型
- 显示模式：CPK 空间填充
- 显示模式：线框
- 显示模式：范德华表面
- ---
- 显示/隐藏氢原子
- 显示/隐藏标签
- 显示/隐藏坐标轴
- ---
- 居中 & 重置相机

**计算(&C)**：
- Gaussian 计算设置 (Ctrl+G)
- GFN2-xTB 几何优化 (Ctrl+Shift+X)
- 复旦 REST 输入设置...
- ---
- 引擎状态...（查看 Gaussian/Multiwfn/GROMACS 路径配置）

**结果(&R)**：
- （现有 79 项 Results 菜单，保持不变）

**窗口(&W)**：
- 新建 3D 画布
- 关闭当前画布
- ---
- 平铺所有画布
- 层叠所有画布
- ---
- 切换到下一个 (Ctrl+Tab)
- 切换到上一个 (Ctrl+Shift+Tab)
- ---
- （列出所有打开的标签页）

**帮助(&H)**：
- 关于 MolForge Studio 3D v7.2

---

### P1 — Studio2DWindow 升级

#### P1-1. 多标签页系统
同 Studio3DWindow，中央区域改成 QTabWidget，每个标签页是一个 2D 画布。

#### P1-2. 工具栏
同 Studio3DWindow 的工具栏，但适配 2D 绘图：
- 选择工具 (V)
- 原子工具 (A)
- 键工具 (B)
- 擦除工具 (E)
- 撤销/重做
- 清洁 2D 布局
- 切换隐式/显式氢
- 切换纸张/深色模式

#### P1-3. 菜单栏升级
同 Studio3DWindow 的菜单结构，适配 2D 绘图。

---

### P2 — StudioSplitWindow 升级

#### P2-1. 多标签页 + 分屏
每个标签页是一个 2D-3D 分屏视图（左边 2D，右边 3D）。
标签页标题显示分子名称。
2D 和 3D 共享同一个文档，选中联动。

---

### P3 — 欢迎界面优化

#### P3-1. 默认启动模式
- 默认显示欢迎界面（而不是直接进入 split 模式）
- 保留 `--mode` 命令行参数可直接进入指定模式

#### P3-2. 欢迎界面卡片说明
每个卡片下面加一行小字说明：
- **2D 化学结构设计**：简洁 2D 绘图，多标签页，适合画分子结构、导出 SVG
- **3D 多窗口建模**：Chem3D 风格 3D 建模，多标签页 + 多视口分屏
- **2D–3D 分屏联动**：左边画 2D，右边看 3D，实时同步
- **经典三栏工作台**：完整功能的旧版界面（分子库 + 属性面板）

---

### P4 — Results 菜单验证与完善

#### P4-1. 验证 79 项 Results 功能
逐项检查 `AnalysisRegistry` 里的 79 项功能：
- 哪些是真的有计算逻辑的（不是空对话框）
- 哪些只是注册了但没实现
- 列出"假功能"清单

#### P4-2. 集成用户本机的 Multiwfn 工作流
用户本机已有三个完整工作流技能，需要集成到 Results 菜单：

1. **ESP 表面分析**（`结果 → ESP 表面分析...`）
   - 输入：fchk 文件
   - 调用 Multiwfn.exe 做 0.001 a.u. 电子密度等值面 ESP 分析
   - 输出：sigma2+/sigma2-/nu/Pi/MPI 等描述符 + BWR 配色 ESP 表面图
   - 参考：`C:\Users\Administrator\AppData\Local\DoubaoWork\User Data\Profile 2\.doubaowork\agent_mode\workspace\.user_skills\esp-surface-analysis\SKILL.md`

2. **HOMO-LUMO 能级图**（`结果 → HOMO/LUMO 能级图...`）
   - 输入：多个 fchk 文件
   - 调用 Multiwfn 生成轨道 cube → VMD 渲染 → matplotlib 拼合能级图
   - 输出：带分子轨道等值面图的 HOMO-LUMO 能级阶梯图
   - 参考：`...\homo-lumo-plot\SKILL.md`

3. **OSC 能级图**（`结果 → OSC 能级图...`）
   - 输入：给体/受体分子的 fchk/log
   - 输出：三种论文级 OSC 能级对比图
   - 参考：`...\osc-energy-level-diagram\SKILL.md`

#### P4-3. 新增 Results 功能项
在现有 79 项基础上，再补充以下功能：
- **分子平面性分析**：最佳拟合平面 RMSD、最大离面距离
- **偶极矩分析**：计算并可视化分子偶极矩矢量
- **分子间相互作用分析**：氢键检测、范德华接触、π-π 堆积检测
- **能量分解分析 (EDA)**：sobEDA 风格的相互作用能分解
- **MD 轨迹后处理**：RMSD/Rg/氢键统计/簇分析（基于 MDAnalysis）

---

## 技术约束（必须遵守）

1. **Studio 系统绝对不要加左侧/右侧面板**——保持 Chem3D 风格的简洁，功能全走菜单和工具栏；主系统（经典三栏）保持现状不动
2. **不要包装旧 MolForgeWindow**——Studio 窗口必须是全新的 QMainWindow
3. **多标签页用 QTabWidget**——标签在底部，像 Chem3D 那样
4. **菜单保持中文**——所有菜单、按钮、对话框都用中文
5. **删除文件进回收站**——不要永久删除任何文件，修改前先备份
6. **不要在 C 盘安装任何东西**
7. **Python 环境路径硬编码**——`run_molforge.bat` 里硬编码 `D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe`
8. **Gaussian 串行**——mem 12GB, nprocshared 8，严禁并行跑多个任务
9. **VTK 多视口用 SetViewport**——不要创建多个独立 RenderWindow（避免 Windows 11 下 0xC0000409 崩溃）
10. **CommandBus 方法名是 add_listener**——不是 subscribe

---

## 验收标准

### 启动验证
- [ ] 双击 `run_molforge.bat` 能正常启动
- [ ] 默认显示欢迎界面
- [ ] 四个卡片按钮都能正常打开对应窗口，不崩溃
- [ ] 每个窗口都能通过 `文件 → 返回欢迎界面` 回到主入口

### 主系统（经典三栏）验证
- [ ] 中央区域是 QTabWidget，底部有标签栏
- [ ] `文件 → 新建` 在主系统里新建标签页
- [ ] `文件 → 打开...` 在主系统里新建标签页打开分子
- [ ] 切换标签页时，左侧侧边栏和右侧属性面板跟着切换
- [ ] 标签页右键菜单有"弹出为独立 Studio 窗口"选项
- [ ] `窗口 → 弹出为独立 3D 窗口` 能把当前标签页弹出成 Studio3DWindow
- [ ] Studio 窗口里修改分子后，主系统里的对应标签页同步更新

### Studio3DWindow 验证
- [ ] 中央区域是 QTabWidget，底部有标签栏
- [ ] `文件 → 新建 3D 画布` (Ctrl+N) 能新建标签页
- [ ] `文件 → 打开...` (Ctrl+O) 能在新标签页打开分子
- [ ] 标签页标题显示分子名称
- [ ] 工具栏有选择/原子/键/擦除等按钮，可切换高亮
- [ ] `视图 → 四视口` 能切换成前/侧/俯/透视四个视角
- [ ] `窗口 → 平铺所有画布` 能把多个标签页并排显示
- [ ] `窗口 → 切换到下一个` (Ctrl+Tab) 能切换标签页
- [ ] 菜单全中文
- [ ] 底部状态栏显示原子数/电子数/电荷/自旋
- [ ] 没有左侧面板、没有右侧面板——保持简洁

### Studio2DWindow 验证
- [ ] 中央区域是 QTabWidget
- [ ] 新建/打开文件能新建标签页
- [ ] 工具栏按钮可切换
- [ ] 菜单全中文

### Results 菜单验证
- [ ] ESP 表面分析对话框能打开，能选择 fchk 文件
- [ ] HOMO/LUMO 能级图对话框能打开
- [ ] OSC 能级图对话框能打开
- [ ] 列出所有 79 项功能中哪些是真实现的、哪些是空壳

---

## 文件修改清单（预估）

需要修改的文件：
1. `molforge/ui/shells/studio_3d.py` — 加 QTabWidget、工具栏、多视口、菜单升级
2. `molforge/ui/shells/studio_2d.py` — 同上
3. `molforge/ui/shells/studio_split.py` — 同上
4. `molforge/ui/welcome_window.py` — 优化卡片说明
5. `molforge/ui/qc_result_dialog.py` — 新增 ESP/HOMO/OSC 对话框
6. `molforge/application/invalidation.py` — 新增 Results 功能注册
7. `run_molforge.bat` — 确认硬编码 Python 路径

可能需要新建的文件：
1. `molforge/ui/shells/studio_toolbar.py` — 工具栏组件
2. `molforge/io/multiwfn_adapter.py` — Multiwfn 调用封装
3. `molforge/workflows/esp_surface.py` — ESP 表面分析工作流
4. `molforge/workflows/homo_lumo_plot.py` — HOMO-LUMO 能级图工作流

---

## 交付物

1. **完整修改后的代码**（整个 MolForge 目录打包）
2. **修改记录文档**（`docs/CHANGES_v7_2.md`）：列出改了哪些文件、为什么改、怎么验证
3. **假功能清单**（`docs/RESULTS_FAKE_FEATURES.md`）：79 项 Results 里哪些是空壳
4. **验证截图**：欢迎界面 + Studio3DWindow（多标签页 + 四视口）+ Studio2DWindow 的截图

---

## 注意事项

- 先备份再修改！重要文件修改前复制一份 `.bak`
- 每完成一个 P0 任务就测试一次，不要全部写完再测试
- 遇到崩溃先查 `$env:USERPROFILE\.molforge_crash.log`
- 用户是化学专业研究生（OSC 方向），不是程序员，代码要写得健壮，不要因为一个小错误就整个窗口崩溃
- 回答要让用户听懂，不要用太多黑话
- **核心风格**：Chem3D 那种简洁感——菜单栏 + 工具栏 + 标签页 + 大画布，不要侧边栏！
