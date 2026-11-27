# MolForge Studio 8.1 全量修复 · 操作记录（OPERATION_LOG）

工作区：`E:\YDW\Trae_Chemdraw\docs\desktop\fix_20261120\`
基线：`audit_20261119\MolForge_Studio_8.1_真实性验收报告.md`（RED 11 + YELLOW 18）
原则：改前备份、真进程实测、失败诚实报错、禁 C 盘安装、可回滚。

## 1. 备份与回滚（已完成）

- `backup\` 镜像备份 27 个待改文件 + `MANIFEST.txt`（含旧 `molforge-server.exe`）。
- 回滚方法：按 MANIFEST 将 backup 内文件覆盖回原路径；服务回滚 = 停新进程 → 拷回旧 exe → 冷启动。
- 源码另有 git 工作区差异可对照（未提交，保留现场）。

## 2. 真进程探测（probe\，已完成）

| 时间序 | 操作 | 产物 |
|---|---|---|
| P1 | Multiwfn 3.8 主菜单实测：20=弱相互作用（技能表写 13 为错） | menu_main.txt |
| P2 | 子菜单 2=promolecular NCI（仅坐标）/1=波函数 NCI | menu_rdg.txt / menu_nci.txt |
| P3 | 网格 1（低质量）→ 后处理 2 导出 output.txt → 0 → q | menu_post.txt |
| P4 | 苯真跑：134064 散点、2-3s；五列取第 4/5 列 | run_real.txt / output.txt |
| P5 | 子菜单 q 退出码 59、主菜单 q 为 0；成功判据 stdout 含 "Calculation of grid data" | run_real.txt |
| P6 | 开 Clash Verge 代理 → PubChem PUG REST 取 ITIC/Y6/C60 ConnectivitySMILES | pubchem_*.json |
| P7 | RDKit ETKDG+MMFF 生成苯/并五苯/ITIC/Y6 坐标；C60 用截角二十面体数学构造+几何法键级 | gen_fragments.py / fragments_gen.rs.txt |

## 3. Rust 后端修改（molforge-core\crates\）

- `molforge-core/src/engines.rs`
  - ExternalRunOutput 增 energy_hartree / converged / timed_out；run_with_timeout 600s 护栏；parse_last_energy。
  - run_xtb_native：解析 "total energy" 末行 + .xtboptok 收敛判据。
  - run_multiwfn_native 全重写：真实序列 20→(1|2)→1→2→0→q；散点取 cols[3]/cols[4]；stride≤20000；metrics 含 total_scatter_points/sampled_points/grid_wall_s/mode；ok=false 诚实文案。
  - **诚实门禁**：仅 WFN-12/WFN-NCI/NCI 走真序列；其余 WFN 编号返回 ok=false + unavailable 说明（不跑 NCI 冒充 ESP/Mayer/ADCH）。
  - run_external_native：ORCA input.inp / Gaussian input.gjf 真 spawn；keywords 覆盖路线行；能量标记解析；元素符号用 elements::symbol_of。
- `molforge-core/src/commands.rs`：新增 SetBondOrder（order=4→aromatic）、MoveAtom2D、SetAtomCharge（i8 字段 cast 三处：执行/undo/redo）；AddRing 增 hetero 杂原子表；UndoAction::AtomChargeChanged 双臂；补测试 thiophene_ring_hetero_and_set_bond_order。
- `molforge-core/src/io.rs`：write_xtb_input（xtb 命令注释行 + 真 xyz）。
- `molforge-core/src/workflow.rs`：capability_has_adapter + gate_adapters；execute 与 plan 双门禁（md-rdf → blocked）。
- `molforge-core/src/python_worker.rs`：无 Python 回退 ok:false / formula:null / mw:null + 错误文案（不再硬编码 C/12.011）。
- `molforge-core/src/presets.rs`：fragment_catalog 拼入 benzene/pentacene/itic/y6/c60 真实坐标（12/36/186/187/60 原子）。
- `molforge-server/src/main.rs`
  - move_atom 认 pos_2d 对象；add_ring 认 center_2d + hetero；delete_atoms 认 ids|atom_ids 且空→400。
  - 新路由 /api/edit/set_bond_order、/api/edit/set_atom_charge（charge 范围 [-4,4] 否则 400）。
  - export_input 认 engine|kind + xtb 分支。
  - run_external 真跑：status completed/failed/timeout + exit_code/energy_hartree/timed_out/stdout_tail。
  - analysis/run 诚实分派：WFN*→Multiwfn、CORE*/FRONTIER/HOMO→TB、其余 unavailable。
  - jobs/submit 全真分派（xtb/orca/gaussian/calchem 各 sp/opt；md_rdf→Err；未知→Err）。
  - ai/chat：删硬编码 Key；api_key/base_url/model 与 ai_* 双别名；离线显式前缀"【离线降级·本地紧束缚模板，非 AI 生成】"+offline/offline_reason；文档替换仅限显式构建指令+document_replaced 标记。
  - **run_calchem 契约对齐**：认 mode:"opt"|"sp"；响应 ok/mode/homo_ev/lumo_ev（Hartree→eV）/error；available=false 或零能量→ok:false。
  - **run_xtb 契约对齐**：认 gfn_level/apply_geometry；响应 ok/energy_hartree/converged/timed_out/exit_code/message/error/stdout_tail（ok 由退出码+能量解析决定）。

## 4. 前端修改（desktop\src\）

- `views/EditorView.tsx`：测量 HUD 全真 3D（距离/键角/二面角含符号与共面判据）；onSetBondOrder 真传 order；新增 onSetAtomCharge 接线。
- `services/api.ts`：setBondOrder/setAtomCharge 新方法；moveAtom 发 pos_2d 对象；exportQcInput kind 扩 gaussian|rest|orca|xtb；runExternalQc/runXtb 响应类型对齐；aiChat 增 offline 字段。
- `components/editor/Molecule2DCanvas.tsx`：电荷 prop 链路；元素热键仅在 atom 工具下生效（消 b/f 双重映射）。
- `components/editor/CanvasContextMenu.tsx`：形式电荷 -2..+2 设置段。
- `components/layers/CoordinatesTableModal.tsx`：真 x/y/z 三列 + 复制真 z；电荷列替代假"基态"。
- `components/layers/OrbitalLadderModal.tsx`：无数据显"—"（删 -5.50/-3.50 假默认）；能级条按真实 eV 动态刻度定位；EHT 诚实标注。
- `components/layers/FloatingWindow.tsx`：全局递增 z 计数（最后交互置顶）。
- `components/layers/CalculationSetupModal.tsx`：电荷/自旋先 setChargeSpin 真写入；calchem/xtb/external 全按 ok/status 诚实展示（失败红框）；freq/tddft 不支持引擎前置拦截；导出走 exportQcInput。
- `components/layers/FragmentsLayer.tsx`：锚点改 atom_id（index→find 映射）。
- `components/layers/AiCopilotLayer.tsx`：KaTeX 真渲染（$...$ / $$...$$）。
- `components/shell/StatusBar.tsx` + `store/useStudioStore.ts`：toast 堆栈（error 8s / 其余 4s，可关闭），pushNotification 同步发 toast。
- `components/shell/StudioHeader.tsx`：加氢菜单改诚实命名"3D 力场重排坐标"；fit 快捷键标注 Shift+F。
- `App.tsx`：Shift+F 重置视角、H 切换显式氢（atom 工具下让位元素热键）。
- `engine/camera.ts`：三向预设切严格正交投影（projMatrix+pickRay 同步），手动旋转回透视。
- `views/AnalysisView.tsx`：xtb/calchem 通知按 ok 诚实分级；Multiwfn 下拉未接入项 disabled；WFN-12 标签改准确；新增 ORCA/xtb 输入导出按钮；qcPreview 契约对齐。
- `tests/api_parity_contract.test.ts`：no-useless-escape 修复。
- `package.json`：katex + @types/katex（npm 缓存重定向 E:\YDW\Trae_Chemdraw\.npm-cache）。

## 5. 编译与验证轮次

| 轮 | 命令 | 结果 |
|---|---|---|
| C1 | cargo check --features calchem | FAIL 6 错（i8/i32）→ logs/cargo_check.log |
| C2 | 修 cast 后 check | PASS → logs/cargo_check2.log |
| C3 | 契约对齐后 check | PASS → logs/cargo_check3.log |
| B1 | release build（中途停，因源码继续修改） | 停止，缓存保留 |
| B2 | release build（最终源码） | 进行中 → logs/cargo_build_release2.log |
| F1 | tsc --noEmit | 1 错（qcPreview kind）→ 已修 → logs/typecheck_fix2.log |
| F2 | eslint / vitest | 进行中 → logs/lint_fix.log / vitest_fix.log |

## 6. 第三~五轮冒烟驱动的产品修复（补记）

| 轮 | 结果 | 新发现与处置 |
|---|---|---|
| S3 | 15 PASS / 1 FAIL | s12 判据误设"g16 必败"；实测本机 g16 真算成功（exit 0）但 energy=null、stdout 空 → 取证：Windows 下 g16/ORCA 主输出写工作目录文件 |
| S4 | 16 PASS / 0 FAIL | engines.rs run_external_native 合并 stdout + 工作目录 *.out/*.log（8MB 上限）解析能量；g16 E=-662.103913332 与 CalChem -662.103913149 交叉吻合；但 ORCA 仍 energy=null |
| S5 | 进行中 | 取证 ORCA 6.1.1 串行版无 input.out、stdout 空，能量在 input.property.txt 的 &FinalEnergy 行 → 产物读取扩展 *.txt；optimize 时回收 input.xyz 为 optimized_xyz 并据此判 converged |

- 服务 PID 链：33584(原)→6132(v2)→36504(v3)→32360(v4)→v5（见 logs/server_v5_*）。
- 前端热键重构（E2E C6/C7 判据要求 select 工具悬停换元素）：Molecule2DCanvas 改 ref + 单次 mount 监听 + select|atom 生效 + stopImmediatePropagation，消除 b/f/h 双映射；随后 npm run build（26.87s）+ build:renderer（3.56s），KaTeX 入包；此后前端无再改动。
- eslint 终态：0 error / 4 warning（自写审计脚本 flat config 不认 eslint-env，改精确 /* global */）；vitest 12/12；tsc 0 错。
- 第四轮 release 编译 1 个 warning（molforge-core lib，未展开明细，非错误）。

## 7. 第六轮冒烟与 E2E 五轮（补记）

- S6（v6）：16/16 PASS；ORCA 能量 -662.103913266278 回收（整行扫数修复）。三引擎交叉互差 ≤2e-7 Hartree。
- E2E 第 1 轮：FATAL 等"化学计算内核在线"超时 → 探针 10 端点全 200 → 归因系统代理劫持回环 → electron/main.ts setProxy direct://（改前备份 backup/desktop/electron/main.ts，MANIFEST 已登记）→ build:electron。
- E2E 第 2 轮（代理 ON 验证直连修复）：30/36；FAIL C6,C7,F2,F3,I1,I2。
- 归因与修复：I1=UI 不同步外部文档变更 → store syncExternalChanges + App 500ms revision 轮询；I2=判据窗口 ±60 截不到离线前缀 → 放宽 -300（s15 已证前缀存在）。
- E2E 第 3 轮：32/36；I1/I2 过；C6,C7,F2,F3 仍 FAIL。
- 探针 probe-hotkey（desktop/scripts/probe-hotkey-20261120.mjs）：干净态热键真生效；elementFromPoint 证实脚本"空白点"命中 SMILES 输入框（F2/F3 根因，Shift toggle 残留与观测值逐一对上）；C6/C7 根因=preset 后 sleep 600 与 500ms 轮询相位竞争，悬停旧 id 静默 no-op。
- 修复：空白点改右缘中部；preset 后 waitForFunction 原子数=24；产品侧热键改 id 解析防旧对象误改（Molecule2DCanvas.tsx）。
- E2E 第 4 轮：34/36（F2/F3 过，二面角 179.95° 真算）；C6/C7 待第 5 轮。
- vitest 复跑 12/12（含 sync 改动后）；build:renderer 两次 0 错。
- 经验补记 E11–E14；修复报告第四节扩至 9 真缺陷 + 3 测试校准。

## 8. 第七~八轮与收尾（补记）

- 第七轮 FATAL：一次性初始化离线；取证服务 PID 21056（8:57:10 启动，v6）存活、health 200 → 环境瞬态，不改动产品，第八轮复跑验证。
- 第六轮控制台取证 `[HK] skip o fragment 0` → 真缺陷#10 工具门控过严 → 悬停意图优先（任何工具下悬停+元素字母键换元素）+ id 解析加固；保留 console.debug("[HK]") 诊断日志。
- 第八轮：**36/36 PASS 0 FAIL**（logs/e2e_fix8.log）。基线 9 FAIL 全转 PASS。
- 代理 off 已执行（clash-verge skill proxy-control.ps1 off，输出 System proxy DISABLED）；第八轮在 off 后复跑同样全过。
- 修复报告定稿：MolForge_Studio_8.1_修复报告.md（判定 Conditional Fail → 通过）。

## 9. 遗留（见修复报告第六节）

jobs calchem 臂契约不一致、dist 发行包未重打包、C 盘 Temp 旧 molforge_* 遗留、1 个编译 warning、md-rdf 适配器待接入（诚实阻塞中）。