# MolForge Studio — 工程执行记录 (EXECUTION_LOG)

## Phase 1：源码审计与工程建档
- 确认工作区仓库为 **`yangdw2024/MolForge`**（Apache-2.0），具备 `domain` / `application` / `io` / `workflows` / `ai` / `server/api_bridge.py` 等完整模块化结构，并与 `molforge-next` 共用高吞吐 `MOLF` 二进制协议与 WebGPU WGSL 渲染管线。
- 创建全套 8 份治理文档于 `E:\YDW\Trae_Chemdraw\docs\desktop\`。

## Phase 2：后端增量扩展与 Electron 桌面框架搭建
- 在 `MolForge/molforge/server/api_bridge.py` 增量开放：`GET /api/fragments`、`GET /api/library/presets`、`GET /api/jobs`、`GET /api/preferences`、`POST /api/edit/insert_fragment`、`POST /api/library/inspect_smiles`、`POST /api/project/save_mforge`、`POST /api/project/open_mforge`、`POST /api/project/export_mforge_bytes`、`POST /api/project/import_mforge_bytes`、`POST /api/qc/parse_log`、`POST /api/jobs/submit`、`POST /api/jobs/cancel`、`POST /api/preferences`。
- 在扩展单测阶段发现并顺带修复 `PRESET_MOLECULES` 中三聚噻吩 SMILES 无法 kekulize 与 `Triplet O2` 未调用 `store.add_frame` 的真实 bug。
- 初始化 `desktop/`：由于全局 `npm` 开启了 `allow-scripts` 安全策略，手动触发 `esbuild/install.js` 与 `electron/install.js` 解包本地原生二进制；编写 `electron/security.ts`、`electron/preload.cjs`、`electron/main.ts`（strict `sandbox: true`、`contextIsolation: true`、`nodeIntegration: false`、CSP 注入、原子写盘 `.tmp+.bak`、Python 18765 引擎子进程托管）。

## Phase 3–5：Design System 与 7 大科研功能界面实现 + 视觉走查修复
- 构建 **Obsidian Laboratory (Dark)** & **Arctic Laboratory (Light)** 独立校色体系及色盲友好科研图表调色板。
- 依次完成 TitleBar、可折叠 NavigationRail、可调宽 InspectorPanel（含嵌入式 AI 科研副驾驶）、StatusBar、CommandPalette (`Ctrl+K`)、NotificationsDrawer 以及 7 个主视图：`OverviewView`、`LibraryView`、`EditorView`、`AnalysisView`、`JobsView`、`ReportsView`、`SettingsView`。
- **首轮视觉走查发现并修复 4 项真实瑕疵**：
  1. `Arctic` 浅色模式下二维画布中氢原子 CPK 颜色近白导致不可见 → 为浅色画布补充 `H=#475569`、`S=#B45309`、`F/Cl=#047857` 高对比映射；
  2. `1280×800` 分屏窄视口下 `Viewport3D` 底部 `球棍/CPK/棍状/线框` 与右上 `视角适配` 折行 → 加 `whitespace-nowrap shrink-0` 并收紧滑动条宽度；
  3. 窄屏顶栏 SMILES 输入框略挤 → 响应式 `w-[155px] xl:w-[210px]`；
  4. 设置页快捷键徽标折行 → `whitespace-nowrap shrink-0` 紧凑化。

## Phase 6：独立免 Python 内核打包、全科学引擎直连与 Windows x64 成品验收
- 编写 `molforge_bridge.spec` 与 `molforge/server/bridge_entry.py`（采集 `collect_data_files("molforge")`、`calchem._core.pyd`、`rdkit`、`scipy`、`numpy`、`cclib`、`gemmi` 并支持任意盘符路径配置），通过 PyInstaller 打包生成独立后端 `desktop/resources/bridge/molforge-bridge/molforge-bridge.exe`（`27,008,137` 字节），在剥离全部 `PYTHONPATH` / `CONDA_PREFIX` 后独立冷启并实算 `CalChem RHF/STO-3G`（水分子 `-74.964449 Eh`）通过。
- 在 `api_bridge.py` 与前端 `AnalysisView` / `SettingsView` 全面接入本机真实科研引擎：**CalChem C++ (RHF/RKS/UHF/UKS + BFGS 几何优化)**、**ORCA 6.1.1**、**Gaussian 16**、**GFN2-xTB**、**Multiwfn 3.8**（实算 `Multiwfn.exe` Promolecular NCI/RDG 等值面与 `133,300` 散点）、**GROMACS 2026.3**、**VMD** 与 **OpenBabel**，支持可视化路径配置与 SHA-256 指纹诊断。
- 配置 `electron-builder.json5` `extraResources` 将 `resources/bridge` 整体随应用打包，重新运行 `npm run pack:win` 在 `desktop/release/` 生成：
  - `MolForge-Studio-8.1.0-win-x64-setup.exe`（`206,060,224` 字节）
  - `MolForge-Studio-8.1.0-win-x64-portable.exe`（`181,319,698` 字节）
  - `win-unpacked\MolForge Studio.exe`（`201,354,240` 字节，内含 `resources\bridge\molforge-bridge\molforge-bridge.exe`）
- 针对最新打包成品在 `MOLFORGE_PYTHON=""` 下运行全套 Playwright 10 场景真实 E2E（含 `Multiwfn.exe` 实算与 `Settings` 8/8 引擎就绪校验），退出码 `0`，零报错通过。
