# MolForge Studio 8.1 真实性全面审计 — 规划文档 (AUDIT_PLAN)

- 审计日期：2026-11-19（周四）
- 审计人角色：首席 QA 架构师 + 资深计算化学研究员
- 审计原则：Zero-Mock、端到端、全部结论必须附真实终端日志 / API 返回 / 截图证据；不接受推测性结论。

## 1. 项目工作流逆推（基于实际文件与时间线，非旧 AI 自述）

| 时间 | 事实（文件证据） |
|---|---|
| 10/26–11/06 | PyQt6 版 MolForge 7.x 迭代（MolForge/、MolForge_v8/ 保留） |
| 11/17 | Electron 35 + React 19 桌面端 `desktop/` 建成，Python 桥接 api_bridge.py，PyInstaller 独立内核 molforge-bridge.exe；治理文档 8 份于 docs/desktop/ |
| 11/18 | 纯 Rust 核心 `molforge-core/`（crates: molforge-core + molforge-server，tiny_http，127.0.0.1:18765），Hub/Workflow/Skills/PythonWorker 模块；HUB_ARCHITECTURE_ADR.md |
| 11/19 00:34–00:51 | engines.rs / main.rs 最后修改并重编 molforge-server.exe（2,335,232 B，00:51，比源码新 → 无需重编） |
| 11/19 01:18 | FEATURE_PARITY.md 更新（38 对话框 / 116 动作迁移清单） |
| 11/19 15:44–16:04 | 重新打包 8.1.0 setup/portable/win-unpacked，Playwright 10 场景截图已生成于 desktop/test-artifacts/ |
| 当前 | 无 molforge 进程运行，18765 未监听 → 审计需自行冷启动服务 |

**启动链**：electron/main.ts `resolvePythonBridgeLaunch()` 三级回退：
1. Rust `molforge-server.exe`（resources/core → desktop/resources/core → molforge-core/target/release）
2. 打包 Python 内核 molforge-bridge.exe
3. 本机 conda molforge-webengine Python -m molforge.server.api_bridge

**前端**：desktop/src（React19+Zustand+WebGPU WGSL），services/api.ts 对接 18765；
**测试设施**：npm run typecheck / lint / test (Vitest) / test:e2e (Playwright 真 Electron)；scripts/run-electron-e2e.mjs --packaged。

## 2. 审计执行规则

1. 所有证据落盘 `docs/desktop/audit_20261119/evidence/`（api / engines / ui / tests 子目录），日志落 `logs/`。
2. 审计以只读为主：不修改任何源码；如发现问题只记录文件+行号，不擅自修复（修复需另行批准并先 .bak_20261119 备份）。
3. 服务冷启动使用 `molforge-core/target/release/molforge-server.exe`，环境变量 MOLFORGE_PORT=18765；审计结束保留或关闭进程需在操作记录中注明。
4. 长任务（E2E、Multiwfn、CalChem）后台运行并轮询，不打断本机其他训练/计算任务（当前已确认无 GPU 任务冲突；本审计全部为 CPU 轻量计算，不入 Pueue GPU 队列）。
5. 每项判定给出 Pass/Fail + 耗时 + 证据路径；发现 Mock/404/死角直接标红并定位源码行号。
6. 磁盘约束：证据与文档写 E 盘归档区（本审计无活跃大计算，无 D 盘工作区需求）；禁止向 C 盘安装任何东西。

## 3. 回滚还原机制

- 本审计不删除、不移动、不覆盖既有文件；新增文件全部位于新建目录 audit_20261119/。
- 若需启动/停止服务：只操作本次审计自己 spawn 的进程（记录 PID），不杀既有进程。
- E2E 会写 desktop/test-artifacts/ 截图：执行前先把现有 12 张截图备份到 audit_20261119/evidence/ui/prev_test_artifacts/。
- 打包产物 release/ 不触碰。

## 4. 六阶段审计清单（对应用户 6 维度）

- P1 底座：进程/端口/health(python_worker)/内存稳定性 + 5 关键路由零 404（ai/chat、edit/clean_3d、edit/insert_fragment、library/inspect_smiles、qc/run_external）
- P2 UI：StudioHeader 38px 十大菜单+Ctrl+K；ChemicalToolRail 44px 抽屉；CanvasContextMenu 原子/键右键+悬停热键；5 大 HUD 玻璃层拖拽/折叠/层级；Ctrl+B；Front/Top/Side 相机
- P3 化学：SMILES 阿司匹林/咖啡因生成；Clean 3D 真实弛豫；Y6/ITIC/BDT/并五苯/C60 插入接枝原子数递增；Shift 2/3/4 原子测量精度
- P4 引擎：Rust Tight-Binding HOMO/LUMO/Eg + 能级梯图；CalChem SCF 收敛 Hartree；gjf/inp 生成合法性；Multiwfn 3.8 NCI/RDG 真实 stdout
- P5 Hub/AI：AI 上下文捕获+KaTeX；Hub 搜索匹配+工作流草稿；工作流执行 Provenance（RunID/SHA256/节点耗时）
- P6 交付：typecheck/Vitest/Playwright 真实执行摘要 + 状态矩阵 + 零容忍问题清单 + 截图路径 → 《真实性验收报告》