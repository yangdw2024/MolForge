# MolForge v5 → v6 完整开发指令（给 ChatGPT）

## 项目概况
- **目标**：碾压 GaussView / ChemDraw / Chem3D / VMD 的分子工作台
- **技术栈**：Python 3.13 + PyQt6 6.11 + VTK 9.7 + RDKit 2026.9 + PyVista + OpenBabel
- **主目录**：E:\YDW\Trae_Chemdraw\MolForForge
- **启动**：`run_molforge.bat` → `scripts/launch.py`
- **Python 环境**：`D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe`

---

## 一、3D 交互层问题（最严重，按优先级）

### P0-1：框选后多选平移不工作
**现象**：Shift+框选选中多个原子后，拖动其中一个原子，只动这一个，其他不动。
**根因猜测**：`_capture_multi_drag_origins()` 只在左键点原子时调用，框选完成后 `_multi_drag_start` 字典是空的。
**修复方案**：
1. 在 `_finish_box_select()` 末尾，选中完成后立即调用 `self._capture_multi_drag_origins()`
2. 或者在鼠标按下原子开始拖动时，重新收集所有选中原子的初始坐标，不依赖之前捕获的
**验收**：框选 3 个原子 → 拖其中一个 → 3 个一起移动 → Ctrl+Z 全部恢复

### P0-2：3D 旋转卡顿
**现象**：左键拖空白旋转 3D 视图时很卡，不流畅。
**根因猜测**：
- 每帧都重新渲染所有原子球体 + 键圆柱
- VTK 抗锯齿 FXAA 每帧重算
- 没有旋转时的 LOD（细节层级）降级
**修复方案**：
1. 旋转/缩放时临时关闭 FXAA，静止后再开
2. 原子数 > 100 时，旋转时用低分辨率球体（icosphere 细分 1 代替 2）
3. 检查 `render()` 方法有没有不必要的全量重建，应该用 `Modified()` 局部更新
**验收**：24 原子咖啡因旋转 60fps 不卡；几百原子蛋白旋转也流畅

### P0-3：右键菜单功能太少
**现状**：右键菜单只有删除/建键/改色/改键长/复制/粘贴/清空。
**应该有的完整右键菜单**（参考 GaussView）：
- **对原子右键**：删除原子、改元素类型、改原子颜色、改原子大小、改形式电荷、在两原子间建键、复制这个原子坐标、查看原子详情
- **对键右键**：删除键、切换键级（单/双/三）、精确改键长、改键颜色、改键粗细、查看键长/键角
- **对空白右键**：粘贴分子、新建空白画布、导入文件、显示/隐藏氢原子、显示/隐藏标签、显示/隐藏坐标轴、切换 2D/3D 视图
**修复方案**：扩展 `_show_context_menu()`，按 hit_aid/hit_bid/空白 三种情况分别构建菜单

### P0-4：工具模式逻辑混乱
**现状**：选择/原子/键/擦除四种模式，按钮按下没有高亮选中态，状态栏提示过时。
**修复方案**：
1. 工具栏按钮按下时高亮（当前模式按钮背景变色）
2. 状态栏实时显示："当前模式：选择 | 操作：左键点选，Shift+拖框选，右键菜单"
3. 四种模式的鼠标行为写成一个状态表，统一在 eventFilter 分发

### P0-5：拖拽文件到窗口打开
**现象**：用户要求把 .gjf/.xyz/.pdb 文件拖到画布上直接打开。
**修复方案**：
1. MainWindow `setAcceptDrops(True)`
2. `dragEnterEvent`：接受 .gjf/.xyz/.sdf/.mol/.pdb/.mol2/.smi/.cif
3. `dropEvent`：调用 `load_molecule_document(path)` 加载

---

## 二、复制粘贴问题

### P1-1：Ctrl+V 粘贴不工作
**现状**：之前修过，但只支持 XYZ 格式，且粘贴是替换当前文档不是追加。
**修复方案**：
1. 智能识别剪贴板：SMILES（短文本）/ XYZ（多行坐标）/ 分子名
2. 粘贴应该是**追加**到当前文档，不是替换
3. 粘贴后自动居中显示

### P1-2：Ctrl+C 只复制整个分子，不复制选中
**现状**：Ctrl+C 复制整个分子的 XYZ，不是选中的原子。
**修复方案**：如果有选中原子，只复制选中的；没选中才复制整个分子

---

## 三、文件导入导出

### P2-1：OpenBabel 集成已完成但未充分测试
**现状**：obabel.exe 在 `E:\openbabel-install-msvc\bin\obabel.exe`，可读 142 种，可写 121 种。
**待测试**：
1. 导入大文件（1CRN.pdb 几百原子、4HHB.pdb 几千原子）
2. 导出各种格式（cif/mol2/pdb/sdf/smi）
3. 拖拽导入

### P2-2：SMILES 导出
**现状**：能导出 SMILES（`Cn1c(=O)c2c(ncn2C)n(C)c1=O`）。
**待加**：右键菜单"导出 SMILES 到剪贴板"

---

## 四、计算模块缺失

### P3-1：xtb 免费优化
**需求**：菜单"计算(C)" → xtb 快速几何优化
**实现**：
1. subprocess 调用 xtb.exe（用户本地路径需配置）
2. 生成输入文件 → 运行 → 读回优化后坐标 → 更新文档
3. 进度条显示

### P3-2：Gaussian 输入生成
**现状**：已有 Ctrl+G 设置。
**待加**：
1. 生成完整 .gjf 文件（坐标 + 路线卡 + 电荷自旋）
2. 保存到指定目录

### P3-3：分子轨道可视化
**需求**：导入 cube 文件显示 HOMO/LUMO 等值面
**现状**：代码框架有（`load_orbital_cube`），未测试

---

## 五、UI/UX 问题

### P4-1：预设分子 SMILES 错误
**现象**：左侧"IC 端基"预设分子，羰基和氰基画成邻位，应该是间位（1,3-取代）。
**修复**：检查 `rdkit_adapter.py` 的 SAMPLE_MOLECULES 字典，修正 IC 端基 SMILES

### P4-2：多窗口并排展示
**现状**：有 `_spawn_new_window` 多窗口系统，G1:M1:V1 标签。
**待验证**：新建独立窗口、并排显示、各自独立编辑

### P4-3：右侧属性面板功能太少
**现状**：右侧只有原子大小/颜色/电荷、键粗细/颜色/键长。
**应该有**（参考 GaussView）：
- 原子：元素符号、原子序号、坐标 XYZ、形式电荷、杂化方式
- 键：键级、键长、键角、二面角
- 测量：选 2 个原子显示距离，选 3 个显示键角，选 4 个显示二面角

### P4-4：2D 视图问题
**现状**：2D 画布能显示咖啡因，但编辑功能弱。
**需求**：
- 2D 里加原子/删原子/改键级
- 2D/3D 联动（2D 改了 3D 同步）

---

## 六、打包发布

### P5-1：PyInstaller 打包成 Windows exe
**需求**：不需要 Python 环境的绿色版，双击就能用。
**实现**：
1. PyInstaller spec 文件
2. 正确收集 PyQt6/VTK/PyVista/RDKit 依赖
3. openbabel.exe 作为外部二进制打包
4. 测试双击 exe 能启动、能导入导出

---

## 七、工程纪律（必须遵守）

1. **改任何文件前先备份** `.bak_日期`
2. **所有修改走 CommandBus**，带 Undo/Redo
3. **不要在 eventFilter 里同步调用 VTK render()**，用 `_defer()` 异步
4. **改完启动测试** `python scripts/verify_v5_start.py` 截图验证
5. **不要向 C 盘安装任何东西**
6. **删文件进回收站**，不永久删除
7. **用户是化学研究生**，回答要让他听懂，不要堆术语

---

## 八、关键文件位置

| 文件 | 作用 |
|---|---|
| `molforge/ui/window.py` | 主窗口、菜单、快捷键 |
| `molforge/ui/render3d_widget.py` | 3D 交互 eventFilter |
| `molforge/rendering/vtk_backend.py` | VTK 渲染、相机、坐标轴 |
| `molforge/io/rdkit_adapter.py` | RDKit 导入导出、预设分子 |
| `molforge/io/openbabel_adapter.py` | OpenBabel subprocess |
| `molforge/application/builtin_commands.py` | 命令总线（所有操作） |
| `molforge/application/selection.py` | 选择服务 |
| `scripts/launch.py` | 启动入口 |
