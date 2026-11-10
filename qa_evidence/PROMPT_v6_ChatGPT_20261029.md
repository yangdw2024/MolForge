# MolForge v5 → v6 开发提示词（给 ChatGPT）

## 项目背景
MolForge 是一个 Windows 桌面分子编辑器，目标是碾压 GaussView/ChemDraw/Chem3D/VMD。
- 技术栈：Python 3.13 + PyQt6 + VTK 9.7 + RDKit 2026 + PyVista + OpenBabel
- 当前版本：v5（osc_studio 基线 + 3D 交互改进）
- 主目录：E:\YDW\Trae_Chemdraw\MolForge

## 当前已完成
- 2D/3D 分屏联动，咖啡因示例分子
- 4 个停靠面板：模型树、笛卡尔坐标表、测量表、原子/键属性表
- 多窗口系统（G1:M1:V1 标签）
- OpenBabel 142 读/121 写格式
- 3D：PBR 球棍渲染、XYZ 角落坐标轴、前视/侧视/俯视/等轴测
- 选择：点选、Shift 多选、Shift+框选（带半透明矩形 overlay）
- 右键上下文菜单（删除/建键/改色/改键长）
- 完整快捷键（Ctrl+C/X/V/Z/Y/A/N/O/S/G/J/M）
- per-atom/per-bond 颜色、大小、键长修改（走 CommandBus 带 Undo）

## 最紧急的 5 个问题（按优先级）

### P0-1：框选后多选平移不工作
**现象**：Shift+框选选中多个原子后，拖动其中一个原子，只动这一个，其他不动。
**原因猜测**：`_capture_multi_drag_origins()` 在选择模式点原子时被调用，但框选完成后选中了一批原子，此时 `_multi_drag_start` 字典是空的（因为框选是直接 `select_atom(add=True)`，没经过 `_capture_multi_drag_origins`）。
**修复方向**：
- 方案 A：框选完成后，在 `_finish_box_select` 里立即调用 `_capture_multi_drag_origins()`
- 方案 B：拖动开始时（鼠标按下在原子上），重新收集当前所有选中原子的初始坐标，而不是依赖之前捕获的
- 验收：框选 3 个原子 → 拖其中一个 → 3 个一起移动相同距离 → Ctrl+Z 全部恢复

### P0-2：工具模式逻辑混乱
**现象**：选择/原子/键/擦除四种模式，鼠标行为不一致，用户不知道当前是什么模式。
**参考**：GaussView 的工具栏是图标按钮，按下高亮，状态栏显示当前模式提示。
**修复方向**：
- 工具栏按钮按下时高亮（当前只有文字提示，没有视觉选中态）
- 状态栏实时显示：当前模式 + 鼠标操作提示（如"选择模式：左键点选，Shift+拖框选，右键菜单"）
- 每种模式的鼠标行为写成一个状态表，统一在 eventFilter 里分发

### P0-3：拖拽文件到窗口直接打开
**现象**：用户要求把 .gjf/.xyz/.pdb 文件拖到画布上直接打开。
**修复方向**：
- MainWindow setAcceptDrops(True)
- dragEnterEvent：接受 .gjf/.xyz/.sdf/.mol/.pdb/.mol2/.smi/.cif 等
- dropEvent：调用 `load_molecule_document(path)` 加载

### P0-4：预设分子 SMILES 错误
**现象**：左侧"IC 端基"预设分子，羰基和氰基画成了邻位，应该是间位（1,3-取代）。
**修复方向**：检查 `molforge/io/rdkit_adapter.py` 的 SAMPLE_MOLECULES 字典，修正 IC 端基的 SMILES。

### P0-5：pyinstaller 打包
**现象**：用户要一个不需要 Python 环境的 Windows 绿色包。
**修复方向**：
- PyInstaller spec 文件，正确收集 PyQt6/VTK/PyVista/RDKit/OpenBabel
- openbabel.exe 作为外部二进制打包
- 测试双击 exe 能启动、能导入导出文件

## P1：下一步功能

### P1-1：xtb 免费优化集成
- subprocess 调用 xtb.exe（用户本地需要安装）
- 菜单：计算(C) → xtb 快速优化
- 优化完自动读回坐标更新文档

### P1-2：套索选择模式
- 选择模式下，右键或工具栏切换"框选/套索"
- 套索：记录鼠标轨迹点，用射线法判断原子在曲线内
- 多边形：多次点击画顶点，闭合后选中

### P1-3：大文件性能
- 测试导入 1CRN.pdb（几百原子）和 4HHB.pdb（几千原子）
- 2D 视图大分子卡顿优化
- 3D 渲染 LOD（远距离用球，近距离用球棍）

## 工程纪律
1. 改任何文件前先备份 .bak_日期
2. 所有修改走 CommandBus，带 Undo
3. 不要在 eventFilter 里同步调用 VTK render()，用 _defer() 异步
4. 改完启动测试 `python scripts/verify_v5_start.py` 截图
5. 不要向 C 盘安装任何东西

## 关键文件位置
- 主窗口：molforge/ui/window.py
- 3D 交互：molforge/ui/render3d_widget.py（eventFilter 在第 280 行附近）
- VTK 渲染：molforge/rendering/vtk_backend.py
- 文件导入导出：molforge/io/rdkit_adapter.py, openbabel_adapter.py
- 命令总线：molforge/application/builtin_commands.py
- 预设分子：molforge/io/rdkit_adapter.py 的 SAMPLE_MOLECULES
- 启动脚本：scripts/launch.py, run_molforge.bat
