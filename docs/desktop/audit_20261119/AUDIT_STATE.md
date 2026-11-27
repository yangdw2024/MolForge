# 审计时点项目状态快照 (AUDIT_STATE) — 2026-11-19

## 版本与产物
- 桌面端：MolForge Studio 8.1.0（Electron 35 + React 19 + TS + Tailwind + Zustand + WebGPU WGSL）
- 后端：纯 Rust molforge-server.exe（2,335,232 B，2026-11-19 00:51 编译，晚于全部源码修改时间 → 产物新鲜）
  - 路径：E:\YDW\Trae_Chemdraw\molforge-core\target\release\molforge-server.exe
  - 路由：59 条 /api/*（main.rs 实测 grep），含全部 5 条历史 404 路由
- 备用后端：PyInstaller molforge-bridge.exe（desktop/resources/bridge/，11-17 打包）
- 发布产物：desktop/release/ 8.1.0 setup(95.1MB)/portable(86.3MB)/win-unpacked（11-19 15:44）
- 既有 E2E 截图：desktop/test-artifacts/ 12 张（11-19 16:03，已备份至本目录 evidence/ui/prev_test_artifacts/）

## 审计开始时运行态
- molforge-server / electron 进程：无
- 127.0.0.1:18765：未监听 → 本次审计自行冷启动（PID 记录于 OPERATION_LOG.md）
- GPU：本审计不涉及占显存任务，无需 Pueue 入队

## 治理文档基线（docs/desktop/）
MASTER_PLAN / ARCHITECTURE / DESIGN_SYSTEM / FEATURE_INVENTORY / FEATURE_PARITY(11-19) / EXECUTION_LOG / TEST_REPORT / TASK_BOARD / LESSONS_LEARNED（5 条历史教训：预设 kekulize、npm allow-scripts、preload CJS、Arctic 对比度、builder 宏）

## 已知风险点（审计重点核对）
1. Rust server 为 tiny_http + 全局 Mutex<AppState> + 每请求一线程：长计算持锁可能阻塞其他请求（死锁/卡顿风险）→ P1 并发探测
2. /api/ai/chat 依赖 DeepSeek 外网 API：需确认 Key 配置与真实网络往返（代理 Clash Verge 7897）
3. Multiwfn / Gaussian / ORCA / xtb 外部引擎路径探测（engines.rs 11-19 00:34 刚改过）
4. python_worker 发现逻辑：health 的 python_worker 字段真实性

## 审计收尾状态（2026-11-19 22:45 更新）

- 六阶段全部完成：42 项矩阵 = PASS 24 / PARTIAL 9 / FAIL 9；RED 11 项、YELLOW 18 项。
- 验收判定：**Conditional Fail**（壳层/底座/真实计算链达标；假完成与契约错配修复前不得宣称旗舰真实版）。
- 交付物：MolForge_Studio_8.1_真实性验收报告.md（主报告）、AUDIT_EXPERIENCE.md（经验）、AUDIT_PLAN.md、OPERATION_LOG.md、本文件。
- 证据资产清单：
  - evidence/api/：health/engines_status/fragments/contract_×6/contract_matrix.csv/memory_probe/deepseek_diagnosis/mismatch_×7+mismatch_summary/route_diff
  - evidence/engines/：p4_×10 + p5_×7 + phase4_5_summary.txt + xtb_stdout_full.txt + multiwfn_stdout_tail.txt + mwfn_crosscheck/full_stdout.txt + input_gaussian/orca/xtb.txt + hub_search_homo.json
  - evidence/ui/：audit_×27 截图 + scene_×11 截图 + 3 份 results.json + prev_test_artifacts/（旧图备份）
  - logs/：server_stdout/stderr、typecheck/lint/vitest/e2e_standard/e2e_audit/e2e_retest/e2e_micro、phase1_contract.ps1、phase2_mismatch.ps1、phase4_5_engines.ps1、phase4_5_run.log、test_exits.txt
  - desktop/scripts/：audit-e2e-20261119.mjs、audit-retest-20261119.mjs、audit-micro-20261119.mjs（可复跑回归）
- 运行态：molforge-server.exe PID 33584 保留（18765）；文档态=咖啡因；ai_api_key=""；产品源码零修改。
- 回滚：旧截图备份在 prev_test_artifacts/；无源码改动故无需代码回滚；停止服务 Stop-Process -Id 33584。