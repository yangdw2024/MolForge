# MolForge Studio — 任务进度看板 (TASK_BOARD)

> 所有 Done 状态均对应真实已执行并验证的测试输出或截图检查证据。

| 编号 | 阶段 | 任务项 | 状态 | 验证证据 |
| :--- | :--- | :--- | :--- | :--- |
| **P1-01** | Phase 1 | 真实源码审计 (`yangdw2024/MolForge` vs `lwang68/molforge`) | **Done** | 已盘点全部核心模块与 79 项 `AnalysisRegistry` |
| **P1-02** | Phase 1 | 产出 `docs/desktop/*.md` 全套 8 份文档 | **Done** | 全部 8 份文档写入并随每阶段回填验证记录 |
| **P2-01** | Phase 2 | 扩展 Python `api_bridge.py` 增量端点（片段库、分子库批量检查、`.mforge` 存取、后台 Job 队列、`.fchk/.log` 解析、安全偏好读写）并修复 `thiophene_trimer` / `triplet_o2` 预设缺陷 | **Done** | `unittest discover -s tests -p test_next_api_bridge.py -v` 4 项全通过（`3.438s`） |
| **P2-02** | Phase 2 | 初始化 `desktop/` Electron 35 + Vite 6 + React 19 + TS + Tailwind + Zustand 工程 | **Done** | `npm run build` 打包无错（`407.79 kB` JS） |
| **P2-03** | Phase 2 | 实现 Electron 安全 Main/Preload (`contextIsolation=true`, `nodeIntegration=false`, `sandbox=true`, CSP, 路径防穿越) & `.mforge` 自动恢复 | **Done** | Vitest `security.test.ts` 5 项全通过 + Playwright Renderer 隔离断言通过 |
| **P2-04** | Phase 2 | 建立 Obsidian/Arctic 双主题 Design System 与 Adaptive Workbench 五区骨架 | **Done** | 10 组真实界面截图视觉核验通过（含深/浅主题） |
| **P3-01** | Phase 3 | **Overview 科研启动首页**（新建 SMILES、`.mforge` 打开、最近工程、示例分子、32 万原子实测入口、崩溃恢复横幅） | **Done** | `scene_01_overview_obsidian.png` 视觉与 E2E 通过 |
| **P3-02** | Phase 3 | **Molecule Library 分子库**（表/卡双视图、清晰 2D SVG 缩略图、列切换、排序、批选 CSV 导出、批量 RDKit SMILES 导入） | **Done** | `scene_02_library_obsidian.png` 与 `test_studio_library_fragments_mforge_and_jobs` 通过 |
| **P3-03** | Phase 3 | **Molecular Editor 分子编辑器**（2D 矢量编辑、WebGPU 3D 视口、118 元素周期表、GaussView 3D 片段库、Undo/Redo、拖拽打开） | **Done** | `scene_03` / `scene_04` / `scene_09`（含 `1280×800` Arctic 适配）实测通过 |
| **P4-01** | Phase 4 | **Analysis Workbench 分析中心**（79 项真实分析、Tight-Binding OSC 能级阶梯图、`.fchk/.log` 解析、GJF/REST 输入生成、SVG/CSV 导出） | **Done** | `scene_05_analysis_obsidian.png` + `EnergyLadderChart`/`AnalysisPlotChart` 单测通过 |
| **P4-02** | Phase 4 | **Jobs & Workflows 任务中心**（真实后台任务 `Pending/Running/Completed/Failed/Cancelled`、日志、取消、重跑） | **Done** | `scene_06_jobs_obsidian.png` + 真实 TB 任务转 `Completed` 通过 |
| **P4-03** | Phase 4 | **Reports & Export / Settings / Command Palette (`Ctrl+K`) / AI 副驾驶侧栏** | **Done** | `scene_07` / `scene_08` / `scene_10` 实测通过 |
| **P5-01** | Phase 5 | 布局分栏记忆、快捷键、`1280×800` 小屏与 Arctic 浅色画布氢原子对比度修复 | **Done** | 修复 4 项视觉微瑕疵并二次截图复验通过 |
| **P6-01** | Phase 6 | TypeScript / ESLint / Vitest / Electron Playwright 10 场景 E2E | **Done** | `typecheck`、`lint`、`vitest`（10/10）、Playwright E2E 退出码 0 |
| **P6-02** | Phase 6 | `electron-builder` Windows x64 打包（NSIS 安装包 + Portable 单文件 + 免安装目录）并对打包后 `.exe` 跑通全套 10 场景 E2E | **Done** | `node scripts/run-electron-e2e.mjs --packaged` 退出码 0 |
