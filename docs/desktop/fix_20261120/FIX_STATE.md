# MolForge 8.1 全量修复 · 状态文档（FIX_STATE）

更新时刻：2026-11-20 09:1x（Asia/Shanghai）
基线：audit_20261119 验收报告 RED 11 / YELLOW 18。

## 当前状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| 规划+备份 | 完成 | FIX_PLAN.md；backup/ 28 文件 + MANIFEST.txt（含旧 exe 与 electron/main.ts） |
| Multiwfn 真序列探测 | 完成 | probe/ 留痕；20→(1\|2)→1→2→0→q；133458 点实测 |
| 五砌块真坐标 | 完成 | PubChem SMILES + RDKit；C60 数学构造；presets.rs 已拼入 |
| Rust 源码修复 | 完成 | 7 文件 + 复测期 engines.rs 三轮追加；release 0 错 |
| 前端源码修复 | 完成 | 16 文件 + electron/main.ts 代理直连；tsc 0 错 / eslint 0 error / vitest 12/12 |
| 服务替换 | 完成 v6 | PID 链 33584→6132→36504→32360→38664→v6；calchem=true |
| API 冒烟复测 | **完成 16/16** | 第六轮（v6）全过；ORCA 真能量 -662.103913266278 回收；三引擎交叉互差 ≤2e-7 |
| 界面 E2E 复测 | **完成 36/36** | 第八轮 0 FAIL；基线 9 FAIL 全转 PASS；过程八轮归因见修复报告第五节 |
| 修复报告 | **定稿** | fix_20261120/MolForge_Studio_8.1_修复报告.md（判定 Conditional Fail → 通过） |
| 代理恢复 | **完成** | clash-verge off 已执行；第八轮在直连基线复跑全过 |

## 复测期新修真缺陷（7 个，详见修复报告第四节）

1. 计算临时目录落 C 盘 → scratch_workdir() 默认 D:\YDW\MolForge_Scratch。
2. ORCA 硬编码 %pal nprocs 4（无 MPI 即崩）→ 串行默认 + MOLFORGE_ORCA_NPROCS 显式并行。
3. gjf 硬编码 opt freq → optimize 参数。
4. jobs orca/gaussian 丢 keywords → 透传 + 失败附 workdir/stdout 尾。
5. Windows 下 g16/ORCA 主输出不写 stdout → 合并工作目录 *.out/*.log/*.txt 解析；ORCA 能量在 input.property.txt &FinalEnergy 行；optimize 回收 input.xyz。
6. parse_last_energy 只扫标记后数值 → 整行扫数。
7. 系统代理 ON 时 Electron 回环被劫持致内核误判离线 → main.ts setProxy direct://（渲染层无外网 fetch，安全）。

## 冒烟轮次

S2 11/5（脚本与环境问题为主）→ S3 15/1 → S4 16/0（ORCA 能量 null）→ S5 16/0（同）→ S6 16/0 + ORCA 能量回收。

## 回滚

- 服务：Stop-Process 当前 PID → 拷 backup\molforge-core\target\release\molforge-server.exe 回 target\release → 冷启动。
- 源码：按 backup\MANIFEST.txt 覆盖还原（含 electron/main.ts）。
- 前端：dist 与 dist-electron 可由 npm run build 重现。

## 下一步（已于 2026-11-27 全部清零，见 `docs/desktop/upgrade_20261127/MolForge_Studio_8.1_升级验收报告.md`）

1. ~~jobs calchem 臂契约统一~~（已统一于 shared `format_calchem_json()`）；2. ~~dist 发行包重打包~~（已重建 8.1.0 setup/portable/win-unpacked 且 SHA-256 一致）；3. ~~C 盘 Temp 旧 molforge_* 清理~~（已清零，`C_TEMP_REMAINING=0`）；4. ~~md-rdf 执行适配器接入~~（已接入纯 Rust `compute_pairwise_rdf` 及 workflow/jobs 管线）；5. ~~1 个编译 warning 明细~~（已清除，0 errors / 0 warnings）。