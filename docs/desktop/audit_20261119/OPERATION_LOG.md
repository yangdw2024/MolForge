# 审计操作记录 (OPERATION_LOG) — 2026-11-19

| 时间(约) | 操作 | 影响 | 可回滚性 |
|---|---|---|---|
| 16:10 | 阅读 docs/desktop 治理文档、desktop/electron/main.ts、molforge-core 源码 | 只读 | — |
| 16:12 | 新建 docs/desktop/audit_20261119/{evidence,logs}；备份 desktop/test-artifacts/ 12 张截图至 evidence/ui/prev_test_artifacts/ | 新增文件 | 直接删除新目录即可 |
| 16:14 | Start-Process 冷启动 molforge-server.exe，**PID=33584**，监听 127.0.0.1:18765，stdout/stderr 重定向 logs/server_*.log | 新进程 | 审计结束 Stop-Process 33584 |
| 16:16 | GET health / engines/status / fragments → evidence/api/*.json | 只读 | — |
| 16:18 | phase1_contract.ps1：6 路由真实调用（inspect_smiles 阿司匹林+咖啡因、clean_3d、insert_fragment phenyl@atom0、run_external orca、ai/chat）；期间文档被改为 Caffeine+phenyl（rev3），随后 POST build/preset caffeine 恢复 | 服务端内存文档状态变化 | 已恢复 caffeine 初始态 |
| 16:19 | 200 次串行 + 20 并发 health 压测：全部 200；WS 7.07→7.73MB，线程 10，无泄漏/死锁迹象 | 只读 | — |
| 16:21 | curl 直连 DeepSeek 诊断：网络可达 230ms，Key 无效（authentication_error）→ evidence/api/deepseek_diagnosis.txt | 外网只读请求 | — |
| 16:30 | phase2_mismatch.ps1：8 项前后端字段错配实测（T1-T8），期间文档 benzene→caffeine 切换，测试 Key 已清空恢复 | 服务端内存状态 | 已恢复 caffeine + 空 Key |
| 16:40 | 后台顺序执行 npm typecheck(0)/lint(1)/vitest(0)/test:e2e(0)，日志 logs/*.log；标准 E2E 10 场景全过，截图刷新 desktop/test-artifacts/ | 新截图覆盖旧截图（已备份） | 旧图在 evidence/ui/prev_test_artifacts/ |
| 16:50 | 路由集合差分：FE 52 ⊆ BE 58，零缺失 → evidence/api/route_diff.txt | 只读 | — |
| 17:00 | audit-e2e-20261119.mjs 四轮迭代运行（选择器修正），最终 36 项 27PASS/9FAIL，截图 evidence/ui/audit_*.png | 文档状态多次切换 | 脚本起始重置 caffeine |
| 17:20 | audit-retest-20261119.mjs 聚焦复测 F/I1/H1 | 同上 | — |
| 22:33 | audit-micro-20261119.mjs：键角107.4°/二面角Mock/通知抽屉 pentacene 失败记录 | 同上 | — |
| 22:36 | phase4_5_engines.ps1（修正 Hub items 字段后重跑）：22 项引擎/工作流真实调用，xtb/Multiwfn 外部进程、SHA256 独立复算匹配、md-rdf 诚实 failed | workdir 临时产物（%TEMP%） | 自动清理 |
| 22:40 | 截图汇总 evidence/ui/（41 文件）；目视核验 HUD/二面角/俯视截图 | 只读 | — |
| 22:45 | 撰写《MolForge_Studio_8.1_真实性验收报告.md》+ AUDIT_EXPERIENCE.md；更新 AUDIT_STATE | 新文件 | — |

## 收尾状态
- 服务 PID 33584 保留运行（监听 18765）；停止命令：Stop-Process -Id 33584
- 服务端文档态：咖啡因（md-rdf 工作流 validate 后未改动分子）；ai_api_key 已清空
- 产品源码零修改；全部新增资产见 AUDIT_STATE.md 资产清单

## Phase1 结论速记
- 6/6 路由 HTTP 200 + 合法 JSON，零 404、零 HTML 错误页 → 契约回归 Pass
- health: ok=true, python_worker=true, core=molforge-rust, document=Caffeine C8H10N4O2 24 原子 → Pass
- 内存/并发稳定性 → Pass（7.7MB 级轻量，20 并发全 200）
- 【红】/api/qc/run_external 为 Mock：main.rs:921-951 仅拼接命令字符串，status=completed 但未执行进程、workdir 0 文件
- 【红】/api/ai/chat 静默降级：内置 Key 失效（main.rs:1309），失败后模板文案冒充 AI 回答（main.rs:1322-1337），无离线标注
- 【黄】calchem feature 未编译（health.calchem=false，engines.calchem=false）→ Rust 服务端 CalChem 不可用，需核对前端实际调用链
- 【黄】Rust fragments 目录 19 项，无 Y6/ITIC/并五苯/C60 → 需核对前端 OSC 库数据来源