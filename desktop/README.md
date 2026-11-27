# MolForge Studio (Electron + WebGPU Desktop Workstation)

面向 `yangdw2024/MolForge`（Apache-2.0）的新一代专业桌面工作站，基于 **Electron 35 + React 19 + TypeScript + Tailwind CSS + Zustand + WGSL WebGPU + Python 化学引擎桥接**。

## 开发与启动命令

```powershell
# 1. 安装依赖（首次）
cd E:\YDW\Trae_Chemdraw\desktop
npm install

# 2. 生产构建并启动 Electron 桌面版（自动拉起 Python 18765 引擎桥接）
npm start

# 3. 仅启动 Vite 渲染层开发服务（配合 Python --bridge 热重载开发）
npm run dev:renderer
```

## 测试与验收命令

```powershell
npm run typecheck    # TypeScript 严格类型检查（Renderer + Electron Main）
npm run lint         # ESLint 静态检查
npm test             # Vitest 单元测试（IPC 安全防线 / MOLF 二进制协议 / UI 组件）
npm run test:e2e     # Playwright 启动真实 Electron 窗口并执行 10 场景端到端测试
node scripts/run-electron-e2e.mjs --packaged  # 针对打包后 .exe 执行端到端验证
```

## Windows x64 独立打包（内置免 Python `molforge-bridge.exe`）

```powershell
# 1. 可选：重新构建 PyInstaller 独立化学计算内核到 resources/bridge/molforge-bridge/
cd E:\YDW\Trae_Chemdraw
D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe -m PyInstaller --noconfirm --clean --distpath E:\YDW\Trae_Chemdraw\desktop\resources\bridge --workpath E:\YDW\Trae_Chemdraw\_build_tmp\bridge_work E:\YDW\Trae_Chemdraw\molforge_bridge.spec

# 2. 打包全套安装版与便携版（自动打包 resources/bridge）
cd E:\YDW\Trae_Chemdraw\desktop
npm run pack:win
```

产物输出目录：`E:\YDW\Trae_Chemdraw\desktop\release\`：
- `MolForge-Studio-8.1.0-win-x64-setup.exe`（NSIS 安装包，含内置独立内核）
- `MolForge-Studio-8.1.0-win-x64-portable.exe`（免安装便携单文件，含内置独立内核）
- `win-unpacked\MolForge Studio.exe`（绿色免安装目录，`resources\bridge\molforge-bridge\molforge-bridge.exe`）

## 说明与许可

- 本前端代码遵守 `MolForge` 根目录 [LICENSE](file:///e:/YDW/Trae_Chemdraw/MolForge/LICENSE)（Apache License 2.0）。
- 原版 PyQt6 桌面端（[MolForge](file:///e:/YDW/Trae_Chemdraw/MolForge)）与 Tauri 2 版本（[molforge-next](file:///e:/YDW/Trae_Chemdraw/molforge-next)）均完整保留，未受破坏。
