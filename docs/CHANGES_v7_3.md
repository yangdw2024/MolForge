# MolForge v7.2 Bug 修复与 v7.3 科学工作流集成修改记录

## 一、v7.2 八项 P0/P1 交互与功能 Bug 全部修复

1. **P0-1 新建标签页后构建不了分子 (`molforge/ui/shells/document_tabs.py`, `molforge/ui/editor2d_widget.py`, `molforge/ui/window.py`)**：
   - 修复了 `Editor2DWidget.fit_view()` 中平移量重复叠加 `canvas_w / 2` 的坐标偏移缺陷（`world_to_screen` 已内置 `self.width() * 0.5`，`fit_view` 现修正为 `self._pan_x = -center_x * s`, `self._pan_y = center_y * s`）。
   - 修复了 `StudioTabs._register_page()` 当 `index == currentIndex` 时不触发 `currentChanged` 导致 `self.document / self.command_bus / self.canvas2d` 未绑定新标签页的问题。
   - 新建空白画布标签页时自动激活「原子 (A)」工具并同步工具栏状态；且当画布原子数为 0 时，左键点击画布即使原本处于「选择」模式也会自动放置第一个原子并进入「原子」绘制模式。
2. **P0-2 框选后右键菜单没有删除选项 (`molforge/ui/editor2d_widget.py`)**：
   - 在 `_show_canvas_context_menu`、`_show_atom_context_menu`、`_show_bond_context_menu` 中，只要当前存在选中的原子或化学键，菜单顶部第一项立即显示 **「🗑️ 删除选中 (N 个原子, M 条键) [Delete]」**。
3. **P0-3 隐式氢模式下框选/全选选不到氢原子 (`molforge/ui/editor2d_widget.py`)**：
   - `_apply_marquee` 在框选骨架重原子后，自动把所有命中重原子相连的隐式氢原子 (`atomic_num == 1`) 一并纳入选中集合（例如框选咖啡因时完整选中全部 24 个原子：14 个重原子 + 10 个氢原子）。
   - `_select_all` (`Ctrl+A` / 右键全选) 选中拓扑中的全部原子与全部化学键。
4. **P0-4 Delete 键删除不生效 (`molforge/domain/topology.py`, `molforge/domain/ids.py`, `molforge/application/builtin_commands.py`, `molforge/ui/editor2d_widget.py`)**：
   - 修复了 `DeleteAtomCommand.do()` 中调用 `bond.other_end`、`atom.element` 与 `sorted(AtomId)` 引发异常导致删除静默失败的根本原因；在 `Atom`、`Bond`、`Topology`、`AtomId` 上补齐了双向兼容属性与方法，并在 `Editor2DWidget.delete_selected()` 及 Studio 菜单/工具栏中统一绑定 `Delete` / `Backspace` 快捷键。
5. **P1-5 Studio 子系统导出功能齐全 (`molforge/ui/shells/document_tabs.py`)**：
   - 在三大 Studio 窗口的 `文件(&F) → 📤 导出结构与图像 (Export)` 子菜单中新增：**复制 SMILES 到剪贴板**、**导出 XYZ 坐标文件 (.xyz)**、**导出 MOL/SDF 结构文件 (.mol/.sdf)**、**导出 PDB/MOL2 文件 (.pdb/.mol2)**、**导出 PNG 截图 / SVG 矢量图 (.png/.svg)**。
6. **P1-6 定时自动保存与关闭未保存提示 (`molforge/ui/shells/document_tabs.py`)**：
   - 内置 5 分钟 (`300,000 ms`) 定时自动保存器，自动将活动分子备份至 `~/.molforge_autosave/`。
   - 重写 `closeEvent` 与标签页关闭逻辑，检测到未保存修改 (`revision > saved_revision`) 时弹出「保存 / 不保存 / 取消」确认对话框。
7. **P1-7 3D 视口坐标轴默认显示 (`molforge/rendering/vtk_backend.py`, `molforge/ui/render3d_widget.py`)**：
   - 将 `VtkRendererBackend.show_axes` 默认设为 `True`，修复 `vtkOrientationMarkerWidget.SetInteractor` 传入 C++ `vtkRenderWindowInteractor` 的绑定逻辑，同时在场景中添加左下角坐标轴指示器与顶栏 **「🧭 坐标轴」** 开关按钮。
8. **P1-8 明确「🔢 原子编号」按钮作用与提示 (`molforge/ui/render3d_widget.py`)**：
   - 将原 `# 序号` 按钮升级为 **「🔢 原子编号」**，点击后同时显示元素符号与唯一编号（如 `C1, N2, O3...`），并附详细 Tooltip 说明其在测量键角/二面角及配置 Multiwfn/GROMACS 原子索引时的用途。

## 二、v7.3 科学工作流集成

- **完整工作流清单 (`docs/WORKFLOWS_CATALOG.md`)**：梳理出 `WF-01` ~ `WF-25` 共 25 个标准化工作流。
- **模块化工作流代码 (`molforge/workflows/`)**：新增 `esp_surface.py`、`homo_lumo_plot.py`、`osc_energy_diagram.py`、`reorganization_energy.py`、`dipole_analysis.py`、`planarity_analysis.py`、`md_rdf_analysis.py`、`igmh_interaction.py`。
- **8 个独立中文工作流对话框 + `ToolPathConfigDialog` (`molforge/ui/shells/workflow_inputs.py`)**：全部采用 `QThread` 异步执行外部命令，工具路径持久化保存于 `QSettings("MolForge", "ExternalEngines")`。
- **`结果(&R)` 菜单更新 (`molforge/ui/qc_result_dialog.py`)**：按 `基础性质`、`波函数分析 (Multiwfn)`、`分子间相互作用`、`光谱`、`OSC 专题`、`分子动力学 (GROMACS)`、`数据导出` 七大子菜单整齐挂载。
