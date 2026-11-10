# MolForge 全面重建与修复规划（2026-10-30）

> 本文档基于对当前代码的实际阅读与运行取证，不采信历史"已完成"自述。
> 目标：把所有记录过的问题真实修复并逐项验收，最终交付压缩包与专业提示词。

## 一、已取证的真实入口与架构

- 统一入口：`main.py` 的 `run_application`，默认 welcome；`run_molforge.bat` 经 `scripts/launch.py` 走同一启动链。
- 欢迎窗真实存在（MolForge Studio v7.2，四个卡片：2D / 3D / 分屏 / 经典三栏）。
- 分层：domain（document/topology/coordinate_store）、application（command_bus/builtin_commands/selection）、rendering（vtk_backend）、ui（editor2d_widget/render3d_widget/shells）。
- 重活后端均为编译型：VTK(C++)、RDKit(C++)、NumPy(C)。Python 负责界面与编排。

## 二、经代码实证的问题与根因

### P1 性能（几百原子卡顿，用户最新重点）
- 2D `paintEvent` 每帧都全量重算：
  - 网格双重循环逐点 drawPoint（数千次）；
  - `_get_screen_coords` 每次全量 dict 推导；
  - `_ensure_world_coords_2d` 即使坐标齐全也每帧调 `sync_2d_coords_from_3d`（全量 O(N)）；
  - `_find_ring_centroids` 每帧全量。
- 鼠标移动每次都 `update()`，无节流；拖拽/框选高频触发上述全量。
- 3D 用 vtkGlyph3DMapper 把每原子渲染成独立高细分球体，需实测瓶颈；LOD 机制存在但需验证生效。
- 部分分析在 GUI 线程做重计算。

### P2 2D 编辑真实性
- 文档声称加/删原子、加/删键、环工具可用，但用户实测否定；需实际运行验证，修复后每步可撤销。

### P3 2D↔3D 同步 / 原子编号
- 需实测同步与编号；编号需在 2D/3D 稳定一致、可开关。

### P4 计算/结果模块
- 已实证：`ExternalWorkflowDialog` 全部要求用户点"添加输入文件"浏览磁盘，**完全不接收当前文档**——这就是"模块连不上分子、还要手动选文件"的根因。
- 79 项中大量共用路径/通用摘要冒充；未实现项必须 disabled 并如实标注。

### P5 分子动力学
- 缺少独立 MD 模块；需外接 GROMACS（路径/脚本/Pueue 队列）与 MDAnalysis（轨迹/RMSD/Rg/RDF/RMSF/氢键）。

### P6 LLM/MCP
- 需打通 MCP：LLM 读取当前分子、调用编辑与分析工具、回写结果；支持 OpenAI 兼容端点。

### P7 帮助/关于
- 关于对话框与帮助文档过时，需更新并移除夸大宣传。

## 三、修复方案与验收标准（逐项）

| 编号 | 修复 | 验收（必须有可复现证据） |
|---|---|---|
| P1-2D | 网格预渲染 QPixmap；屏幕坐标缓存+单原子增量；坐标变换向量化；update 节流 | 几百原子拖拽/框选帧率前后对比，截图+计时 |
| P1-3D | 实测瓶颈；验证 LOD；评估 impostor/实例化；命中检测向量化 | 真实分子旋转帧率对比 |
| P2 | 加/删原子、加/删键、改键级、环真实改分子 | 自动化脚本交互+分子状态断言 |
| P3 | 2D3D 双向同步、双视图高亮、编号 | 分屏实测+断言 |
| P4 | 对话框默认带入当前文档；未实现 disabled | 打开对话框即见当前分子，无需浏览 |
| P5 | MD 模块外接 GROMACS/MDAnalysis | 用本机 .xtc 真实出 RMSD/Rg/RDF |
| P6 | MCP 桥接 | LLM 真实调用工具改分子 |
| P7 | 更新关于/帮助 | 内容与真实功能一致 |
| 最终 | 全量回归、压缩包、提示词 | 全部测试通过后打包 |

## 四、执行纪律
- 修改重要文件前已备份到 `backup_20261030/`，可整体回滚。
- 活跃计算在 D 盘、E 盘仅归档、禁写 C 盘；GPU 任务走 Pueue。
- 不提问、自己决断、连续执行；每完成一项立即验收并记录到状态文档。
- 未实现功能一律 disabled 或如实标注，禁止假按钮、禁止降级冒充。
