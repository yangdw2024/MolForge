# MolForge Studio — 真实功能盘点与桌面端映射 (FEATURE_INVENTORY)

> 重要审计结论：当前工作目录仓库为 **`yangdw2024/MolForge`**（有机半导体 / 量子化学 / 2D-3D 分子建模 / 分子动力学工作站，License: Apache-2.0），**而非** GitHub 同名仓库 `lwang68/molforge`（单文件 HTML 药物化学 SAR/ADME/Kinase 工具）。因此 **MolForge Studio 严格不引入虚假的 SAR Matrix / ADME / MPO / AutoQSAR / Kinase Selectivity 假功能**，而是完整承接本仓库真实计算引擎。

## 1. 原始代码库真实能力清单（已逐文件核实）

| 领域 | 源文件模块 | 真实能力摘要 |
| :--- | :--- | :--- |
| **领域模型与大体系** | `molforge/domain/document.py`, `topology.py`, `ids.py`, `coordinate_store.py`, `massive_system.py`, `periodic.py` | `MoleculeDocument` 统一数据模型；稳定 `AtomId`/`BondId`（显示编号 `id+1`）；`CRYST1` 晶胞矩阵与 `box_origin`；32 万+ 原子矢量化数组存储 |
| **118 元素周期表** | `molforge/domain/elements.py` | 118 号完整元素周期表（中英文名、原子量、Pauling 电负性、VdW/共价半径、电子排布、族/周期/分区、CPK 配色） |
| **几何形态与自旋** | `molforge/domain/chemical_summary.py` | 3D 惯性张量特征值几何形态/点群判定（线型/平面/非平面）、电荷与自旋多重度语义解析（含 Triplet O₂） |
| **命令总线与撤销栈** | `molforge/application/command_bus.py`, `builtin_commands.py`, `fragment_commands.py`, `geometry_commands.py` | `AddAtom`, `AddBond`, `AddRing`, `ChangeElement`, `ChangeBondOrder`, `MoveAtom3D`, `CleanGeometry3D`, `DeleteAtom`, `DeleteBond` 及完整 Undo/Redo |
| **分类基团库** | `molforge/application/fragment_catalog.py` | GaussView 对标 3D 模板片段库（`C`/`O`/`N`/`Common`，包含甲基、乙烯基、乙酰基、苯环、噻吩、BDT 等精确局部坐标） |
| **结构 IO 与项目持久化** | `molforge/io/mforge_storage.py`, `rdkit_adapter.py`, `writers/*`, `readers/*` | 原生 `.mforge` v1.1 ZIP 工程（含 SHA-256 manifest 与原子保存）；读取 `.pdb`/`.xyz`/`.mol`/`.sdf`/`.cif`/`.mol2`；SMILES（RDKit ETKDG）三维构象生成 |
| **量子化学与 OSC 工作流** | `molforge/io/calculators.py`, `application/calculators/qc_input_generator.py`, `workflows/scientific_workflows.py` | 实时 Tight-Binding MO 求解（HOMO/LUMO/Gap/S₀→S₁ 跃迁）；Gaussian `.gjf` 与复旦 REST `ctrl.in` 生成；Gaussian `.log`/`.fchk` 真实轨道能量解析；PM6/Y6/ITIC/P3HT OSC 能级对比 |
| **79 项分析注册表与状态裁决** | `molforge/application/invalidation.py` (`AnalysisRegistry` + `CapabilityResolver`) | 覆盖 **基础结果(6)、波函数(17)、分子性质(8)、分子间作用(7)、光谱(8)、分子动力学(18)、OSC 专题(6)、药物化学(5)、分析工作流(4)**，共计 79 项真实能力与前置依赖判定（`ready` / `needs_external` / `unavailable`） |
| **WebGPU 3D 渲染与 2D 矢量** | `molforge-next/frontend/src/engine/*`, `Molecule2DCanvas.tsx` | 自研 WGSL Instanced WebGPU 管线，支持 321,554 原子 60 FPS、球棍/CPK/棍状/细线框模式、氢原子/晶胞框/坐标轴开关、2D 交互画布 |
| **AI 科研副驾驶** | `molforge/ai/mcp_bridge.py`, `server/api_bridge.py` (`/api/ai/chat`) | 对接本地 OpenAI 兼容端点（当前 `http://127.0.0.1:8045/v1`，`gemini-3.8-flash`），结合实时分子指标与紧束缚轨道生成 Google A2UI 卡片与建模指令 |

## 2. MolForge Studio（Electron 桌面端）模块映射

| 导航模块 | 功能定位 | 对接的真实后端能力 |
| :--- | :--- | :--- |
| **Overview (科研工作台)** | 项目启动中心、最近工程、快速新建/导入/预设、核心健康状态 | `/api/health`, `/api/build/preset`, `/api/build/smiles`, `/api/open`, Electron 本地最近文件与自动恢复 |
| **Molecule Library (分子库)** | 表格/卡片双视图、2D SVG 缩略图、搜索/筛选/排序/列宽调节、批量 SMILES 导入与快速载入 | `/api/molecules/library`, `/api/library/inspect_smiles`, `/api/fragment_catalog`, `/api/build/preset` |
| **Molecular Editor (分子编辑器)** | 2D 矢量编辑器 + WebGPU 3D 视口（可分屏/切换）、118 元素周期表、片段与环模板、几何清理与撤销/重做 | `/api/atoms`, `/api/document/binary`, `/api/elements`, `/api/fragments`, `/api/edit/*` |
| **Analysis Workbench (分析中心)** | 79 项 `CapabilityResolver` 分析浏览与执行、Tight-Binding OSC 能级阶梯图、Gaussian `.log`/`.fchk` 解析、GJF/REST 输入生成 | `/api/analysis/catalog`, `/api/analysis/run`, `/api/qc/tight_binding`, `/api/qc/parse_log`, `/api/qc/export_input` |
| **Jobs & Workflows (任务中心)** | 真实后台计算队列（Pending/Running/Completed/Failed/Cancelled）、运行日志、取消与重试、标准科研流水线向导 | `/api/jobs/submit`, `/api/jobs`, `/api/jobs/cancel` |
| **Reports & Export (结果与报告)** | `.mforge` v1.1 工程保存/打开、结构与量化文件导出（PDB/XYZ/MOL/GJF/REST）、科研分析报告 Markdown/JSON 导出 | `/api/project/save_mforge`, `/api/project/open_mforge`, `/api/export`, Electron 原生保存对话框 |
| **Settings (偏好设置)** | Obsidian/Arctic 主题切换、动态减弱、渲染默认设置、本地桥接服务状态、`.mforge` 自动备份策略、快捷键速查 | `/api/preferences`, Electron `userData` 配置持久化 |
