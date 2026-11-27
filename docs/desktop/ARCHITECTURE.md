# MolForge Studio — Electron 桌面应用架构 (ARCHITECTURE)

## 1. 总体进程模型（三层隔离 + 科学计算桥接）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ MolForge Studio (Electron Main Process — Node.js / TypeScript)          │
│ - 无边框窗口生命周期 (min/max/close)、Bounds 持久化、CSP 拦截            │
│ - 受控原生对话框 (Open/Save) & 路径安全白名单检查                        │
│ - 原子写盘与备份 (.mforge/.pdb/.xyz/.gjf/.csv + .bak)、Session 崩溃恢复 │
│ - 管理本地 Python 引擎子进程 (127.0.0.1:18765)，退出时优雅清理           │
└───────────────────────────────▲─────────────────────────────────────────┘
                                │ contextBridge (仅暴露白名单方法)
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Preload Script (sandbox: true, contextIsolation: true)                  │
│ window.molforgeDesktop: WindowControls | Dialogs | ProjectIO | SysStats │
└───────────────────────────────▲─────────────────────────────────────────┘
                                │ React Props / Zustand Store
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Renderer Process (React 19 + TypeScript + Tailwind + WebGPU Engine)     │
│ - AppShell (TitleBar, NavRail, SplitWorkspace, Inspector, StatusBar)    │
│ - Views: Overview / Library / Editor / Analysis / Jobs / Reports / Set  │
│ - WebGPUMolEngine (WGSL Instanced 321k+ 原子 60 FPS) + 2D SVG Canvas    │
└───────────────────────────────▲─────────────────────────────────────────┘
                                │ HTTP + Binary "MOLF" Stream (127.0.0.1:18765)
┌───────────────────────────────▼─────────────────────────────────────────┐
│ Python Scientific Engine (`MolForge/molforge/server/api_bridge.py`)     │
│ - CommandBus (Undo/Redo), RDKit, Element/Fragment Catalog, Tight-Binding│
│ - 79 项 CapabilityResolver, .mforge v1.1 ZIP, JobManager, AI Copilot    │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. 安全设计清单

1. `BrowserWindow` 强制设置：
   - `contextIsolation: true`
   - `nodeIntegration: false`
   - `sandbox: true`
   - `webSecurity: true`
2. 禁止在 Renderer 中暴露 `fs`、`child_process`、任意 `ipcRenderer.send/invoke`；所有 IPC 在 `ipcMain.handle` 中做严格参数类型与路径白名单校验（扩展名过滤 + 拒绝 `..` 目录穿越及任意系统目录覆写）。
3. 生产模式通过 `session.defaultSession.webRequest.onHeadersReceived` 注入严格 CSP（仅允许 `'self'` 资源与 `http://127.0.0.1:18765` 本地引擎通信），屏蔽 `will-navigate` 跳出及不受信 `window.open`（外部链接仅允许 `https://` 并经用户确认后由 `shell.openExternal` 打开）。
4. 工程数据严格本地存储于 `%APPDATA%/MolForge Studio/` 与用户显式指定的目录，绝不静默上传用户科研结构或日志。

## 3. 本地数据持久化与 `.mforge` v1.1 兼容策略

- **工程格式兼容**：直接调用后端 `molforge/io/mforge_storage.py` 实现原生 `.mforge` ZIP 格式读写（保持 `SCHEMA = "1.1"`，保留 `AtomId`、`BondId`、2D/3D 坐标帧、外观属性与 SHA-256 校验，确保与原版 PyQt6 100% 互通）。
- **原子保存与崩溃恢复**：
  - 本地元数据、最近打开列表、工作区面板尺寸和用户主题保存在 Electron `userData/studio-state.json`（临时文件写入 + 重命名 + `.bak` 回退，坏文件捕获异常并弹出可恢复提示）。
  - 可配置的定时自动备份至 `userData/autosave/recovery.mforge`，软件意外关闭后重启提供一键恢复上一次会话。
- **离线运行策略**：前端 React、Tailwind 样式、Lucide 图标、字体兜底与 WebGPU WGSL 着色器全部随 Vite/Electron 本地打包，零外部 CDN 依赖；仅当用户主动点击 AI 副驾驶在线 LLM 推理或打开外链时明确标注依赖局部/外部代理服务。

## 4. 目录结构规划

```text
desktop/
├── package.json
├── tsconfig.json / tsconfig.node.json
├── vite.config.ts
├── electron-builder.json5
├── electron/
│   ├── main.ts            # Main 进程、窗口管理、Python 桥接托管、IPC 与文件安全读写
│   ├── preload.ts         # contextBridge 白名单 API
│   └── security.ts        # 路径穿越防护、后缀白名单、外链协议校验（独立单测覆盖）
├── src/
│   ├── main.tsx / App.tsx
│   ├── styles/tokens.css  # Obsidian & Arctic 双主题系统 + 缩放与动效媒体查询
│   ├── types/studio.ts    # 全量类型定义
│   ├── store/useStudioStore.ts  # Zustand 全局状态（主题/视图/文档/选区/Job/布局/未保存标识）
│   ├── services/api.ts    # Python Bridge HTTP + 二进制 MOLF 协议客户端
│   ├── engine/            # WebGPUMolEngine.ts / camera.ts / shaders.ts（支持明暗画布底色）
│   ├── components/
│   │   ├── shell/         # TitleBar, NavigationRail, InspectorPanel, StatusBar, CommandPalette
│   │   ├── common/        # EmptyState, MetricPill, SplitPane, ResizableTable
│   │   ├── editor/        # Molecule2DCanvas, Viewport3D, PeriodicTableModal, FragmentDrawer
│   │   └── charts/        # EnergyLadderChart, AnalysisPlotChart (色盲友好+SVG/CSV导出)
│   └── views/             # OverviewView, LibraryView, EditorView, AnalysisView, JobsView, ReportsView, SettingsView
└── tests/                 # Vitest (IPC安全/Store/二进制协议/适配层) & Playwright Electron E2E
```
