# MolForge Studio — 故障归因与预防机制 (LESSONS_LEARNED)

| 序号 | 实际遇到的问题 | 根本原因 | 修复方案 | 防止复发防线 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `library/presets` 报 HTTP 500 | 预设列表 `thiophene_trimer` SMILES 写法无法 kekulize，`triplet_o2` 未先调用 `store.add_frame` | 修正 `thiophene_trimer` 规范 SMILES 并为 `triplet_o2` 先追加坐标帧；库遍历增加单条错误隔离 | 在 `test_next_api_bridge.py` 中对全量预设建立自动化回读断言 |
| 2 | `npm install` 后 `electron` / `esbuild` 缺可执行文件 | 宿主全局 `npm` v11 默认启用 `allow-scripts` 阻止 postinstall 自动运行 | 显式运行 `node_modules/{esbuild,electron}/install.js` 并校验 `electron.exe` 存在 | 写入 `desktop/README.md` 与构建排查说明 |
| 3 | Electron 35 `sandbox: true` 与 ESM `"type": "module"` 冲突风险 | 沙箱化 Preload 在 Electron 中优先需要 CommonJS 入口 | 将 Preload 定为 `electron/preload.cjs` 在构建阶段复制至 `dist-electron/preload.cjs`，并为 ESLint 配置 `**/*.cjs` 规则 | E2E 首条强制验证 `window.molforgeDesktop.isElectron === true` 且 `window.require === undefined` |
| 4 | `Arctic` 浅色模式下 2D 画布 H 原子几乎不可见，且 `1280×800` 3D 工具栏折行 | 浅色模式下直接复用近白 CPK RGB 导致白底低对比度；窄屏分屏胶囊缺 `whitespace-nowrap shrink-0` | 针对浅色画布校准 `H/S/F/Cl` 墨水色，工具按钮加 `whitespace-nowrap shrink-0` | 将 `1280×800 + Arctic` 纳入 E2E 自动截图必检清单 |
| 5 | `electron-builder` 报错 `macro target is not defined` | `win.artifactName` 中误用了不支持的 `${target}` 宏 | 将具体文件名模板下移至 `nsis.artifactName` 与 `portable.artifactName` | 对打包产物执行真实 `--packaged` 端到端启动校验 |
