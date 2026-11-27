# MolForge 8.1 修复 · 经验文档（FIX_EXPERIENCE）

记录本轮多次执行错误与严重问题修复，供后续任务避坑。

## E1 PowerShell 函数内 `+=` 写不到父作用域
现象：smoke_api.ps1 第一跑证据文件齐全但 smoke_report.json 与 Tee 日志均不存在、stdout 全空。
根因：`function Step { $report += ... }` 中 `+=` 在函数局部作用域创建副本，父级 `$report` 始终为空数组；空管道进 Set-Content/Tee-Object 不创建文件。
修复：`$script:report += ...`。
教训：PS 脚本聚合结果必须显式作用域前缀；"文件没生成"先查管道输入是否为空。

## E2 ESLint flat config 不认 `/* eslint-env node */`
现象：给审计 .mjs 脚本加 eslint-env 注释后 error 不减反增（no-redeclare process/console）。
根因：eslint 9 flat config 忽略 eslint-env 注释；且 process/console 已是内置 global，重复声明报 no-redeclare。
修复：按文件精确 `/* global Buffer, setTimeout */`（只声明真正缺的）。
教训：flat config 下用 global 注释或 config 的 languageOptions.globals；不要照搬旧 eslintrc 习惯。

## E3 ORCA 输入硬编码 `%pal nprocs 4` 在本机必败
现象：ORCA 后台任务退出码 1，工作目录只有 input.inp 没有任何 .out。
根因：本机未装 MS-MPI，ORCA 见 nprocs>1 直接退出；且 write_orca_inp 硬编码 Opt 使 sp 任务变优化。
修复：串行默认（省略 %pal），MOLFORGE_ORCA_NPROCS 显式开并行；Opt 由 optimize 参数决定。
教训：外部引擎输入模板不要硬编码并行度/任务类型；失败时工作目录产物清单是第一诊断证据。

## E4 计算临时目录落 C 盘违反本机磁盘约束
现象：xtb/Multiwfn/ORCA workdir 全在 C:\Users\...\Temp。
根因：std::env::temp_dir() 默认 C 盘；用户硬约束活跃计算/临时文件必须在 D 盘(NVMe)。
修复：engines.rs scratch_workdir() 默认 D:\YDW\MolForge_Scratch，MOLFORGE_SCRATCH_DIR 可覆盖。
教训：任何 spawn 外部计算的代码，workdir 必须显式选盘，不能信系统 temp。

## E5 复测脚本期望值要跟着"诚实化"更新
现象：s12 期望 gaussian engine_not_found，但本机其实装了 g16（无许可证退出 1）；s14 期望 md_rdf submit 直接 400，实际 submit 200 + 任务异步 failed。
根因：审计期"未检测到"结论与运行期 find_engine_path 搜索范围不同；诚实化设计把拒绝放在执行期而非提交期。
修复：判据改为"真 spawn 且诚实失败/或缺失诚实标注"、"异步 failed 且 error 含适配器说明"。
教训：复测判据描述的是"诚实行为"而非某个固定错误码；写判据前先读实现确认拒绝发生在哪一层。

## E6 测试分子几何污染导致引擎真失败被误判为产品缺陷
现象：xtb 退出 128、ORCA 退出 1。
根因：前序编辑步骤（2D 插环/插片段）产生重叠原子，引擎真实拒绝。
修复：引擎类测试步前重置确定性 preset（咖啡因真 3D）。
教训：编辑类与计算类测试要隔离初始态；引擎非零退出先看重叠/电荷/自旋，再怀疑代码。

## E7 i8/i32 电荷字段 cast 三处缺一不可
现象：cargo check 6 错全在 SetAtomCharge。
根因：Atom.charge 是 i8，命令/undo 记录用 i32；执行臂、undo 臂、redo 臂三处赋值都要 as i8（比较处 as i32）。
教训：改字段类型相关命令时，grep 全部读写点（执行+undo+redo+测试），一次修全再编译。

## E8 Multiwfn 技能菜单表不可信
现象：技能写主菜单 13=RDG，本机 3.8 实测 20=弱相互作用。
修复：以 probe/ 真进程留痕序列为准（20→mode→1→2→0→q），成功判据 stdout 含 "Calculation of grid data" 且 output.txt 可解析。
教训：版本敏感 CLI 一律实测留痕，不抄文档/技能表。

## E9 Windows 下 ORCA/g16 主输出不在 stdout
现象：run_external 真算 exit 0 但 energy=null、stdout_len=0。
取证：g16 主输出写工作目录 input.out（53KB，含 SCF Done:）；ORCA 6.1.1 串行版连 input.out 都没有，能量在 input.property.txt 的 "&FinalEnergy [&Type "Double"] -6.62…e+02 "Final single point energy"" 行。
修复：run_external_native 合并 stdout + 工作目录 *.out/*.log/*.txt（最多 4 文件、8MB 上限）再 parse_last_energy；optimize 时回收 input.xyz 为 optimized_xyz 并据此判 converged。
教训：外部引擎"成功但无数据"先列工作目录产物文件，别只盯 stdout；解析标记行要核对产物里的真实行格式（property.txt 的 &totalEnergy 行无数值 token，不会误命中）。

## E10 冒烟判据要跟着实测事实改，不能凭旧印象
现象：s12 旧判据"g16 无许可证必败"，实测本机 g16 真算成功 → 误 FAIL。
修复：判据改三选一（真成功且有能量 / 诚实 engine_not_found / 真 spawn 诚实 failed）。
教训：验收判据本身也要被实测校准；引擎在不在、能不能算，以 find_engine_path + 真跑一次为准。

## E11 UI 必须同步服务端外部文档变更
现象：E2E 经 API 重置文档后，画布/AI 上下文停留旧分子，悬停热键、Shift 测量、上下文断言全错。
根因：store 无 revision 轮询，外部客户端/API 改文档后 UI 不知道。
修复：syncExternalChanges()（GET /api/document 比 revision，变了才 refreshScene）+ App 500ms 轮询。
教训：多客户端架构里"UI 只信自己发起的 mutation"是隐性单客户端假设；revision 轮询是最小同步机制。

## E12 系统代理会劫持 Electron 回环请求
现象：代理 ON 时 E2E 等"化学计算内核在线"超时；10 个桥接端点探针全 200。
根因：渲染层 fetch 127.0.0.1 走系统代理（Clash Verge），回环不在 bypass 列表。
修复：main.ts whenReady 里 session.setProxy({proxyRules:"direct://"})——渲染层无外网 fetch，直连安全。
教训：本地桥接型桌面应用应在主进程显式声明回环直连，别依赖系统 bypass 列表。

## E13 E2E 的"空白点"和焦点状态都要实测确认
现象：F2/F3 测量 FAIL，观测值恰为 Shift _toggle_ 残留选择（{2}、{0,1,3}）。
根因：脚本空白点取画布左上 (25,25)，实际命中 SMILES 输入框（elementFromPoint=INPUT）→ 点击只聚焦不取消选择；且焦点在 INPUT 时热键被正确抑制（产品行为正确）。
修复：空白点改右缘中部；探针 elementFromPoint 先验证命中 svg 再用作空白点。
教训：坐标类测试点必须 elementFromPoint 验证；"看起来空白"不等于事件落到画布。产品侧焦点抑制是正确设计，不要为测试关掉它。

## E14 悬停热键 FAIL 要用控制台取证归因，别猜
现象：C6/C7 悬停热键 FAIL；干净探针与四组二分探针（atom 工具/右键/Escape/删除）全成功；DIAG 命中 circle、焦点 BODY 均正常。
取证：渲染层 console.debug("[HK] skip/hit") + E2E console 捕获 → 第六轮日志 `[HK] skip o fragment 0` 一锤定音：B5 片段抽屉把 activeTool 置 fragment，"仅 select|atom" 门控拒绝。
修复：悬停意图优先——任何工具下悬停原子+元素字母键一律换元素（ChemDraw 惯例）；stopImmediatePropagation 消除双映射；悬停记 id、执行时解析最新原子表。
教训：交互类 FAIL 先加最小诊断日志拿事实，再改产品；固定 sleep 与异步同步轮询存在相位竞争，坐标交互前要等可观测同步条件（waitForFunction 原子数）。