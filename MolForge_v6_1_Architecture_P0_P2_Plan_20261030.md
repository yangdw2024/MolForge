# MolForge v6.1 架构设计、实施计划与源码审查报告

**版本**：Design Draft 1.0  
**日期**：2026-10-30  
**规划范围**：P0 / P1 / P2；Windows 11；PyQt6 + VTK；GaussView 风格 G:M:V；2D、3D 与联动工作台  
**执行边界**：本报告依据上传的 v6.1 源码包开展**静态审查与有限自动化测试**；未改动源码，未宣称完成 Windows 11 或 VTK 原生交互验证。

---

## 一、执行摘要

### 1.1 最终建议

采用**渐进式重构（Strangler / 兼容壳）**，不重写分子核心、不抛弃当前三栏界面、不在早期同时替换 2D、3D 渲染器。

推荐顺序：

**先修 P0 的几何正确性和编辑闭环 → 抽出共享 DocumentSession → 在其上建立三个独立的完整 UI Shell → 实现可信的 G:M:V、多视图和 Gaussian 工作流 → 完成 Windows 11 原生稳定性及打包验收。**

三个新系统应共享分子模型与应用服务，但拥有完整、独立的菜单、工作流程、工具栏、状态栏与窗口生命周期。现有三栏工作台继续作为“经典工作台”保留，不能用“隐藏左右面板”冒充完整的新系统。

### 1.2 基线及审查方法

基准文件：

- `MolForge_v6_1_ForChatGPT_20261030.zip`：本次实际审查的源码；
- `PROMPT_FOR_CHATGPT.md`：v6.0 规划要求；
- `ISSUES_AND_TODO.md`：v6.0 问题、优先级和验收方向。

两份 Markdown 使用 **v6.0** 表述，压缩包命名为 **v6.1**。本报告以 v6.1 源码的实际实现为判断基础，避免重复实施已存在的功能。

检查范围：压缩包内 `main.py`、`scripts/launch.py`、`molforge/domain/`、`application/`、`ui/`、`rendering/`、`io/`、现有测试和 Windows 诊断脚本。扫描到 **122 个 Python 源码文件，AST 语法解析全部通过**。这不是依赖安装、GUI 启动或运行稳定性的证明。

有限测试（在隔离的 Linux 分析环境，未修改原项目文件）：

```text
python -m pytest -q tests/test_windows10_contract.py tests/golden/science/test_golden.py
结果：8 passed, 1 failed, 6 skipped
```

失败项：`test_launcher_no_personal_hardcoded_python_path`，当前 `run_molforge.bat` 仍含固定的个人 Python 解释器绝对路径。六项 golden science 测试是 `pytest.skip`，**不代表已验证科学正确性**。本环境缺少 PyQt6，故**无法宣称 Windows 11 GUI、Qt/VTK 原生多窗口和用户交互通过**。

### 1.3 现状与目标差距

| 领域 | v6.1 源码现状 | 真实差距 / 决策 |
|---|---|---|
| 经典三栏工作台 | `MolForgeWindow`、`Workspace`、`RightPanel` 已存在 | **必须保留**，只做兼容性修复 |
| 2D / 3D / 分屏 | `Workspace.set_mode(0/1/2)` 已支持三种画布可见模式 | 当前是一个工作台内部的模式切换，**不是三个完整独立系统** |
| 三维多窗口 | `G1:M1:V1` 标签、创建新分子和克隆窗口已具备 | 缺少中心化窗口/分子/视图注册与统一命令总线；缺 1/2/4 真正多视图布局 |
| 几何测量 | `measurement.angle()` 使用标准向量夹角公式 | UI 以 `list(selected_atoms_set)` 确定三原子顺序，可能把错误原子选为顶点；两相邻键未形成规范测角流程 |
| 精确键角修改 | 对话框、右侧按钮和单原子移动调用已存在 | 右侧两个按钮未正确接入主窗口引用；未保持连接基团几何；选点顺序不可靠 |
| 精确二面角修改 | 菜单、按钮、`ModifyInternalCoordDialog` 已存在 | `_set_selected_dihedral_angle()` 仅打开扭转曲线图，**未调整坐标** |
| 官能团构建 | 官能团菜单、`BuilderFragmentDialog` 已存在 | 无元素按钮右键分组面板；元素片段多为单原子；多步插入和优化缺少完整事务 |
| Gaussian | 有 `.gjf` 输入生成与量化工作台（3 个顶层页签） | 不是规定的 11 个设置页签 + 6 个控制按钮；本地提交、快速启动与校验还需整合 |
| Windows 11 | `scripts/windows10_diagnostics.py` 专门检测 Win10 | 其中明确将 build ≥ 22000 判为 Win11 并拒绝；需要新增 Win11 发布契约 |
| 回归保障 | 有样式/存储等测试，也有科学测试骨架 | 测角及其他 golden tests 仍被跳过；需新增原生 GUI / VTK 耐久测试 |

### 1.4 已识别的高优先级源码问题

**S01 — P0：原子选择没有保存顺序。**  
`molforge/application/selection.py` 使用 `set[AtomId]`；`ui/window.py::_update_measurement()` 与 `ui/views.py::ModifyInternalCoordDialog` 将它转成 `list(...)`。对 `angle(i,j,k)` 来说，**第二个位置 j 必须是中心原子**。三个原子同属一个分子并不能保证无序集合的第二个元素正好是中心。不要把 `180° - 原角度` 当修复措施：那会破坏正确输入。

**S02 — P0：精确修改的操作闭环不完整。**  
`ui/panels.py::_on_modify_angle/_on_modify_dihedral()` 依赖 `_window_ref`，而审查的源码中没有找到赋值；按钮可能静默无响应。另一条“精确修改选中内坐标”路径已经绑定主窗口回调，但二面角最终进入 `DihedralChartDialog`，而非坐标更新命令。键角调整当前只移动第三个原子，连接基团会被拉伸。

**S03 — P0：测量记录的不可变性冲突。**  
`application/measurement.py` 将 `Measurement` 声明为 `@dataclass(frozen=True)`，而 `MeasurementService.cleanup_after_delete()` 却给 `m.valid` / `m.diagnostic` 赋值。该分支若执行，会触发 `FrozenInstanceError`。需改为替换不可变记录或采用显式可变状态，不应直接赋值。

**S04 — P0/P1：官能团插入是多次独立修改。**  
`ui/window.py::_on_fg_insert()` 逐条执行多个 `AddAtomCommand` / `DeleteAtomCommand`，随后直接调用 `document.relax_3d_geometry()`。这与“一次接枝、一次撤销、整组坐标可恢复”的产品预期不一致，应封装事务命令，不在命令总线外留下几何变更。

**S05 — P1：共享 Document 不等于共享编辑会话。**  
`ui/window.py::_on_add_clone_view()` 将相同 `MoleculeDocument` 传入新的 `MolForgeWindow`；每个构造函数又新建自己的 `CommandBus`、`UndoHistory` 和 `SelectionService`。这会使共享对象的多个视图在刷新事件、选择和撤销历史上发生分裂。

**S06 — P0/P2：Windows 发布路径和版本信息漂移。**  
`run_molforge.bat` 使用固定个人目录；Windows10 诊断拒绝 Win11；`main.py` 应用版本、窗口标题里的 v4.0、需求 v6.0 与压缩包 v6.1 不一致。应统一版本声明，发布器从当前目录或可配置环境定位解释器。

**S07 — P1：量化任务执行路径需要后台化。**  
`ui/window.py::_on_run_xtb_optimization()` 在 UI 调用链同步运行优化，仅在运行前使用 `processEvents()`。现有 `application/jobs.py::JobCenter` 可用于将耗时计算迁移到可取消的后台任务，输出绑定文档 revision，避免旧任务结果覆盖新编辑。

---

## 二、目标产品架构

### 2.1 核心设计原则

1. **一个分子，一份事实**：`MoleculeDocument` 是唯一化学与几何事实源；2D 和 3D 不维护互相冲突的分子副本。
2. **一个文档，一条写入通道**：同一 `document_id` 只绑定一个 `CommandBus` 和 `UndoHistory`；多个窗口共享它们。
3. **视图独立，数据共享**：相机、视角、渲染模式、窗口布局与浮动面板位置属于 `ViewSession`，不能修改化学结构。
4. **所有结构修改事务化**：批量官能团、扭转、优化结果回填走 `CommandBus`，一次用户操作对应一次撤销。
5. **新界面复用旧组件**：保留 `Editor2DWidget`、`Render3DWidget`、现有渲染后端、存储与应用命令；外壳改造优先，核心重写靠后。
6. **原生稳定性先于多视口数量**：先实现可靠的单视图与窗口生命周期，再开放 2 / 4 视图。
7. **科学操作与示意演示分开**：`DihedralChartDialog` 当前曲线是示意性势能包络，不能称作实际 xtb/Gaussian 扫描结果；实际扫描必须有计算任务及来源记录。

### 2.2 分层架构

```text
ApplicationBootstrap (main.py / scripts/launch.py)
  └── WelcomeWindow（启动欢迎与最近工程）
       └── ShellFactory
            ├── Studio2DShell（完整 2D 化学绘图系统）
            ├── Studio3DShell（完整 3D 菜单驱动系统）
            │    └── MoleculeGroupManager（G:M:V 与 1/2/4 视图）
            ├── StudioSplitShell（完整 2D—3D 联动系统）
            └── LegacyWorkbenchAdapter（保留原三栏工作台）

WorkspaceRegistry
  ├── GroupSession[G]                         分子组
  ├── DocumentSession[document_id]            每分子共享编辑会话
  │    ├── MoleculeDocument                  拓扑、3D、2D 坐标
  │    ├── CommandBus + UndoHistory           唯一写入与撤销
  │    ├── SelectionService                   有序选择 + origin
  │    ├── Measurement / InternalCoordService
  │    ├── DocumentEventHub + Revision
  │    └── JobCenter / ResultStaleness
  └── ViewSession[view_id]
       ├── document_id
       ├── camera / render preset
       ├── layout: 1 | 2 | 4 panes
       └── active pane / view visibility

Infrastructure
  ├── 2D: QPainter / RDKit
  ├── 3D: PyVistaQt / VTK 9.7.1
  ├── Gaussian / xtb / ORCA / REST adapters
  └── .mforge / SMILES / SDF / MOL / PDB / XYZ / ...
```

该图是**建议新增的逻辑结构**，并不表示这些新文件或类已经存在。

### 2.3 关键对象契约

| 类型 | 职责 | 生命周期 | 不能做的事 |
|---|---|---|---|
| `WorkspaceRegistry` | 维护组、文档、窗口、视图索引与激活对象 | 应用级 | 不储存几何坐标副本 |
| `DocumentSession` | 持有唯一 Document、CommandBus、Undo、Selection、事件 | 最后一个使用者关闭或工程卸载后销毁 | 不持有 VTK 原生对象 |
| `GroupSession` | 管理 G 编号、多个 M、每个 M 的 V | 分子组级 | 不复制文档来模拟克隆视图 |
| `ViewSession` | 管理相机、渲染、1/2/4 布局、选中 pane | 视图级 | 不自建独立的同文档 UndoHistory |
| `ShellFactory` | 根据启动入口建立各系统完整 UI | 工厂级 | 不改变科学数据 |
| `DocumentEventHub` | 发送 revision、来源、变更类型与激活状态 | Session 级 | 不让各 Shell 互相直接调用 |
| `JobCenter` | 可取消的外部计算、任务状态、结果归属 | 应用/文档级 | 不在 Worker 线程创建或操作 VTK / QWidget |

**共享文档的行为保证**：在 G1:M1:V1 编辑后，G1:M1:V2 的 2D/3D 内容通过同一会话的变更事件更新；在 V2 执行 Ctrl+Z 也应撤销 V1 发起的最后一次文档编辑。相机旋转、工具栏切换则保持各视图独立。

### 2.4 G:M:V 命名与映射规则

- **G**：分子组编号，一个组可管理多个分子，标识 `G1`、`G2`；
- **M**：组内分子编号，`G1:M1` 与 `G1:M2` 可指向不同的 DocumentSession；
- **V**：同一分子的不同视图，`G1:M1:V1` 与 `G1:M1:V2` 指向同一个 DocumentSession，但有各自 ViewSession；
- **Pane**：一个 V 内部的 1/2/4 子视图，使用 `P1…P4`，不误当作独立 V。

例：`G1:M1:V2` 使用四分屏时，在界面内部显示 `P1 Front / P2 Side / P3 Top / P4 Perspective`；G:M:V 标识不变。

编号由 `MoleculeGroupManager` 分配，不能简单地 `当前打开的数量 + 1`，以免关闭窗口后重新创建时发生标识重复。推荐采用每个 Group 的递增计数器与独立 UUID，显示标签只是人类可读别名。

### 2.5 三套完整系统的要求

#### Studio2DShell：二维分子化学绘图

- 自有菜单：File / Edit / Draw / Structure / Templates / View / Tools / Window / Help；
- 2D 工具栏：选择、原子、键、环、官能团、化学属性、对齐/清理、撤销/重做；
- 完整的项目管理、打开/保存/导出、结构检查、画布缩放、快捷键、状态栏、最近文件；
- 化学操作复用现有 `Editor2DWidget`、RDKit 适配器与 CommandBus；
- 不依赖一个隐藏的 3D 主工作台才能使用关键功能。

#### Studio3DShell：GaussView 式三维系统

- 顶部九组菜单：**File / Edit / Tools / Builder / View / Calculate / Results / Windows / Help**；
- 中央为轻量三维画布；底部状态栏显示原子数、电子数、电荷、自旋多重度；
- Builder / Calculate / Results 等功能通过**独立对话框**唤起，避免强制占用巨大右侧属性面板；
- G:M:V 新组、新分子、克隆视图、窗口切换、关闭单一 View；
- 1/2/4 布局；每 pane 的 Front / Side / Top / Perspective 相机；同步相机作为可选开关；
- 保留点选、拖动、框选/套索、右键、xtb、轨道、构象和测量能力。

电子数采用 `Σ(原子序数) − 总电荷`；自旋多重度采用文档当前计算设置或可验证状态，不要根据原子数硬编码。用户设定的多重度须与电子数奇偶性校验。

#### StudioSplitShell：联动 2D—3D 系统

- 自有完整菜单、工具栏、左右分屏与状态栏；
- 2D、3D 同时引用同一 DocumentSession；右侧属性检查器是可切换的可停靠组件，而非唯一入口；
- 支持双视图定位、共同选择、高亮、跨画布编辑、单次撤销；
- 2D 布局变化不自动废弃量化结果；3D 拓扑/几何变化须按照失效规则更新缓存和任务状态。

#### 经典工作台兼容

当前 `MolForgeWindow` 的三栏界面作为 **LegacyWorkbenchAdapter** 原样保留，初期由欢迎页三种系统中的相应菜单“打开经典工作台”进入，不必在欢迎页增加第四个主入口。待新系统稳定后，由用户设置保留或隐藏该入口。

---

## 三、P0：必须先修复的科学正确性与可用性

### 3.1 修复测量角度，而不是修改角度公式

当前标准公式为：

\[
\theta = \arccos \left( \frac{(\mathbf r_i-\mathbf r_j)\cdot(\mathbf r_k-\mathbf r_j)}
{|\mathbf r_i-\mathbf r_j|\,|\mathbf r_k-\mathbf r_j|} \right)
\]

其中 **j 必须是中心原子**。目前 `measurement.angle()` 的向量定义正确，错误集中在输入原子顺序的构造。

**建议实现：**

1. `SelectionService` 内部同时维护 `ordered_atom_ids: list[AtomId]` 和 membership set；现有 `.selected_atoms` 继续返回 set，保持兼容；新增 `.ordered_atoms` 只读属性。
2. 选择、取消选择、框选时维护序列；跨界面选择传递 `origin + revision`，禁止反向循环。
3. 测量输入由 `MeasurementTargetResolver` 整理：
   - 两个相邻键：求唯一公共原子作为中心 `j`，两外端作为 `i/k`；
   - 三个原子：如果拓扑只存在一条 `i-j-k` 链，自动以两键交汇原子为 `j`；
   - 三角环、断开拓扑、多个可能中心：提示用户明确选择 `i-j-k`，不猜测；
   - 4 原子测二面角，要求有向链 `i-j-k-l` 与中央键 `j-k` 合法。
4. 展示测量值时同时展示 `#i–#j–#k` / `#i–#j–#k–#l`，让用户知道系统测的到底是什么。
5. 不使用 `180° − θ` 纠正小角。此转换只适用于另一个几何定义，并不能弥补顶点错误。
6. 处理零长度向量、共线、NaN/Inf、坐标索引越界；失败时显示诊断而不是假数值。

**确定性单元测试**：构造以原子 j 为顶点、真实夹角 110° 的三原子坐标，`angle(i,j,k)` 返回 110°；将 i 错误作为顶点会得到约 35°。三个原子的任意选取顺序都不得改变拓扑解析后的目标夹角。

### 3.2 修复键角与二面角的“精确修改”

- 将 `RightPanel` 的 `_on_modify_angle/_on_modify_dihedral` 绑定到显式 `on_modify_angle` / `on_modify_dihedral` 回调，或注入受检查的主窗口引用，避免未设置 `_window_ref` 后按钮静默无效。
- `ModifyInternalCoordDialog` 显示**当前真实值、原子序列、目标值、影响的原子数、可否撤销**。角度范围 0°–180°，实际应拒绝退化端点；二面角采用统一的 `(-180°, 180°]` 约定。
- 新增 `ModifyAngle3DCommand`：解析三原子中心，确定被移动的连通子图，围绕顶点实施几何旋转，保留连接段的键长并尽量保持被移动侧的内部几何；对无法可靠处理的成环/交叉约束情况禁止静默修改。
- 新增 `ModifyDihedral3DCommand`：识别 `j–k` 中心键，拓扑断开该键后确定应随动的一侧，用 Rodrigues 旋转公式对整个连通子图作刚体扭转；中心键处于环中时提示“需要约束优化/环系编辑”，禁止直接扯坏环。
- 一次数值确认执行**一条原子级事务命令**，可以复用 `TransformCoordinates3DCommand` 写回整帧，但业务校验及目标残差应由专门的内坐标服务负责。
- 结果更新后验证目标角度误差、分子不变量、其它应保持的键长；只在校验通过后写入。撤销恢复完整坐标与 2D 布局。
- 将 `DihedralChartDialog` 保留为分析入口，**不要**再用它替代几何编辑；示意势能曲线必须标注“示意模型，非实际计算数据”。

### 3.3 修复测量记录的冻结数据冲突

建议 `Measurement` 保持不可变，并在删除原子时用 `dataclasses.replace(m, valid=False, diagnostic="原子已删除…")` 生成新对象，替换列表原项。清理后自动通知 MeasurementTable 刷新。加一条针对删除原子后测量失效的回归测试。

### 3.4 Element Fragments：真正的片段级插入

新增数据驱动的 `ElementFragmentsDialog`：C/O/N 元素按钮**右键**弹出；左键继续保留原有选择元素行为。支持“元素分类 → 可视化片段列表 → 连接点预览 → 选择插入”。

建议首批片段：

| 分类 | 片段 |
|---|---|
| C | 单碳、甲基、乙炔基、乙烯基、异丙基、叔丁基 |
| O | 单氧、羟基、羰基连接模板、醚基/醚桥模板 |
| N | 单氮、氨基、硝基、氰基连接模板 |
| 通用 | 卤素、羧基、甲氧基、苯环、常用五/六元杂环；延用现有库 |

“羰基”“醚桥”“氰基”等必须提供**明确的键连接语义**，不能只按照用户按下的元素分类盲目拼一个原子。

`FragmentSpec` 至少包含：`id`、显示名称、分类、经验证的 SMILES/拓扑模板、入口原子、离去原子/隐氢策略、连接键级、默认空间取向、2D 图样、3D 局部构象、化学适用条件。支持 RDKit 结构检查、原子价态、形式电荷、冲突检查和附着位置预览。

**原子级事务**：`InsertFragmentCommand` 或可回滚的 `CompositeCommand` 将离去基替换、新增原子/键、生成初步坐标及修复布局作为**一次**命令，任一步失败时整体撤回；不要插入一半时停住。生成几何前保存完整坐标快照，避免 `relax_3d_geometry()` 在命令总线外修改后无法撤销。

**P0 最低验收**：C/O/N 右键面板能打开；甲基、乙烯基、羟基、氨基、氰基插入合法；一次 Ctrl+Z 恢复插入前的拓扑和坐标；保存、重新打开 `.mforge` 后一致。

### 3.5 P0 任务清单与完成门槛

| 编号 | 任务 | 主要位置 | 验收 |
|---|---|---|---|
| P0-00 | 建立 Git 基线、锁定依赖、备份 `.mforge` 样本 | 项目根、`requirements` | 原项目可运行并可回退 |
| P0-01 | 有序选择服务与兼容 API | `application/selection.py` | 选择顺序稳定，不破坏旧调用 |
| P0-02 | 拓扑测角目标解析（选原子或两相邻键） | `application/measurement.py` / 新 Resolver | 顶点总是明确、合法 |
| P0-03 | 修复测量 UI 提示、展示原子序列 | `ui/window.py`、`ui/panels.py` | 110° 不显示为 35° |
| P0-04 | 修复 `Measurement` 冻结对象失效逻辑 | `application/measurement.py` | 删除原子无异常 |
| P0-05 | 修复两个“精确修改”按钮接线 | `ui/panels.py`、`ui/window.py` | 点击必有有效响应/解释 |
| P0-06 | 建立 `ModifyAngle3DCommand` | 应用层几何服务、命令层 | 多原子刚体更新 + 一次撤销 |
| P0-07 | 建立 `ModifyDihedral3DCommand` | 应用层几何服务、命令层 | 真正旋转坐标，保留键长 |
| P0-08 | 实现最小 Element Fragments 列表与右键 | `ui/element_picker.py`、`ui/window.py`、新对话框 | C/O/N 片段可浏览 |
| P0-09 | 片段事务插入与化学验证 | 新 `fragments` 服务、`builtin_commands.py` | 不出现半成品分子 |
| P0-10 | 修复启动绝对路径与 Windows 11 诊断方案 | `run_molforge.bat`、`scripts/` | 解释器可配置；Win11 有独立诊断 |
| P0-11 | 将测量 golden tests 由 skip 变为真实断言 | `tests/golden/science/` | 指定测试全部通过 |
| P0-12 | 回归既有编辑、撤销、保存/加载、xtb、轨道入口 | `tests/` / Windows GUI | 无已知核心功能倒退 |

**P0 退出条件**：

- 理想四面体约 109.47°、水分子约 104.5°、三原子 110°、芳香环约 120° 测量均在预设合理容差内；
- 用户任意顺序选择同一有效三原子链，不会把错误原子当作中心；
- 正负二面角及跨越 ±180° 的目标设置正确，撤销/重做完全恢复；
- C/O/N 片段事务插入通过结构、价态、回滚、文件往返测试；
- 原有三栏 UI、2D、3D、分屏模式不被破坏；
- 启动脚本不再依赖某个人的开发机路径。

---

## 四、P1：三个独立 UI 系统与 GaussView 风格多窗口

### 4.1 P1 建设次序

**第 1 步：会话抽取。**  
从 `MolForgeWindow.__init__` 抽出 `DocumentSession` 的初始化和引用，现有 `MolForgeWindow` 先改成消费会话。确保主窗口、克隆视图、2D/3D Widget 不再各自独立建立共享分子的命令总线。

**第 2 步：欢迎入口。**  
在 `main.py` 和 `scripts/launch.py` 中统一 bootstrap：先展示 `WelcomeWindow`，提供 **2D 设计 / 3D 设计 / 2D—3D 分屏** 三个入口、最近工程、打开文件；选择之后才延迟创建对应 Shell。欢迎界面不提前实例化三个 VTK 画布。

**第 3 步：2D 与分屏完整 Shell。**  
复用原编辑器与渲染器，先实现菜单、状态栏、文档生命周期、快捷键、保存/导出与同步，避免“看上去是独立窗口但没有完整功能”。

**第 4 步：3D 菜单驱动 Shell。**  
把当前 `window.py` 的菜单构建逻辑分拆成命令注册/菜单描述，按 File / Edit / Tools / Builder / View / Calculate / Results / Windows / Help 重组。功能对话框统一接受 `DocumentSession` 和 `ViewSession`，不直接依赖整个旧主窗口。

**第 5 步：G:M:V 管理器与多 pane。**  
优先落实 G / M / V 的引用关系与同步语义；先开放同一 View 的 1-pane，验证原生窗口关闭；再实施 2-pane 和 4-pane。

### 4.2 1/2/4 视图的 VTK 设计

为降低 Qt+VTK 原生窗口风险，建议**一个 3D ViewWidget 内尽量使用一个 `QtInteractor` / `vtkRenderWindow`，根据布局放置 1、2、4 个 `vtkRenderer` viewport**。可共享稳定的、与图形上下文无关的几何缓存；相机和交互状态独立；每个 viewport 需要自己的命中识别与 pane 坐标变换。

不同**顶层窗口**仍可能需要不同 OpenGL 上下文，不能假定 VTK 的原生 renderer / actor / interactor 对象可跨窗口自由共享。共享的是 `MoleculeDocument`、渲染快照或可安全重建的只读数据，不是原生 QWidget/Interactor。

Native 生命周期守则：

1. 所有 VTK/QWidget 对象在 **Qt GUI 主线程** 创建、交互与销毁；
2. 不在 `eventFilter` 的底层 VTK 事件栈中直接执行复杂改拓扑和即时重建；沿用现有 `_defer()` / `QTimer.singleShot(0, ...)`；
3. 延迟初始化、节制 Render 调用、避免鼠标移动时重建整个 actor 场景；
4. 在关闭窗口时停用输入、取消计时器/待执行刷新、从注册表解绑监听器、关闭 `QtInteractor`、释放引用；
5. 采用空文档、咖啡因、上千原子 PDB、多窗口循环作为不同压力层次；
6. 每次 native crash 采集平台版本、显卡/驱动、Qt/VTK 版本、窗口和视图数、最后事件、原生日志；
7. **0xC0000409 是必须复现和追踪的异常代码，不可在没有 dump 的前提下武断认定“Qt 多窗口必然导致”**；
8. 先通过 100 次开/关与切换的耐久测试，再把 4 pane 设为默认开放功能。

### 4.3 Gaussian Calculation Setup

现有 `QcResultDialog` 的 Gaussian 输入页和 `generate_gaussian_gjf()` 是可复用基础；增加专门的、与结果浏览器解耦的 `GaussianCalculationSetupDialog`，配置模型由 `GaussianJobSpec` 管理。

**11 个页签：**

1. Job Type：单点、优化、频率、TD-DFT、IRC/Scan 等，依据引擎实际能力启用；
2. Method：方法、基组、色散、泛函/自旋；
3. Title：任务标题；
4. Link 0：资源与执行控制，例如 `%chk`、`%mem`、`%nprocshared`；
5. General：通用运行参数；
6. Guess：初始波函数；
7. Pop.：电荷/轨道/布居分析；
8. PBC：周期边界设置，不支持的组合禁用并说明；
9. Solvation：PCM / SMD 等求解模型；
10. Add. Inp.：需要追加的高级输入；
11. Preview：由**唯一输入模型**实时生成、可复制/保存的最终 `.gjf`。

**6 个按钮语义：**

| 按钮 | 实际行为 |
|---|---|
| Submit | 验证 JobSpec 后按配置提交可用执行引擎；不可用时明确提示，可转为导出输入文件 |
| Quick Launch | 使用可用的本地 Gaussian 执行器快速启动，进入 JobCenter，UI 不阻塞 |
| Cancel | 关闭对话框，不对分子执行修改 |
| Edit | 切换到高级原始输入编辑模式，同时检测 UI 参数与文本的潜在不一致 |
| Retain | 将当前设置保存为可复用预设，不混淆“运行任务” |
| Defaults | 恢复明确版本的默认预设，提供取消/确认边界 |

必须校验电子数与自旋多重度的奇偶性、坐标是否为空及有限值、任务与方法兼容性、基组/溶剂支持、引擎路径及输出目录权限；不要把空文档伪装成一个 C 原子来提交。当前 `extract_xyz_lines()` 存在空文档写入占位 C 原子的行为，建议对 **真实计算 Submit / Quick Launch** 明确拒绝空结构；如希望保留示例预览，必须另行标注样例模式。

`JobCenter` 的任务应保存输入文本 hash、`document_id`、`revision`、方法参数、程序版本和执行日志。输出写回前对比当前 revision；若分子已被用户修改，只能提示“结果来自旧结构”，不得静默覆盖。

### 4.4 P1 任务清单

| 编号 | 任务 | 验收 |
|---|---|---|
| P1-01 | `WorkspaceRegistry`、`DocumentSession` 最小实现 | 同一 document_id 仅一个 CommandBus |
| P1-02 | 旧 `MolForgeWindow` 改成消费 DocumentSession | 经典界面与旧快捷键不变 |
| P1-03 | 事件中心化与文档 revision 刷新 | V1 编辑，V2 自动刷新，无事件循环 |
| P1-04 | `WelcomeWindow`、`ShellFactory` | 三入口启动稳定、延迟创建 VTK |
| P1-05 | 完整 Studio2DShell | 绘图、菜单、保存、撤销可独立完成 |
| P1-06 | 完整 StudioSplitShell | 跨视图选择、编辑、撤销一致 |
| P1-07 | 完整 Studio3DShell | 九组菜单、对话框式功能入口 |
| P1-08 | G/M/V 注册、编号和关闭语义 | 新建/克隆/切换不冲突、不丢编辑 |
| P1-09 | 单 pane 基线、多窗口资源销毁 | 100 次开关无原生崩溃 |
| P1-10 | 2-pane、4-pane viewport | 命中拾取、独立相机、布局切换通过 |
| P1-11 | Gaussian 11 页签与 JobSpec | Preview 与设置一致 |
| P1-12 | Submit/Quick Launch 集成 JobCenter | 可取消、状态准确、旧结果不覆盖 |
| P1-13 | 任务/构象/轨道、旧浮动 Dock 完整回归 | 所有旧功能有新入口或保留经典入口 |

**P1 退出条件**：三个入口是完整可用的工作流；G1:M1:V1、G1:M2:V1、G1:M1:V2、G2:M1:V1 均有明确文档归属；两个 View 对同一分子的编辑/撤销历史一致；1/2/4 分屏与 Gaussian 输入设置有自动化及 Windows 原生验收记录。

---

## 五、P2：专业化、发布和质量保障

### 5.1 P2 任务清单

| 编号 | 任务 | 验收 |
|---|---|---|
| P2-01 | 2D 版式与化学绘图完善 | 标注、杂环、模板、导出适合出版 |
| P2-02 | Fragment Catalog 扩充与搜索 | 碳、氧、氮及常用杂环模板覆盖需求 |
| P2-03 | Windows 11 依赖锁定与完整安装诊断 | 实机可重建环境 |
| P2-04 | PyInstaller / 发布打包 | 无开发机专属路径，干净 Win11 可启动 |
| P2-05 | 多视图缓存与 GPU 性能分析 | 交互流畅，分屏切换不反复全量重建 |
| P2-06 | `.mforge` 会话布局/恢复策略 | 文档向后兼容，布局可选恢复 |
| P2-07 | 任务、轨道与构象结果溯源 | 与 document revision 匹配 |
| P2-08 | 自动化 Windows GUI 耐久测试 | 多窗口、关闭、拖拽、保存、计算入口通过 |
| P2-09 | 真实用户可用性测试与 UX 收尾 | 完成 2D、3D、Gaussian 三条真实任务 |
| P2-10 | 发布说明、升级迁移及崩溃诊断 | 可发布/回滚、已知限制清晰 |

### 5.2 Windows 11 兼容性与依赖策略

目标环境：**Windows 11 x64 / Python 3.13 / PyQt6 6.11.0 / VTK 9.7.1**，同时评估 OpenBabel 3.2.1、RDKit、PyVista、PyVistaQt 及本地外部计算引擎。版本组合需要在真实 Windows 11 设备上逐一验证，不能凭 wheel 存在就宣布兼容。

本次外部参考核对：

- Qt for Python 6.11 官方文档明确列出 Windows 11 x86_64 支持：https://doc.qt.io/qtforpython-6.11/overviews/qtdoc-windows.html
- PyPI 的 VTK 9.7.1 发布文件包含 `cp313-cp313-win_amd64` wheel：https://pypi.org/project/vtk/9.7.1/

以上只能证明**平台被支持或安装包存在**，不能替代 VTK + PyVistaQt + GPU 驱动的组合实测。

建议：

- 增加 `scripts/windows11_diagnostics.py` 或通用 `windows_diagnostics.py`；保留原 Win10 检查的历史契约，不要简单让 Win11 假扮 Win10；
- 确认并固定直接依赖和间接依赖版本、wheel 的可获得性、应用打包环境及 VC 运行库；
- 测试 Intel 集成显卡与 NVIDIA 独立显卡、100%/150%/200% DPI、单/双显示器、拖拽窗口到另一显示器后的 VTK 重绘；
- 规定 Windows 原生核心验证：启动、关闭、窗口克隆、1/2/4 分屏、原子点选、框选/套索、多原子移动、Undo、导入导出、轨道、xtb；
- 发布脚本优先使用项目 `.venv` 或由用户设置的 `MOLFORGE_PYTHON`，再回退 `py -3.13` / `python`；不使用个人机器固定路径；
- 优先做“可复制环境 + 故障诊断 + 人工验收”，再做一键安装或绿色版。

---

## 六、质量验证矩阵（必须自动化的验收）

| 验证项 | 测试数据 / 步骤 | 通过条件 |
|---|---|---|
| 键角标准向量 | 人工构造 110° 三点 | 误差 ≤ 0.1° |
| 键角选中顺序 | 三原子有效链，排列与 Shift 选取顺序改变 | 自动识别相同中心；结果一致 |
| 邻接双键测角 | 两条共享一个原子的键 | 显示真实夹角并标注中心 |
| 三角环歧义 | 三个互相相连的环顶点 | 明确提示需要确认中心，不隐式猜测 |
| 内坐标修改 | 非环链条调整至 115°、+60°、−60° | 目标误差在约定阈值内，随动基团未扯断 |
| 环键扭转 | 尝试将闭环中间键直接扭转 | 明确拒绝或进入受约束算法，不破坏结构 |
| 事务性 | 插入甲基、羟基、氰基后 Ctrl+Z/Ctrl+Y | 原子数、键数、坐标与结构一致 |
| 保存兼容 | v6.1 既有 `.mforge` 1.0/1.1 样本往返 | 不丢结构、坐标、属性、稳定 ID |
| 共享编辑会话 | 同一文档两 View；在 V1 编辑，在 V2 撤销 | V1 / V2 / 2D 全部同步 |
| 视图独立性 | V1 改相机/显示模式，V2 不动 | 数据相同，视角不同 |
| G:M:V | 新建分子组、追加 M、克隆 V、关闭/新建 | ID 不冲突，文档不串线 |
| 四视图 | 1 ↔ 2 ↔ 4 连续切换，点击不同 pane | 无误拾取、空白、灰屏或native crash |
| Gaussian | 各页参数修改、Preview 与导出 | `.gjf` 一致且合法，空文档被阻止提交 |
| 计算过期检测 | 提交任务后用户继续改结构 | 返回旧结果不覆盖新结构 |
| 高负载 | 咖啡因、327 原子 PDB、数千原子样本 | 不变量保持、界面可响应 |
| Native 耐久 | 100 次 3D 窗口创建/切换/销毁 | 无 0xC0000409 和不可恢复资源增长 |
| Windows 发布 | 干净 Windows 11 64 位环境 | 无私人绝对路径、能启动、能运行样例 |

**建议测试层次**：数学/拓扑单元测试 → CommandBus 事务/文档测试 → PyQt `QTest` 组件测试 → Windows 11 原生 VTK 多窗口压力测试 → 发布版端到端走查。

当前科学 golden tests 的 `pytest.skip` 应当逐项清除，不能把“测试存在”误写成“测试通过”。

---

## 七、风险评估与回滚方案

| 风险 | 影响 | 预防 / 缓解 | 回滚触发 |
|---|---|---|---|
| R01 选中顺序改变既有行为 | 旧选择/AI/拖动逻辑受影响 | 保留旧 set API，新有序 API 增量接入；补双向测试 | 旧选择/框选失败 |
| R02 几何旋转破坏化学结构 | 科学数据不可信 | 图连通验证、环约束、目标残差检查、事务前快照 | 出现键断裂或不可撤销 |
| R03 Fragment 部分成功 | 结构损坏、Undo 不完整 | CompositeCommand 一次提交、整组验证、失败回滚 | 插入后出现半成品 |
| R04 Clone View 不同步 | 视图与历史互相矛盾 | 单文档唯一 Session/Bus、事件 revision、回归测试 | 不同视图观察到不同分子状态 |
| R05 Qt + VTK native crash | 直接进程退出，可能丢数据 | GUI 主线程、延迟事件、资源显式销毁、分阶段开放 2/4 pane | 复现 0xC0000409 |
| R06 多窗口 GPU 内存上涨 | 性能恶化、驱动崩溃 | 稳定单个 RenderWindow、监控显存/内存、缓存生命周期 | 内存不回收且持续增长 |
| R07 Gaussian 输入/运行错误 | 浪费计算资源或得出错误结果 | JobSpec 校验、输入预览、外部引擎检测、版本与日志归档 | 验收输入与运行行为不一致 |
| R08 旧 `.mforge` 不兼容 | 无法打开原有工程 | 保留 1.0/1.1 读取、迁移测试、只扩展可选元数据 | 任何既有项目无法无损恢复 |
| R09 Windows 11 依赖组合不稳定 | 无法发布 | 固定版本、实机矩阵、PyInstaller 专项验收 | 启动失败/原生崩溃 |
| R10 大型 `window.py` 改造面过大 | 回归复杂 | 通过 Adapter 分模块迁移，旧 UI 功能不删除 | 经典工作台核心能力下降 |

### 7.1 回滚分级

**L0 — 提交级回退（所有阶段）**：每个可运行改动形成独立 Git 提交；保留原文件的版本控制记录与可恢复样本；禁止把大批 UI、模型、文件格式同时合入一个无法拆分的提交。

**L1 — 功能开关回退（P1）**：建议设置 `MF_ENABLE_NEW_SHELLS`、`MF_ENABLE_GMV`、`MF_ENABLE_FRAGMENT_LIBRARY`、`MF_ENABLE_QC_WIZARD`；新系统出现 native 崩溃时，切回经典 `MolForgeWindow`，不迁移或更改用户工程数据。

**L2 — 数据回退（P0/P2）**：修改项目前先保存带校验 hash 的 `.mforge` 快照。利用已有原子级临时文件 + `os.replace()` 保存策略；文件格式不在 P0 改大版本，新增会话布局可先放 `QSettings` 或单独布局文件，避免破坏旧 schema。

**L3 — 依赖/打包回退（P2）**：保留已验证的 Python 解释器、依赖锁定文件、发布构建、GPU/驱动兼容矩阵；升级 Qt/VTK/RDKit 不得与核心几何改动混批。失败时恢复上一组验证过的二进制依赖。

### 7.2 分阶段发布闸门

- **P0 Gate**：科学正确性、命令撤销、启动脚本路径、原三栏回归均通过；
- **P1 Gate**：三个 Shell 完整、文档会话唯一、G:M:V 管理与 Windows native 基线通过；
- **P2 Gate**：干净 Windows 11 发布版、兼容迁移、性能/多窗口耐久、真实任务闭环通过。

任何 Gate 未达标，保持上一阶段默认入口，不把未稳定的新架构强制替换旧应用。

---

## 八、最小侵入式文件改造清单

**保留并尽可能保持 API 稳定：**

- `molforge/domain/document.py`、`topology.py`、`coordinate_store.py`；
- `molforge/application/command_bus.py`、`builtin_commands.py`、`history.py`；
- `molforge/ui/editor2d_widget.py`、`render3d_widget.py`；
- `molforge/rendering/vtk_backend.py`、`rendering/contracts.py`；
- `molforge/io/mforge_storage.py`、`io/rdkit_adapter.py`；
- 现有 xtb、Gaussian、Cube、构象解析与结果窗口。

**优先调整现有文件：**

| 文件 | 目标 |
|---|---|
| `molforge/application/selection.py` | 加有序选择契约 |
| `molforge/application/measurement.py` | 原子序列解析、无效测量清理 |
| `molforge/ui/panels.py` | 修复键角/二面角按钮接线 |
| `molforge/ui/views.py` | 对话框显示准确目标和失败信息 |
| `molforge/ui/window.py` | 消费 Session，后续逐步拆解单体窗口 |
| `molforge/ui/qc_result_dialog.py` | 保留结果功能，Gaussian Setup 独立 |
| `molforge/application/jobs.py` | 承载耗时计算 |
| `main.py`、`scripts/launch.py` | 共用 bootstrap，欢迎屏入口 |
| `run_molforge.bat`、`scripts/windows10_diagnostics.py` | 可移植启动与 Win11 契约 |
| `tests/golden/science/test_golden.py` | 取消关键测量 skip 并加入真实断言 |

**建议新增（实施时按阶段创建，不要求一次引入）：**

```text
molforge/application/document_session.py
molforge/application/workspace_registry.py
molforge/application/measurement_targets.py
molforge/application/internal_coordinates.py
molforge/application/fragment_catalog.py
molforge/application/fragment_commands.py
molforge/application/calculators/gaussian_job_spec.py

molforge/ui/welcome_window.py
molforge/ui/shells/base_shell.py
molforge/ui/shells/studio_2d.py
molforge/ui/shells/studio_3d.py
molforge/ui/shells/studio_split.py
molforge/ui/gmv_window_manager.py
molforge/ui/vtk_multiview_widget.py
molforge/ui/dialogs/element_fragments.py
molforge/ui/dialogs/gaussian_calculation_setup.py

tests/test_measurement_target_resolution.py
tests/test_internal_coordinate_commands.py
tests/test_fragment_transactions.py
tests/test_document_session_multi_view.py
tests/test_gaussian_job_spec.py
tests/test_win11_native_multiview.py
```

建议在大规模改动前引入简洁的类型契约、依赖注入与回归测试，避免让 `window.py`（当前约 2260 行）持续承担业务规则、计算调度、窗口管理和 GUI 交互的全部职责。

---

## 九、建议的首轮开发顺序

按风险与可验证收益排序：

1. **锁定基线和清理启动路径**：使项目在目标 Windows 11 设备上可重复启动；
2. **修有序选择 + 测量目标解析**：先让键角值可信；
3. **修精确键角/二面角事务命令**：完成可撤销的真实坐标修改；
4. **完成 C/O/N Element Fragments 右键面板和整组回滚**；
5. **抽出单文档唯一 DocumentSession**，先接入原三栏界面；
6. **实现 WelcomeWindow + 2D/Split/3D Shell**；
7. **实现正式 G:M:V 和 1/2/4 Viewport**；
8. **实现 Gaussian 11 页签配置、提交和任务管理**；
9. **完成 Windows 11 原生耐久测试与发布打包**。

**第一轮切勿同时进行**：VTK 渲染器重写、三套 UI 全部重做、文件格式大版本迁移、Qt/VTK 升级和几何核心替换。这样会大幅提高定位崩溃与回滚的难度。

---

## 十、验收交付物

P0 应交付：可回滚源码分支、测量/内坐标测试、新片段事务功能、原三栏兼容报告。  
P1 应交付：三套完整 Shell、共享 DocumentSession、G:M:V 窗口管理、1/2/4 视图、Gaussian Setup、GUI/Native 测试报告。  
P2 应交付：Windows 11 绿色版/安装版或可重现构建、依赖锁定、旧 `.mforge` 兼容报告、崩溃测试记录、使用说明及发布回滚指南。

**最终判定标准不是“菜单与按钮存在”，而是每条研究操作能正确完成“选择 → 编辑 → 可视化 → 撤销 → 保存 → 再打开 → 科学结果可信”的完整闭环。**

---

## 附录：证据与边界说明

源码定位（均为所上传 v6.1 压缩包中的相对路径）：

- `molforge/application/measurement.py`：`angle` 约 L48；`Measurement` 冻结声明约 L23；失效清理约 L193。
- `molforge/application/selection.py`：`selected_atoms` set 与选择维护约 L32–L114。
- `molforge/ui/window.py`：窗口构造与 CommandBus 约 L372–L397；G:M:V 克隆约 L1159–L1190；精确角度更新约 L1417–L1440；测量显示约 L1956–L1982。
- `molforge/ui/views.py`：`BuilderFragmentDialog` 约 L553；`ModifyInternalCoordDialog` 约 L657；二面角操作转发约 L750。
- `molforge/ui/panels.py`：两按钮约 L609–L633；`_window_ref` 依赖约 L647–L657。
- `molforge/ui/qc_result_dialog.py`：现有三个顶层量化页签约 L200；`Gaussian` 输入页实现约 L225。
- `scripts/windows10_diagnostics.py`：拒绝 Win11 构建号；`tests/test_windows10_contract.py` 对该行为进行断言。
- `run_molforge.bat`：当前固定个人 Python 路径，导致本次测试失败。

**未验证项目**：Windows 11 原生 GUI 启动、VTK 9.7.1 与 PyVistaQt 实际多窗口行为、GPU 驱动性能、0xC0000409 的真正原生崩溃栈、Gaussian 16/xtb 可执行程序的本机运行。这些项目在本报告中均按待验收处理，而非视作已通过。

**外部参考**（仅用于平台支持判断，不替代源码审查）：Qt for Python 6.11 Windows 支持文档；PyPI VTK 9.7.1 发布文件页面。
