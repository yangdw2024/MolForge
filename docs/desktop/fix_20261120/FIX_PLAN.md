# MolForge Studio 8.1 全量修复规划（FIX_PLAN）— 2026-11-20

依据：《MolForge_Studio_8.1_真实性验收报告.md》（audit_20261119/）RED 11 项 + YELLOW 18 项。
用户指令："全部修复"。模式：完全访问；审计期"只读"约束解除，允许改源码与重编。

## 一、工作流逆推（构建链）
1. Rust 后端：`molforge-core/` workspace（molforge-core + molforge-server）→ `cargo build --release -p molforge-server` → `target/release/molforge-server.exe`（发行包 extraResources 只带它）。
   - calchem 为可选 feature，path 依赖 `E:/YDW/Trae_Gaussian/crates/calchem-*`（15 crate 已确认存在）→ 本次以 `--features calchem` 重编（R9）。
2. 前端：`desktop/`（Electron35+React19+TS+Vite）→ typecheck / lint / vitest / Playwright 真机 E2E；发行由 electron-builder 打包（本次不重打包发行安装包，只验证 dev 真机 + 新 exe）。
3. 服务态：审计遗留 PID 33584 占用 18765 → 重编后需 Stop-Process 再冷启动新 exe（旧 exe 已备份）。
4. 外部引擎：xtb / ORCA / Multiwfn 真实可执行（路径见 engines.rs fallback）；Gaussian g16 未检测到 → 诚实 engine_not_found。

## 二、执行规则
- 改前备份：27 文件镜像备份 `backup/`（含 MANIFEST.txt 与旧 exe），回滚=按 MANIFEST 拷回 + 旧 exe 复位。
- 零假数据原则延续：任何引擎缺失/失败必须诚实 blocked/failed/offline 标注，禁止模板冒充。
- Multiwfn 菜单序列以**本机实测**为准（probe/ 目录留痕）：主菜单 20 → 2(promolecular NCI) 或 1(波函数 NCI) → 1(低质量网格) → 后处理 2(导出 output.txt) → 0 → q；output.txt 5 列，取第 4/5 列 sign(λ2)ρ 与 RDG。
- 新砌块坐标用 RDKit/数学法**预生成真实 3D 坐标**硬编码进 presets.rs（与现有 19 项同模式，运行时零 Python）。
- 不安装任何东西到 C 盘：npm 缓存重定向 E 盘；cargo target 已在 E 盘。
- 每阶段操作记入 OPERATION_LOG.md；严重修复经验补记 AUDIT_EXPERIENCE/LESSONS。
- GPU 无关（CPU 轻量计算），无需 Pueue。

## 三、修复设计（对应报告编号）
### Rust 后端
- R1/R2：新增 `engines::run_external_native`（orca/gaussian 真 spawn+超时护栏+能量解析；xtb/multiwfn 复用真 runner）；`run_external` 与 `jobs/submit` 全部分派真引擎，缺失→诚实失败。
- R3：`run_multiwfn_native` 改实测菜单序列，解析 output.txt 真散点（采样≤2万点入 JSON，metrics 记总点数/网格耗时/模式）。
- R6：ai/chat 读 `ai_api_key|api_key` 等别名；删除硬编码 Key；无 Key/失败→回复带"【离线降级】"前缀 + `offline:true` + 原因；`pm6_match` 硬编码 true 删除改模型说明；文档替换仅限显式"生成/构建/加载+预设名"且回复与字段明示。
- R7：delete_atoms 接受 `ids|atom_ids`。
- R8：新增 `EditCommand::SetBondOrder`（含芳香 order=4）+ 路由 `/api/edit/set_bond_order`；前端右键改调它。
- R10：`AddRing` 增加 hetero 映射；handler 读 `hetero` 与 `center_2d` 别名。
- R11：presets 补 benzene/pentacene/Y6/ITIC/C60 真实坐标片段。
- Y2：move_atom 接受 `pos_2d` → 新 `MoveAtom2D`（只改 2D，可撤销）。
- Y3：export_input 读 `engine|kind`；新增 xtb 分支（io::write_xtb_input）。
- Y4：ExternalRunOutput 增 `energy_hartree/converged`；xtb stdout 末行 total energy 解析。
- Y9：workflow 规划/执行增加"适配器存在性"门禁（trajectory.rdf 无适配器→plan 即 blocked）。
- Y10：analysis/run 按 id 分派（CORE-01→TB；WFN-*→Multiwfn；其余→诚实 unavailable，删除 Z 散点回退）。
- Y13：python_worker 无 Python 回退改 ok:false+error，不再伪造 C/12.011。
- R9：`--features calchem` 重编；qc.rs 已真算无需改。
### 前端
- R4/Y1：EditorView 测量改真实 3D 坐标（store atoms pos），二面角向量法真算（0.1°），距离 0.001Å、键角 0.1°。
- R5：CoordinatesTableModal 显示真 3D X/Y/Z 列，复制 XYZ 用真 z。
- R8：CanvasContextMenu/EditorView 设键级调 set_bond_order（含芳香）。
- Y6：原子右键加电荷设置子菜单（-2..+2）调 set_charge_spin。
- R9/UI 诚实：CalculationSetupModal 提交电荷/自旋（Y17）；available=false 显示"引擎未启用"而非 0.000000 完成；xtb 能量显示真值。
- Y7：OrbitalLadderModal 失败显示"未求解"诚实态；梯图按能量比例定位。
- Y8：FloatingWindow 全局递增 z 计数器置顶。
- Y11：引入 KaTeX（npm 缓存 E 盘）渲染 $…$ 与 $$…$$；离线徽章。
- Y12：lint 转义修复。
- Y14：store 增 toasts + ToastHost 组件，runTask/api 失败即时 toast（保留通知抽屉）。
- Y15：camera 预设视图改真正交投影矩阵（CPU 侧 mat4，无需改 WGSL）。
- Y16：FragmentsLayer 锚点改 atom_id。
- Y5：热键去冲突（悬停原子时元素键优先；F=适配、H=显氢 实现；片段抽屉改 Alt+F 并同步标注）。
- R11/UI：菜单/砌块卡宣传与后端目录对齐（新增项真实存在后自然对齐）。
### 复测验收
- typecheck/lint/vitest 全绿；标准 E2E 10 场景；审计 E2E 36 项原 9 FAIL 转 PASS（C2/C3/C5/C7/F2/F3/H1/I1/I2 对应修复点）；契约 6 路由 200；引擎实测：Multiwfn 真散点>1万点、xtb energy 非空、calchem SCF 收敛、run_external orca 真产物、md-rdf plan blocked。
- 截图归集 fix_20261120/evidence/；前后对照矩阵入修复报告。

## 四、回滚还原
- 源码：backup/MANIFEST.txt 27 项拷回原路径。
- 二进制：backup/molforge-core/target/release/molforge-server.exe 拷回 + 重启。
- 依赖：package.json 备份可还原；katex 仅增依赖不影响回滚编译（还原后 npm ci 可选）。
- 服务态：文档内存态重启即复位 caffeine 默认。