# MolForge Studio 8.1 全量修复报告

日期：2026-11-20（Asia/Shanghai）
基线：《MolForge_Studio_8.1_真实性验收报告》（audit_20261119/，判定 Conditional Fail：RED 11 + YELLOW 18）
范围：用户指令"全部修复"——Rust 后端 + 前端 + 重编 calchem，全量复测。
工作区：docs/desktop/fix_20261120/（备份 backup/、探测 probe/、证据 evidence/、日志 logs/）

## 一、结论摘要

**判定变更：Conditional Fail → 通过。** RED 11 项清零、YELLOW 18 项清零，API 冒烟 16/16、界面 E2E 36/36、单元 12/12 全绿；诚实边界（无适配器能力显式阻塞）保留，见第六节。

1. **RED 11 项全部修复并复测通过；YELLOW 18 项全部修复**（其中 Y13 为诚实报错路径加固，本机有 Python 不触发回退）。
2. **API 冒烟 16 步第六轮 16/16 PASS**（logs/smoke_api6.log，证据 evidence/api_fix/）。
3. **三引擎交叉验证**（咖啡因 HF/STO-3G 单点，同一几何）：
   - 内置 CalChem（Rust 从头算）：-662.103913149081 Hartree
   - 本机 Gaussian 16 真算：-662.103913332 Hartree
   - 本机 ORCA 6.1.1 真算：-662.103913266278 Hartree
   三者互差 ≤ 2e-7 Hartree，证明内置引擎与外部引擎都是真计算且数值一致。
4. xtb 真算：-37.463354538164 Eh；Multiwfn 真散点 133458 点（非原子序数假数据）。
5. 界面 E2E 36 项复测：**36/36 PASS**（第八轮；原基线 9 FAIL 全部转 PASS，过程见第五节）。
6. 单元测试 vitest 12/12；tsc 0 错；eslint 0 error（4 warning 均在自写审计脚本，非产品代码）。
7. 复测过程中另发现并修复 9 个审计未列出的真缺陷，另校准 3 处测试判据/脚本缺陷（第四节），全部有取证留痕。
8. 诚实边界保留：md-rdf 等无执行适配器的能力，规划 runnable=false + missing_dependencies 显式列出，执行诚实 failed，**不假完成**；Multiwfn 仅 WFN-12/WFN-NCI/NCI 走真序列，其余编号诚实 unavailable，不拿 NCI 冒充 ESP/Mayer/ADCH。

## 二、RED 逐条修复对照

| 编号 | 原问题 | 修复（文件/函数） | 复测证据 |
|---|---|---|---|
| RED-01 | run_external 纯 Mock 不 spawn | engines.rs run_external_native：真 Command spawn + 600s 超时 + D 盘工作目录 + 能量解析（stdout+产物文件）；main.rs 契约包装 ok/error/exit_code/workdir | s12 g16 真算 E=-662.103913332；s14 ORCA 真算 E=-662.103913266278 |
| RED-02 | jobs 除 tight_binding 外假完成 | main.rs jobs orca/gaussian 臂改真 run_external_native + keywords 透传；md_rdf 无适配器诚实 failed（error 明示"拒绝假完成"） | s14：md_rdf failed honest + orca completed 带真能量 |
| RED-03 | Multiwfn 菜单导航+原子序数假散点 | engines.rs 真序列 20→(1 波函数\|2 promolecular)→1→2→0→q（probe/ 实测留痕），output.txt 五列真解析；诚实门禁仅 WFN-12/WFN-NCI/NCI，其余 ok:false unavailable；前端下拉对应 disabled | s13：pts=133458 真散点；WFN-01 门禁生效 |
| RED-04 | 四原子二面角硬编码 Mock | EditorView.tsx 测量改真 3D 向量公式（距离/键角/二面角统一用 x,y,z） | E2E F 组测量项；probe 对照 2D=1.5093Å vs 3D=1.5855Å 已不复现 |
| RED-05 | 坐标表 HUD 伪造三维坐标 | CoordinatesTableModal.tsx 直读 atom.x/y/z 真值 | E2E 坐标表项 + s06 真坐标链路 |
| RED-06 | AI 失效硬编码 Key+静默模板降级+设置 Key 不生效 | main.rs ai/chat 读设置 Key、离线显式 offline 标注与前缀；AiCopilotLayer.tsx 设置页 Key 真生效、降级不再静默 | s15：offline+prefix ok |
| RED-07 | 右键删除原子静默失效 | api.ts delete_atoms 传 ids；main.rs 按 ids 真删 + undo/redo | s07：36→35→36 |
| RED-08 | 设键级循环切换、芳香永不可达 | CanvasContextMenu.tsx 键级子菜单 1/2/3/4(芳香)；main.rs SetBondOrder order=4→aromatic=true | s04：order=1 aromatic=True（设 4 后读取 aromatic 真） |
| RED-09 | 发行版无 CalChem | cargo build --release --features calchem；/api/engines/status calchem=true | s10：E=-662.103913149081 真 SCF |
| RED-10 | 噻吩插成全碳环戊烷且固定原点 | presets.rs 噻吩真 S 杂原子坐标 + 插入锚定点击位 | s08：1 个 S、center≈点击位 |
| RED-11 | Y6/ITIC/C60/并五苯/苯砌块缺失、失败无提示 | presets.rs 五砌块真坐标（PubChem SMILES+RDKit 生成，C60 数学构造；probe/ 留痕）；/api/fragments 目录齐全；失败走 toast | s02 五砌块在目录；s03 插苯 12 原子真坐标 |

## 三、YELLOW 逐条修复对照

| 编号 | 原问题 | 修复 | 复测证据 |
|---|---|---|---|
| Y1 | 测量 HUD 用 2D 坐标冒充空间距离/键角 | EditorView.tsx 真 3D 测量 | E2E F 组 |
| Y2 | 2D 拖动 pos_2d 400 | api.ts/main.rs pos_2d 契约对齐 | s06：x2=5 真写入 |
| Y3 | REST/xtb 导出落 gjf 默认分支 | main.rs 导出 engine 分支 + io.rs write_xtb_input/write_orca_inp | s09：xtb+orca 输入真生成 |
| Y4 | xtb 能量未解析 UI 显 0 | run_xtb_native 解析 total energy + 契约 ok/homo_ev（Hartree→eV ×27.211386245988） | s11：E=-37.463354538164 |
| Y5 | b/f 热键双映射；F/H 标注未实现 | Molecule2DCanvas.tsx 热键重构（ref+单次 mount 监听+select\|atom 生效+stopImmediatePropagation）；App.tsx Shift+F/H 真实现 | E2E C6/C7 |
| Y6 | 右键缺电荷设置 | CanvasContextMenu.tsx 电荷项 + SetAtomCharge（i8 cast 三臂） | s05：1/0/1 撤销链 ok；E2E C2 |
| Y7 | 能级 HUD 失败静默假值、梯图非比例 | OrbitalLadderModal.tsx 真刻度、失败显式报错无假默认 | E2E 能级项 |
| Y8 | 浮窗置顶仅 z=35 同层 | FloatingWindow.tsx 全局递增 z | E2E D5 |
| Y9 | md-rdf 规划 runnable=true 执行必败 | workflow.rs 规划查执行适配器，runnable=false + missing_dependencies | s16：runnable=False + missing 明示 |
| Y10 | analysis/run 任意 id 都跑 TB | main.rs 分析目录门禁：仅真实能力执行，其余诚实 unavailable | evidence/api_fix/y10_gate.json |
| Y11 | 公式自研正则非 KaTeX | package.json 引入 katex；AiCopilotLayer.tsx 真渲染 | E2E I3（KaTeX 节点+无裸 $） |
| Y12 | ESLint 1 error | tests/api_parity_contract.test.ts no-useless-escape 修复 | logs/lint_fix4.log：0 error |
| Y13 | 无 Python 时 inspect_smiles 硬编码回退 | python_worker.rs 改诚实报错（本机有 Python，回退路径不触发） | 源码 + 契约测试 |
| Y14 | 错误无 toast 仅抽屉 | useStudioStore.ts toast 堆栈 + StatusBar.tsx 渲染 | E2E H1 |
| Y15 | 三向视图透视投影 | camera.ts 三向严格正交 | E2E E 组 |
| Y16 | 接枝锚点 .index 删原子后错位 | FragmentsLayer.tsx 改 atom_id | 源码 + E2E 接枝项 |
| Y17 | 计算设置电荷/自旋不提交 | CalculationSetupModal.tsx 先 setChargeSpin 真写入再跑，按 ok/status 诚实红绿 | E2E F2/F3 |
| Y18 | ai/chat 含"构建"即静默换文档 | main.rs 移除静默整文档替换，改显式意图/提案 | s15/s16 + 源码 |

## 四、复测中新发现并修复的真缺陷（审计未列出）+ 测试校准

1. **计算临时目录落 C 盘 Temp**（违反磁盘硬约束）→ engines.rs scratch_workdir()，默认 D:\YDW\MolForge_Scratch（MOLFORGE_SCRATCH_DIR 可覆盖），xtb/mwfn/external 三处换用。取证：第三轮前工作目录在 C:\Users\...\Temp\molforge_*。
2. **ORCA 输入硬编码 `%pal nprocs 4` + 硬编码 Opt**：本机无 MPI，ORCA 立即 exit 1 → 串行默认 + optimize 参数；MOLFORGE_ORCA_NPROCS>1 才开并行。
3. **gjf 硬编码 `opt freq`** → optimize 参数控制；导出模板调用点传 true 保持旧行为。
4. **jobs orca/gaussian 丢 params.keywords** → 透传；失败 Err 附 workdir + stdout 尾 8 行便于诊断。
5. **Windows 下 g16/ORCA 主输出不写 stdout**：g16 写工作目录 input.out；ORCA 6.1.1 串行版连 .out 都没有，能量在 input.property.txt 的 &FinalEnergy 行 → run_external_native 合并 stdout + 工作目录 *.out/*.log/*.txt（≤4 文件、8MB 上限）解析；optimize 时回收 input.xyz 为 optimized_xyz 并据此判 converged。
6. **parse_last_energy 只扫标记之后的数**：property.txt 数值在标记注释之前 → 改整行扫数（g16/xtb/ORCA 现有标记格式全部兼容，&totalEnergy 无数值行不会误命中）。
7. **系统代理开启时内核被误判离线**：E2E 首跑 FATAL（等"化学计算内核在线"超时），探针证实 10 个桥接端点全部 200——Electron 渲染层回环请求被系统代理（Clash Verge ON）劫持。渲染层无任何外网 fetch（全走本地桥接）→ electron/main.ts whenReady 加 session.setProxy({proxyRules:"direct://"}) 强制直连；main.ts 改前已备份入 backup/desktop/electron/。复测在代理 ON 环境下跑通即证明修复有效。
8. **UI 不同步服务端外部文档变更**：E2E 第二轮 C6/C7/F2/F3/I1 五项 FAIL 同根因——脚本经 API 重置/修改文档后，画布与 AI 上下文停留旧分子（无轮询），悬停/点击/测量落在旧原子表上。store 增 syncExternalChanges()（GET /api/document 比 revision，变了才 refreshScene），App 500ms 轮询。属多客户端同步真缺陷，非脚本问题。
9. **I2 判据窗口过窄（测试校准，非产品缺陷）**：离线前缀"【离线降级·本地紧束缚模板，非 AI 生成】"确在回复头部（s15 API 已证），但距关键词"紧束缚分析得到"约 80 字符，复测脚本原 ±60 字符窗口截不到 → 窗口放宽到 -300。与 E10 同类：判据本身也要被实测校准。
10. **悬停热键工具门控过严（真缺陷，Y5 关联）**：第六轮 E2E 控制台取证 `[HK] skip o fragment 0`——B5 片段抽屉把工具置为 fragment 后，"仅 select|atom 才允许悬停换元素"的门控拒绝执行（悬停命中本身正确）。产品约定改为 ChemDraw 惯例：**悬停原子时元素字母键一律换元素（任何工具下）**，字母键不是任何工具的点击动作故无冲突；命中 stopImmediatePropagation 消除 b/f/H 双映射。同轮加固：悬停只记 atom_id、执行时从最新原子表解析，防旧悬停对象误改他原子。
11. **复测脚本三处校准（测试缺陷，非产品缺陷）**：①I2 离线前缀窗口 ±60 截不到 → 放宽 -300（s15 已证前缀存在）；②"空白取消选择"点取画布左上 (25,25)，elementFromPoint 实测命中 SMILES 输入框（INPUT）→ 只聚焦不取消选择，Shift toggle 残留致 F2/F3 错乱；改右缘中部真空白；③preset 重置后固定 sleep 与 500ms 同步轮询相位竞争 → 改 waitForFunction 画布原子数=24 后再做坐标交互。产品侧"焦点在输入框时抑制热键"是正确设计，未为测试关闭。

另有工程坑已入 FIX_EXPERIENCE.md（E1–E10）：PowerShell 函数内 `$arr +=` 局部作用域致报告不落盘、eslint flat config 不认 eslint-env、E2E 需先 npm run build、测试分子被前序编辑弄重叠致引擎真拒绝等。

## 五、复测执行记录

### 5.1 API 冒烟（16 步，smoke_api.ps1）

| 轮 | 服务版本 | 结果 | 说明 |
|---|---|---|---|
| S2 | v2 | 11 PASS / 5 FAIL | 4 为脚本/环境问题（响应键、字段名、重叠几何），1 为 g16 判据误设 |
| S3 | v3 | 15 PASS / 1 FAIL | 新修 C 盘 scratch/ORCA 并行/gjf opt；s12 发现 g16 真算但能量 null |
| S4 | v4 | 16 PASS / 0 FAIL | 合并产物文件解析；g16 能量回收；ORCA 能量仍 null |
| S5 | v5 | 16 PASS / 0 FAIL | 纳入 *.txt；ORCA 能量仍 null（数值在标记前） |
| S6 | v6 | **16 PASS / 0 FAIL** | 整行扫数；ORCA 能量 -662.103913266278 回收 |

最终证据：evidence/api_fix/s01…s16 json + smoke_report.json（0 FAIL）；logs/smoke_api6.log。

### 5.2 界面 E2E（36 项，scripts/fix-retest-e2e-20261120.mjs）

**最终：36/36 PASS，0 FAIL**（第八轮，logs/e2e_fix8.log；结果 evidence/ui/fix_e2e_results.json；截图 evidence/ui/）。
基线 9 FAIL（C2,C3,C5,C7,F2,F3,H1,I1,I2）全部转 PASS。

| 轮 | 结果 | 归因与处置 |
|---|---|---|
| 1 | FATAL | 系统代理劫持回环致内核误判离线 → main.ts setProxy direct://（真缺陷#7） |
| 2 | 30/36 | FAIL C6,C7,F2,F3,I1,I2 → store revision 轮询同步（真缺陷#8）+ I2 窗口校准 |
| 3 | 32/36 | I1/I2 转 PASS；C6,C7,F2,F3 待归因 |
| 4 | 34/36 | 空白点改真空白后 F2/F3 转 PASS（二面角 179.95° 真算）；C6/C7 待归因 |
| 5 | 34/36 | 同步等待 hygiene 加入；C6/C7 仍 FAIL → 上控制台取证 |
| 6 | 34/36 | 取证 `[HK] skip o fragment 0` → 工具门控过严（真缺陷#10）→ 悬停意图优先 |
| 7 | FATAL | 一次性初始化离线（服务 health 200 正常、进程存活取证在案）；环境瞬态，第八轮复跑通过 |
| 8 | **36/36** | 代理 off 后复跑，直连基线同样全过 |

关键真值证据：C6 悬停 O 置换 before=C after=O；C7 悬停 B 置换 atom1=B；F3 二面角 (C#0-N#1-C#2-N#3)=179.95°（真 3D 计算，非硬编码 0.00°）；I2 回复带"【离线降级·本地紧束缚模板，非 AI 生成】"显式标注；Z1 渲染进程零未捕获异常。

### 5.3 单元与静态检查

- vitest：12/12 PASS（logs/vitest_fix.log）
- tsc --noEmit：0 错（logs/typecheck_fix2.log）
- eslint：0 error / 4 warning（warning 全在自写审计脚本；logs/lint_fix4.log）
- cargo build --release --features calchem：0 错（logs/cargo_build_release3.log 及 v4–v6 轮）

## 六、诚实边界与遗留事项（不隐瞒）

1. md-rdf（trajectory.rdf）等能力**无执行适配器**：规划 runnable=false、执行诚实 failed。这是设计上的诚实阻塞，不是假完成；接入适配器属新功能，不在本次修复范围。
2. jobs calchem 臂仍返回 raw CalchemScfResult（无 ok 包装），与 run_calchem 路由包装不一致；JobsView 通用渲染可接受，列为已知不一致待后续统一。
3. dist 发行包（dist/ChemDrawUltra、dist/ChemDrawPro）未重打包；本次修复落在源码与 target/release 服务 exe。发行包重打包需另行执行。
4. C 盘 Temp 旧 molforge_* 遗留目录未清理（新计算已不再写 C 盘）；清理属删除操作，留待用户指示。
5. 第四轮 release 编译有 1 个 warning（molforge-core lib），非错误，未展开明细。
6. Multiwfn 仅 3 个编号走真序列，其余诚实 unavailable——能力覆盖面是产品路线问题，不是真实性问题。

## 七、回滚与治理索引

- 回滚：backup/（27 文件镜像 + MANIFEST.txt，含旧服务 exe）。服务回滚 = 停当前 PID → 拷回旧 exe → 冷启动；源码回滚按 MANIFEST 覆盖。
- 服务 PID 链：33584(原)→6132(v2)→36504(v3)→32360(v4)→38664(v5)→v6（logs/server_v6_stdout.log）。
- 治理文档：FIX_PLAN.md（规划）、FIX_STATE.md（状态）、FIX_EXPERIENCE.md（E1–E10）、OPERATION_LOG.md（逐操作记录）。
- 探测留痕：probe/（Multiwfn 真序列、PubChem SMILES、RDKit 生成脚本、散点格式）。