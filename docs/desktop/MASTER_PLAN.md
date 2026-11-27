# MolForge Studio — Electron 桌面端总体实施计划 (MASTER_PLAN)

> 对应真实代码库：`yangdw2024/MolForge`（2D/3D 分子建模、有机半导体 OSC、量子化学 Tight-Binding / Gaussian / REST / Multiwfn 分析与 MD 工作站，Apache-2.0 协议）

## 1. 项目定位与目标

将现有的原版 **MolForge (PyQt6)** 与 **molforge-next (WebGPU 渲染内核)** 的科学计算与 32 万原子渲染能力，整合构建为全新商业级桌面应用 **MolForge Studio**（目录：`desktop/`），完全遵循：

- **视觉定位**：Scientific Precision × Modern Desktop × Premium Minimalism
- **双主题实时切换**：**Obsidian Laboratory**（深色）与 **Arctic Laboratory**（浅色）
- **绝对真实性**：全部计算、分析、文件持久化均直连 `MolForge` Python 科研内核（HTTP + `MOLF` 二进制协议 + `.mforge` v1.1 ZIP 工程存储），绝不伪造计算数据或虚构 `lwang68/molforge` 的药物发现指标。
- **零破坏隔离**：原版 `MolForge/` 与 `molforge-next/` 保持完整独立，Electron 新桌面端全部落在 `desktop/`，文档落在 `docs/desktop/`；仅对 `molforge/server/api_bridge.py` 做向后兼容的增量接口扩展。

## 2. 分阶段实施路线与验收标准

| 阶段 | 核心任务 | 关键输出产物 | 阶段验收条件 |
| :--- | :--- | :--- | :--- |
| **Phase 1：审计与架构** | 盘点真实 `MolForge` 模块；确定功能清单、设计规范与 IPC 安全边界 | `docs/desktop/*.md` 全套 8 份文档 | 真实模块映射无遗漏、无幻觉功能；架构文档明确安全边界与复用路径 |
| **Phase 2：设计系统与 Electron 框架** | 初始化 `desktop/`；实现无边框 Custom Title Bar、Obsidian/Arctic 主题、Navigation Rail、Status Bar、Inspector 骨架与安全 Preload/IPC | `desktop/electron/*`, `desktop/src/styles/tokens.css`, `AppShell` | `contextIsolation=true`, `nodeIntegration=false`, `sandbox=true`, `Ctrl+K`、缩放/窗口最大化还原可用，深浅色一键切换 |
| **Phase 3：后端增量与核心科研视图** | 扩展 `api_bridge.py`（Fragment/Library/Job/Save-Load `.mforge`/Fchk-Log 解析）；实现 Overview 首页、Molecule Library、Molecular Editor（2D + WebGPU 3D + 118 元素周期表） | `api_bridge.py` 扩展 + `OverviewView`, `LibraryView`, `EditorView` | 前后端 `MOLF` 二进制与 `.mforge` 双向读写无误；2D/3D 协同编辑与撤销/重做通过 |
| **Phase 4：分析工作台与真实任务流** | 接入 79 项 `CapabilityResolver` 分析、Tight-Binding OSC 能级对比图、Gaussian/REST 输入导出与日志解析、真实后台 Job Center 与 Reports | `AnalysisView`, `JobsView`, `ReportsView`, `SettingsView`, `CommandPalette` | 所有图表具备坐标轴、单位、图例、缺失提示与 SVG/CSV 导出；后台任务支持 Cancel/Rerun 且状态绑定真实执行 |
| **Phase 5：高级交互与稳定性打磨** | 分栏拖拽记忆、快捷键系统、文件拖拽打开、大数据集分页/虚拟滚动、`.mforge_autosave` 崩溃恢复、AI 副驾驶侧栏联动 | `useWorkspaceStore`, `Autosave`, `A2UI Drawer` | 支持 `1280×800` 与 `1920×1080`；32 万原子 PDB 流畅加载；断电/重启可恢复工程 |
| **Phase 6：全面验证与 Windows 打包** | 运行 TypeScript、Vitest（单测 + IPC 安全测试）、Electron Playwright E2E + 多场景真实截图视觉审计、`electron-builder` Windows x64 打包并实测运行 | `desktop/release/*.exe`、`TEST_REPORT.md`、`LESSONS_LEARNED.md` | 打包后的 `.exe` 离线直连本地引擎冷启动可用；9 类必检视图视觉与 E2E 全部留痕 |
