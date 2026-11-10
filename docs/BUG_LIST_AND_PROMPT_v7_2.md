# MolForge v7.2 完整 Bug 清单 + 修复提示词

> 版本：v7.2 complete source
> 整理时间：2026-10-30
> 目标：全面修复交互 bug，达到 GaussView / ChemDraw 可用性水平

---

## 一、P0 紧急 Bug（影响基本使用）

### 1. 新建标签页后构建不了分子
**现象：** 点"新建画布"新建标签页后，点击画布添加原子不生效，画不了分子。
**已尝试修复：** `refresh_views()` 里加了 `canvas2d.set_document(self.document)`
**状态：** 还是不行，需要继续排查
**涉及文件：** `studio_2d.py`、`studio_split.py` 的 `refresh_views` 方法、`document_tabs.py` 的 `add_document_tab`

### 2. 框选后右键菜单没有删除选项
**现象：** 框选了多个原子后，右键弹出的菜单只有撤销/重做/清洁/居中/全选，没有"删除选中"选项。
**预期：** 框选后右键应该有"删除选中原子"选项。
**涉及文件：** `editor2d_widget.py` 的 `_show_context_menu` 方法

### 3. 隐式氢模式下框选/全选选不到氢原子
**现象：** 隐式氢模式下，框选整个分子，只能选中骨架原子（14个），氢原子（10个）选不到。
**预期：** 框选/全选应该选中所有原子（包括隐式氢），即使氢不显示。
**涉及文件：** `editor2d_widget.py` 的 `_apply_marquee` 方法、全选逻辑

### 4. Delete 键删除不生效
**现象：** 选中原子后按 Delete 键，删不掉。
**预期：** 选中原子后按 Delete 键应该删除选中的原子（连带氢）。
**涉及文件：** `editor2d_widget.py` 的 `keyPressEvent` 方法

---

## 二、P1 重要 Bug（提升体验）

### 5. Studio 子系统没有导出功能
**现象：** 文件菜单里没有导出 SMILES/XYZ/MOL/图片的选项。
**预期：** 加导出功能：导出 SMILES 到剪贴板、导出 XYZ 文件、导出 MOL/SDF 文件、导出 PNG 截图。
**涉及文件：** `studio_2d.py`、`studio_3d.py`、`studio_split.py` 的文件菜单

### 6. 没有自动保存和关闭提示
**现象：** 忘记保存就关窗口，数据丢了。
**预期：** 关闭窗口时提示"是否保存"；定时自动保存（每 5 分钟）。
**涉及文件：** 所有 Studio 窗口的 `closeEvent`

### 7. 3D 视口坐标轴不显示
**现象：** 3D 图里看不到三维坐标轴，"感觉它还是隐藏了一样"。
**预期：** 3D 视口左下角应该显示 XYZ 坐标轴。
**涉及文件：** `render3d_widget.py`

### 8. "序号"按钮不知道干嘛的
**现象：** 工具栏上有个"#序号"按钮，用户不知道它是干嘛的。
**预期：** 搞清楚作用，加 tooltip 说明，或者去掉没用的按钮。
**涉及文件：** 工具栏代码

---

## 三、P2 已修复的 Bug（供参考）

以下 bug 已经修复，不需要再修：

- ✅ Studio2DWindow 无 canvas3d 崩溃
- ✅ 标签页/MDI 切换时 QTabWidget 被删除
- ✅ 删除原子残留氢（连带删除相连氢）
- ✅ 切换标签页后 2D 画布交互失效（set_document）
- ✅ 左右栏一键折叠（setVisible 真正完全收起）
- ✅ 右栏宽度限制太死（调到 600px）
- ✅ 大分子 2D 画布缩放范围太小（调到 15%-400%）
- ✅ 大分子自动适应窗口大小（fit_view）
- ✅ 批量拖动多个选中的原子
- ✅ 选择模式下点键会改变键级（现在只有"键"工具模式才改）
- ✅ Alt+左键 或 中键 平移画布

---

## 四、给 AI 的修复提示词

```
你是一个 PyQt6 分子编辑器专家。请修复 MolForge v7.2 的以下 bug，目标是达到 GaussView / ChemDraw 的可用性水平。

## 项目背景
- MolForge 是一个自研的分子编辑器，类似 GaussView / ChemDraw / Chem3D
- 主系统是经典三栏布局（左栏面板 + 中间画布 + 右栏属性）
- Studio 子系统是简洁风格（菜单 + 工具栏 + 大画布），分 2D / 3D / Split 三种
- 技术栈：PyQt6 + VTK + RDKit + OpenBabel

## 需要修复的 Bug（按优先级）

### P0 紧急（影响基本使用）

1. **新建标签页后构建不了分子**
   - 问题：点"新建画布"新建标签页后，点击画布添加原子不生效，画不了分子。
   - 预期：新建标签页后，应该可以正常点击画布添加原子，像第一个标签页一样。
   - 已尝试修复：`refresh_views()` 里加了 `canvas2d.set_document(self.document)`，但还是不行。
   - 可能原因：新建标签页时，canvas 的 selection_service、command_bus 绑定有问题；或者切换标签页时，当前激活的 canvas 引用不对。
   - 文件：`molforge/ui/shells/studio_2d.py`、`studio_split.py`、`document_tabs.py`

2. **框选后右键菜单没有删除选项**
   - 问题：框选了多个原子后，右键弹出的菜单只有撤销/重做/清洁/居中/全选，没有"删除选中"选项。
   - 预期：框选后右键应该有"删除选中原子"选项。
   - 文件：`molforge/ui/editor2d_widget.py` 的 `_show_context_menu` 方法

3. **隐式氢模式下框选/全选选不到氢原子**
   - 问题：隐式氢模式下，框选整个分子，只能选中骨架原子（14个），氢原子（10个）选不到。
   - 预期：框选/全选应该选中所有原子（包括隐式氢），即使氢不显示。
   - 文件：`molforge/ui/editor2d_widget.py` 的 `_apply_marquee` 方法、全选逻辑

4. **Delete 键删除不生效**
   - 问题：选中原子后按 Delete 键，删不掉。
   - 预期：选中原子后按 Delete 键应该删除选中的原子（连带氢）。
   - 文件：`molforge/ui/editor2d_widget.py` 的 `keyPressEvent` 方法

### P1 重要（提升体验）

5. **Studio 子系统没有导出功能**
   - 问题：文件菜单里没有导出 SMILES/XYZ/MOL/图片的选项。
   - 预期：加导出功能：导出 SMILES 到剪贴板、导出 XYZ 文件、导出 MOL/SDF 文件、导出 PNG 截图。
   - 文件：`molforge/ui/shells/studio_2d.py`、`studio_3d.py`、`studio_split.py`

6. **没有自动保存和关闭提示**
   - 问题：忘记保存就关窗口，数据丢了。
   - 预期：关闭窗口时提示"是否保存"；定时自动保存（每 5 分钟）。
   - 文件：所有 Studio 窗口的 `closeEvent`

7. **3D 视口坐标轴不显示**
   - 问题：3D 图里看不到三维坐标轴。
   - 预期：3D 视口左下角应该显示 XYZ 坐标轴。
   - 文件：`molforge/ui/render3d_widget.py`

8. **"序号"按钮不知道干嘛的**
   - 问题：工具栏上有个"#序号"按钮，用户不知道它是干嘛的。
   - 预期：搞清楚作用，加 tooltip 说明，或者去掉没用的按钮。
   - 文件：工具栏代码

## 修复要求
1. 保持现有代码风格，不要重构整个文件
2. 修复后要验证：Python 语法正确，import 不报错
3. 不要破坏已有的功能（比如撤销/重做、2D/3D 联动、批量拖动）
4. 修复完成后，列出修改了哪些文件，每个文件改了什么
```
