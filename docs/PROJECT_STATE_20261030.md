> 2026-11-03更新：以下是历史自报记录，当前修复/未验收状态以docs/ISSUE_MATRIX_20261103.md和CHANGES_20261103.md为准。当前源码7.3.1；不得继续引用历史“全部完成”作为验收证据。

# MolForge 当前状态文档（2026-10-30 22:37）

## 阶段
代码现状重建/取证完成，进入实际修复阶段。尚未改动业务代码（仅创建备份与文档）。

## 已验证事实
1. 入口 `main.py` 默认 welcome，欢迎窗真实可显示，四卡片。
2. 2D 渲染存在每帧全量重算问题（网格/坐标/sync/环中心），是几百原子卡顿根因之一。
3. 工作流对话框不接收当前文档，强制用户浏览磁盘文件——"模块连不上分子"根因已实证。
4. 3D 已有 LOD 与合并 render，真实瓶颈待实测。

## 任务进度（对应系统任务 #49–#58）
- #49 规划/状态/备份：已完成
- #50 2D 性能：已完成（327 原子完整重绘 15.84→6.41ms，约 2.47 倍 / 156 FPS）
- #51 3D 性能：进行中（框选 O(N²)→O(N) 已修，327 原子 144.9→11.6ms、4779 原子 29.6s→2.27s，约 13 倍）
- #52 2D 编辑：已完成（test_2d_editing + test_2d_qtest 全过，加/删原子、加/删键、改键级、撤销重做真实可用）
- #53 2D3D 同步/编号：已完成（新增 2D 编号角标；2D/3D 编号统一 1-based；修复命令总线变更后两视图不自动重建，test_2d3d_sync 全过；分屏实测）
- #54 分析直连/诚实标注：已完成（新增 export_document_to_xyz；对话框接收 document 自动预填结构、fchk/轨迹类诚实提示不伪造；8 子类透传；菜单调用传当前文档；test_workflow_canvas_link 全过；PLANE 端到端真实产出 SVD 数值）
- #55 MD 模块：已完成（新增 md_studio.py 内存安全分析 RMSD/Rg/RMSF/RDF/氢键、gromacs_submit.py 生成 ps1+Pueue 入队、MdStudioDialog 挂菜单；71554 原子真实轨迹 npt_500.xtc 验收，产出 csv/json/png；修复 RDF 自配对伪峰与氢键版本兼容）
- #56 MCP：已完成（新增 ai/mcp_bridge.py：OpenAI 兼容 function-calling，6 工具读结构/经命令总线编辑原子键/跑平面性；ui/llm_config_dialog.py 配置端点；菜单入口；修复 glog_reader 坏导入；test_mcp_bridge 13 项全过）
- #57 帮助/关于：已完成（统一权威版本 7.3.0；重写关于框真实能力清单与诚实边界；帮助菜单打开 docs/HELP.md；welcome/三子壳版本号统一）
- #58 回归/打包/提示词：已完成（核心回归 test_2d3d_sync/test_workflow_canvas_link/test_mcp_bridge 全过；清理临时产物；打包 MolForge_v7.3.0.zip 363 文件 8.7MB；docs/PROMPT.md 专业提示词）

## 回滚
- 备份位置：`backup_20261030/`（10 个核心文件，保留目录结构）。
- 回滚方法：将 backup_20261030 内对应文件复制回 molforge/ 原路径即可。
- 用户提供的 performance_fix.zip 已解压到 `_integration_perf_fix/`；其 document_tabs/workflow_inputs 比当前旧，
  仅作参考，不整体覆盖。

## 操作记录
- 22:37 创建 10 个核心文件备份；写 REBUILD_PLAN、PROJECT_STATE。
- 2D：环缓存(SSSR)、网格预渲染、隐藏氢集合、画笔/颜色/字体缓存、坐标向量化；修复 QColor(tuple) 非法构造导致的 native 崩溃。
- 修复三大 Studio 窗口 init_tabs 与 status_label 初始化顺序导致的启动崩溃（2D/3D/split 均已实测可启动）。
- 3D：框选结束改用 select_atoms_ordered 批量选择，消除逐原子 select 的 O(N²) 高亮重建，已用 perf_3d_box.py 验证。
