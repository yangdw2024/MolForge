# MolForge Studio 8.1 旗舰版真实性验收报告

- 审计日期：2026-11-19（周四）22:00–22:45（UTC+8）
- 审计角色：首席 QA 架构师 × 资深计算化学研究员
- 审计原则：**Zero-Mock、端到端、零推测**。全部判定基于真实终端日志、API 返回载荷、外部进程产物与真机 Electron 截图。
- 被测对象：`desktop/`（Electron 35 + React 19 + WebGPU WGSL）+ `molforge-core/target/release/molforge-server.exe`（2,335,232 B，2026-11-19 00:51 编译，晚于全部源码修改 → 产物新鲜，无需重编）
- 服务冷启动：PID 33584，监听 127.0.0.1:18765（审计自行 spawn，记录于 OPERATION_LOG.md）
- 证据根目录：`E:\YDW\Trae_Chemdraw\docs\desktop\audit_20261119\`（evidence/api、evidence/engines、evidence/ui、logs）

---

## 一、核验状态矩阵（6 模块 / 42 项）

状态：**PASS** 真实通过 ｜ **FAIL** 不通过 ｜ **PARTIAL** 部分达标

### Phase 1 底座服务与网络通信契约

| # | 核验项 | 状态 | 耗时 | 证据 |
|---|---|---|---|---|
| 1.1 | molforge-server.exe 稳定监听 127.0.0.1:18765 | PASS | 冷启动 2s | logs/server_stdout.log；Get-NetTCPConnection |
| 1.2 | /api/health：ok=true、python_worker=true、文档态 | PASS | 6ms | evidence/api/health.json（Caffeine C8H10N4O2 24原子） |
| 1.3 | 内存泄漏/死锁：200 串行+20 并发 health | PASS | 220 请求 | evidence/api/memory_probe.txt（WS 7.07→7.73MB，线程 10，全 200） |
| 1.4 | /api/ai/chat 零 404 + 合法 JSON | PASS(契约)/FAIL(真实性见 R6) | 347.5ms | evidence/api/contract_ai_chat.json |
| 1.5 | /api/edit/clean_3d 零 404 | PASS | 385ms | contract_clean3d.json（rev 递增，真实 RDKit） |
| 1.6 | /api/edit/insert_fragment 零 404 | PASS | 12ms | contract_insert_fragment.json（phenyl 接枝成功） |
| 1.7 | /api/library/inspect_smiles 零 404 | PASS | 290ms | contract_inspect_smiles.json（阿司匹林+咖啡因 RDKit 解析） |
| 1.8 | /api/qc/run_external 零 404 | PASS(契约)/FAIL(真实性见 R1) | 0.4ms | contract_run_external.json |
| 1.9 | 前后端路由集合差分（FE 52 ⊆ BE 58） | PASS | — | evidence/api/route_diff.txt（FE-only=∅） |

### Phase 2 工业级 UI 质感与 UX

| # | 核验项 | 状态 | 耗时/实测值 | 证据 |
|---|---|---|---|---|
| 2.1 | 38px 一体化顶栏（消除双层标题栏） | PASS | height=38.0px | audit_A_menu_cascade.png；E2E A1 |
| 2.2 | 10 大科研菜单（文件/编辑/构建/结构/计算/分析/结果/视图/图层/帮助） | PASS | 10/10 | E2E A2 |
| 2.3 | 活动分子式徽章 + Ctrl+K Spotlight + 窗口控制 | PASS | 徽章 C8H10N4O2；palette 可见 | audit_A_spotlight.png；E2E A3/A5 |
| 2.4 | 菜单悬停级联 + 快捷键标注 + 点击响应 | PARTIAL | 级联正常；F/H 快捷键标注未实现（Y5） | audit_A_menu_cascade.png |
| 2.5 | 44px 工具轨贴边 + 0 遮挡 | PASS | width=44.0px，absolute 浮动不占布局 | E2E B1 |
| 2.6 | A/R/F 磨砂侧滑抽屉 + 选中自动收起 | PASS | w-56/w-52/w-64 backdrop-blur-2xl；选 N 后收起 | audit_B_atom_drawer.png、audit_B_fragment_drawer.png；E2E B2-B5 |
| 2.7 | 原子右键：元素速换 C/N/O/S/P/F/Cl/Br/H + 删除 | PASS | 9 元素+删除齐全 | audit_C_atom_context.png；E2E C1 |
| 2.8 | 原子右键：电荷设置 | **FAIL** | 菜单无电荷项（Y6） | E2E C2 菜单全文 |
| 2.9 | 原子右键：删除原子真实生效 | **FAIL** | 24→24 静默失效（R7） | E2E C3；mismatch T1 |
| 2.10 | 键右键：单/双/三/芳香切换 UI | PASS | 4 选项齐全 | audit_C_bond_context.png；E2E C4 |
| 2.11 | 键右键：设键级精确生效 | **FAIL** | 点"三键"实际 order=2（R8） | E2E C5；mismatch T8 |
| 2.12 | 悬停热键 C/N/O/S 瞬时置换 | PARTIAL | O ✓（C→O）；B/F 被工具键抢占（Y5） | E2E C6/C7 |
| 2.13 | 5 大 HUD 呼出 + 磨砂玻璃 | PASS | 5/5，backdrop-blur-2xl | audit_D_five_hud_layers.png；E2E D1/D2 |
| 2.14 | HUD 标题栏拖拽 + 最小化折叠 | PASS | 拖拽 (+180,+120)px；折叠高 38px | audit_D_hud_drag_minimize.png；E2E D3/D4 |
| 2.15 | 多层叠加层级防遮挡 | PARTIAL | bringToFront 仅升至 35，同层靠 DOM 序（Y8） | E2E D5 z-index 快照 |
| 2.16 | Ctrl+B 隐藏主导航，视口 100% | PASS | nav 192px→隐藏；editor 宽 1440px | audit_E_ctrlB_immersive.png；E2E E1 |
| 2.17 | 正视/俯视/侧视相机重设 | PASS(方向)/PARTIAL(正交) | pitch/yaw 正确；透视非严格正交（Y15） | audit_E_front/top/side.png；camera.ts:16-29 |

### Phase 3 二维/三维化学编辑与材料砌块库

| # | 核验项 | 状态 | 耗时/实测值 | 证据 |
|---|---|---|---|---|
| 3.1 | SMILES 阿司匹林生成 | PASS | 277.7ms，C9H8O4 21原子（RDKit 真实） | p4_build_aspirin.json；audit_G_aspirin.png |
| 3.2 | Clean 3D 真实力场弛豫 | PASS | 最大位移 0.2708Å；C-C 均 1.4372Å、C-O 均 1.3974Å（化学合理） | p4_clean3d.json；phase4_5_summary P4-2 |
| 3.3 | OSC 砌块：BDT 给体接枝 | PASS | 21→33 原子，拓扑递增 | audit_H_bdt_graft.png；E2E H2 |
| 3.4 | OSC 砌块：Y6/ITIC/C60/并五苯 | **FAIL** | 后端目录 19 项无此 4 类；pentacene/benzene 插入 404（R11） | fragments.json；retest H1r-api |
| 3.5 | 噻吩环插入（菜单） | **FAIL** | hetero 被忽略→全碳环戊烷，中心固定原点（R10） | mismatch T7 |
| 3.6 | Shift 2 原子距离 0.001Å | PARTIAL | 格式达标（1.396Å）但用 2D 布局坐标（Y1） | audit_F_measure_2atoms.png；P4-2b |
| 3.7 | Shift 3 原子键角 0.1° | PARTIAL | 107.4° 格式达标，同为 2D 值 | audit_F3_angle_clean.png |
| 3.8 | Shift 4 原子二面角 + 共平面度 | **FAIL** | 硬编码 "0.00° (共平面)"（R4） | audit_F4_dihedral_clean.png（甲基 H 明显离面） |
| 3.9 | 坐标表 HUD 真实 3D 坐标 | **FAIL** | 仅 2D X/Y；复制 XYZ 的 Z 全填 0（R5） | CoordinatesTableModal.tsx:32,108-109 |

### Phase 4 真实科学计算与量子化学引擎

| # | 核验项 | 状态 | 耗时/实测值 | 证据 |
|---|---|---|---|---|
| 4.1 | Rust Tight-Binding HOMO/LUMO/Eg | PASS | 1.7ms；阿司匹林 HOMO=-9.200 LUMO=-5.751 Eg=3.449eV，10π原子/10π电子/10 MO，S1=359.5nm f=0.25 | p4_tight_binding.json |
| 4.2 | 能级阶梯图渲染 | PARTIAL | 数值真实；梯图为示意固定高度，失败时静默显示假值 -5.50/-3.50（Y7） | audit_D_five_hud_layers.png；OrbitalLadderModal.tsx:41-42 |
| 4.3 | CalChem SCF 收敛能量 | **FAIL** | 发行版未编译 calchem feature；available=false E=0（R9） | p4_calchem.json；engines_status.json |
| 4.4 | Gaussian .gjf 生成合法性 | PASS | 30 行：%nprocshared/%mem/#p B3LYP/def2-SVP opt freq/0 1/21 坐标 | input_gaussian.txt；P4-5b |
| 4.5 | ORCA .inp 生成合法性 | PASS | 26 行：! B3LYP def2-SVP Opt + 坐标块 | input_orca.txt |
| 4.6 | xTB/REST 输入生成 | **FAIL** | engine=xtb 与 kind=rest 均落入 gjf 默认分支（Y3） | input_xtb.txt（实为 gjf）；mismatch T4 |
| 4.7 | xTB 外部真实执行 | PASS(进程)/PARTIAL(能量) | exit=0，CPU 1.75s，xtbopt.xyz/.xtboptok/charges/wbo 真实产物，几何写回；但 API 不返回能量（Y4） | p4_run_xtb.json；xtb_stdout_full.txt（-39.4991309 Eh） |
| 4.8 | Multiwfn 3.8 NCI/RDG 真实分析 | **FAIL** | 进程真实启动但仅菜单导航（100→1→0→q），散点图=原子序数 Z 冒充（R3） | multiwfn_stdout_tail.txt；mwfn_crosscheck/full_stdout.txt；plot_y=[6,6,8,8,6,6…] |
| 4.9 | ORCA/Gaussian 外部实算 | **FAIL** | run_external 纯 Mock（R1）；后台 orca_sp 假完成（R2） | contract_run_external.json；p4_job_orca_sp.json |

### Phase 5 MolForge Hub 生态与 AI 科学副驾驶

| # | 核验项 | 状态 | 耗时/实测值 | 证据 |
|---|---|---|---|---|
| 5.1 | AI HUD 自动捕获上下文 | PASS | 徽章：C8H10N4O2 · 24原子/25键 · Singlet（经 UI 加载复测） | audit_I1_ai_context_retest.png；retest I1r |
| 5.2 | AI 真实 DeepSeek 回答 | **FAIL** | 内置 Key 失效→347ms 离线模板冒充回答，无降级标注（R6） | deepseek_diagnosis.txt；audit_I_ai_copilot.png |
| 5.3 | Markdown/公式渲染 | PARTIAL | $…$/粗体/代码块自研正则渲染可用；E_g 原样显示，无 KaTeX（Y11） | audit_I_ai_copilot.png；AiCopilotLayer.tsx:55-99 |
| 5.4 | Hub 搜索 HOMO/LUMO 与 MD | PASS | HOMO 命中 2（qc-frontier-orbital runnable）；MD 命中 7 | hub_search_homo.json；P5-1 |
| 5.5 | AI 工作流草稿规划 | PASS(匹配)/PARTIAL( runnable) | frontier-mo 匹配 1 技能可运行；md-rdf 标 runnable 但执行必败（Y9） | p5_plan_homolumo.json；p5_md_rdf_run.json |
| 5.6 | 工作流执行 + Provenance 溯源卡 | PASS | run_id=wfrun-1a1f43b58bc；分子 SHA256 独立复算**完全匹配**；工作流 SHA256、节点耗时、技能哈希齐全 | p5_run_frontier_mo.json；P5-3b |
| 5.7 | 外部进程审批门 | PASS | xtb-preopt 未审批=pending_approval；审批后真实执行 38ms | p5_xtb_wf_noapprove/approved.json |
| 5.8 | 缺失依赖诚实阻塞（不假成功） | PASS | calchem-sp-opt=blocked；md-rdf=failed（rdf 无适配器） | p5_calchem_wf.json；p5_md_rdf_run.json |
| 5.9 | Hub 工作流 UI 执行（标准 E2E） | PASS | scene_05b "Provenance Run:" 断言通过 | scene_05b_hub_obsidian.png |

### Phase 6 自动化测试与交付

| # | 核验项 | 状态 | 结果 | 证据 |
|---|---|---|---|---|
| 6.1 | TypeScript 类型检查（renderer+electron） | PASS | exit=0，0 错误 | logs/typecheck.log |
| 6.2 | ESLint | **FAIL** | exit=1：1 error（no-useless-escape）+5 warning | logs/lint.log（Y12） |
| 6.3 | Vitest 单元测试 | PASS | 4 文件 12/12 通过（含路由契约 parity） | logs/vitest.log |
| 6.4 | Playwright 标准 E2E（真 Electron） | PASS | 10 场景全过，0 pageerror | logs/e2e_standard.log；scene_*.png |
| 6.5 | 审计专用 E2E（36 项细粒度交互） | PARTIAL | 27 PASS / 9 FAIL，0 pageerror | logs/e2e_audit.log；audit_e2e_results.json |
| 6.6 | 聚焦复测 + 微补证 | PASS | 二面角 Mock/AI 上下文/通知抽屉证据闭合 | logs/e2e_retest.log、e2e_micro.log |

**矩阵汇总：42 项中 PASS 24 ／ PARTIAL 9 ／ FAIL 9。**

---

## 二、零容忍问题清单（RED，附源码文件与行号）

> 以下每项均有真实执行证据，非推测。行号经本轮 grep/read 双重核验。

**【RED-01】`/api/qc/run_external` 是纯 Mock，从未执行任何外部进程**
- 源码：`molforge-core/crates/molforge-server/src/main.rs:921-951` —— 仅 `format!` 拼接命令字符串，返回 `status:"completed"`、`stdout_tail:"任务已提交至 … (PID: native)"`，无 `Command::spawn`。
- UI 放大：`desktop/src/components/layers/CalculationSetupModal.tsx:63-70` 把该假响应用 CheckCircle2 成功图标展示为"运行完成"。
- 证据：`evidence/api/contract_run_external.json`（0.4ms 返回 completed）；`evidence/api/deepseek_diagnosis.txt` 第 4 条（workdir 0 文件）。

**【RED-02】后台任务队列除 tight_binding 外全部假完成**
- 源码：`main.rs:1043-1050` —— `else { Ok(json!({ "ok": true, "num_atoms": … })) }`，orca_sp / gaussian_sp / calchem_opt / analysis 等全部直接"Completed successfully"。
- UI 放大：`desktop/src/views/AnalysisView.tsx:404-416`（ORCA/Gaussian"提交至后台实算队列"）、`:329-336`（CalChem 后台优化）。
- 证据：`evidence/engines/p4_job_orca_sp.json` + `phase4_5_summary.txt` P4-7（result 仅 {ok,num_atoms}，无 ORCA 任何输出）。

**【RED-03】Multiwfn"WFN-12 Promolecular NCI/RDG"实为菜单导航 + 原子序数假散点**
- 源码：`molforge-core/crates/molforge-core/src/engines.rs:379`（命令序列 `"100\n1\n0\nq\n"` 进入散点图菜单后退出，未执行任何实空间分析）；`:412-415`（`plot_y = 原子序数 Z`，`y_label="Atomic Number (Z)"`）。
- UI 放大：`AnalysisView.tsx:424` 下拉项宣称"Promolecular NCI/RDG 弱相互作用"。
- 证据：`evidence/engines/multiwfn_stdout_tail.txt`（尾部为实空间函数选择菜单，无 NCI 计算输出）；`mwfn_crosscheck/full_stdout.txt`（独立进程交叉验证，exit=59，全程菜单）；`p4_multiwfn_wfn12.json`（plot_y=[6,6,8,8,6,6…]）。
- 注：8.0 Python 桥接曾真实产出 133,300 点 NCI 散点（旧 TEST_REPORT），8.1 迁移 Rust 后**功能回归**，且发行包只带 Rust 内核（`electron-builder.json5` extraResources 仅 resources/core）。

**【RED-04】四原子二面角硬编码 Mock**
- 源码：`desktop/src/views/EditorView.tsx:148-153` —— `value: "0.00° (共平面)"` 常量，与所选原子坐标无关。
- 证据：`evidence/ui/audit_F4_dihedral_clean.png` —— 选中 C#0-C#6-N#12-H#18（含 sp3 甲基氢，3D 视口清晰可见其离面），HUD 仍显示"0.00° (共平面)"。

**【RED-05】坐标表 HUD 伪造三维坐标**
- 源码：`desktop/src/components/layers/CoordinatesTableModal.tsx:108-109`（仅显示 2D 布局 x2/y2，无 Z 列）；`:32`（"复制 XYZ"把每个原子 Z 写死 `0.0000`）。标题却为"笛卡尔空间坐标表"。
- 证据：源码直读 + 后端 `/api/atoms` 明明提供真实 x/y/z（main.rs:200-202）而前端弃用。

**【RED-06】AI 副驾驶：失效硬编码 Key + 静默模板降级 + 设置页 Key 永不生效**
- 源码：`main.rs:1309`（硬编码 `sk-9baf…1660`，已失效）；`:1322-1337`（curl 失败后**不标注离线**，用紧束缚模板文案冒充 AI 回答）；`desktop/src/services/api.ts:317-328` 保存字段 `api_key/base_url/model`，而 `main.rs:1308-1310` 读取 `ai_api_key/ai_base_url/ai_model` → 用户在设置页填的 Key 永远不生效。
- 证据：`evidence/api/deepseek_diagnosis.txt`（直连 230ms 真实往返，authentication_error，request_id f4d9f086…）；`contract_ai_chat.json`（347.5ms 返回，reply 与 main.rs:1328 模板逐字一致）；`mismatch_preferences_after_save.json`（api_key 与 ai_api_key 分离）；`audit_I_ai_copilot.png`。
- 安全附注：API Key 明文硬编码于源码，应移除。

**【RED-07】右键"删除此原子"静默失效（前后端字段错配）**
- 源码：`api.ts:271-274` 发送 `{atom_ids:[…]}`；`main.rs:786` 读取 `body["ids"]` → 空 vec；`commands.rs` DeleteAtoms 空 ids 返回 Ok 无操作。
- 证据：`mismatch_delete_atoms_frontend_payload.json`（12→12，ok=true）；E2E C3（24→24）。正确字段 `{ids}` 实测 12→11 成功（T2 对照）。

**【RED-08】右键"设置键级"实为循环切换，芳香键永不可达**
- 源码：`EditorView.tsx:195`（onSetBondOrder → cycleBondOrder，丢弃用户选择的 order）；`commands.rs` CycleBondOrder 仅 1→2→3→1。
- 证据：E2E C5（点"三键"→ order=2）；`mismatch_bond_cycle.txt`（4 次循环无 order=4）。

**【RED-09】CalChem 纯 Rust 从头算在发行版中不存在**
- 源码：`crates/molforge-server/Cargo.toml` `default=[]`，calchem 为可选 feature；发行 exe 未启用 → `qc.rs run_calchem` 返回 available=false/E=0。UI `CalculationSetupModal.tsx:52` 仍显示"计算完成！基态总能量 0.000000 Hartree"。
- 证据：`p4_calchem.json`、`engines_status.json`（calchem=false）、`p5_calchem_wf.json`（工作流诚实 blocked）。
- 可修复性：CalChem 15 个 crate 真实存在于 `E:\YDW\Trae_Gaussian\crates\`（path 依赖已配置），`cargo build --release --features calchem` 即可启用——但**当前发行产物没有**。

**【RED-10】"插入噻吩环"实际插入全碳环戊烷且位置固定原点**
- 源码：`StudioHeader.tsx:247` 传 `hetero:{0:16}, center_2d`；`main.rs:690-706` 只读 `size/aromatic/attach_to/center`，hetero 与 center_2d 均被忽略。
- 证据：`mismatch_add_ring_center2d.json` + T7（新 5 原子全 C，中心 (0,0)，非点击位 (5,5)）。

**【RED-11】宣传的 Y6/ITIC/C60/并五苯/苯环砌块后端缺失，失败无画布提示**
- 源码：`StudioHeader.tsx:227`（菜单宣称"Y6 / ITIC / BDT"）；`FragmentsLayer.tsx:47`（pentacene 卡片）、`:58`（benzene 卡片）；后端 `presets.rs fragment_catalog` 仅 19 项，无 pentacene/benzene/Y6/ITIC/C60。
- 证据：`fragments.json`；retest H1r-api（pentacene/benzene 均 HTTP 404"未找到基团/片段"）；`audit_H1_notification_drawer.png`（错误仅收入通知抽屉，画布无 toast，用户视角=点击无反应）。

---

## 三、一般问题清单（YELLOW）

| # | 问题 | 源码定位 | 证据 |
|---|---|---|---|
| Y1 | 测量 HUD 用 2D 布局坐标冒充空间距离/键角 | EditorView.tsx:120-121,133-134 | P4-2b：键#0 2D=1.5093Å vs 真 3D=1.5855Å |
| Y2 | 2D 拖动原子 400 报错 | api.ts:266-269（pos_2d）vs main.rs:671-677（pos[x,y,z]） | mismatch T3 |
| Y3 | REST/xtb 输入生成落入 gjf 默认分支 | api.ts:293-296（kind）vs main.rs:857（engine）；main.rs:862-865 无 xtb 分支 | T4；input_xtb.txt |
| Y4 | xTB 能量未解析，UI 显示 0.000000 Eh | main.rs:892-919（ExternalRunOutput 无 energy 字段）；AnalysisView.tsx:364 | xtb_stdout_full.txt 含 -39.4991309 Eh |
| Y5 | 热键 b/f 双重映射冲突；F/H 菜单快捷键标注未实现 | App.tsx:87,89 vs Molecule2DCanvas.tsx:91；StudioHeader.tsx:417,442 | E2E C7（按 B 原子不变） |
| Y6 | 原子右键菜单缺电荷设置 | CanvasContextMenu.tsx（全文无 charge 项） | E2E C2 |
| Y7 | 能级 HUD 失败静默显示假值；梯图非能量比例 | OrbitalLadderModal.tsx:41-42,117-156 | 源码直读 |
| Y8 | HUD 置顶仅升至 z=35，多窗同层靠 DOM 序 | FloatingWindow.tsx:40-42 | E2E D5 |
| Y9 | md-rdf 规划 runnable=true 但执行必败 | workflow.rs:632（trajectory.rdf 无适配器）vs plan 仅查能力注册 | p5_md_rdf_run.json |
| Y10 | analysis/run 对任意 analysis_id 都跑 TB；79 项目录仅 CORE-01 真实 | main.rs:961-1013 | 源码直读 |
| Y11 | 公式渲染为自研正则，非 KaTeX；E_g 无下标 | AiCopilotLayer.tsx:55-99；package.json 无 katex | audit_I_ai_copilot.png |
| Y12 | ESLint 1 error | tests/api_parity_contract.test.ts:17（no-useless-escape） | logs/lint.log |
| Y13 | 无 Python 时 inspect_smiles 硬编码 C/12.011 回退（本机未触发） | python_worker.rs:492-493 | 源码直读 |
| Y14 | 错误通知无 toast，仅抽屉+计数，画布操作失败无即时反馈 | useStudioStore.ts:266-274；StatusBar.tsx:86-95 | audit_H1_notification_drawer.png |
| Y15 | 三向视图为透视投影，非严格正交 | camera.ts:100-124 | 源码直读 |
| Y16 | 砌块接枝锚点用 .index 而非 .atom_id（删除原子后错位） | FragmentsLayer.tsx:191 | 源码直读 |
| Y17 | 计算设置 HUD 电荷/自旋输入未提交后端 | CalculationSetupModal.tsx:23-24,43-72 | 源码直读 |
| Y18 | ai/chat 含"生成/构建/画/build"即静默替换整个文档 | main.rs:1290-1306 | 源码直读 |

---

## 四、真实亮点（经实测确认，非宣传）

1. **底座极稳**：纯 Rust 7.7MB 级内存，220 请求+20 并发零失败零泄漏；59 路由与前端 52 端点零缺失。
2. **WebGPU 真渲染**：nvidia WebGPU 60 FPS，球棍/CPK/棍状/线框四模式，三向相机方向正确（俯视图分子平面侧视成线，截图可证）。
3. **工业级壳层达标**：38px 单行顶栏、44px 工具轨、磨砂抽屉自动收起、5 层玻璃 HUD 可拖拽可折叠、Ctrl+B 真沉浸。
4. **Tight-Binding 真实求解**：阿司匹林 10π 电子 Hückel 型 MO，HOMO/LUMO/Eg/S1 全谱输出，1.7ms。
5. **xTB 真实外部进程**：GFN2-xTB 6.7.1pre 优化 exit=0，xtbopt.xyz/.xtboptok/charges/wbo 全套产物，几何经 CommandBus 写回（可撤销）。
6. **RDKit 真实 SMILES/力场**：阿司匹林 277ms 生成，MMFF 弛豫键长化学合理。
7. **工作流引擎是系统最诚实的部分**：DAG 环检测、能力门禁、外部进程审批门、缺失依赖**诚实 blocked/failed 绝不假成功**；Provenance 分子 SHA256 经独立复算**逐位匹配**，含工作流哈希、节点耗时、技能版本哈希。
8. **量化输入生成器（gjf/orca）合法**：关键词、电荷自旋、21 坐标齐全。
9. **测试设施真实**：typecheck 0 错、Vitest 12/12、标准 E2E 10 场景 0 异常。

---

## 五、自动化测试报告摘要

| 套件 | 命令 | 退出码 | 结果 | 日志 |
|---|---|---|---|---|
| TypeScript | npm run typecheck | 0 | renderer+electron 双配置 0 错误 | logs/typecheck.log |
| ESLint | npm run lint | 1 | 1 error + 5 warning（Y12） | logs/lint.log |
| Vitest | npm test | 0 | 4 文件 12 测试全过（binary_protocol 2 / security 5 / api_parity 2 / ui_components 3） | logs/vitest.log |
| Playwright 标准 E2E | npm run test:e2e | 0 | 真 Electron 10 场景：Overview/Library/118 周期表/Editor/分屏 HUD/Analysis+Multiwfn/Hub Provenance/Jobs/Reports/Settings+Arctic 主题/CommandPalette，0 pageerror | logs/e2e_standard.log |
| 审计专用 E2E | node scripts/audit-e2e-20261119.mjs | 0 | 36 项 27PASS/9FAIL，0 pageerror | logs/e2e_audit.log + evidence/ui/audit_e2e_results.json |
| 聚焦复测 | node scripts/audit-retest-20261119.mjs | 0 | 二面角 Mock/AI 上下文/pentacene 404 证据闭合 | logs/e2e_retest.log |
| 微补证 | node scripts/audit-micro-20261119.mjs | 0 | 键角 107.4°/二面角 0.00°/通知抽屉失败记录 | logs/e2e_micro.log |
| 引擎/工作流实测 | phase4_5_engines.ps1 | 0 | 22 项真实调用（含 xtb/Multiwfn 外部进程、SHA256 复算） | evidence/engines/phase4_5_summary.txt |

---

## 六、关键场景截图索引（evidence/ui/）

- 顶栏与菜单级联：audit_A_menu_cascade.png、audit_A_spotlight.png
- 工具轨抽屉：audit_B_atom_drawer.png、audit_B_fragment_drawer.png
- 右键菜单：audit_C_atom_context.png（无电荷项）、audit_C_bond_context.png
- 五层玻璃 HUD：audit_D_five_hud_layers.png、audit_D_hud_drag_minimize.png
- 沉浸与三向：audit_E_ctrlB_immersive.png、audit_E_front/top/side.png
- 测量：audit_F_measure_2atoms.png、audit_F3_angle_clean.png（107.4°）、**audit_F4_dihedral_clean.png（Mock 铁证）**
- 化学编辑：audit_G_aspirin.png、audit_H_bdt_graft.png、audit_H1_notification_drawer.png（pentacene 404 仅入抽屉）
- AI：audit_I1_ai_context_retest.png（上下文徽章）、audit_I_ai_copilot.png（降级模板）
- 标准 10 场景：scene_01…scene_10（含 scene_05b_hub_obsidian.png Provenance 卡）
- 旧截图备份：prev_test_artifacts/（回滚还原用）

---

## 七、修复优先级建议（供决策，本次审计未改任何源码）

| 优先级 | 动作 | 涉及 |
|---|---|---|
| P0 | 统一前后端载荷契约（ids/pos/engine/ai_api_key/hetero/center），补 set_bond_order 路由 | R7/R8/R10/Y2/Y3/R6 |
| P0 | run_external 与 jobs 非 TB 分支接真实 engines::run（orca/g16 已探测就绪），或删除假完成改为诚实 blocked | R1/R2 |
| P0 | Multiwfn 改真实 NCI/RDG 菜单序列（如 20→14/16 散点或 100→其他真实功能），plot 用真实计算数据；或恢复 Python 桥接 NCI 路径 | R3 |
| P0 | 二面角用真实 3D 坐标计算；测量/坐标表全面改用 /api/atoms 的 x/y/z | R4/R5/Y1 |
| P1 | 重编发行版启用 calchem feature（crate 已就绪）；AI Key 改设置页注入+失效显式标注"离线降级" | R9/R6 |
| P1 | 补齐 Y6/ITIC/C60/pentacene/benzene 片段目录（SMILES→RDKit 生成）；错误 toast 即时化 | R11/Y14 |
| P2 | 热键去冲突、电荷右键项、HUD 相对置顶、KaTeX、lint 修复 | Y5/Y6/Y8/Y11/Y12 |

---

## 八、审计结论

MolForge Studio 8.1 的**壳层质感、底座稳定性、Tight-Binding/xTB/RDKit 真实计算链、工作流溯源引擎**达到旗舰级真实水准；但存在 **11 项零容忍 RED 问题**，集中于三类：
1. **假完成/假数据**（run_external、后台 jobs、Multiwfn 散点、二面角、坐标表 Z=0、AI 模板降级）——违背 Zero-Mock 底线；
2. **前后端契约错配导致的静默失效**（删除原子、设键级、拖原子、噻吩、REST 导出、设置页 Key）——功能"看起来有、实际不工作"；
3. **宣传与实现不符**（Y6/ITIC/C60 砌块、CalChem 发行版缺失、NCI/RDG 标签）。

**验收判定：不予通过（Conditional Fail）。** 契约回归与 UI 质感达标，但 RED-01~R11 修复并复测前，不得以"旗舰真实版"对外宣称。工作流引擎的诚实阻塞设计值得保留并推广到 run_external/jobs 分支。

—— 首席 QA 架构师 / 资深计算化学研究员
2026-11-19