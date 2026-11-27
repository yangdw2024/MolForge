# MolForge Hub — 统一生态架构决策记录 (ADR-001) 与迁移清单

> 状态：P0 基线规范（配合 `MolForge_Hub_Unified_Ecosystem_Design_v0.2.md` 实施）  
> 适用架构：Electron + React + TypeScript 前端 · Rust 原生核心 (`molforge-core` / `molforge-server`) · 可选隔离 Python Worker

## 1. 核心架构决策

1. **单一能力注册表 (`CapabilitySpec`)**  
   所有计算与分析功能（无论来自旧界面按钮、动态搜索框、`CommandPalette`、工作流节点还是 AI 编排提案）统一绑定不可变 `capability_id`（如 `qc.tight_binding`、`qc.calchem_scf`、`qc.calchem_opt`、`qc.xtb`、`wfn.multiwfn`、`md.gromacs_mdp`、`trajectory.rdf`、`structure.export`）。
2. **四类资源统一管理 (`ResourceKind`)**
   - `plugin`: 软件与适配器（`org.molforge.plugin.calchem`、`org.molforge.plugin.xtb`、`org.molforge.plugin.multiwfn`、`org.molforge.plugin.gromacs`、`org.molforge.plugin.orca`、`org.molforge.plugin.gaussian`、`org.molforge.plugin.python_rdkit`）
   - `skill`: 兼容 Agent Skills 开放规范的 `SKILL.md`（仅解析 `name`/`description` YAML 头与指导正文，可选扩展元数据存 `molforge-manifest.yaml`）
   - `workflow`: 版本化有向无环图（DAG）工作流模板（`schema_version: "molforge.workflow/v1"`）
   - `model`: 机器学习势与参考参数资产（记录 `sha256`、适用元素、许可证、依赖运行时）
3. **确定性工作流引擎 + 溯源 (`WorkflowRun` / `ProvenanceRecord`)**  
   工作流执行前必须经过 **DAG 环检测 → 依赖可满足性检查 → 输入校验 → 权限/审批门禁**；执行结果写入完整 `ProvenanceRecord`（输入分子哈希、工作流版本、使用到的技能/插件版本、节点输出与真实退出码/收敛状态）。

## 2. 威胁模型与安全边界

| 风险面 | 约束措施 |
|---|---|
| 导入恶意 `SKILL.md` 提示词注入 | `SKILL.md` 仅作低信任参考文本按需检索，**绝不解析或执行正文中的 shell 命令**，不能覆盖策略或获得新权限。 |
| 缺失外部引擎或依赖时假成功 | `check_dependencies` 校验对应 `plugin` 的 `available` 状态；缺失时明确标记 `missing_dependencies` 并阻断运行，禁止用 AI 文字或假数据充数。 |
| 高风险操作 / 外部进程 / 文件覆写 | 含 `external_process` / `file_write` 的工作流在执行前进入 `approval` 审批门禁，必须由用户显式批准。 |
| API 密钥与凭据泄露 | 凭据仅存内存/系统安全存储，不写入工作流 JSON、模板导出包或 `ProvenanceRecord`。 |

## 3. 旧功能按钮 → `capability_id` 迁移清单

| 旧版入口 | 目标 `capability_id` | 类型 | 所属引擎/适配器 | 对应工作流模板 |
|---|---|---|---|---|
| Tight-Binding π-MO | `qc.tight_binding` | `analyze` | `molforge-core` (原生 Rust) | `org.molforge.workflow.frontier-mo` |
| CalChem SCF 单点能 | `qc.calchem_scf` | `engine.run` | `calchem` (纯 Rust 进程内) | `org.molforge.workflow.calchem-sp-opt` |
| CalChem 几何优化 | `qc.calchem_opt` | `engine.run` | `calchem` (纯 Rust 进程内) | `org.molforge.workflow.calchem-sp-opt` |
| GFN2-xTB 优化 | `qc.xtb` | `engine.run` | `xtb` (外部原生进程) | `org.molforge.workflow.xtb-preopt` |
| Multiwfn 波函数分析 | `wfn.multiwfn` | `engine.run` | `multiwfn` (外部原生进程) | `org.molforge.workflow.multiwfn-wfn` |
| GROMACS MDP 生成 | `md.gromacs_mdp` | `transform` | `molforge-core` / `gromacs` | `org.molforge.workflow.md-rdf` |
| 轨迹 RDF 分析 | `trajectory.rdf` | `engine.run` | `gromacs` / `mdanalysis` | `org.molforge.workflow.md-rdf` |
| 结构导出 (XYZ/PDB/GJF/ORCA) | `structure.export` | `export` | `molforge-core` (原生 Rust) | 多工作流复用出口节点 |
