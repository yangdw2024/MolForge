# MolForge Studio — Full Feature Parity & Migration Inventory

> **Source Baseline**: MolForge 7.4.3 (PyQt6 Architecture)  
> **Target Architecture**: MolForge Studio 8.1+ (Electron + React + WebGPU + Native Rust Core)  
> **Generated Inventory**: 38 Dialogs, 4 Docks, 13 Panels, 13 Menus, 116 Actions, 0 Analyses  

---

## 1. Top-Level Scientific Menus (100% Target Parity)

| Menu (PyQt6) | English / System ID | Purpose | Desktop 8.1 Status |
|---|---|---|---|
| `窗口(&W)` | `窗口(W)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `文件(&F)` | `文件(F)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `最近打开文件` | `最近打开文件` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `编辑(&E)` | `编辑(E)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `工具(&T)` | `工具(T)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `构建器(&B)` | `构建器(B)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `视图(&V)` | `视图(V)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `🪟 3D 单窗口多视口分屏 (1 / 2 / 4 Viewports P1..P4)` | `🪟 3D 单窗口多视口分屏 (1 / 2 / 4 Viewports P1..P4)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `结构(&S)` | `结构(S)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `计算(&C)` | `计算(C)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `结果(&R)` | `结果(R)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `表面(&U)` | `表面(U)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |
| `帮助(&H)` | `帮助(H)` | Menu container for scientific commands | `Migrated (CommandRegistry & MenuBar)` |

---

## 2. Dialog & Dock Classes (42 Total)

### 2.1 Scientific Dialogs

| Class Name | Source File | Description | Target Layer / Modal | Status |
|---|---|---|---|---|
| `BioStructureDialog` | `[MolForge/molforge/ui/bio_structure_dialog.py#L12]` | Scientific calculation / setup modal | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ConformerDialog` | `[MolForge/molforge/ui/conformer_dialog.py#L15]` | Scientific calculation / setup modal | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ElementPickerDialog` | `[MolForge/molforge/ui/element_picker.py#L32]` | 完整元素周期表选择器。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `GromacsJobDialog` | `[MolForge/molforge/ui/gromacs_job_dialog.py#L13]` | Scientific calculation / setup modal | Floating Layer / Modal | `Phase 2-3 Migration` |
| `LiveLlmDialog` | `[MolForge/molforge/ui/live_llm_dialog.py#L33]` | Scientific calculation / setup modal | Floating Layer / Modal | `Phase 2-3 Migration` |
| `LlmConfigDialog` | `[MolForge/molforge/ui/llm_config_dialog.py#L17]` | 配置任意 OpenAI 兼容端点（本地 vLLM/Ollama/DeepSeek/OpenAI 等）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `SaveCustomFragmentDialog` | `[MolForge/molforge/ui/panels.py#L235]` | 保存自定义砌块 / 分子 / 片段的交互对话框，支持设置名称、选择/新建分组、类型与说明。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `QcResultDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L277]` | 量化计算与 OSC 能级工作台对话框（兼容旧版 QcResultDialog(parent, result, on_show_step) 签名， | Floating Layer / Modal | `Phase 2-3 Migration` |
| `BaseAnalysisDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1114]` | v7.1 科学结果后处理基类对话框： | Floating Layer / Modal | `Phase 2-3 Migration` |
| `WavefunctionAnalysisDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1390]` | 波函数分析专属工作台 (WFN-01..WFN-17：Multiwfn 批处理控制、等值面阈值、BWR 色阶与 3D 轨道生成)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `MolecularPropertyDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1436]` | 分子性质与成药性专属工作台 (PROP-01..PROP-08, DRUG-01..DRUG-06：SVD 平面拟合子集、RDKit Ertl TPSA、Lipinski 雷达)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `IntermolecularDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1459]` | 分子间与分子内非共价弱相互作用专属工作台 (INTER-01..INTER-08：氢键/π-π/vdW 距离截断实时调节)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `SpectrumAnalysisDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1493]` | 光谱分析专属工作台 (SPEC-01..SPEC-08：IR / Raman / UV-Vis / ECD 半峰宽 FWHM 与频率缩放因子实时联动)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `MdTrajectoryAnalysisDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1527]` | GROMACS 分子动力学与轨迹分析专属工作台 (MD-01..MD-18：温度/压强/步数配置、一键导出全套 .mdp 与 RMSD/Rg 曲线)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `OscSpecialAnalysisDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1584]` | 有机光伏 (OSC) 专题分析工作台 (OSC-01..OSC-07, WFN-03：内置 HOMO/LUMO 阶梯能级对比图 + 给受体驱动力)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `EngineStatusDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1607]` | 8.1 节外部科学引擎探测与路径配置对话框 (Gaussian / xtb / Multiwfn / GROMACS / VMD / OpenBabel)。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `AnalysisRegistryBrowserDialog` | `[MolForge/molforge/ui/qc_result_dialog.py#L1670]` | 79 项 Results 功能矩阵全景浏览器与一键启动器。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `DihedralChartDialog` | `[MolForge/molforge/ui/views.py#L519]` | Chem3D `Dihedral Chart` / GaussView `Scan`：共轭二面角扭转势能曲线分析对话框。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `BuilderFragmentDialog` | `[MolForge/molforge/ui/views.py#L555]` | GaussView `Builder -> Element / Ring / R-Group / Biological / Custom Fragment` 构件库对话框。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ModifyInternalCoordDialog` | `[MolForge/molforge/ui/views.py#L659]` | GaussView `Builder -> Modify Bond / Modify Angle / Modify Dihedral` 精确内坐标修改对话框。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `AIMQTAIMDialog` | `[MolForge/molforge/ui/dialogs/aim_qtaim_dialog.py#L46]` | Multiwfn 波函数分析控制面板。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `CalChemOrbitalsDialog` | `[MolForge/molforge/ui/dialogs/calchem_orbitals_dialog.py#L32]` | CalChem 纯 Rust 分子轨道能级阶梯与 3D 渲染控制面板。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `_EmbeddedTable` | `[MolForge/molforge/ui/dialogs/element_fragments.py#L15]` | Scientific calculation / setup modal | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ElementFragmentsDialog` | `[MolForge/molforge/ui/dialogs/element_fragments.py#L56]` | Scientific calculation / setup modal | Floating Layer / Modal | `Phase 2-3 Migration` |
| `GaussianCalculationSetupDialog` | `[MolForge/molforge/ui/dialogs/gaussian_calculation_setup.py#L22]` | GaussView 风格 11 页签 + 6 按钮 Gaussian Calculation Setup 对话框。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `HpcJobDialog` | `[MolForge/molforge/ui/dialogs/hpc_job_dialog.py#L30]` | Linux HPC 超算作业提交与任务管理对话框。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `VibrationalSpectrumDialog` | `[MolForge/molforge/ui/dialogs/vibrational_spectrum_dialog.py#L161]` | 简正振动光谱与 3D 视口振动动画交互工作台。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ToolPathConfigDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L41]` | 第四步：统一外部科学工具探测与路径配置对话框（配置持久化保存在 QSettings 中）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ExternalWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L227]` | 通用与专项科研工作流对话框基类（全中文界面、支持参数面板扩展、工具状态自检、后台 QThread 执行与结果预览）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `EspSurfaceWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L441]` | 1. ESP 表面分析对话框（选择 fchk -> 调用 Multiwfn + VMD -> 输出描述符表格 + BWR 表面图）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `HomoLumoWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L464]` | 2. HOMO-LUMO 能级图对话框（选择多个 fchk -> 提取能级 -> 画阶梯图 + 轨道图）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `OscEnergyDiagramWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L471]` | 3. OSC 能级对齐图对话框（给体+受体 fchk+log -> 画能级对齐图 + Excel + PPTX）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `ReorganizationEnergyWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L478]` | 4. 重组能计算对话框（输入中性/阴离子 4 个 log 计算 λh/λe 与 Marcus 速率，或从结构生成 4 个 gjf）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `DipoleAnalysisWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L515]` | 5. 偶极矩分析对话框（读取 fchk -> 显示总偶极矩矢量与 Debye 数值 + VMD 箭头）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `PlanarityAnalysisWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L522]` | 6. 分子平面性分析对话框（SVD 最佳拟合平面 -> RMSD/MPP + 最大离面距离 SDP + PQR）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `MdRdfWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L529]` | 7. MD 后处理：RDF 径向分布函数对话框（选择结构/轨迹 -> 计算 g(r) 曲线 + 导出 gmx rdf 脚本）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `IgmhInteractionWorkflowDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L550]` | 8. IGMH 弱相互作用对话框（生成二聚体 igmh.gjf 或调用 Multiwfn 20->10 计算 IGMH 等值面）。 | Floating Layer / Modal | `Phase 2-3 Migration` |
| `MdStudioDialog` | `[MolForge/molforge/ui/shells/workflow_inputs.py#L600]` | 统一外接分子动力学工作台：选择真实 GROMACS 轨迹，做 RMSD/Rg/RMSF/RDF/氢键分析。 | Floating Layer / Modal | `Phase 2-3 Migration` |

### 2.2 Docks & Panels

| Class Name | Source File | Description | Target Layer | Status |
|---|---|---|---|---|
| `ModelExplorerDock` | `[MolForge/molforge/ui/views.py#L71]` | Chem3D / GaussView 风格模型结构树浏览器（支持停靠、浮动、关闭与点击选中联动）。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `CartesianTableDock` | `[MolForge/molforge/ui/views.py#L161]` | GaussView `Atom List` / Chem3D `Cartesian Table`：支持直接编辑 X/Y/Z 坐标与单原子半径百分比。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `MeasurementTableDock` | `[MolForge/molforge/ui/views.py#L282]` | Chem3D `Measurement Table` / GaussView `Redundant Coordinates`：列出全部键长、键角与二面角。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `AtomBondPropertyDock` | `[MolForge/molforge/ui/views.py#L384]` | GaussView `Results -> Atom Properties / Bond Properties` 独立可停靠属性总表。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `AtomLabelOverlay` | `[MolForge/molforge/ui/atom_labels.py#L9]` | Dockable scientific workspace panel | Floating Glass Layer | `Phase 2-3 Migration` |
| `Editor2DWidget` | `[MolForge/molforge/ui/editor2d_widget.py#L51]` | ChemDraw 级可交互 2D 分子编辑器（世界坐标 Å <-> 屏幕像素精确双射）。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `MolStarWidget` | `[MolForge/molforge/ui/molstar_widget.py#L37]` | Dockable scientific workspace panel | Floating Glass Layer | `Phase 2-3 Migration` |
| `LeftPanel` | `[MolForge/molforge/ui/panels.py#L313]` | MolForge 现代科学建模工具箱与结构树 (LeftPanel) | Floating Glass Layer | `Phase 2-3 Migration` |
| `RightPanel` | `[MolForge/molforge/ui/panels.py#L1414]` | Dockable scientific workspace panel | Floating Glass Layer | `Phase 2-3 Migration` |
| `EnergyLevelCanvas` | `[MolForge/molforge/ui/qc_result_dialog.py#L40]` | 出版级 HOMO-LUMO 能级阶梯对比图实时渲染组件（支持导出 SVG/PDF/PNG）。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `AnalysisPlotCanvas` | `[MolForge/molforge/ui/qc_result_dialog.py#L1023]` | 通用科学谱图/曲线/直方图实时绘制画布（支持导出 SVG / PNG）。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `SelectionOverlayWidget` | `[MolForge/molforge/ui/render3d_widget.py#L88]` | 支持矩形框选 (Box) 与自由套索/多边形 (Lasso/Polygon) 的半透明青色高亮绘制层。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `Render3DWidget` | `[MolForge/molforge/ui/render3d_widget.py#L121]` | Studio 3D 分子建模与渲染视口（零崩溃异步事件状态机）。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `SettingsPanel` | `[MolForge/molforge/ui/settings_panel.py#L72]` | 模块化渲染与外观设置面板。 | Floating Glass Layer | `Phase 2-3 Migration` |
| `SvgPreview` | `[MolForge/molforge/ui/views.py#L42]` | Dockable scientific workspace panel | Floating Glass Layer | `Phase 2-3 Migration` |
| `_DihedralPlotCanvas` | `[MolForge/molforge/ui/views.py#L472]` | Dockable scientific workspace panel | Floating Glass Layer | `Phase 2-3 Migration` |
| `IRSpectrumCanvas` | `[MolForge/molforge/ui/dialogs/vibrational_spectrum_dialog.py#L32]` | 红外吸收光谱 (IR Spectrum) 交互式渲染画布。 | Floating Glass Layer | `Phase 2-3 Migration` |

---

## 3. Registered Scientific Analyses (0 Modules)

| Code | Module Title | Category | Backend Engine | Desktop UI Status |
|---|---|---|---|---|

---

## 4. OSC Building Block & Fragment Library

1. **OSC Donor/Acceptor Cores**: Y6, ITIC, BDT-F, Pentacene, Carbazole, Fluorene, Thieno[3,2-b]thiophene.
2. **GaussView Element Fragments**: C, N, O, S, P ideal coordination geometry templates (Linear, Bent, Trigonal, Tetrahedral, Trigonal Bipyramidal, Octahedral).
3. **Ring Templates**: Benzene (6-Ar), Cyclohexane, Cyclopentane, Thiophene (5-S), Pyrrole (5-N), Furan (5-O), Pyridine (6-N).
4. **Functional Endgroups**: Fluorine (-F), Chlorine (-Cl), Bromine (-Br), Hydroxyl (-OH), Amino (-NH2), Nitro (-NO2), Cyano (-CN), Methoxy (-OCH3), Vinyl, Ethynyl.

---

## 5. UI/UX Architecture Evolution

### 5.1 Why the Previous Layouts Failed
- **Gen 1 (PyQt6)**: Inflexible fixed side panels; top control strips wasted 160px+ vertical space and could not be collapsed.
- **Gen 4 Initial**: Squeezed 3D viewport between rigid full-height sidebar and inspector; hid 95% of PyQt6 features; broken AI copilot.

### 5.2 The New Layered Architecture (MolForge Studio 8.1)
- **100% Screen Viewport Canvas**: 2D and 3D WebGPU canvases stretch to 100% of the window.
- **Native Top Menu Bar**: 10-menu system directly exposing 343 scientific commands with global shortcuts.
- **Slim Contextual Toolbar**: Collapsible single-row bar (<36px) that can be hidden with 1 click (`Ctrl+B`).
- **Floating Glass Layers**: Panels (Inspector, AI Copilot, Fragment Library, Calculations, Orbitals) exist as movable, minimizable, translucent floating HUD layers that never restrict the canvas.
