//! Deterministic DAG Workflow Engine, Provenance Recorder, and AI Intent Planner.
//!
//! Enforces `MolForge_Hub_Unified_Ecosystem_Design_v0.2.md`:
//! - DAG validation (cycle & missing-dependency detection)
//! - Capability & dependency verification (never fakes success when engines are absent)
//! - Explicit approval gate for external processes / file writes
//! - Full `WorkflowRun` provenance with SHA-256 input & skill hashes

use crate::engines::{self, EnginePaths};
use crate::hub::{CapabilitySpec, HubRegistry};
use crate::io;
use crate::model::Molecule;
use crate::qc;
use crate::skills::sha256_hex;
use crate::summary;
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum NodeKind {
    Input,
    Validate,
    Transform,
    #[serde(rename = "engine.run")]
    EngineRun,
    Analyze,
    Visualize,
    Approval,
    Export,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowNode {
    pub id: String,
    pub title: String,
    pub kind: NodeKind,
    pub capability: Option<String>,
    pub depends_on: Vec<String>,
    pub params: serde_json::Value,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowSpec {
    pub schema_version: String,
    pub id: String,
    pub version: String,
    pub title: String,
    pub category: String,
    pub description: String,
    pub tags: Vec<String>,
    pub requires_capabilities: Vec<String>,
    pub permissions: Vec<String>,
    pub nodes: Vec<WorkflowNode>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum WorkflowRunStatus {
    PendingApproval,
    Completed,
    Failed,
    Blocked,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeExecutionRecord {
    pub node_id: String,
    pub title: String,
    pub capability: Option<String>,
    pub status: String,
    pub duration_ms: u64,
    pub summary: String,
    pub output: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProvenanceRecord {
    pub run_id: String,
    pub workflow_id: String,
    pub workflow_version: String,
    pub workflow_sha256: String,
    pub input_molecule_name: String,
    pub input_molecule_formula: String,
    pub input_molecule_sha256: String,
    pub matched_skill_ids: Vec<String>,
    pub capabilities_used: Vec<String>,
    pub approved_by_user: bool,
    pub timestamp_unix: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowRun {
    pub run_id: String,
    pub workflow_id: String,
    pub title: String,
    pub status: WorkflowRunStatus,
    pub missing_dependencies: Vec<String>,
    pub requires_approval: bool,
    pub node_records: Vec<NodeExecutionRecord>,
    pub outputs: serde_json::Value,
    pub provenance: ProvenanceRecord,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowProposal {
    pub query: String,
    pub intent_capabilities: Vec<String>,
    pub matched_skills: Vec<serde_json::Value>,
    pub selected_workflow: WorkflowSpec,
    pub runnable: bool,
    pub missing_dependencies: Vec<String>,
    pub status_reason: String,
    pub explanation: String,
}

pub fn builtin_workflows() -> Vec<WorkflowSpec> {
    vec![
        WorkflowSpec {
            schema_version: "molforge.workflow/v1".into(),
            id: "org.molforge.workflow.frontier-mo".into(),
            version: "1.0.0".into(),
            title: "前线分子轨道与能隙分析 (Tight-Binding)".into(),
            category: "量子化学".into(),
            description: "校验当前分子结构后，使用内置杂原子紧束缚模型计算 HOMO/LUMO 与 π-能隙，并生成能级数据。".into(),
            tags: vec!["homo".into(), "lumo".into(), "gap".into(), "tight-binding".into(), "轨道".into()],
            requires_capabilities: vec!["qc.tight_binding".into()],
            permissions: vec!["in-process:read-only".into()],
            nodes: vec![
                WorkflowNode {
                    id: "validate".into(),
                    title: "分子结构与价态校验".into(),
                    kind: NodeKind::Validate,
                    capability: None,
                    depends_on: vec![],
                    params: serde_json::json!({ "min_atoms": 2 }),
                },
                WorkflowNode {
                    id: "tb".into(),
                    title: "Tight-Binding π-MO 求解".into(),
                    kind: NodeKind::Analyze,
                    capability: Some("qc.tight_binding".into()),
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({}),
                },
                WorkflowNode {
                    id: "viz".into(),
                    title: "能级与跃迁谱汇总".into(),
                    kind: NodeKind::Visualize,
                    capability: None,
                    depends_on: vec!["tb".into()],
                    params: serde_json::json!({}),
                },
            ],
        },
        WorkflowSpec {
            schema_version: "molforge.workflow/v1".into(),
            id: "org.molforge.workflow.calchem-sp-opt".into(),
            version: "1.0.0".into(),
            title: "CalChem 纯 Rust 从头算 SCF 与构型导出".into(),
            category: "量子化学".into(),
            description: "使用内置纯 Rust CalChem 引擎执行 HF/DFT 单点能计算，并生成可复现 Gaussian/ORCA 输入脚本。".into(),
            tags: vec!["calchem".into(), "scf".into(), "dft".into(), "hf".into(), "从头算".into()],
            requires_capabilities: vec!["qc.calchem_scf".into(), "structure.export".into()],
            permissions: vec!["in-process:compute".into(), "file-export".into()],
            nodes: vec![
                WorkflowNode {
                    id: "validate".into(),
                    title: "电荷与自旋多重度校验".into(),
                    kind: NodeKind::Validate,
                    capability: None,
                    depends_on: vec![],
                    params: serde_json::json!({ "max_atoms": 32 }),
                },
                WorkflowNode {
                    id: "scf".into(),
                    title: "CalChem SCF 单点能计算".into(),
                    kind: NodeKind::EngineRun,
                    capability: Some("qc.calchem_scf".into()),
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({ "method": "HF", "basis": "STO-3G" }),
                },
                WorkflowNode {
                    id: "export".into(),
                    title: "导出标准 XYZ 归档".into(),
                    kind: NodeKind::Export,
                    capability: Some("structure.export".into()),
                    depends_on: vec!["scf".into()],
                    params: serde_json::json!({ "format": "xyz" }),
                },
            ],
        },
        WorkflowSpec {
            schema_version: "molforge.workflow/v1".into(),
            id: "org.molforge.workflow.xtb-preopt".into(),
            version: "1.0.0".into(),
            title: "GFN2-xTB 快速构型预优化".into(),
            category: "量子化学".into(),
            description: "调用本机 GFN2-xTB 外部进程执行几何优化，需经用户审批后运行外部程序。".into(),
            tags: vec!["xtb".into(), "opt".into(), "几何优化".into(), "conformer".into()],
            requires_capabilities: vec!["qc.xtb".into(), "structure.export".into()],
            permissions: vec!["external-process".into()],
            nodes: vec![
                WorkflowNode {
                    id: "validate".into(),
                    title: "三维坐标与电荷检查".into(),
                    kind: NodeKind::Validate,
                    capability: None,
                    depends_on: vec![],
                    params: serde_json::json!({ "min_atoms": 2 }),
                },
                WorkflowNode {
                    id: "approve".into(),
                    title: "外部进程执行审批".into(),
                    kind: NodeKind::Approval,
                    capability: None,
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({ "reason": "即将调用外部 xtb.exe 子进程" }),
                },
                WorkflowNode {
                    id: "xtb".into(),
                    title: "GFN2-xTB 几何优化".into(),
                    kind: NodeKind::EngineRun,
                    capability: Some("qc.xtb".into()),
                    depends_on: vec!["approve".into()],
                    params: serde_json::json!({ "method": "gfn2", "optimize": true }),
                },
            ],
        },
        WorkflowSpec {
            schema_version: "molforge.workflow/v1".into(),
            id: "org.molforge.workflow.multiwfn-wfn".into(),
            version: "1.0.0".into(),
            title: "Multiwfn 波函数实空间分析".into(),
            category: "波函数分析".into(),
            description: "调用 Multiwfn 3.8 对当前体系执行实空间波函数指标分析并留存原始日志溯源。".into(),
            tags: vec!["multiwfn".into(), "esp".into(), "elf".into(), "波函数".into()],
            requires_capabilities: vec!["wfn.multiwfn".into()],
            permissions: vec!["external-process".into()],
            nodes: vec![
                WorkflowNode {
                    id: "validate".into(),
                    title: "输入文件与坐标检查".into(),
                    kind: NodeKind::Validate,
                    capability: None,
                    depends_on: vec![],
                    params: serde_json::json!({ "min_atoms": 1 }),
                },
                WorkflowNode {
                    id: "approve".into(),
                    title: "Multiwfn 子进程审批".into(),
                    kind: NodeKind::Approval,
                    capability: None,
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({ "reason": "即将调用 Multiwfn.exe 子进程" }),
                },
                WorkflowNode {
                    id: "multiwfn".into(),
                    title: "Multiwfn 实空间计算".into(),
                    kind: NodeKind::EngineRun,
                    capability: Some("wfn.multiwfn".into()),
                    depends_on: vec!["approve".into()],
                    params: serde_json::json!({ "analysis_id": "WFN-12" }),
                },
            ],
        },
        WorkflowSpec {
            schema_version: "molforge.workflow/v1".into(),
            id: "org.molforge.workflow.osc-4char".into(),
            version: "1.0.0".into(),
            title: "OSC 分子平面性与前线轨道快速表征".into(),
            category: "有机半导体".into(),
            description: "内置纯 Rust 零外部依赖流程：结构校验 → Tight-Binding 前线轨道 HOMO/LUMO → 最佳平面拟合 MPP/SDP 指标。".into(),
            tags: vec!["osc".into(), "planarity".into(), "mpp".into(), "sdp".into(), "homo".into(), "平面性".into()],
            requires_capabilities: vec!["qc.tight_binding".into(), "structure.planarity".into()],
            permissions: vec!["in-process:read-only".into()],
            nodes: vec![
                WorkflowNode {
                    id: "validate".into(),
                    title: "重原子数与电荷自旋校验".into(),
                    kind: NodeKind::Validate,
                    capability: None,
                    depends_on: vec![],
                    params: serde_json::json!({ "min_atoms": 3 }),
                },
                WorkflowNode {
                    id: "tb".into(),
                    title: "Tight-Binding HOMO/LUMO 能隙".into(),
                    kind: NodeKind::Analyze,
                    capability: Some("qc.tight_binding".into()),
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({}),
                },
                WorkflowNode {
                    id: "mpp".into(),
                    title: "分子平面性 MPP/SDP 计算".into(),
                    kind: NodeKind::Analyze,
                    capability: Some("structure.planarity".into()),
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({}),
                },
                WorkflowNode {
                    id: "viz".into(),
                    title: "汇总 OSC 表征指标".into(),
                    kind: NodeKind::Visualize,
                    capability: None,
                    depends_on: vec!["tb".into(), "mpp".into()],
                    params: serde_json::json!({}),
                },
            ],
        },
        WorkflowSpec {
            schema_version: "molforge.workflow/v1".into(),
            id: "org.molforge.workflow.md-rdf".into(),
            version: "1.0.0".into(),
            title: "MD 轨迹 RDF 与动力学分析".into(),
            category: "分子动力学".into(),
            description: "校验周期性盒子与 GROMACS 适配器后，生成 NVT/NPT 参数并执行轨迹 RDF 分析。".into(),
            tags: vec!["md".into(), "rdf".into(), "gromacs".into(), "轨迹".into(), "径向分布".into()],
            requires_capabilities: vec!["md.gromacs_mdp".into(), "trajectory.rdf".into()],
            permissions: vec!["external-process".into()],
            nodes: vec![
                WorkflowNode {
                    id: "validate".into(),
                    title: "体系原子映射与周期盒校验".into(),
                    kind: NodeKind::Validate,
                    capability: None,
                    depends_on: vec![],
                    params: serde_json::json!({ "min_atoms": 1 }),
                },
                WorkflowNode {
                    id: "mdp".into(),
                    title: "生成 GROMACS MDP 参数".into(),
                    kind: NodeKind::Transform,
                    capability: Some("md.gromacs_mdp".into()),
                    depends_on: vec!["validate".into()],
                    params: serde_json::json!({ "ensemble": "nvt", "nsteps": 50000 }),
                },
                WorkflowNode {
                    id: "rdf".into(),
                    title: "GROMACS 轨迹 RDF 计算".into(),
                    kind: NodeKind::EngineRun,
                    capability: Some("trajectory.rdf".into()),
                    depends_on: vec!["mdp".into()],
                    params: serde_json::json!({}),
                },
            ],
        },
    ]
}

/// Topological sort with cycle & unknown-dependency detection.
pub fn topological_order(spec: &WorkflowSpec) -> Result<Vec<usize>> {
    let n = spec.nodes.len();
    let id_to_idx: HashMap<&str, usize> = spec
        .nodes
        .iter()
        .enumerate()
        .map(|(i, node)| (node.id.as_str(), i))
        .collect();

    let mut indegree = vec![0usize; n];
    let mut adj = vec![Vec::new(); n];
    for (idx, node) in spec.nodes.iter().enumerate() {
        for dep in &node.depends_on {
            let &dep_idx = id_to_idx.get(dep.as_str()).ok_or_else(|| {
                CoreError::InvalidOp(format!(
                    "workflow node '{}' depends on unknown node '{dep}'",
                    node.id
                ))
            })?;
            adj[dep_idx].push(idx);
            indegree[idx] += 1;
        }
    }

    let mut q: VecDeque<usize> = (0..n).filter(|&i| indegree[i] == 0).collect();
    let mut order = Vec::with_capacity(n);
    while let Some(u) = q.pop_front() {
        order.push(u);
        for &v in &adj[u] {
            indegree[v] -= 1;
            if indegree[v] == 0 {
                q.push_back(v);
            }
        }
    }

    if order.len() != n {
        return Err(CoreError::InvalidOp(format!(
            "workflow '{}' contains a dependency cycle",
            spec.id
        )));
    }
    Ok(order)
}

fn now_unix() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

pub fn execute_workflow(
    spec: &WorkflowSpec,
    mol: &Molecule,
    registry: &HubRegistry,
    engine_paths: &EnginePaths,
    python_exe: Option<&Path>,
    approved: bool,
    param_overrides: Option<&serde_json::Value>,
) -> Result<WorkflowRun> {
    let order = topological_order(spec)?;
    let engines = engines::probe_all(engine_paths, python_exe);
    let caps = registry.capabilities(&engines);

    let mut required_caps: HashSet<String> = spec.requires_capabilities.iter().cloned().collect();
    for node in &spec.nodes {
        if let Some(c) = &node.capability {
            required_caps.insert(c.clone());
        }
    }
    let req_vec: Vec<String> = required_caps.into_iter().collect();
    let (runnable, missing, reason) = gate_adapters(
        &req_vec,
        registry.check_dependencies(&req_vec, &caps),
    );

    let mol_xyz = io::write_xyz(mol);
    let mol_sha = sha256_hex(mol_xyz.as_bytes());
    let wf_json = serde_json::to_vec(spec).unwrap_or_default();
    let wf_sha = sha256_hex(&wf_json);

    let run_id = format!("wfrun-{:x}", (now_unix() * 1000.0) as u64);
    let matched_skills: Vec<String> = registry
        .skills
        .iter()
        .filter(|s| s.capabilities.iter().any(|c| req_vec.contains(c)))
        .map(|s| format!("{}@{}", s.id, s.version))
        .collect();

    let provenance = ProvenanceRecord {
        run_id: run_id.clone(),
        workflow_id: spec.id.clone(),
        workflow_version: spec.version.clone(),
        workflow_sha256: wf_sha,
        input_molecule_name: mol.name.clone(),
        input_molecule_formula: summary::formula(mol),
        input_molecule_sha256: mol_sha,
        matched_skill_ids: matched_skills,
        capabilities_used: req_vec,
        approved_by_user: approved,
        timestamp_unix: now_unix(),
    };

    if !runnable {
        return Ok(WorkflowRun {
            run_id,
            workflow_id: spec.id.clone(),
            title: spec.title.clone(),
            status: WorkflowRunStatus::Blocked,
            missing_dependencies: missing,
            requires_approval: false,
            node_records: Vec::new(),
            outputs: serde_json::json!({}),
            provenance,
            error: Some(reason),
        });
    }

    let needs_approval = spec.nodes.iter().any(|n| n.kind == NodeKind::Approval)
        || spec.permissions.iter().any(|p| p == "external-process");
    if needs_approval && !approved {
        return Ok(WorkflowRun {
            run_id,
            workflow_id: spec.id.clone(),
            title: spec.title.clone(),
            status: WorkflowRunStatus::PendingApproval,
            missing_dependencies: Vec::new(),
            requires_approval: true,
            node_records: Vec::new(),
            outputs: serde_json::json!({}),
            provenance,
            error: None,
        });
    }

    let mut node_records = Vec::with_capacity(order.len());
    let mut outputs_map = serde_json::Map::new();

    for idx in order {
        let node = &spec.nodes[idx];
        let t0 = std::time::Instant::now();
        let merged_params = merge_params(&node.params, param_overrides);

        let exec_res: std::result::Result<(String, serde_json::Value), String> = match node.kind {
            NodeKind::Input | NodeKind::Approval => {
                Ok(("已通过权限与审批门禁".into(), serde_json::json!({ "approved": true })))
            }
            NodeKind::Validate => {
                let min_atoms = merged_params["min_atoms"].as_u64().unwrap_or(1) as usize;
                let max_atoms = merged_params["max_atoms"].as_u64().unwrap_or(1_000_000) as usize;
                if mol.atoms.len() < min_atoms || mol.atoms.len() > max_atoms {
                    Err(format!(
                        "原子数 {} 不在节点校验范围 [{min_atoms}, {max_atoms}]",
                        mol.atoms.len()
                    ))
                } else {
                    let (chg, mult, spin) = summary::resolve_spin_state(mol);
                    Ok((
                        format!("通过校验: {} 原子, 电荷 {chg}, 自旋 {spin} ({mult})", mol.atoms.len()),
                        serde_json::json!({ "num_atoms": mol.atoms.len(), "charge": chg, "multiplicity": mult }),
                    ))
                }
            }
            NodeKind::Analyze | NodeKind::EngineRun | NodeKind::Transform | NodeKind::Export => {
                run_capability_node(
                    node.capability.as_deref(),
                    &merged_params,
                    mol,
                    engine_paths,
                    &caps,
                )
            }
            NodeKind::Visualize => Ok((
                "已汇总前序节点数据并准备可视化载荷".into(),
                serde_json::json!({ "ready": true }),
            )),
        };

        let elapsed = t0.elapsed().as_millis() as u64;
        match exec_res {
            Ok((sum, out_val)) => {
                outputs_map.insert(node.id.clone(), out_val.clone());
                node_records.push(NodeExecutionRecord {
                    node_id: node.id.clone(),
                    title: node.title.clone(),
                    capability: node.capability.clone(),
                    status: "completed".into(),
                    duration_ms: elapsed,
                    summary: sum,
                    output: Some(out_val),
                });
            }
            Err(err_msg) => {
                node_records.push(NodeExecutionRecord {
                    node_id: node.id.clone(),
                    title: node.title.clone(),
                    capability: node.capability.clone(),
                    status: "failed".into(),
                    duration_ms: elapsed,
                    summary: err_msg.clone(),
                    output: None,
                });
                return Ok(WorkflowRun {
                    run_id,
                    workflow_id: spec.id.clone(),
                    title: spec.title.clone(),
                    status: WorkflowRunStatus::Failed,
                    missing_dependencies: Vec::new(),
                    requires_approval: needs_approval,
                    node_records,
                    outputs: serde_json::Value::Object(outputs_map),
                    provenance,
                    error: Some(err_msg),
                });
            }
        }
    }

    Ok(WorkflowRun {
        run_id,
        workflow_id: spec.id.clone(),
        title: spec.title.clone(),
        status: WorkflowRunStatus::Completed,
        missing_dependencies: Vec::new(),
        requires_approval: needs_approval,
        node_records,
        outputs: serde_json::Value::Object(outputs_map),
        provenance,
        error: None,
    })
}

fn merge_params(base: &serde_json::Value, overrides: Option<&serde_json::Value>) -> serde_json::Value {
    let mut obj = base.as_object().cloned().unwrap_or_default();
    if let Some(ov) = overrides.and_then(|v| v.as_object()) {
        for (k, v) in ov {
            obj.insert(k.clone(), v.clone());
        }
    }
    serde_json::Value::Object(obj)
}

/// 能力是否真正接入了执行适配器（与 run_capability_node 的分派臂一一对应）。
/// 注册在 Hub 目录 ≠ 可执行：规划与执行都必须过这道门禁，避免"runnable 但必败"。
pub fn capability_has_adapter(cap: &str) -> bool {
    matches!(
        cap,
        "qc.tight_binding"
            | "qc.calchem_scf"
            | "qc.calchem_opt"
            | "qc.xtb"
            | "wfn.multiwfn"
            | "md.gromacs_mdp"
            | "trajectory.rdf"
            | "structure.planarity"
            | "structure.export"
    )
}

/// 在依赖检查之上叠加适配器门禁，返回 (runnable, missing, reason)。
fn gate_adapters(
    required: &[String],
    base: (bool, Vec<String>, String),
) -> (bool, Vec<String>, String) {
    let (mut runnable, mut missing, mut reason) = base;
    let no_adapter: Vec<String> = required
        .iter()
        .filter(|c| !capability_has_adapter(c))
        .map(|c| format!("capability '{c}' 尚未接入执行适配器"))
        .collect();
    if !no_adapter.is_empty() {
        runnable = false;
        missing.extend(no_adapter.clone());
        reason = format!("{reason}；{}", no_adapter.join("；"));
    }
    (runnable, missing, reason)
}

fn run_capability_node(
    capability: Option<&str>,
    params: &serde_json::Value,
    mol: &Molecule,
    engine_paths: &EnginePaths,
    _caps: &[CapabilitySpec],
) -> std::result::Result<(String, serde_json::Value), String> {
    match capability.unwrap_or("") {
        "qc.tight_binding" => {
            let res = qc::run_tight_binding(mol).map_err(|e| e.to_string())?;
            let sum = format!(
                "HOMO = {:.3} eV, LUMO = {:.3} eV, Gap = {:.3} eV",
                res.homo_ev.unwrap_or(0.0),
                res.lumo_ev.unwrap_or(0.0),
                res.gap_ev.unwrap_or(0.0)
            );
            Ok((sum, serde_json::to_value(res).unwrap_or_default()))
        }
        "qc.calchem_scf" | "qc.calchem_opt" => {
            let method = params["method"].as_str().unwrap_or("HF");
            let basis = params["basis"].as_str().unwrap_or("STO-3G");
            let optimize = capability == Some("qc.calchem_opt")
                || params["optimize"].as_bool().unwrap_or(false);
            let (chg, mult, _) = summary::resolve_spin_state(mol);
            let res = qc::run_calchem(mol, method, basis, chg, mult as usize, optimize)
                .map_err(|e| e.to_string())?;
            if !res.available {
                return Err(res.message);
            }
            let sum = format!(
                "{method}/{basis}: E = {:.6} Eh (converged={})",
                res.total_energy_hartree, res.converged
            );
            Ok((sum, serde_json::to_value(res).unwrap_or_default()))
        }
        "qc.xtb" => {
            let method = params["method"].as_str().unwrap_or("gfn2");
            let optimize = params["optimize"].as_bool().unwrap_or(true);
            let (chg, mult, _) = summary::resolve_spin_state(mol);
            let res = engines::run_xtb_native(
                mol,
                method,
                optimize,
                chg,
                mult.saturating_sub(1),
                engine_paths,
            )
            .map_err(|e| e.to_string())?;
            Ok((
                format!("xTB ({method}) 退出码 {}", res.exit_code),
                serde_json::to_value(res).unwrap_or_default(),
            ))
        }
        "wfn.multiwfn" => {
            let aid = params["analysis_id"].as_str().unwrap_or("WFN-01");
            let res = engines::run_multiwfn_native(mol, aid, None, engine_paths)
                .map_err(|e| e.to_string())?;
            Ok((res.message.clone(), serde_json::to_value(res).unwrap_or_default()))
        }
        "md.gromacs_mdp" => {
            let ensemble = params["ensemble"].as_str().unwrap_or("nvt");
            let nsteps = params["nsteps"].as_u64().unwrap_or(50000);
            let mdp = engines::generate_gromacs_mdp(ensemble, nsteps, 0.002, 300.0);
            Ok((
                format!("已生成 {ensemble} ({nsteps} 步) GROMACS MDP 参数"),
                serde_json::json!({ "mdp": mdp }),
            ))
        }
        "trajectory.rdf" => {
            let r_max = params["r_max"].as_f64().unwrap_or(12.0);
            let n_bins = params["n_bins"].as_u64().unwrap_or(80) as usize;
            let res = engines::compute_pairwise_rdf(mol, r_max, n_bins).map_err(|e| e.to_string())?;
            Ok((
                format!(
                    "RDF ({}) 实算完成：首峰 r = {:.2} Å (g(r) = {:.2}, {} 对)",
                    res.mode, res.first_peak_r_angstrom, res.first_peak_g_r, res.num_pairs
                ),
                serde_json::to_value(res).unwrap_or_default(),
            ))
        }
        "structure.planarity" => {
            let res = summary::compute_planarity(mol).map_err(|e| e.to_string())?;
            Ok((
                format!(
                    "平面性实算完成：MPP = {:.4} Å, SDP = {:.4} Å ({} 重原子)",
                    res.mpp_angstrom, res.sdp_angstrom, res.heavy_atom_count
                ),
                serde_json::to_value(res).unwrap_or_default(),
            ))
        }
        "structure.export" => {
            let fmt = params["format"].as_str().unwrap_or("xyz");
            let text = match fmt {
                "pdb" => io::write_pdb(mol),
                "mol" => io::write_mol_v2000(mol),
                _ => io::write_xyz(mol),
            };
            Ok((
                format!("已导出 {fmt} ({} 字节)", text.len()),
                serde_json::json!({ "format": fmt, "content": text }),
            ))
        }
        other => Err(format!("capability '{other}' 尚未接入执行适配器")),
    }
}

/// Deterministic AI Intent Router + Skill Retriever + Workflow Planner.
pub fn plan_workflow_from_intent(
    query: &str,
    registry: &HubRegistry,
    engine_paths: &EnginePaths,
    python_exe: Option<&Path>,
) -> WorkflowProposal {
    let q = query.trim().to_ascii_lowercase();
    let workflows = builtin_workflows();

    let (wf_id, intent_caps): (&str, Vec<String>) = if q.contains("rdf")
        || q.contains("gromacs")
        || q.contains("轨迹")
        || q.contains("动力学")
        || q.contains("md")
    {
        (
            "org.molforge.workflow.md-rdf",
            vec!["md.gromacs_mdp".into(), "trajectory.rdf".into()],
        )
    } else if q.contains("multiwfn") || q.contains("esp") || q.contains("elf") || q.contains("波函数") {
        ("org.molforge.workflow.multiwfn-wfn", vec!["wfn.multiwfn".into()])
    } else if q.contains("xtb") || q.contains("构象") || q.contains("优化") {
        (
            "org.molforge.workflow.xtb-preopt",
            vec!["qc.xtb".into(), "structure.export".into()],
        )
    } else if q.contains("calchem") || q.contains("scf") || q.contains("dft") || q.contains("从头算") {
        (
            "org.molforge.workflow.calchem-sp-opt",
            vec!["qc.calchem_scf".into(), "structure.export".into()],
        )
    } else {
        (
            "org.molforge.workflow.frontier-mo",
            vec!["qc.tight_binding".into()],
        )
    };

    let selected = workflows
        .into_iter()
        .find(|w| w.id == wf_id)
        .expect("builtin workflow must exist");

    let engines = engines::probe_all(engine_paths, python_exe);
    let caps = registry.capabilities(&engines);
    let (runnable, missing, reason) = gate_adapters(
        &selected.requires_capabilities,
        registry.check_dependencies(&selected.requires_capabilities, &caps),
    );

    let matched_skills: Vec<serde_json::Value> = registry
        .skills
        .iter()
        .filter(|s| {
            s.capabilities
                .iter()
                .any(|c| selected.requires_capabilities.contains(c))
        })
        .map(|s| {
            serde_json::json!({
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "sha256": s.sha256,
            })
        })
        .collect();

    let explanation = if runnable {
        format!(
            "已匹配工作流「{}」，关联 {} 个科研技能（{}），所有依赖能力已就绪，可直接审核后执行。",
            selected.title,
            matched_skills.len(),
            selected.requires_capabilities.join(", ")
        )
    } else {
        format!(
            "已匹配工作流「{}」，但检测到缺失依赖（{}）。请先在 Hub 中安装/配置对应引擎后再执行，系统不会使用模拟数据替代。",
            selected.title,
            missing.join("；")
        )
    };

    WorkflowProposal {
        query: query.to_string(),
        intent_capabilities: intent_caps,
        matched_skills,
        selected_workflow: selected,
        runnable,
        missing_dependencies: missing,
        status_reason: reason,
        explanation,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presets::build_preset;

    #[test]
    fn frontier_mo_workflow_runs_with_provenance() {
        let mol = build_preset("benzene").unwrap();
        let reg = HubRegistry::new();
        let paths = EnginePaths::default();
        let wf = builtin_workflows()
            .into_iter()
            .find(|w| w.id == "org.molforge.workflow.frontier-mo")
            .unwrap();
        let run = execute_workflow(&wf, &mol, &reg, &paths, None, true, None).unwrap();
        assert_eq!(run.status, WorkflowRunStatus::Completed);
        assert_eq!(run.node_records.len(), 3);
        assert!(!run.provenance.input_molecule_sha256.is_empty());
        assert!(!run.provenance.matched_skill_ids.is_empty());
    }

    #[test]
    fn xtb_workflow_requires_approval_before_external_exec() {
        let mol = build_preset("water").unwrap();
        let reg = HubRegistry::new();
        let paths = EnginePaths::default();
        let wf = builtin_workflows()
            .into_iter()
            .find(|w| w.id == "org.molforge.workflow.xtb-preopt")
            .unwrap();
        let run = execute_workflow(&wf, &mol, &reg, &paths, None, false, None).unwrap();
        assert!(matches!(
            run.status,
            WorkflowRunStatus::PendingApproval | WorkflowRunStatus::Blocked
        ));
    }

    #[test]
    fn cycle_detection_rejects_cyclic_dag() {
        let mut wf = builtin_workflows().into_iter().next().unwrap();
        let dep_id = wf.nodes[1].id.clone();
        wf.nodes[0].depends_on.push(dep_id);
        assert!(topological_order(&wf).is_err());
    }
}
