# MolForge Studio — 最终测试与验收报告 (TEST_REPORT)

## 1. 自动化检查实测汇总（全部在最终代码改动完成后执行）

| 测试类别 | 执行命令 | 退出码 | 实测结果摘要 |
| :--- | :--- | :---: | :--- |
| **TypeScript 类型检查** | `npm run typecheck` (`desktop/`) | `0` | Renderer (`tsconfig.json`) 与 Electron Main (`tsconfig.node.json`) 零错误 |
| **ESLint 静态检查** | `npm run lint` (`desktop/`) | `0` | 全工程 0 errors、0 warnings |
| **Vitest 单元 / 安全 / 组件测试** | `npm test` (`desktop/`) | `0` | 3 个测试文件 / **10 项测试全部通过** (`606 ms`)：<br>• `security.test.ts` (5/5)：路径穿越、相对路径、Null 字节、系统目录写拦截、HTTPS 外链白名单、严格 CSP<br>• `binary_protocol.test.ts` (2/2)：`MOLF` 二进制协议与晶胞解码、非法魔数拒绝<br>• `ui_components.test.tsx` (3/3)：2D 矢量缩略图、Tight-Binding 能级阶梯图、分析曲线组件与空状态 |
| **Python 化学引擎桥接单测** | `python -m unittest discover -s tests -p test_next_api_bridge.py -v` (`MolForge/`) | `0` | **Ran 5 tests in 22.768s, OK**：覆盖 `/api/health`、`/api/document/binary`、Tight-Binding、AI A2UI、SMILES/GJF/REST、Undo/Redo/118 元素/79 分析、片段库、分子库、`.mforge` 往返、后台 Job，以及 **CalChem SCF、GFN2-xTB 优化、Multiwfn NCI/RDG 与 GROMACS 脚本真实执行** |
| **独立免 Python 后端校验** | 剥离 `PYTHONPATH/CONDA_PREFIX` 启动 `molforge-bridge.exe --port 18799` | `0` | `HEALTH: True C8H10N4O2 24`、8/8 科学引擎探测为 `True`、内置 `CalChem RHF/STO-3G` 计算水分子 `-74.964449 Eh` (`HOMO -10.6372 eV`) |
| **Electron 打包成品 E2E（无外置 Python）** | `$env:MOLFORGE_PYTHON=""; node scripts/run-electron-e2e.mjs --packaged` | `0` | 直接冷启动 `desktop/release/win-unpacked/MolForge Studio.exe`（内置 `resources/bridge/molforge-bridge/molforge-bridge.exe`），验证沙箱隔离、**Settings 8/8 科学引擎 `已就绪`**、**AnalysisView 实时运行 `Multiwfn.exe` 生成 `133,300` 个弱相互作用散点**，全部 10 场景零未捕获异常通过 |

## 2. 视觉截图核验矩阵（`desktop/test-artifacts/`）

| 场景编号 | 界面与条件 | 截图文件 | 视觉检查结论 |
| :--- | :--- | :--- | :--- |
| Scene 01 | 首页工作台 Overview (Obsidian 1440×880) | `scene_01_overview_obsidian.png` | 布局紧凑克制，六边形科学底纹、快速 SMILES 与示例卡片无遮挡 |
| Scene 02 | 分子库 Library (Obsidian 1440×880) | `scene_02_library_obsidian.png` | 全 8 预设清晰 SVG 缩略图与分子量/SMILES 对齐良好，无模糊位图 |
| Scene 03 | 完整 118 元素周期表 + `"Pt"` 检索 | `scene_03_periodic_table_118.png` | 18 列等宽布局整齐，镧系/锕系独立展示，选中 `#78 Pt` 正常联动 |
| Scene 04 | 分子编辑器 Editor (Obsidian 2D+WebGPU 3D) | `scene_04_editor_obsidian.png` | 2D 与 WebGPU 60 FPS 同屏联动，右侧检查器与片段库完整无截断 |
| Scene 05 | 分析中心 Analysis Workbench (79 项 + 能级图) | `scene_05_analysis_obsidian.png` | HOMO/LUMO/Eg 阶梯图坐标轴单位清晰，符号+颜色双重编码，`CORE-01` 结构化表输出完整 |
| Scene 06 | 后台任务中心 Jobs (Tight-Binding Completed) | `scene_06_jobs_obsidian.png` | 真实计算耗时 (`0.6 ms`)、执行日志与 JSON 结果展示完整 |
| Scene 07 | 结果与导出中心 Reports (.mforge + Markdown) | `scene_07_reports_obsidian.png` | 五类化学/量化格式按钮与 Markdown 汇报预览完整 |
| Scene 08 | 偏好设置 Settings (Arctic Light 1440×880) | `scene_08_settings_arctic.png` | 极地白对比度自然，`sk-9ba...1660` 脱敏状态正确识别，快捷键胶囊单行不折行 |
| Scene 09 | 分子编辑器小窗适配 (Arctic Light 1280×800) | `scene_09_editor_arctic_1280x800.png` | 修复后浅色画布氢原子清晰可辨，底部 3D 工具栏与 `视角适配` 单行不折行 |
| Scene 10 | 全局命令面板 (`Ctrl+K`) | `scene_10_command_palette.png` | 键盘唤起迅速，可直达全部视图、分析项与预设分子 |
