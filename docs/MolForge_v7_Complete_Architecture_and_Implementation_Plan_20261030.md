# MolForge v7.0 完整架构规划、Results 后处理体系与前端集成实施方案

> **审查基线**：`MolForge_v7_0_Complete_Plan_20261030.zip`（其中 v6.2 源码）＋ `PROMPT_v7_complete.md` ＋压缩包内 `docs/ISSUES_AND_TODO.md`  
> **规划日期**：2026-10-30　　**文档版次**：1.0　　**交付性质**：架构与验收方案，非代码修改或成品 v7.0  
> **目标环境**：Python 3.13 / PyQt6 6.11.0 / VTK 9.7.1 / Windows 11 x64  
> **目标产品**：独立 2D 系统、独立 G:M:V 3D 系统、2D–3D 分屏系统，以及可扩展的 Results 科学后处理平台

## 0. 核心结论与决策

**总体技术路线：以现有 v6.2 的 `MoleculeDocument + DocumentSession + CommandBus + WorkspaceRegistry` 为核心，实行“保留可运行的经典工作台、实现真实 Qt Shell、将科学分析改为可溯源任务与结果、逐模块接入外部计算引擎”的增量升级。**

当前阻塞 v7.0 的关键不是缺少类文件或菜单，而是五个断层：

1. **启动断层**：`main.py` 和 `scripts/launch.py` 仍直接创建 `MolForgeWindow`。`welcome_window.py` 中有 `ShellFactory` 却没有真正的 `WelcomeWindow(QWidget/QDialog/QMainWindow)`。
2. **UI 断层**：`Studio2DShell` / `Studio3DShell` / `StudioSplitShell` 均是普通 Python 对象，含标签、会话与逻辑方法，尚未绑定实际菜单、画布、交互、窗口生命周期。因此对外描述时应称“后端逻辑外壳 / Headless Shell”，不能称“完成三套独立 GUI”。
3. **视图断层**：`VtkMultiviewController` 已计算 1/2/4 viewport 矩形及命中 pane，未在真实 `vtkRenderWindow` 上创建 `vtkRenderer`、建立相机/Pick/交互状态。100 次 Shell 创建测试仅测试 Python 状态对象；**不是 VTK 原生多窗口稳定性测试**。
4. **结果断层**：已有 Results 顶级菜单、量化日志窗口、Cube 轨道与轨迹播放器，然而 `Results` 行为散在 `window.py`：一些操作复用通用表格/日志窗口，一些跳到示意图，没有独立的输入要求、计算状态、可重复的解析器、Results provenance 和独立对话框体系。
5. **外部引擎断层**：Gaussian/xtb 具备部分基础与适配器；Multiwfn 3.8(dev)、GROMACS 批处理、VMD 可选渲染还没有统一的发现、版本锁定、受控执行、输出解析、异常和取消协议。

**决定采用两层 Shell 结构**：保留现有 `Studio*Shell` 作为无 GUI、可测试的后端逻辑控制器；额外创建 `Studio*Window(QMainWindow)` 做真实前端，使用**组合而非直接把当前后端类改继承 `QMainWindow`**。这样可以最小化现有 27 项测试的破坏，并复用 `WorkspaceRegistry` 及现成 2D/3D Widget。既能满足“实际完整 Qt 主窗口”的产品要求，又兼顾渐进回滚。

**决定建立统一 Results Registry + 科学输入能力检测 + 结果来源模型**，使所有指定 Results 子菜单都能打开独立功能对话框。未实现或缺少必需数据的分析不得产生模拟数值；只能显示依赖诊断、输入缺失及禁用状态。功能是否“完成”以**真实计算、可靠解析、可复现输出**为准。

---

## 1. 审查方法与证据边界

### 1.1 已审查资源

| 材料 | 内容 | 处理方式 |
|---|---|---|
| `MolForge_v7_0_Complete_Plan_20261030.zip` | 251 个归档条目、148 个 Python 源码文件，包括主入口、UI、application、domain、rendering、io 与 tests | 静态检查、抽查关键路径、运行受限测试 |
| `PROMPT_v7_complete.md` | v7.0 五项交付、完整 Results、专业软件调研、现代趋势 | 作为范围与功能基准 |
| `docs/ISSUES_AND_TODO.md` | v6.2 未集成 UI、Multiwfn 缺失、Gaussian 现状和待验收事项 | 作为既有问题清单，逐条与源码对照 |
| `docs/ARCHITECTURE_P0_P2_PLAN_20261030.md` | 前一版 P0–P2 架构规划 | 保留合理数据边界，修正与最新源码不符部分 |
| 专业软件官方资料 | Gaussian、ChemDraw、VMD、GROMACS、Avogadro、Molden、Multiwfn、RDKit、PLUMED、AMBER、Qt 与 VTK 等 | 外部功能对标和方法边界，不把它们写成 MolForge 已实现 |

### 1.2 实际测试

在隔离的 Linux 分析环境中，选取与 v6.2 后端有关的测试运行：

```text
python -m pytest -q \
  tests/test_document_session_multi_view.py \
  tests/test_fragment_transactions.py \
  tests/test_gaussian_job_spec.py \
  tests/test_internal_coordinate_commands.py \
  tests/test_measurement_target_resolution.py \
  tests/test_windows10_contract.py \
  tests/golden/science/test_golden.py

结果：27 passed, 1 failed
```

失败测试是 `test_launcher_no_personal_hardcoded_python_path`，因 `run_molforge.bat` 仍写入开发机的绝对 Python 路径。**这只是一组指定测试的结果，不能推断全部测试通过。**

分析环境装有 VTK 9.6.2 而不是目标 9.7.1，且未安装 PyQt6，故未在此环境启动真实 GUI、没有进行 Windows 11 的 GPU 和 native 多窗口实测。不存在对 `0xC0000409` 崩溃根因的可靠定位；建议将原生 dump 视为前置证据。

### 1.3 具体源码状态表

| 项目 | 发现 | 建议 |
|---|---|---|
| `main.py`、`scripts/launch.py` | 直接 `MolForgeWindow()` | 共用 bootstrap，改为先开欢迎页 |
| `ui/welcome_window.py` | 只有 `ShellFactory`，`legacy` 还映射到 `StudioSplitShell` 后端 | 增加真实 `WelcomeWindow`；Legacy 走真实经典主窗口 |
| `ui/shells/base_shell.py` | 纯 Python Session controller | 保留作为 Model/Controller；新 `QMainWindow` 消费它 |
| `ui/shells/studio_2d.py`、`studio_split.py` | 只有菜单名称与类型标签 | 在独立 Qt Window 中补完整工具栏、编辑器、文件工作流 |
| `ui/shells/studio_3d.py` | G:M:V 和 pane count 控制存在 | 补 Qt 菜单、3D Widget、多 viewport、输入与状态栏 |
| `ui/vtk_multiview_widget.py` | **仅矩形和点击区域计算** | 新增真实 VTK renderer 与 camera/picker 管理 |
| `application/document_session.py` | 一个文档独立 Bus/Selection/Measurement，命令变更有事件 | 把 UI 的所有修改接到 `session.execute/undo/redo`；处理旧监听解绑 |
| `application/workspace_registry.py` | Document / Group / View 注册与关闭计数已有 | 继续用单调编号；增加窗口 owner 和生命周期一致性校验 |
| `ui/gmv_window_manager.py` | 有注册逻辑；每次创建实例持有自己的窗口字典 | 将顶层 Qt 窗口管理集中到 application/controller 级 |
| `ui/dialogs/element_fragments.py`、`application/fragment_commands.py` | 已有片段对话框及事务命令 | 将新 Shell 实际接入，保留经典路径并统一事务语义 |
| `ui/dialogs/gaussian_calculation_setup.py` | 11 页签＋6 按钮；Submit/Quick Launch 设置标记并 `accept()` | 把返回的 job action 交由统一任务执行器，确认日志、取消和结果回填 |
| `application/calculators/gaussian_engine.py` | 有 `probe/prepare/parse`；输出解析主要是 SCF 能量与结束状态 | 补活跃执行、优化轨迹/频率/激发态/轨道等解析，保存版本与来源 |
| `ui/window.py` 的 Calculate 菜单 | “Gaussian 计算输入配置”仍接 `_open_qc_log` | 正式启动新 GaussianCalculationSetupDialog，勿只打开旧综合页 |
| `ui/window.py` 的 Results 菜单 | Summary/Charge/IR/NMR/UV-Vis/Scan/Trajectory 等入口存在 | 每项替换或接入独立 Results 对话框＋科学输入能力检查 |
| `io/mdanalysis_adapter.py` | 有轨迹缓存、异步预取；主读取与后台线程使用同一个 `MDAnalysis.Universe` | 修复并发读取风险，采用独立 Reader 或串行 I/O Worker |
| `ui/trajectory_window.py` | 有真实轨迹播放器与 VTK 点云 | 作为 P0 可复用的 MD 基础，逐步添加 PBC、同步高亮与真正分析 |
| `requirements.txt` | 开发范围声明过宽且未覆盖完整运行依赖；`rdkit>=2026.9` 与目标固定版本需要校验 | 加锁和分层依赖，区分 core / gui / qc / md / optional |
| `run_molforge.bat` | 写死开发机 Python 绝对路径 | 清理；由项目 `.venv` / 环境变量 / `py -3.13` 启动 |
| `scripts/windows11_diagnostics.py` | Win11 版本号纯逻辑检测存在 | 继续增加依赖、VTK/GL、显卡、外部工具、临时目录权限检查 |
| `tests/test_win11_native_multiview.py` | 100 次创建的是不含 Qt/VTK 原生对象的 Shell | 新增真正 `QApplication + QtInteractor` 压力测试，不能把此测试当原生验收 |

### 1.4 两个应立即纠正的“完成度误判”

**“有 `Studio3DShell` 类”不等于“已完成 GaussView 式 3D UI”**：在源码中没有真实窗口菜单、画布、底部 Build/Select 放置模式和 1/2/4 原生 VTK 视图的整套联动。

**“有菜单”不等于“功能可用”**：例如旧 Results→IR 调用 `_show_spectrum_summary`；OSC 能级图跳往量化综合日志；Scan 入口打开 `DihedralChartDialog`，而该类并不能作为通用真实计算扫描的证据。因此新系统必须区分 `Ready`、`Missing Data`、`Missing Engine`、`Experimental`、`Not Implemented` 五个状态。

---

## 2. 专业产品对标与设计取舍

> **对标是功能域与用户工作流的对照，不是宣称复刻其他软件每一个菜单字样。** 各产品会随版本、许可证和模块变化。下表列的是与 MolForge 直接相关、可从公开官方资料验证的主要能力领域。

| 产品 | 核心能力/对标维度 | MolForge 应借鉴 | 主要资料 |
|---|---|---|---|
| **GaussView 6** | 分子构建、多个分子/视图、Gaussian 作业配置、优化/轨道/振动/表面与路径结果 | 小型多窗口、独立设置对话框、计算结果和结构严格绑定 | [S01] |
| **ChemDraw / Chem3D** | 化学结构和反应绘制、模板、清理、结构属性、名称转换、NMR 预测；3D 建模和几何处理 | 将 2D 当成完整专业编辑系统，而不是附属预览 | [S02] |
| **VMD** | 多种结构/轨迹可视表示、选择、RMSD、氢键、接触图、GofR、VolMap、Timeline、QwikMD 等插件 | 轨迹与空间分析、二维图表和三维高亮联动 | [S03] |
| **Avogadro 2** | 多平台编辑、现代渲染、插件、输入生成、优化、轨道表面、Z-matrix | 容易扩展的输入生成器、插件、内坐标编辑和稳定渲染 | [S04] |
| **Molden** | MO、电子密度/差分密度、ESP、振动、反应路径和 Z-matrix | 简洁独立的电子结构结果对话框 | [S05] |
| **Multiwfn 3.8(dev)** | 波函数、电荷与键级、ESP 定量、拓扑、空间函数/激发态/相互作用分析 | 高度模块化的批处理适配＋严格输出解析 | [S06] |
| **GROMACS** | MD 模拟与 RMSD/RMSF/RDF/氢键/能量/WHAM 等命令行分析 | 真实分析能力，不把图像渲染冒充计算 | [S07] |
| **AMBER/CPPTRAJ** | 跨 MD 工具轨迹处理、结构分析、并行分析、数据集计算 | 接受非 GROMACS 轨迹与可替换分析后端 | [S08] |
| **NAMD/Colvars、PLUMED** | 增强采样、CV、umbrella、metadynamics、PMF | 将自由能分析放到后期高级模块并记录偏置和重加权协议 | [S09] |
| **RDKit** | 2D/3D 结构、MolLogP、TPSA、HBD/HBA、MW、Ro5 及大量分子描述符 | 本地可立即交付的真实计算、与 pKa/ADMET 黑盒预测分离 | [S10] |

对标后的**产品定位**：MolForge 不是把 Gaussian、Multiwfn、GROMACS、VMD 全部重新实现一遍，而是统一它们的结构、作业、数据、分析和可视化 UX。**默认能本地计算的部分使用 RDKit/NumPy/MDAnalysis；专业波函数/MD 数值由已验证引擎输出；渲染优先 VTK，VMD 作为可选交互/高质量导出后端。**

### 2.1 特别注意的事实边界

- Multiwfn 官方公开下载页使用 **3.8(dev)** 的称谓，开发版有具体更新日期；**不应仅凭一个固定的“3.8”字符串假定 CLI 菜单序号和解析输出恒定**。每个构建记录启动横幅/版本信息、可执行文件 hash、已验证脚本模板版本。[S06]
- GaussView 6 文档可作为功能对标，但 MolForge 自己的菜单命名应以用户要求的九大组为正式规范，而非与旧 `MolForgeWindow` 的十组结构菜单简单等号。
- Qt for Python 6.11 官方支持 Win11 x86_64；VTK 9.7.1 发布文件提供 CPython 3.13 Win x64 的 wheel，但**平台支持和安装包存在不能证明所有 GPU/驱动/QtInteractor 组合稳定**。[S11][S12]
- `pKa` 属于模型依赖预测；没有经验证、明确版本和适用域的模型时只能禁用或交给用户已安装的外部预测器，不能将 logP 和 pKa 混为一谈。
- NPA 通常依赖 NBO/NPA 相关分析结果；EDA 需要明确 SAPT/ALMO 等方法及其可用输出；**不能承诺任意 Gaussian `.fchk` 都天然能产生这些分析结果**。
- OSC HOMO/LUMO 能级和实验电化学值不是自动等价物：图表需列出理论方法/基组/溶剂、真空参照或实验标尺、电子伏特换算及差异警告。

---

## 3. v7.0 目标架构

### 3.1 进程与 UI 层

```text
main.py / scripts/launch.py
            │
            └─ ApplicationBootstrap
                ├─ AppController (QObject; keep explicit window references)
                ├─ EnvironmentProbe (dependency + engine + GPU)
                ├─ WorkspaceRegistry (existing singleton initially)
                ├─ AnalysisRegistry (new)
                └─ WelcomeWindow (real QWidget/QMainWindow)
                    ├─ [2D 设计] → Studio2DWindow(QMainWindow)
                    ├─ [3D 设计] → Studio3DWindow(QMainWindow)
                    ├─ [2D–3D]   → StudioSplitWindow(QMainWindow)
                    └─ [打开经典工作台] → MolForgeWindow (preserve)
```

建议把 `ShellFactory` 定位为**后端会话/控制器工厂**；另引入 `ShellWindowFactory`：接收逻辑 `Studio*Shell`、创建对应 Qt Window。这样无需打破现有 `test_document_session_multi_view.py` 对无 GUI Shell 的测试契约。

### 3.2 数据层及科学后处理层

```text
WorkspaceRegistry
  ├── GroupSession G
  ├── DocumentSession M
  │   ├── MoleculeDocument                 化学事实源
  │   ├── CommandBus + UndoHistory         单文档唯一编辑/撤销
  │   ├── SelectionService + Measurement   跨视图选区
  │   ├── document_revision + events       失效检测
  │   └── JobCenter                        后台作业
  └── ViewSession V
      ├── pane P1..P4 / camera / render_style
      └── active_view / own native VTK widget

AnalysisRegistry
  ├── AnalysisDefinition [id,title,category,inputs,capabilities,dialog_class]
  ├── CapabilityResolver [Available | MissingData | MissingEngine | Experimental]
  ├── AnalysisExecutionService [native | external cli | parsed result]
  ├── AnalysisResultStore [Provenance + artifacts + hashes]
  ├── AnalysisDialogFactory [one module → one independent QDialog]
  ├── EngineRegistry [Gaussian / Multiwfn / xtb / GROMACS / VMD / ...]
  └── ScientificRenderService [chart + VTK + export]
```

### 3.3 一份 DocumentSession、多个视图

`G1:M1:V1` 和 `G1:M1:V2` 应共享同一文档、命令历史和可选同步选区，而相机、窗口尺寸、viewport 和渲染设置独立。`G1:M2:V1` 是第二个分子、第二份 DocumentSession。一个 View 内 1/2/4 **pane** 使用 `P1…P4`，不算新的 V。

**所有编辑和可回写的优化结果经过 Session 的命令接口**。Results 默认只读；若用户明确确认“将优化后的坐标覆盖文档”，必须形成一条可撤销的命令，并做 revision/hash 检查。

### 3.4 独立系统的完成定义

**Studio2DWindow**：拥有自己的文件/编辑/绘图/结构/模板/视图/工具/窗口/帮助菜单；可独立新建、绘制、编辑键级、使用片段/环、2D 清理、保存/导出、撤销重做、修改属性。复用 `Editor2DWidget`，不依赖后台藏一个旧三栏窗口。

**Studio3DWindow**：正式九组菜单 `File / Edit / Tools / Builder / View / Calculate / Results / Windows / Help`；中央 VTK 画布；底部 `Build / Select Placement`；状态栏原子数、电子数、电荷、自旋；G:M:V 顶层窗口管理；1/2/4 pane；所有高级功能独立 QDialog。复用 `Render3DWidget`、CommandBus、外部计算入口。

**StudioSplitWindow**：真实左右 `QSplitter`，共享一个 DocumentSession 的 2D 与 3D；同步高亮、编辑事件、Undo、坐标/结构失效通知；布局和显示可独立配置。右侧属性检查器可停靠，但不是所有功能的唯一入口。

**Legacy MolForgeWindow**：保留现有三栏并作为回退入口；新 GUI 未通过验收前不删除原主窗口的任何工具、快捷键、菜单与渲染后端。

---

## 4. 前端 UI 真正集成的落地方案（优先级 P0）

### 4.1 建议的新增/调整目录

```text
molforge/
  ui/
    welcome_window.py              # 增加真正的 WelcomeWindow(QMainWindow)
    shells/                       # 保留现有纯 Python Studio*Shell
    shell_windows/
      __init__.py
      base_window.py               # QMainWindow composition + common session wiring
      studio_2d_window.py
      studio_3d_window.py
      studio_split_window.py
      window_factory.py
    results/
      dialogs/
      widgets/                     # charts, result tables, provenance, 3D preview
      menu_builder.py
  application/
    results/
      definitions.py               # registry / capabilities
      models.py                    # AnalysisInput / AnalysisResult / Artifact
      execution.py                 # job / validation / parse
      provenance.py
      repository.py
      modules/
    engines/
      tool_registry.py
      multiwfn_adapter.py
      gromacs_adapter.py
      vmd_export_adapter.py
  rendering/
    vtk_multiview_backend.py       # 真正 vtkRenderer viewport 管理
  bootstrap.py                     # main/launch 共用
  tests/
    native/                        # 在 Windows Qt GPU 环境中跑
```

后续可将 `ui/window.py` 中的菜单逐步重构为 `ActionRegistry` 驱动，避免在一个大类里复制三套菜单。**P0 不需要重写现有 `MolForgeWindow`**。

### 4.2 入口与生命周期的正确调用流程

1. `main.py` 和 `scripts/launch.py` 调用同一个 `bootstrap.run_application()`；保留 `launch.py` 的错误日志入口但取消第二套窗口创建逻辑。
2. 构造 `QApplication`、设置 style/applicationName/version、初始化统一 `AppController`。
3. `AppController` 持有 `WelcomeWindow`，展示三个入口。欢迎页**不得提前创建 VTK**。
4. 用户点击 `2D` / `3D` / `split` → 控制器创建或接入 `DocumentSession` → 调用 `ShellFactory` 创建逻辑 Shell → `ShellWindowFactory` 创建 `QMainWindow`。
5. **先 `show()` 新窗口并保留强引用，再 hide 欢迎页**，防止窗口被 GC 或最后窗口关闭导致应用提前退出。
6. Qt Window 的 `closeEvent` 只调用一次 `shell.close_shell`，断开 Session/Selection 的 GUI 回调，停 `QTimer`、注销 VTK observers、等待受管后台任务按策略处理后释放 `QtInteractor`。
7. 用户关闭一个 V，不应销毁仍被另一个 V 使用的 DocumentSession；关闭最后一个研究窗口后可回欢迎页或退出，行为由设置明确决定。
8. 新 Shell 异常时提供 **Open Legacy Workbench** 回退，而不是全局捕获错误后继续渲染空白工作区。
9. 新建/打开 `.mforge` 文件在 `AppController` 统一处理，明确文件属于哪个 G/M，禁止把一个分子意外覆盖到其他 View。

最小接口草案（设计示意，**非已经存在的可执行实现**）：

```python
class ShellWindowFactory:
    def create(self, shell_kind: str, controller, document=None):
        shell = ShellFactory.create_shell(shell_kind, document=document)
        window_type = {
            "2d": Studio2DWindow,
            "3d": Studio3DWindow,
            "split": StudioSplitWindow,
        }[shell_kind]
        return window_type(shell=shell, app_controller=controller)

class AppController(QObject):
    def open_studio(self, kind: str):
        window = self.window_factory.create(kind, self)
        self._windows.append(window)  # 避免过早 GC
        window.show()
        self.welcome.hide()
```

### 4.3 双系统互相同步的最小契约

| 操作 | 共享数据行为 | 视图行为 |
|---|---|---|
| 增加/删除原子键 | `session.execute(command)` 产生 revision/event | 所有相关画布增量刷新 |
| 改变 3D 坐标/内坐标 | 单次可撤销坐标命令 | 所有 3D View 更新、相关 Results 标记为过期 |
| 2D 改画布布局（纯美学） | 修改 2D 坐标但不改变 3D 计算的 hash | 2D 视图刷新；仅相关 2D 缓存失效 |
| V1 旋转镜头 | 不改 Document | 仅 V1 或明确同步相机组更新 |
| 选择一组原子 | 有序选择＋origin，避免回声 | 2D/3D 高亮同步 |
| Undo/Redo | 唯一文档历史栈 | 全部关联视图刷新 |
| 一个外部计算结束 | 保存只读 AnalysisResult | 结果可打开；revision 不匹配则显示 stale |

---

## 5. Results 菜单：完整信息架构与交互规范

### 5.1 目标菜单树

```text
Results
├─ Summary & Jobs
│  ├─ Calculation Summary...
│  ├─ Optimization History...
│  ├─ Atom & Bond Properties...
│  ├─ Scan & Potential Energy...
│  ├─ IRC / Reaction Path...
│  └─ Surface / Contour Manager...
├─ Wavefunction Analysis (Multiwfn)
│  ├─ ESP Surface & Descriptors...
│  ├─ HOMO/LUMO Energy & Orbital Diagram...
│  ├─ OSC Donor/Acceptor Levels...
│  ├─ ELF / LOL...
│  ├─ Mayer & Wiberg Bond Orders...
│  ├─ Hirshfeld / ADCH / NPA Charges...
│  ├─ Electron-Hole / NTO...
│  ├─ IRI / NCI-RDG / AIM-QTAIM...
│  └─ Electron Density / Laplacian / Difference / DOS / Spin...
├─ Molecular Properties
│  ├─ Planarity / Torsions...
│  ├─ Dipole Moment...
│  ├─ Surface Area & Volume...
│  ├─ logP / pKa...
│  ├─ Molecular Descriptors...
│  └─ Shape & Conformer Properties...
├─ Intermolecular Interactions
│  ├─ Energy Decomposition (EDA)...
│  ├─ Hydrogen Bonds...
│  ├─ π-π Stacking...
│  ├─ vdW Contacts / Salt Bridges...
│  └─ Protein-Ligand Interaction Fingerprints...
├─ Spectroscopy
│  ├─ IR / Raman...
│  ├─ UV-Vis / Excited States...
│  ├─ NMR...
│  ├─ CD / ECD / ORD...
│  ├─ Vibronic Spectrum...
│  └─ Vibration Mode Viewer...
├─ Molecular Dynamics (GROMACS / MDAnalysis)
│  ├─ MD Setup & Run...
│  ├─ Trajectory Player...
│  ├─ RMSD / RMSF / Radius of Gyration...
│  ├─ H-Bonds / RDF / Dihedrals / Energies...
│  ├─ Clustering / PCA / Free Energy Landscape...
│  ├─ MSD / Contact Network / Secondary Structure...
│  └─ Umbrella WHAM / Metadynamics / FEP-BAR-MBAR / MM-PBSA...
├─ OSC / Organic Photovoltaics
│  ├─ D/A Energy Alignment...
│  ├─ Exciton / CT / NTO...
│  ├─ Hole/Electron Reorganization Energy...
│  ├─ Absorption Comparison...
│  └─ Electronic Coupling...
├─ Drug Discovery
│  ├─ Drug-likeness / PAINS...
│  ├─ Protonation & Tautomers...
│  ├─ Protein-Ligand Contacts...
│  ├─ ADMET & Applicability...
│  └─ Docking Pose Review...
└─ Result Management
   ├─ Browse Results / Filter / Compare...
   ├─ Publication Export...
   ├─ Batch Analysis...
   └─ Analysis Tool & Dependency Status...
```

**每个具体 Analysis ID 有一个独立 `QDialog` 类或专属 Dialog 实例**。可以共享 `BaseAnalysisDialog` 的布局、文件选择器、运行按钮、进度、错误、图表与导出容器，但不应该把所有功能挤在一个万能主对话框里。

同一能力在菜单中可以出现于两个学科分组（例如 ESP、H-Bond），但**实际只注册一个 Analysis ID**；别让不同入口计算出不同含义的数值。

### 5.2 统一 AnalysisDialog 标准界面

建议单个对话框从上到下：

- **标题及状态**：方法、引擎、来源文件、当前/过期状态；缺引擎时提供“设置工具路径…”。
- **输入选择**：文档、构象、原子选区、波函数/日志/轨迹及必要的源文件，自动检查文件与当前文档是否同一套坐标。
- **参数**：科学阈值、单位、网格步长、BWR 上下界、展宽函数、PBC/对齐、轨迹帧范围等，保存有版本的预设。
- **运行**：`Run` / `Cancel` / `Preview Input` / `View Log`；大计算在 JobCenter 后台运行。
- **结果**：表格、曲线/等值面、数值及可折叠的方法元数据、异常与警告。
- **导出**：CSV、JSON、SVG、PNG、体数据 Cube、可选 VMD Tcl、带 provenance 的 Markdown/HTML 方法报告。
- **上下文联动**：结果表点击某原子或轨道，可定位当前 G:M:V 的选区，不修改分子拓扑。

结果状态颜色/图标必须有文字辅助说明，不允许用“绿色已完成”的单一装饰暗示科学正确性。

### 5.3 必要输入与引擎能力检查

任何选项都应先运行 `CapabilityResolver`：

```text
Ready            → 拥有所需输入、引擎版本可用、原子索引可映射
Missing Data     → 缺 fchk、缺跃迁密度、缺轨迹拓扑、缺能量等
Missing Engine   → 未安装 Multiwfn/GROMACS/Gaussian 或不可执行
Experimental     → 输出解析适配此构建尚未验证
Not Implemented  → 保留入口、查看功能说明和预期输入，不生成任何值
```

**输入能力示例**：ESP 分析常需 `.fchk/.wfn/.wfx`；电子-空穴需有足够的激发态/跃迁密度信息；IR 需频率及强度；Raman 需拉曼活性；RMSD 必须有拓扑＋轨迹＋对齐策略；EDA 必须有可识别方法的分解结果；pKa 必须有可核验预测模型。不能因为“文件能打开”就认为后处理所需物理量已具备。

### 5.4 Results 清单与分期策略

本次将用户指定能力扩展为 **79 个唯一分析/工作流模块**；详见同目录 `MolForge_v7_Results_Feature_Matrix_20261030.csv`。本报告末尾附全部条目及独立对话框类。模块清单是**开发目标**，而非代码已经实现的声明。

- **P0（6 个）**：建立真实数据贯通的 Summary、Atom/Bond、Surfaces、Descriptor、Trajectory、Analysis Registry。
- **P1（39 个）**：ESP、HOMO/LUMO、ELF/LOL、常用电荷/键级、基础相互作用、IR/Raman/UV-Vis、8 项 MD 分析、OSC 基础比较等。
- **P2（34 个）**：EDA、QTAIM、NPA、密度差、NMR/ECD/ORD、pKa/ADMET、复杂 OSC、MM/PBSA、FEP、WHAM、metadynamics 和批量/AI/导出扩展。

此计数是功能矩阵中的主开发阶段，不包含每个功能所有潜在算法变体。**不把“P0 菜单已列出”作为“P1/P2 分析已实现”。**

---

## 6. 关键科学工作流设计

### 6.1 Multiwfn — ESP 表面和 OSC 描述符

推荐流程：

```text
输入选择（Gaussian log+fchk / wfn / wfx）
 → 校验坐标、波函数/原子映射、单位、引擎版本
 → 建立独立 jobdir（copy/symlink 输入、固定脚本模板）
 → EngineRunner 启动 Multiwfn（shell=False，受控 stdin，超时与取消）
 → 输出 density/ESP cube、表面网格和结构化分析文本
 → 解析器验证 header、坐标轴、原子数、正负符号、数值有限性
 → Results: σ²+、σ²−、ν、Π、MPI 等严格按指定源程序定义解释
 → vtkVolume / vtkContour / VTK 颜色查找表映射 BWR
 → 显示可配置色条与 ESP 最大/最小点
 → 导出带图例、色标、单位、原始输出引用的图片+表格
```

`docs/ISSUES_AND_TODO.md` 描述的本机既有流程（`Multiwfn.exe xxx.fchk -ESPrhoiso 0.001` 与脚本重定向）可作为**外部复现样例**，但程序内不要硬编码用户电脑的 `D:\Multiwfn\...` 路径；应把它转换为可配置、已探测版本的 recipe。需要**用一份真实、合法、获授权的固定 `.fchk` 样本**在目标版本下测试具体 CLI 参数和结果格式；不是先假设所有构建都有同一选项。

**BWR 渲染**：明确默认色标的负值/正值映射并在图中显示刻度、单位与极值。可按用户原工作流采用蓝→白→红，同时允许反向及截断区间；不应在没有标注的情况下用固定色彩表解释原子电荷。

**科学数值风险**：`σ²±`、`ν`、`Π`、MPI 指标的单位、积分定义、符号约定必须根据实际 Multiwfn 结果文档及 fixture 核对，不能仅凭名字推断。没有 Multiwfn 运行证据时绝不生成示例数值冒充计算结果。

### 6.2 HOMO/LUMO — 轨道等值面 + 能级图

```text
原始 Gaussian/ORCA 结果
 → parser 读取 MO 能量（α/β、能量单位、占据数、轨道索引）
 → Multiwfn 或现有 Cube 路径生成轨道体数据
 → vtkDualPhaseIsosurface 渲染正/负相位（颜色可配置）
 → EnergyDiagramCanvas 绘制能级骨架（能量轴统一为 eV）
 → 同一 Dialog 显示表格＋轨道缩略视图＋一键出版导出
```

**关键警告**：如果是开壳层体系，需分别展示 α/β；如果基组/方法或溶剂不一致，HOMO/LUMO 能隙跨分子比较要明确标注不可直接等价。Gaussian 可用 chk→fchk 工具时记录 `formchk` 版本；不存在时提供文件导入而不是假造 cube。

### 6.3 OSC 能级/激发态综合平台

优先面向用户提示词里的有机太阳能电池研究问题，提供：

1. **给体/受体对比**：HOMO/LUMO、相对偏移，能量基准与计算条件一致性检查；
2. **吸收和激发态**：TD-DFT 吸收谱、振子强度、跃迁贡献及可观测 NTO；
3. **电子/空穴空间分析**：电子空穴重叠、CT 特征和可视化；需要真实激发态数据；
4. **重组能**：中性/正离子/负离子在各自与对方几何的能量四点法，逐项跟踪作业 ID/方法；
5. **二聚体与材料界面**：π–π 堆积、分子间距离、电子耦合和局部极化；专业引擎可选；
6. **批量材料比较**：不同分子组 G:M 叠加比较、导出统一格式结果。

额外增加 **方法一致性规则**：同一组 OSC 对比必须记录 `functional/basis/solvent/charge/multiplicity`、输出文件 hash、真空参考设置和能量单位。跨实验/计算的能级只能标注来源并做有条件比较。

### 6.4 Gaussian — 从 UI 配置走到真实结果

`GaussianCalculationSetupDialog` 已有 11 页签与 6 个按钮，但它把 Submit/Quick Launch 表达为返回动作标记。建议新增 `GaussianJobController`，由 Window/Dialog 将结果提交到统一 JobCenter：

```text
GaussianSetupDialog
 → spec.validate(document)（电荷/自旋/有限坐标/空结构/方法约束）
 → generate_gjf + input_hash
 → EngineRegistry.resolve("gaussian")
 → JobCenter.submit(JobSpec with document_id and revision)
 → GaussianEngine.prepare() + external process launch
 → live progress/log + cancel/kill + normal/error termination
 → cclib / Gaussian adapter parse coordinates/energies/frequencies/TD
 → AnalysisResultStore.save()（只读、溯源、可重试）
 → 若选择 Apply Geometry → 可撤销的 CommandBus 写回 + stale 检查
```

Gaussian 输入预览的**高级原始 Edit 模式**需明确文本覆盖优先级，防止当前 UI 配置覆盖用户编辑的原始输入；首次集成应配测试保证 `Preview = Submitted input bytes`。避免在主线程直接执行 `g16.exe` 或未经确认覆写现有 `chk`。

### 6.5 GROMACS — MD 模拟、轨迹、常规分析

建议把 GROMACS 定位为**可选外部模拟/分析引擎**，MDAnalysis 定位为跨格式的读取与本地分析后端。P1 提供常用 `RMSD、RMSF、Rg、H-Bond、RDF、Dihedral、Energy、Trajectory`，P2 扩充 PCA、聚类、接触、SASA、MSD、PMF 与自由能。

#### 6.5.1 MD setup 向导

拓扑修复 → 力场/水模型/离子/盒参数 → PBC 检查 → 最小化 → NVT/NPT → 生产模拟 → 标准输出归档。每一步显示输入文件、命令、力场来源、可重复运行脚本。**MolForge 不是力场参数自动可靠生成器**：非标准残基、配体未知参数或拓扑有缺失时必须中止并要求用户指定受支持的参数化工作流。

#### 6.5.2 数据与统计约束

- 读取 `.tpr/.gro/.pdb + .xtc/.trr/.dcd/.nc` 时保存 topology/atom order mapping；读取前检查原子数量与关联文件；
- RMSD 必须标记参考结构、对齐/拟合组和观察组；RMSF 必须记录平均对齐策略；
- RDF、MSD、扩散系数和距离依赖数据需要确认 PBC、盒向量、image/unwrapped 处理；
- 氢键要提供 donor/acceptor 定义、距离角度阈值、使用的氢存在性和选区更新策略；
- 聚类必须显示选用特征、距离度量、阈值、帧抽样；自由能 PMF 显示温度、CV、重加权/统计误差；
- 轨迹播放器应支持大型文件抽样、chunk/cache 与异步 I/O；`MDAnalysis.Universe` 不应由主线程和预取线程**同时修改同一个读取游标**。当前 `_prefetch_worker` 在锁外调用共享 Universe 的 `_load_chunk`，需要修复；
- 多帧选择需保证 VTK 原生视图仅在 GUI 线程渲染，后台线程不访问 QWidget / vtkRenderer；
- 若没有能量 `.edr` 或结构化输出，则“能量分析”只显示缺数据，不根据坐标猜测势能。

#### 6.5.3 自由能（P2）

- **WHAM / umbrella**：读窗口中心、弹簧常数、CV 时间序列；显示窗口 overlap、收敛、PMF 与 bootstrap 区间；
- **FEP/TI/BAR/MBAR**：使用有能量矩阵来源的引擎或解析包，明确单位、温度、λ 窗口和 overlap；缺数据时不能从两个结构能差推算“自由能”；
- **MM/PBSA/MM/GBSA**：调用可用外部程序/脚本并记录拓扑/帧选择/介电常数，显示统计误差、假设和适用限制；
- **Metadynamics**：PLUMED 的 HILLS/COLVAR、CV 定义、bias factor、重加权方案与收敛证据为必需输入；
- **NAMD/AMBER**：以外部工具适配器读取其输出，不要求初期把模拟引擎全部嵌入主 GUI。

### 6.6 药物化学（P1/P2 拓展）

优先本地真实且可靠的 `MolWt/TPSA/MolLogP/HBD/HBA/Rotatable Bonds/Ro5/PAINS`；其次是结构标准化、互变异构体/质子化状态枚举、蛋白质-配体接触网络；再后才做 pKa、ADMET、QSAR、对接结果分析。预测结果必须标出模型版本、输入标准化、适用域、置信与不确定性，**不得与实验测量相混淆，更不应标成药物安全性结论**。

---

## 7. Results 的基础数据契约

### 7.1 分离结构、任务和结果

建议模型（字段示意）：

```python
@dataclass(frozen=True)
class AnalysisInput:
    analysis_id: str
    document_id: str
    revision: int
    topology_hash: str
    geometry_hash: str | None
    source_artifact_ids: tuple[str, ...]
    selection_atom_ids: tuple[str, ...]
    options: dict                     # 需通过 schema 验证

@dataclass(frozen=True)
class AnalysisProvenance:
    method: str
    parameters: dict
    engine_name: str
    engine_version: str
    engine_sha256: str | None
    source_hashes: dict[str, str]
    input_hash: str
    created_at: str
    units: dict[str, str]

@dataclass(frozen=True)
class AnalysisArtifact:
    kind: str                        # table | spectrum | volume | plot | trajectory
    uri: str
    sha256: str
    media_type: str

@dataclass(frozen=True)
class AnalysisResult:
    result_id: str
    analysis_id: str
    input: AnalysisInput
    provenance: AnalysisProvenance
    status: str
    artifacts: tuple[AnalysisArtifact, ...]
    warnings: tuple[str, ...]
```

**注意**：示例没有解决所有序列化、安全与引用问题；真正实施时应使用 JSON Schema/Pydantic 或类似强验证结构，并将可变 options 序列化为不可变快照。

### 7.2 Source Mapping 与 ID 稳定性

外部 `.fchk/.log/.cube/.pdb` 的原子序号和 MolForge 的 AtomId 可能不同。增加 `AtomMapping`（原子序号、元素、稳定 ID、参考坐标、旋转/平移矩阵、映射置信与证据）。结构无法一一匹配时**拒绝将电荷/键级/轨道标记到错误原子上**。具有 PBC 的轨迹还须保存单位盒和 image 状态。

### 7.3 缓存失效的分层规则

| 变化 | 必须失效的结果 | 可保留的结果 |
|---|---|---|
| 化学拓扑变化 | 所有依赖原子/键定义的电子结构及 MD/描述符 | 仅与结构无关的历史报告 |
| 3D 几何变化 | 轨道体数据、ESP、振动、几何度量、当前结构分析 | 纯拓扑 2D 描述符（若成分未变） |
| 2D 绘图坐标变化 | 2D 排版缓存与相关图片 | 已算好的 Gaussian 电子能量和原始 trajectory |
| 相机变化 | 当前截图预览缓存 | 所有科学数值 |
| 分析参数变化 | 对应 AnalysisResult 缓存条目 | 其它 analysis 结果 |
| 外部源文件 hash 变化 | 依赖该文件的所有结果 | 其它文档来源结果 |

**过期结果不要静默删除**：保留作为历史，显示 `Stale` 水印和发生失效的原因，禁止在没有用户确认时将其结果写回当前结构。

---

## 8. 引擎集成与安全执行协议

### 8.1 工具发现优先级

1. 用户在设置页手动指定（相对/绝对路径、已记录的可执行文件 hash）；
2. 项目或用户配置文件注册的工具路径；
3. 系统 PATH 能找到的受支持版本；
4. WSL/SSH/SLURM/云端适配器（P2，可选）；无可用工具则进入 Missing Engine。

外部命令仅使用**参数数组** `subprocess.Popen([...], shell=False, cwd=dedicated_jobdir, ...)`；输入脚本通过 stdin 写入或以隔离路径文件传入，不直接拼接命令字符串。保存 stdout/stderr、return code、超时与取消原因，处理 Windows `CREATE_NEW_PROCESS_GROUP`/子进程树终止，避免孤儿作业。对含路径、输入片段的用户数据做严格验证，不允许把外部脚本从未知目录加载后静默执行。

### 8.2 关键适配器

| 适配器 | 最小能力 | 高阶能力 |
|---|---|---|
| Gaussian | detect、validate、write gjf、run、log parse、source hash | freqchk/formchk、TD、MO、优化轨迹、chk 管理 |
| Multiwfn | detect、version/build hash、stdin recipe、esp output parse | ELF/LOL/charges/bond order/IRI/NCI/holes/AIM |
| GROMACS | detect、export topology/mdp、run stage、read energy/trajectory | WHAM、FEP、AWH、增强采样 |
| VMD | export Tcl script / optional visualizer | 高质量 batch orbitals/ESP/trajectory render |
| RDKit | descriptor、mol validate、atom mapping、conformer | reaction/template/ADMET 受限扩展 |
| MDAnalysis | trajectory read、selection、RMSD/RDF/HBonds | stream/PCA/contacts/large systems |
| CPPTRAJ/AmberTools | 可选外部分析兼容入口 | MM/GBSA、跨程序分析 |
| PLUMED | 可选 bias 文件解析 | Metadynamics、PMF/reweight |

**版本矩阵**：把 `Python 3.13 / PyQt6 6.11.0 / vtk 9.7.1 / pyvista / pyvistaqt / rdkit / openbabel / mdanalysis / Gaussian / Multiwfn build / GROMACS / VMD` 的实际版本与检测结果写入诊断报告，独立管理可选依赖。不要在核心安装路径强制下载需要独立授权的外部引擎。

### 8.3 软件可用≠科学能力可用

Gaussian 可能运行成功却没有输出轨道系数；Multiwfn 可能打开 `.fchk` 却缺少某一分析所需的跃迁密度；MDAnalysis 能打开轨迹却缺少 PBC 盒信息；VMD 能渲染不代表生成了真实量子化学结果。`CapabilityResolver` 必须逐功能判定必需输入及可用算法，不能只有 `which("Multiwfn")` 这一层检查。

---

## 9. Windows 11 + VTK 9.7.1 原生稳定性设计

### 9.1 多 viewport 采用最少 native context 策略

单一顶层 3D Window 内的 1/2/4 pane 推荐**一个 `QtInteractor/vtkRenderWindow` + 多个 `vtkRenderer`，每个 renderer 用 `SetViewport(x0,y0,x1,y1)` 配置区域**。同一分子只维护文档事实源；每 pane 独立 camera/interactor state/picker，渲染缓存尽可能共享可安全复用的几何而不是共享不安全的原生窗口实例。

真正的不同 G:M:V 顶层窗口可以各自拥有 `QtInteractor`，**不得把属于一个窗口的 vtkInteractor、QWidget 或 OpenGL context 任意搬到另一个顶层窗口**。Qt GUI 主线程执行所有 QWidget/VTK native 操作；后台进程只生成可解析的数值或不可变数据块。

### 9.2 0xC0000409 风险控制

该异常码代表 Windows 原生异常类别，**在没有 minidump/调用栈/最后一次 Qt/VTK 调用的证据前，不得认定只有“VTK 多窗口”单一根因**。可能与生命周期、交互事件、OpenGL 驱动、资源销毁或其它 native 扩展共同有关。

具体防护：
- 在 QApplication 前设置 Qt 高 DPI 和 Qt OpenGL SurfaceFormat（如经实测需要）。
- VTK 创建/销毁、render 和交互放在 GUI 主线程；大型网格读入在 worker 完成，GUI 线程做 actor 更新。
- 注册每个 `vtkObserver`、QTimer、Qt signal 的 owner，关闭按**停止新事件 → 解除监听 → 结束交互 → 释放资源 → 删除 widget**顺序处理。
- 避免 VTK 的 picker/interactor 回调中直接重建 render window；必要时 `QTimer.singleShot(0,...)` 异步派发。
- 最少运行三组耐久：① 纯 Qt 窗口；② QtInteractor 空 scene；③ 真实分子和多 viewport。三组必须独立记录 crash 次数、内存/显存走势与日志。
- 指定 AMD/Intel/NVIDIA 中**至少两类显卡**的 Win11 环境，含单/双屏和 DPI 100%/150%/200%。
- 100 次**真实 GUI + VTK 原生窗口**新建/克隆/1↔2↔4 切换/销毁，保存事件日志和崩溃 dump。已有 100 次纯 Python Shell 测试仅是底层逻辑测试。
- 原生异常回退 feature flag：`MF_NEW_SHELLS=0`、`MF_MULTIVIEW=0`、`MF_RESULTS_EXPERIMENTAL=0`，不破坏 v6.2 经典工作台。

### 9.3 启动脚本修复

`run_molforge.bat` 必须删除开发机的绝对 Python 路径（当前明确触发测试失败）。建议查找顺序：若用户设置 `MOLFORGE_PYTHON` 且可执行 → 项目 `.venv\Scripts\python.exe` → `py -3.13` → `python`；失败时输出诊断而非无声退出。对应脚本目录使用 `%~dp0`，从项目路径中发现已固定版本的依赖清单和资源。

**PyQt6 官方支持 Windows 11 x86_64，VTK 9.7.1 存在 win_amd64 CPython 3.13 wheel** [S11][S12]；这些仅作为安装/支持的外部条件，最终必须由原生验收记录确认。

---

## 10. 验收标准与用户旅程

### 10.1 核心端到端旅程

**旅程 A：2D 独立设计**  
启动 → 欢迎页 → 2D 设计 → 乙醇/苯结构 → 添加片段/改键 → 保存 `.mforge` / SDF → Undo/Redo → 再打开 → 原子与键不丢失。**不得暗中创建不显示的旧三栏主窗口**。

**旅程 B：G:M:V 3D 建模**  
欢迎页 → 3D → `G1:M1:V1` → clone `G1:M1:V2` → V1 改结构、V2 立即刷新 → V2 Undo、V1 同步 → 新建 `G1:M2:V1` → `1/2/4` 子视口切换 → 正确 Picking → 关闭不崩溃。

**旅程 C：Gaussian**  
选择有效分子 → Calculate → Gaussian Setup 真正 11 页签 → Preview 生成 `.gjf` → 校验电子数/自旋 → 无引擎时清晰报错、能运行时进入后台 JobCenter → 读取真实 log → Results Summary/Optimization → 某个轨道/IR 点点击高亮对应分子。

**旅程 D：Multiwfn ESP / HOMO**  
打开真实 `.fchk` → Results → ESP → Multiwfn 版本/输入检测 → 受控执行 → 解析描述符和 Cube → VTK BWR → 数值与基准 Multiwfn 结果吻合 → SVG/CSV 导出含方法与参数。另一条 HOMO/LUMO 流程输出带等值面的完整能级图。

**旅程 E：GROMACS MD**  
导入合法 topology+trajectory → 预览动画，确认原子数/帧时间/PBC → Results → RMSD/RDF/HBond → 选区与对齐参数 → 结果曲线 → 与固定 GROMACS/MDAnalysis 基准输出一致 → 导出数字及方法。额外大轨迹测试必须证明 GUI 不因一次读取长时间冻结。

### 10.2 科学回归黄金数据

至少准备：
- 简单分子结构：水、乙醇、苯、咖啡因（几何/电荷/描述符）；
- 一个小型有合法 `.fchk/.cube/.log` 的 Gaussian 已完成样本（授权可用于测试）；
- 一个能复现 ESP 描述符/轨道能量的 Multiwfn 固定构建与参考输出；
- 一个小型 `.gro/.tpr + .xtc/.edr` 的 GROMACS 标准样本（不同 PBC、盒形、选区）；
- 一个蛋白/配体复合物用于 H-Bond、π-π、contacts 对照；
- 三条 3D 轨迹（正常单调时间、时间错序、PBC wrap），比较 RMSD、RDF、MSD 处理；
- 一个故意缺少 NPA/跃迁密度/EDR 的负面样本，验证明确提示缺数据，而非伪造数值。

每一个“通过”的科学模块至少有**输入 fixture + 基准数值 + 容差 + 单位 + source version + negative test**，而不只是截图。

### 10.3 质量门槛

| 类型 | P0 门槛 | P1 门槛 | P2 门槛 |
|---|---|---|---|
| UI | 三个真正 Qt Window + WelcomeWindow；经典入口保留 | 全菜单、跨 G:M:V、1/2/4 真 VTK、科学 Dialog | 大批量/可定制布局与高级流程 |
| 科学功能 | 六个核心 Results 主模块中指定最小真实闭环 | 常用量化和 MD 分析有确定性测试 | 高级自由能/EDA/药物预测有严格能力边界 |
| 作业执行 | 可探测引擎、日志、取消、revision/hash | Gaussian、Multiwfn、GROMACS 的标准工作流 | 批量 DAG、可重复运行、远程可选 |
| 数据 | v6.2 文件兼容、结果溯源 | 中间产物与原子映射可追溯 | 工程迁移、归档与出版复现 |
| 原生稳定性 | 单 VTK 窗口真实开关循环 | 多窗口 1/2/4、双 GPU 类别通过 | 打包版回归、长期压力/泄漏记录 |
| 回滚 | 一键切回经典工作台 | 未完成的 Results 不激活真实运行 | 发布版保留上一稳定二进制 |

---

## 11. 风险矩阵与回滚计划

| 风险 ID | 级别 | 风险 | 技术缓解 | 失败时回滚 |
|---|---|---|---|---|
| R-01 | 极高 | 一次重构切换破坏经典三栏工作台 | UI Adapter/feature flag，不删除旧窗口 | `MF_NEW_SHELLS=0` |
| R-02 | 极高 | `0xC0000409` VTK/Qt native 崩溃 | 实际 VTK 压测、主线程、资源 owner、dump | 关闭 2/4 pane，退回单视口 |
| R-03 | 极高 | 错误解析科学结果导致虚假数值 | provenance、golden fixtures、单位/版本/输入强校验 | 禁用该 Analysis ID，保留原始文件 |
| R-04 | 高 | Multiwfn dev 构建 CLI 菜单变化 | recipe→build hash/version；单模块灰度 | 回退上一受支持 recipe |
| R-05 | 高 | 多窗口不共享撤销和历史 | 强制唯一 DocumentSession/CommandBus | 回退 Legacy 后端或禁用 clone |
| R-06 | 高 | MDAnalysis Universe 并发游标竞争 | 独立 reader/串行 IO Worker | 关闭预取，单线程顺序读取 |
| R-07 | 高 | 旧结果覆盖新结构 | input revision + topology/geometry hash | 旧结果仅作为 stale 历史 |
| R-08 | 高 | Gaussian 真实执行误提交/费用浪费 | 输入预览、引擎探测、运行前确认与资源限制 | 只导出 `.gjf`，禁用 Submit |
| R-09 | 高 | 新 `.mforge` 会话格式损害旧文件 | 副本/兼容解析/版本迁移测试 | 退回旧 schema 保存器 |
| R-10 | 中高 | 79 个 Dialog 模块挤爆进度 | 构建统一 Dialog+Registry，优先真实 P0/P1 流程 | 保留目录，禁用未就绪执行 |
| R-11 | 中高 | 外部程序路径、脚本和许可问题 | 手动注册工具，shell=False，独立授权提示 | 禁用外部引擎，仍可加载原始结果 |
| R-12 | 中高 | 内存/显存随 VTK 和轨迹增长 | actor/cache 生命周期、下采样、监测 | 简化渲染，延迟载入 |
| R-13 | 中高 | Results 图像与科研数据混淆 | 标注 simulated/parsed/predicted、版本、单位 | 撤销该可视化发布入口 |
| R-14 | 中 | AI/批量错误扩散 | AI 只生成有证据可确认的建议、任务日志 | 关闭 AI 和批量执行 |

### 11.1 具体回滚级别

**L0：Git 提交级**：P0 每个变更独立提交，不同时升级 Qt/VTK 和重构 GUI。以可运行的经典工作台为 Git tag 基线，保存测试输入的 hash。

**L1：功能开关级**：保留原 `MolForgeWindow`；欢迎页出错可直接启动 Legacy。可对 Shell、MultiView、Multiwfn、MD、experimental Results 分别开关。

**L2：数据级**：重要 `.mforge` 修改前复制原文件或原子写入备份；先记录新数据的引用索引，必要时把 Results 保存在独立 sidecar 目录，不立即修改旧文件 schema。回退程序必须能无损打开原工程。

**L3：引擎级**：Multiwfn/Gaussian/GROMACS 只作为外部进程，不改变用户已有安装；记录可执行 hash、recipe 版本和输出目录。新 recipe 失败只回退此单一 adapter，不回滚核心建模器。

**L4：部署级**：保留上一验证过的 Win11 安装包/绿色版、Python 和依赖锁定，更新失败时恢复上一稳定包。打包期不同时大幅改变工程文件格式。

---

## 12. 分阶段实施顺序与门禁

### 12.1 P0 — 先完成真正可用的系统骨架

**最先交付**：可运行 `WelcomeWindow`、三套真实 `QMainWindow`、经典工作台入口、主入口统一、Session 与 Qt 生命周期、可控 Results 菜单、真实 Gaussian Setup 与基础结果、可移植启动、原生单窗口耐久。并保留现有片段事务与测量逻辑。

**退出 Gate**：三入口都能完成至少一条端到端操作；老工作台不回归；单文档 V 克隆共享 Undo 可实机验证；核心 Results 有真实数据/明确失败；固定开发机路径已消除。

### 12.2 P1 — 常用科学 Results 完整闭环

主攻：真正 1/2/4 VTK；完整 G:M:V 管理；Multiwfn ESP/HOMO/ELF/LOL/电荷/键级、OSC D/A；Gaussian 任务日志+优化/IR/Raman/UV-Vis；RDKit 分子属性、基本分子间作用、GROMACS/MDAnalysis 8 项分析；图表、原子联动、导出和 Win11 多 GPU 验收。

**退出 Gate**：真实外部样本能重复计算和解析；每个 P1 模块的基准值及单位可验证；所有上游工具缺失时 UI 可诊断、不虚构结果；真实 VTK 多窗口与 G:M:V 运行稳定。

### 12.3 P2 — 高级科学研究及平台化

主攻：QTAIM/EDA/NPA/高级光谱、OSC 四点重组能/CT、药物 pKa/ADMET 模型边界、自由能 FEP/MBAR/WHAM/Metadynamics、cpptraj/AMBER 兼容、批量、AI 辅助、远程 HPC/云端可选、发布打包和长期稳定性。

**退出 Gate**：高级模块遵守来源、算法和不确定性要求；批量任务可复现；干净 Win11 发布包通过；旧 `.mforge` 读写向后兼容；发布回滚经过演练。

---

## 13. 有针对性的增强建议（提示词之外）

1. **内建“结果可信度”机制**：每个结果显示 `Measured / Parsed / Calculated / Predicted / Illustrative` 的证据类型；示意性曲线不能混入真实科学图中。
2. **可查询的结果数据仓库**：按分子组 G、分子 M、构象、任务、方法、引擎、日期索引；从一条结果直接返回原始日志和源文件。
3. **分析复现卡（Reproducibility Card）**：点击图表查看所有参数、源哈希、单位、软件版本、算法版本、计算/解析日志及导出脚本。
4. **跨分子的对比工作台**：特别适合 OSC 给受体、药物系列和多构象研究，支持相关性散点图、筛选/排序与一键文献级表格。
5. **Scientific Validation Inspector**：系统自动提示不合理的电荷/多重度、结构缺氢、低采样重叠、RDF 没有盒数据、pKa 模型适用域不足、量化结果来自过期结构等。
6. **External Tool Doctor**：可视化测试 Gaussian、Multiwfn、GROMACS、VMD、OpenBabel 和 GPU/驱动状态，输出脱敏诊断文件。
7. **图表与三维场景共选区**：轨迹图上选择一个峰/时间窗，3D 同步定位帧；电荷表点击一行，高亮原子；尽量形成 VMD 式研究交互而不只是静态截图。
8. **插件 API 优先于硬编码大量后处理**：分析模块需要 `Definition / Validate / Execute / Parse / Render / Export` 六段契约，第三方扩展可按统一方式接入。
9. **现代 3D 体验**：分级 LOD、原子/键 GPU instancing、GPU 体绘制、网格缓存、颜色可访问性、4K/透明图、多轨道统一色标；先做可测性能，再考虑大改渲染引擎。
10. **安全的 AI 辅助**：AI 可以建议计算方法、发现缺数据、生成可审查的任务配置与解释已有结果，但不可默默启动昂贵外部计算、修改当前分子或编造电子结构数值。

---

## 14. 官方与一手参考资料

下列链接是对**专业软件已有能力**或**目标平台支持**的外部佐证，不是 MolForge 完成情况的证据。部分产品的资料来源为某特定版本，不对其所有现行功能作绝对断言。

- **[S01] Gaussian / GaussView 6 Fundamental Help**：https://gaussian.com/wp-content/uploads/dl/gv6.pdf
- **[S02] Revvity Signals / ChemDraw 官方功能对照**：https://revvitysignals.com/sites/default/files/2025-09/rs-chart-chemdraw-chemdraw-which-is-right-for-me%20.pdf
- **[S03] VMD 官方插件与分析目录**：https://www.ks.uiuc.edu/Research/vmd/plugins/
- **[S04] Avogadro 2 官方手册及 2026-10-23 2.1.0 更新说明**：https://avogadro.cc/docs/ ；https://avogadro.cc/install/versions/v210.html
- **[S05] Molden 官方手册**：https://www.theochem.ru.nl/molden/manual.html
- **[S06] Multiwfn 官方/开发者下载页（注意 3.8(dev)）**：https://www.umsyar.com/multiwfn/download.html
- **[S07] GROMACS 2026 命令参考**：https://gromacs-manual.biophysics.kth.se/current/user-guide/cmdline.html
- **[S08] Amber-MD/CPPTRAJ 官方仓库及 AMBER-hub**：https://github.com/Amber-MD/cpptraj ；https://amberhub.chpc.utah.edu/cpptraj/
- **[S09] NAMD Colvars 说明；PLUMED METAD 文档**：https://www.ks.uiuc.edu/Research/namd/2.13b1/ug/node53.html ；https://www.plumed.org/doc-v2.10/user-doc/html/_m_e_t_a_d.html
- **[S10] RDKit 官方 Python 指南与描述符**：https://www.rdkit.org/docs/GettingStartedInPython.html
- **[S11] Qt for Python 6.11 / Windows 支持矩阵**：https://doc.qt.io/qtforpython-6.11/overviews/qtdoc-windows.html
- **[S12] VTK 9.7.1 PyPI wheel 目录**：https://pypi.org/project/vtk/9.7.1/

---

## 15. 最终建议的实施入口

**第一轮开发严格按下面顺序启动：**

1. 修复 `run_molforge.bat`，锁定 Windows 11 依赖和现有可运行 Git 基线；
2. 统一 `main.py` 和 `scripts/launch.py`，新增真正 `WelcomeWindow`；
3. 保留纯 Python `Studio*Shell`，建立 `Studio*Window(QMainWindow)`，逐一接上现有 2D/3D 组件；
4. 确认 DocumentSession 跨窗口事件与撤销同一性，并完成关闭清理；
5. 接入 Gaussian 11 页签与 6 按钮实际任务控制；
6. 完成 Results Registry、`AnalysisInput/Result` 与基础真实分析；
7. 基于隔离的 Multiwfn fixture 落实 ESP、HOMO/LUMO；
8. 实现单窗口 1/2/4 VTK，并开展 native 多窗口耐久；
9. 建 GROMACS MD 常规分析闭环；
10. 完成高级科研功能、批量化与发布。

**开发判定准绳：功能通过“输入校验 → 可执行任务 → 真实计算或可靠解析 → 2D/3D 展示 → 导出可复现 → 保存/重开/复核”，才算真正实现。**


---

## 附录 A：P0 / P1 / P2 任务清单（含源文件位置、依赖和验收）

### P0 任务

| ID | 任务 | 领域 | 代码位置 | 前置依赖 | 验收条件 |
|---|---|---|---|---|---|
| P0-01 | 建立零改动基线与回滚包 | 开发基础 | `main.py+run_molforge.bat+docs` | 无 | 能还原经典三栏并打开历史工程 |
| P0-02 | 消除个人 Python 路径 | 启动 | `run_molforge.bat` | P0-01 | 启动契约测试通过 |
| P0-03 | 统一 main.py 与 scripts/launch.py bootstrap | 启动 | `main.py+scripts/launch.py+新 bootstrap.py` | P0-01 | 两入口进入同一欢迎界面 |
| P0-04 | 真实 WelcomeWindow UI | GUI | `molforge/ui/welcome_window.py` | P0-03 | 点击确实启动新 Qt 工作台 |
| P0-05 | 保持 Shell 后端并新增 QMainWindow Adapter | GUI | `molforge/ui/shells/*+新 shell_windows/*` | P0-04 | 三者能显示、保有独立菜单和画布 |
| P0-06 | 经典工作台回退入口 | 兼容 | `molforge/ui/window.py+ShellFactory` | P0-04 | 原主界面功能完整不丢 |
| P0-07 | Qt 生命周期、会话解绑与异常恢复 | 稳定性 | `window.py+document_session.py+workspace_registry.py` | P0-05 | 反复切换不出现 Python 异常 |
| P0-08 | G:M:V 命名映射与共享编辑事件接线 | 窗口 | `gmv_window_manager.py+workspace_registry.py` | P0-05 | V1 编辑 V2 可见；V2 撤销一致 |
| P0-09 | 建立 Action/Analysis Registry | 分析框架 | `新 results/registry.py+menu_builder.py` | P0-05 | Results 全目录能打开实际 Dialog/说明 |
| P0-10 | 建立 AnalysisResult、Provenance 与 JobAdapter | 分析框架 | `新 results/models.py+results/storage.py` | P0-09 | 旧结果不被当成新分子结果 |
| P0-11 | 结果 Summary/Descriptor/轨道与 Cube 基线 | 科学闭环 | `qc_result_dialog.py+rdkit_adapter.py` | P0-10 | 数据显示实际输入，非占位值 |
| P0-12 | Gaussian Setup 正式 UI 接线 | Gaussian | `gaussian_calculation_setup.py+window.py` | P0-05 | Ctrl+G 打开真实 11 页签对话框 |
| P0-13 | Gaussian 提交执行器与安全验证 | Gaussian | `gaussian_engine.py+jobs.py+新 adapter` | P0-12,P0-10 | 无引擎时准确报错，有引擎可获得日志 |
| P0-14 | 外部工具发现与环境检查 | 引擎 | `新 engines/tool_registry.py` | P0-09 | 不可用功能显示原因而非假数据 |
| P0-15 | VTK 原生单视图+关闭耐久测试 | 渲染 | `render3d_widget.py+tests/native` | P0-05 | 100 次实际窗口开关，无已知崩溃 |
| P0-16 | 轨迹数据线程安全审查与限流 | MD | `mdanalysis_adapter.py` | P0-10 | 大轨迹 UI 可响应无竞争 |
| P0-17 | 回归 P0 几何、片段事务与旧功能 | 回归 | `tests/*` | P0-01 | 原有编辑、片段、选取、存盘通过 |
| P0-18 | 锁定与记录依赖 | 发布 | `requirements.txt+环境导出` | P0-01 | 干净环境安装结果记录 |

### P1 任务

| ID | 任务 | 领域 | 代码位置 | 前置依赖 | 验收条件 |
|---|---|---|---|---|---|
| P1-01 | 2D 主窗口工具栏与文件流程齐全 | UI | `新 studio_2d_window.py` | P0-05 | 不依赖旧主窗口可完成任务 |
| P1-02 | Split 双画布双向同步 | UI | `新 studio_split_window.py` | P0-08 | 2D 编辑 3D 更新，Undo 一次 |
| P1-03 | 3D 专业菜单与对话框驱动 | UI | `新 studio_3d_window.py` | P0-09 | 完整主流程无强制右侧大面板 |
| P1-04 | 真正的 1/2/4 VTK viewport | 渲染 | `vtk_multiview_widget.py+render3d_widget.py` | P0-15 | 四 pane 独立 Pick/Camera 可用 |
| P1-05 | 多窗口管理器与相机保存 | 窗口 | `gmv_window_manager.py` | P1-04 | 编号唯一，状态一致 |
| P1-06 | Multiwfn adapter 与脚本模式 | 波函数 | `new engines/multiwfn_adapter.py` | P0-14 | 固定 fchk 自动生成可检验产物 |
| P1-07 | ESP + BWR + 描述符闭环 | 波函数 | `results/esp.py+Dialog` | P1-06 | 与 Multiwfn 基准样例数值一致 |
| P1-08 | HOMO/LUMO 能级+等值面 | 波函数 | `results/orbitals.py+Dialog` | P1-06 | 一张完整论文级图可导出 |
| P1-09 | OSC D/A 能级对比 | OSC | `results/osc.py` | P1-08 | 不混用不同参照直接比较 |
| P1-10 | ELF LOL Mayer Hirshfeld ADCH IRI NCI | 波函数 | `results/multiwfn_plugins/*` | P1-06 | 每项有标准数据输出 |
| P1-11 | 电子空穴/电荷密度与 Laplacian | 波函数 | `results/excited_state.py` | P1-06 | 缺乏跃迁密度时阻止执行 |
| P1-12 | 平面性/偶极/SASA/logP/描述符 | 性质 | `results/properties/*` | P0-11 | 单位、算法参数、数值回归 |
| P1-13 | H-bond π-π 范德华接触 | 相互作用 | `results/interactions/*` | P1-12 | toy complex 预期相互作用准确 |
| P1-14 | IR/Raman/UV-Vis/振动动画 | 光谱 | `results/spectra/*` | P0-13 | 可控展宽，源峰归属一致 |
| P1-15 | Gaussian 任务监控与结果导入 | Gaussian | `jobs.py+gaussian_engine.py+result_import.py` | P0-13 | 旧 revision 结果不得覆盖最新结构 |
| P1-16 | GROMACS setup/runner 原型 | MD | `engines/gromacs.py+MDSetupDialog` | P0-14 | 能完成小体系样例或导出脚本 |
| P1-17 | MDAnalysis/GROMACS 8 项常用分析 | MD | `results/md/*` | P0-16 | 对照 GROMACS 输出一致 |
| P1-18 | 独立 Dialog 基类与结果可视组件 | UI | `results/dialogs/*` | P0-09 | 所有分析按统一交互逻辑呈现 |
| P1-19 | 导出规范 | 数据 | `results/exports/*` | P1-18 | 同一图重新导出完全复现 |
| P1-20 | Windows 11 多窗口 UI 耐久 | QA | `tests/native/*` | P1-04,P1-05 | 无 0xC0000409、无阻断缺陷 |

### P2 任务

| ID | 任务 | 领域 | 代码位置 | 前置依赖 | 验收条件 |
|---|---|---|---|---|---|
| P2-01 | QTAIM/NPA/密度差/自旋和 DOS | 波函数 | `results/advanced_wfn/*` | P1-06 | 基准计算可回归 |
| P2-02 | EDA 专用计算适配器 | 相互作用 | `results/eda.py` | P0-14 | 不把普通能量差伪装成 EDA |
| P2-03 | NMR ECD ORD Vibronic | 光谱 | `results/advanced_spectra/*` | P1-14 | 与专业程序解析校验 |
| P2-04 | pKa、ADMET 及适用域 | 药物 | `results/prediction/*` | P1-12 | 没有支持数据时清晰不可用 |
| P2-05 | 受体-配体相互作用图 | 药物 | `results/complexes/*` | P1-13 | 可对照可解释交互 |
| P2-06 | OSC 充电重组能与激子/CT | OSC | `results/osc_advanced/*` | P1-09 | 四点法完整 provenance |
| P2-07 | MD PCA/聚类/接触/MSD | MD | `results/md_advanced/*` | P1-17 | 测试体系统计可信 |
| P2-08 | MM/PBSA、WHAM、FEP/MBAR | 自由能 | `engines/ambertools.py+results/free_energy/*` | P1-16 | 缺乏收敛证据需警告 |
| P2-09 | PLUMED Metadynamics | 增强采样 | `engines/plumed.py+results/md_bias/*` | P1-16 | 完整复现自由能图 |
| P2-10 | 批量分析与高通量工作流 | 平台 | `application/batch/*` | P1-19 | 同一输入可重复产生相同报告 |
| P2-11 | 模型受限的 AI 助手 | AI | `application/ai/*+Results` | P2-10 | 不存在虚构数值/自动危险执行 |
| P2-12 | 远程 HPC/云端作业连接 | 平台 | `engines/remote/*` | P2-10 | 模拟环境断网可恢复 |
| P2-13 | 高分辨率 3D 论文图和视频 | 渲染 | `rendering/*` | P1-19 | 一致性基准图通过 |
| P2-14 | 工程文件、Results 资产关联和迁移 | 数据 | `io/mforge_storage.py` | P0-10 | 老文件仍可读新数据可无损保存 |
| P2-15 | 公开 API/插件系统 | 平台 | `application/plugins.py+api/*` | P2-10 | 插件异常不影响项目数据 |
| P2-16 | 干净 Win11 发布与测试报告 | 发布 | `scripts/windows11_diagnostics.py+packaging` | P1-20 | 两种硬件配置复现通过 |


---

## 附录 B：Results 模块完整索引（共 79 项）

### 基础结果

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| CORE-01 | 计算结果摘要 Summary | `ResultSummaryDialog` | Gaussian/ORCA/cclib | P0 |
| CORE-02 | 优化过程 Optimization | `OptimizationHistoryDialog` | Gaussian/xtb 输出解析 | P1 |
| CORE-03 | 电子结构结果表 Atom/Bond Properties | `AtomBondResultsDialog` | 解析器和文档映射 | P0 |
| CORE-04 | 势能扫描 Scan | `ScanResultsDialog` | Gaussian/xtb 实际扫描输出 | P1 |
| CORE-05 | IRC 与反应路径 | `IRCResultsDialog` | Gaussian/ORCA 输出 | P1 |
| CORE-06 | 表面与等值线管理 | `SurfaceManagerDialog` | VTK/Cube | P0 |

### 波函数

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| WFN-01 | ESP 表面+σ²+、σ²−、ν、Π、MPI | `ESPSurfaceAnalysisDialog` | Multiwfn + VTK/VMD 可选 | P1 |
| WFN-02 | HOMO/LUMO 能级与等值面 | `FrontierOrbitalsDialog` | Gaussian/cclib+Multiwfn+VTK | P1 |
| WFN-03 | OSC 给体受体能级对比 | `OSCEnergyComparisonDialog` | Results 数据聚合 | P1 |
| WFN-04 | ELF 电子定域函数 | `ELFAnalysisDialog` | Multiwfn | P1 |
| WFN-05 | LOL 局域轨道定位器 | `LOLAnalysisDialog` | Multiwfn | P1 |
| WFN-06 | Mayer/Wiberg 键级 | `BondOrderAnalysisDialog` | Multiwfn或源引擎 | P1 |
| WFN-07 | Hirshfeld 电荷 | `HirshfeldChargeDialog` | Multiwfn | P1 |
| WFN-08 | ADCH 电荷 | `ADCHChargeDialog` | Multiwfn | P1 |
| WFN-09 | NPA 自然布居电荷 | `NPAChargeDialog` | Gaussian/NBO 等输出解析 | P2 |
| WFN-10 | 电子-空穴分布 | `ElectronHoleDialog` | Multiwfn/激发态解析器 | P1 |
| WFN-11 | IRI 弱相互作用区域 | `IRIAnalysisDialog` | Multiwfn | P1 |
| WFN-12 | NCI/RDG/s(ρ) 图 | `NCIAnalysisDialog` | Multiwfn | P1 |
| WFN-13 | AIM/QTAIM 拓扑 | `AIMAnalysisDialog` | Multiwfn | P2 |
| WFN-14 | 电荷密度与 Laplacian | `DensityLaplacianDialog` | Multiwfn/VTK | P1 |
| WFN-15 | 差分密度与密度重排 | `DifferenceDensityDialog` | Multiwfn/体数据运算 | P2 |
| WFN-16 | 轨道组成 DOS/PDOS | `DOSAnalysisDialog` | Multiwfn/源引擎 | P2 |
| WFN-17 | 自旋密度与多参考指标 | `SpinDensityDialog` | Multiwfn/源引擎 | P2 |

### 分子性质

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| PROP-01 | 平面性与二面角分布 | `PlanarityDialog` | NumPy/RDKit | P1 |
| PROP-02 | 偶极矩矢量 | `DipoleMomentDialog` | 计算输出解析 | P1 |
| PROP-03 | SASA 与体积 | `SurfaceVolumeDialog` | RDKit/FreeSASA/MDAnalysis | P1 |
| PROP-04 | logP 模型预测 | `LogPDialog` | RDKit Crippen | P1 |
| PROP-05 | pKa 模型预测 | `PkaPredictionDialog` | 外部经过验证的预测模型 | P2 |
| PROP-06 | MW/TPSA/HBD/HBA/可旋转键 | `DescriptorDashboardDialog` | RDKit Descriptors | P0 |
| PROP-07 | 形状、PMI 与三维描述符 | `ShapeDescriptorsDialog` | RDKit/NumPy | P2 |
| PROP-08 | 多构象性质比较 | `ConformerPropertyDialog` | RDKit/xtb 结果 | P1 |

### 分子间作用

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| INTER-01 | EDA 能量分解 | `EDAAnalysisDialog` | SAPT/ALMO-EDA 等专门引擎输出 | P2 |
| INTER-02 | 氢键网络 | `HydrogenBondDialog` | MDAnalysis/几何分析 | P1 |
| INTER-03 | π-π 堆积 | `PiStackingDialog` | RDKit/几何算法 | P1 |
| INTER-04 | 范德华接触 | `VDWContactsDialog` | KDTree/半径表 | P1 |
| INTER-05 | 盐桥与阳离子-π | `IonicContactsDialog` | 几何规则+形式电荷 | P2 |
| INTER-06 | 蛋白质-配体接触指纹 | `InteractionFingerprintDialog` | RDKit/MDAnalysis | P2 |
| INTER-07 | 分子配对/结合能比较 | `BindingEnergyDialog` | 计算结果比较 | P2 |

### 光谱

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| SPEC-01 | IR 红外与模式动画 | `IRSpectrumDialog` | Gaussian/ORCA/cclib | P1 |
| SPEC-02 | Raman 拉曼 | `RamanSpectrumDialog` | Gaussian/ORCA/cclib | P1 |
| SPEC-03 | UV-Vis/TD-DFT | `UVVisSpectrumDialog` | Gaussian/ORCA/cclib | P1 |
| SPEC-04 | NMR 化学位移与谱模拟 | `NMRSpectrumDialog` | Gaussian/预测引擎 | P2 |
| SPEC-05 | CD/ECD 圆二色谱 | `CDSpectrumDialog` | TD-DFT/光谱解析 | P2 |
| SPEC-06 | ORD 旋光色散 | `ORDSpectrumDialog` | 来源引擎结果 | P2 |
| SPEC-07 | 振电耦合 Vibronic | `VibronicSpectrumDialog` | 专业计算引擎解析 | P2 |
| SPEC-08 | 振动模式表与同位素比较 | `VibrationModeDialog` | Gaussian/ORCA 解析 | P1 |

### 分子动力学

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| MD-01 | MD 设置向导 | `MDSetupDialog` | GROMACS adapter | P1 |
| MD-02 | 轨迹播放器 | `TrajectoryAnalysisDialog` | MDAnalysis+VTK | P0 |
| MD-03 | RMSD | `RMSDAnalysisDialog` | MDAnalysis/GROMACS | P1 |
| MD-04 | RMSF | `RMSFAnalysisDialog` | MDAnalysis/GROMACS | P1 |
| MD-05 | 回旋半径 Rg | `RadiusGyrationDialog` | MDAnalysis/GROMACS | P1 |
| MD-06 | 轨迹氢键占有率 | `MDHydrogenBondDialog` | MDAnalysis/GROMACS | P1 |
| MD-07 | RDF | `RDFDialog` | GROMACS/MDAnalysis | P1 |
| MD-08 | 二面角时间序列 | `MDDihedralDialog` | MDAnalysis/GROMACS | P1 |
| MD-09 | 能量与温度压力 | `MDEnergyDialog` | GROMACS energy/log | P1 |
| MD-10 | 构象聚类 | `MDClusterDialog` | MDAnalysis/GROMACS/cpptraj | P2 |
| MD-11 | PCA 与自由能景观 | `PCAFELDialog` | MDAnalysis/GROMACS | P2 |
| MD-12 | MSD/扩散系数 | `MSDDialog` | GROMACS/MDAnalysis | P2 |
| MD-13 | SASA / 二级结构时间演变 | `MDSecondaryStructureDialog` | GROMACS/MDAnalysis | P2 |
| MD-14 | 原子接触/盐桥持久性 | `MDContactsDialog` | MDAnalysis/GROMACS | P2 |
| MD-15 | 伞形采样 WHAM/PMF | `UmbrellaPMFDialog` | GROMACS WHAM/PLUMED | P2 |
| MD-16 | Metadynamics 重加权 | `MetaDynamicsDialog` | PLUMED | P2 |
| MD-17 | FEP/TI/BAR/MBAR | `AlchemicalFreeEnergyDialog` | GROMACS/AMBER+alchemlyb | P2 |
| MD-18 | MM/PBSA 或 MM/GBSA | `MMPBSADialog` | AmberTools/gmx_MMPBSA 外部 | P2 |

### OSC 专题

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| OSC-01 | D/A 能级真空基准对齐 | `DAAlignmentDialog` | Result comparison | P1 |
| OSC-02 | 电子/空穴转移 NTO | `NTOAnalysisDialog` | 激发态解析+Multiwfn | P2 |
| OSC-03 | 激子/CT 指标与跃迁密度 | `ChargeTransferDialog` | Multiwfn | P2 |
| OSC-04 | 重组能 λh/λe | `ReorganizationEnergyDialog` | 多任务结果聚合 | P2 |
| OSC-05 | 光谱与吸收边比较 | `OSCOpticalDialog` | 结果聚合 | P2 |
| OSC-06 | 电子耦合与电子转移路径 | `ElectronicCouplingDialog` | 外部电子结构计算 | P2 |

### 药物化学

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| DRUG-01 | Lipinski/Veber/PAINS 快速评估 | `DrugLikenessDialog` | RDKit | P1 |
| DRUG-02 | 质子化/互变异构体枚举 | `ProtonationTautomerDialog` | RDKit/外部 pKa | P2 |
| DRUG-03 | ADMET/QSAR 预测 | `ADMETPredictionDialog` | 经校验的外部模型 | P2 |
| DRUG-04 | 受体-配体接触与口袋测量 | `ProteinLigandDialog` | MDAnalysis/RDKit | P1 |
| DRUG-05 | 对接结果整理与重评分 | `DockingReviewDialog` | 外部 docking engine | P2 |

### 分析工作流

| ID | 功能 | 对话框 | 主依赖 | 实施阶段 |
|---|---|---|---|---|
| INFRA-01 | Analysis Registry 目录 | `AnalysisRegistryDialog` | 内部框架 | P0 |
| INFRA-02 | 结果图表与论文导出 | `PublicationExportDialog` | matplotlib/SVG/VTK | P1 |
| INFRA-03 | 批量分析/高通量运行 | `BatchAnalysisDialog` | 任务中心与队列 | P2 |
| INFRA-04 | AI 辅助分析助手 | `AIAnalysisAssistantDialog` | 受限工具/分析器 | P2 |


**附录 B 的输入、输出、源码现状等完整列请查阅 `MolForge_v7_Results_Feature_Matrix_20261030.csv`。本方案和 CSV 都不应被误读成“这些分析功能目前已经存在”。**
