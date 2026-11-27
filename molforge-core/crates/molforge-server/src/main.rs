//! MolForge Studio Native Rust HTTP + Binary `MOLF` Core Server.
//!
//! Runs standalone on `127.0.0.1:18765` (configurable via `MOLFORGE_PORT`)
//! with ZERO mandatory Python dependency.

use base64::Engine as _;
use molforge_core::commands::{CommandBus, EditCommand};
use molforge_core::engines::{self, EnginePaths};
use molforge_core::hub::HubRegistry;
use molforge_core::jobs::JobQueue;
use molforge_core::presets;
use molforge_core::python_worker;
use molforge_core::qc;
use molforge_core::skills;
use molforge_core::summary;
use molforge_core::workflow::{self, WorkflowRun};
use molforge_core::{binary, delivery, elements, io, topology};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use tiny_http::{Header, Method, Request, Response, StatusCode};

struct AppState {
    bus: CommandBus,
    engine_paths: EnginePaths,
    python_exe: Option<PathBuf>,
    jobs: JobQueue,
    hub: HubRegistry,
    workflow_runs: Vec<WorkflowRun>,
    preferences: Value,
}

impl AppState {
    fn new() -> Self {
        let initial = presets::build_preset("caffeine").expect("caffeine preset");
        let python_exe = python_worker::discover_python();
        Self {
            bus: CommandBus::new(initial),
            engine_paths: EnginePaths::default(),
            python_exe,
            jobs: JobQueue::new(),
            hub: HubRegistry::new(),
            workflow_runs: Vec::new(),
            preferences: json!({
                "theme": "obsidian",
                "render_mode": "ball_and_stick",
                "show_hydrogens": true,
                "ai_provider": "openai-compatible",
                "ai_model": "deepseek-chat",
                "ai_base_url": "https://api.deepseek.com/v1"
            }),
        }
    }

    fn doc_summary(&self) -> summary::DocumentSummary {
        summary::summarize(&self.bus, presets::preset_names())
    }
}

fn cors_headers() -> Vec<Header> {
    vec![
        Header::from_bytes("Access-Control-Allow-Origin", "*").unwrap(),
        Header::from_bytes("Access-Control-Allow-Methods", "GET, POST, OPTIONS").unwrap(),
        Header::from_bytes("Access-Control-Allow-Headers", "Content-Type, Authorization").unwrap(),
    ]
}

fn json_response(status: u16, body: &Value) -> Response<std::io::Cursor<Vec<u8>>> {
    let bytes = serde_json::to_vec(body).unwrap_or_else(|_| b"{}".to_vec());
    let mut resp = Response::from_data(bytes).with_status_code(StatusCode(status));
    resp.add_header(Header::from_bytes("Content-Type", "application/json; charset=utf-8").unwrap());
    for h in cors_headers() {
        resp.add_header(h);
    }
    resp
}

fn bin_response(status: u16, bytes: Vec<u8>) -> Response<std::io::Cursor<Vec<u8>>> {
    let mut resp = Response::from_data(bytes).with_status_code(StatusCode(status));
    resp.add_header(Header::from_bytes("Content-Type", "application/octet-stream").unwrap());
    for h in cors_headers() {
        resp.add_header(h);
    }
    resp
}

fn err_response(status: u16, msg: impl Into<String>) -> Response<std::io::Cursor<Vec<u8>>> {
    json_response(status, &json!({ "ok": false, "error": msg.into() }))
}

fn read_bytes(req: &mut Request) -> Vec<u8> {
    let mut buf = Vec::new();
    let _ = req.as_reader().read_to_end(&mut buf);
    buf
}

fn read_json(req: &mut Request) -> Value {
    let bytes = read_bytes(req);
    if bytes.is_empty() {
        return json!({});
    }
    serde_json::from_slice(&bytes).unwrap_or_else(|_| json!({}))
}

fn hex_color(rgb: [u8; 3]) -> String {
    format!("#{:02x}{:02x}{:02x}", rgb[0], rgb[1], rgb[2])
}

fn contrast_text(rgb: [u8; 3]) -> &'static str {
    let luma = 0.299 * rgb[0] as f64 + 0.587 * rgb[1] as f64 + 0.114 * rgb[2] as f64;
    if luma > 150.0 {
        "#0f172a"
    } else {
        "#f8fafc"
    }
}

fn main() {
    let host = std::env::var("MOLFORGE_HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port: u16 = std::env::var("MOLFORGE_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(18765);
    let addr = format!("{host}:{port}");

    let server = tiny_http::Server::http(&addr).expect("failed to bind molforge-server");
    let state = Arc::new(Mutex::new(AppState::new()));
    println!("molforge-server listening on http://{addr}");

    for mut req in server.incoming_requests() {
        let state = state.clone();
        std::thread::spawn(move || {
            let resp = handle_request(&mut req, &state);
            let _ = req.respond(resp);
        });
    }
}

fn format_calchem_json(res: &qc::CalchemScfResult, optimize: bool) -> Value {
    let ok = res.available
        && res.total_energy_hartree.is_finite()
        && res.total_energy_hartree != 0.0;
    const HARTREE_TO_EV: f64 = 27.211386245988;
    json!({
        "ok": ok,
        "mode": if optimize { "opt" } else { "sp" },
        "method": res.method,
        "basis": res.basis,
        "converged": res.converged,
        "iterations": res.iterations,
        "steps": res.iterations,
        "total_energy_hartree": if ok { json!(res.total_energy_hartree) } else { Value::Null },
        "homo_ev": res.homo_hartree.map(|v| v * HARTREE_TO_EV),
        "lumo_ev": res.lumo_hartree.map(|v| v * HARTREE_TO_EV),
        "gap_ev": res.gap_ev,
        "dipole_magnitude_debye": res.dipole_magnitude_debye,
        "n_ao": res.n_ao,
        "message": res.message,
        "error": if ok { Value::Null } else { json!(res.message) },
    })
}

fn dispatch_analysis(
    mol: &molforge_core::model::Molecule,
    analysis_id: &str,
    input_file: Option<&str>,
    paths: &EnginePaths,
) -> std::result::Result<(bool, Value), String> {
    let aid = analysis_id.trim().to_ascii_uppercase();
    if aid.starts_with("WFN") {
        let res = engines::run_multiwfn_native(mol, analysis_id, input_file, paths)
            .map_err(|e| e.to_string())?;
        let ok = res.ok;
        return Ok((ok, json!({ "ok": ok, "result": res })));
    }
    if aid.starts_with("CORE") || aid.contains("FRONTIER") || aid.contains("HOMO") {
        let tb = qc::run_tight_binding(mol).map_err(|e| e.to_string())?;
        return Ok((
            true,
            json!({
                "ok": true,
                "result": {
                    "analysis_id": analysis_id,
                    "title": format!("MolForge Native Tight-Binding ({analysis_id})"),
                    "status": "completed",
                    "summary": format!(
                        "HOMO = {:.3} eV, LUMO = {:.3} eV, Gap = {:.3} eV",
                        tb.homo_ev.unwrap_or(0.0),
                        tb.lumo_ev.unwrap_or(0.0),
                        tb.gap_ev.unwrap_or(0.0)
                    ),
                    "metrics": {
                        "pi_atoms": tb.num_pi_atoms,
                        "pi_electrons": tb.num_pi_electrons,
                        "homo_ev": tb.homo_ev,
                        "lumo_ev": tb.lumo_ev,
                        "gap_ev": tb.gap_ev,
                    },
                    "plot_x": (1..=tb.mo_energies_ev.len()).collect::<Vec<_>>(),
                    "plot_y": tb.mo_energies_ev,
                    "x_label": "Orbital Index",
                    "y_label": "Energy (eV)",
                }
            }),
        ));
    }
    if aid == "PROP-MPP" || aid.contains("MPP") || aid.contains("PLANAR") {
        let p = summary::compute_planarity(mol).map_err(|e| e.to_string())?;
        return Ok((
            true,
            json!({
                "ok": true,
                "result": {
                    "analysis_id": analysis_id,
                    "title": format!("分子平面性 SVD/Jacobi 实算 ({analysis_id})"),
                    "status": "completed",
                    "summary": format!(
                        "MPP = {:.4} Å, SDP = {:.4} Å, 最大离面 {:.4} Å ({} 重原子)",
                        p.mpp_angstrom, p.sdp_angstrom, p.max_deviation_angstrom, p.heavy_atom_count
                    ),
                    "metrics": {
                        "heavy_atom_count": p.heavy_atom_count,
                        "mpp_angstrom": (p.mpp_angstrom * 100000.0).round() / 100000.0,
                        "sdp_angstrom": (p.sdp_angstrom * 100000.0).round() / 100000.0,
                        "max_deviation_angstrom": (p.max_deviation_angstrom * 100000.0).round() / 100000.0,
                        "plane_normal": p.normal,
                    },
                    "plot_x": p.atom_indices,
                    "plot_y": p.signed_deviations_angstrom,
                    "x_label": "Heavy Atom Index",
                    "y_label": "Plane Deviation d_s (Å)",
                }
            }),
        ));
    }
    if aid == "PROP-TORSION" || aid.contains("TORSION") || aid.contains("DIHEDRAL") {
        let t = topology::compute_torsions(mol).map_err(|e| e.to_string())?;
        let cw_count = t
            .torsions
            .iter()
            .filter(|x| x.bond_type == "core-wing")
            .count();
        let plot_x: Vec<usize> = (1..=t.torsions.len()).collect();
        let plot_y: Vec<f64> = t.torsions.iter().map(|x| x.angle).collect();
        let first_desc = t
            .torsions
            .first()
            .map(|x| {
                format!(
                    "θ1 = {:.2}° (环间 {:.2}°, d = {:.3} Å, {})",
                    x.angle,
                    x.interplanar_deg.unwrap_or(0.0),
                    x.bond_length_a,
                    x.bond_type
                )
            })
            .unwrap_or_else(|| "未检测到环-环可旋转单键".to_string());
        return Ok((
            true,
            json!({
                "ok": true,
                "result": {
                    "analysis_id": analysis_id,
                    "title": format!("拓扑核-翼锐角二面角与构象锁 ({analysis_id})"),
                    "status": "completed",
                    "summary": format!(
                        "{}；共 {} 条旋转键（core-wing {}），{} 处弱相互作用锁（主核 {} 原子）",
                        first_desc,
                        t.torsions.len(),
                        cw_count,
                        t.short_contacts.len(),
                        t.core_atoms.len()
                    ),
                    "metrics": {
                        "torsion_count": t.torsions.len(),
                        "core_wing_count": cw_count,
                        "short_contact_count": t.short_contacts.len(),
                        "core_atoms": t.core_atoms,
                        "axis_used": t.axis_used,
                        "torsions": t.torsions,
                        "short_contacts": t.short_contacts,
                    },
                    "plot_x": plot_x,
                    "plot_y": plot_y,
                    "x_label": "Torsion Bond Index",
                    "y_label": "Acute Torsion Angle (°)",
                }
            }),
        ));
    }
    if aid == "MD-RDF" || aid == "MD-01" || aid.contains("RDF") {
        let r = engines::compute_pairwise_rdf(mol, 12.0, 80).map_err(|e| e.to_string())?;
        return Ok((
            true,
            json!({
                "ok": true,
                "result": {
                    "analysis_id": analysis_id,
                    "title": format!("径向分布函数 RDF g(r) 实算 ({analysis_id})"),
                    "status": "completed",
                    "summary": format!(
                        "首峰 r = {:.2} Å (g(r) = {:.2}), {} 原子 / {} 原子对",
                        r.first_peak_r_angstrom, r.first_peak_g_r, r.num_atoms, r.num_pairs
                    ),
                    "metrics": {
                        "mode": r.mode,
                        "num_atoms": r.num_atoms,
                        "num_pairs": r.num_pairs,
                        "volume_a3": r.volume_a3,
                        "first_peak_r_angstrom": r.first_peak_r_angstrom,
                        "first_peak_g_r": r.first_peak_g_r,
                    },
                    "plot_x": r.r_angstrom,
                    "plot_y": r.g_r,
                    "x_label": "Distance r (Å)",
                    "y_label": "g(r)",
                }
            }),
        ));
    }
    if aid == "QC-01" {
        let (chg, mult, _) = summary::resolve_spin_state(mol);
        let res = qc::run_calchem(mol, "HF", "STO-3G", chg, mult as usize, false)
            .map_err(|e| e.to_string())?;
        let ok = res.available && res.total_energy_hartree.is_finite() && res.total_energy_hartree != 0.0;
        return Ok((
            ok,
            json!({
                "ok": ok,
                "result": {
                    "analysis_id": analysis_id,
                    "title": "CalChem v0.3.0 HF/STO-3G 实算",
                    "status": if ok { "completed" } else { "unavailable" },
                    "summary": res.message,
                    "metrics": {
                        "total_energy_hartree": res.total_energy_hartree,
                        "dipole_magnitude_debye": res.dipole_magnitude_debye,
                        "n_ao": res.n_ao,
                        "iterations": res.iterations,
                    },
                    "plot_x": [],
                    "plot_y": [],
                    "x_label": "",
                    "y_label": "",
                }
            }),
        ));
    }
    Ok((
        false,
        json!({
            "ok": false,
            "result": {
                "analysis_id": analysis_id,
                "title": format!("未接入真实引擎 ({analysis_id})"),
                "status": "unavailable",
                "summary": "该分析项目尚未接入真实计算引擎，系统拒绝返回模拟数据。可选：CORE-01 / PROP-MPP / MD-RDF / QC-01 / WFN-01,06,08,12。",
                "metrics": {},
                "plot_x": [],
                "plot_y": [],
                "x_label": "",
                "y_label": "",
            }
        }),
    ))
}

fn read_energy_from_qc_file(path: &str) -> std::result::Result<f64, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("读取 '{path}' 失败: {e}"))?;
    let parsed = qc::parse_qc_log(&text).map_err(|e| e.to_string())?;
    parsed
        .total_energy_hartree
        .ok_or_else(|| format!("'{path}' 中未解析到 SCF 总能量 (Hartree)"))
}

fn handle_request(
    req: &mut Request,
    state: &Arc<Mutex<AppState>>,
) -> Response<std::io::Cursor<Vec<u8>>> {
    if *req.method() == Method::Options {
        let mut resp = Response::from_data(Vec::new()).with_status_code(StatusCode(204));
        for h in cors_headers() {
            resp.add_header(h);
        }
        return resp;
    }

    let path = req.url().split('?').next().unwrap_or("/");
    let method = req.method().clone();

    match (method, path) {
        (Method::Get, "/api/health") => {
            let st = state.lock().unwrap();
            json_response(
                200,
                &json!({
                    "ok": true,
                    "version": env!("CARGO_PKG_VERSION"),
                    "core": "molforge-rust",
                    "calchem": cfg!(feature = "calchem"),
                    "python_worker": st.python_exe.is_some(),
                    "document": st.doc_summary(),
                }),
            )
        }
        (Method::Get, "/api/document") => {
            let st = state.lock().unwrap();
            json_response(200, &json!(st.doc_summary()))
        }
        (Method::Get, "/api/document/binary") => {
            let bytes = {
                let st = state.lock().unwrap();
                binary::encode_molf_v1(&st.bus.mol)
            };
            bin_response(200, bytes)
        }
        (Method::Get, "/api/atoms") => {
            let st = state.lock().unwrap();
            let mol = &st.bus.mol;
            let limit = 5000usize;
            let truncated = mol.atoms.len() > limit;
            let atoms: Vec<Value> = mol
                .atoms
                .iter()
                .take(limit)
                .enumerate()
                .map(|(i, a)| {
                    let rgb = a.color.unwrap_or_else(|| elements::rgb(a.z));
                    json!({
                        "index": i,
                        "atom_id": a.id,
                        "display_id": i + 1,
                        "symbol": elements::symbol_of(a.z),
                        "atomic_num": a.z,
                        "x2": a.pos2[0],
                        "y2": a.pos2[1],
                        "x": a.pos[0],
                        "y": a.pos[1],
                        "z": a.pos[2],
                        "formal_charge": a.charge,
                        "color": rgb,
                    })
                })
                .collect();
            let bonds: Vec<Value> = mol
                .bonds
                .iter()
                .filter_map(|b| {
                    let i = mol.atom_index(b.a)?;
                    let j = mol.atom_index(b.b)?;
                    if i < limit && j < limit {
                        Some(json!({
                            "bond_id": b.id,
                            "i": i,
                            "j": j,
                            "order": b.order,
                            "aromatic": b.aromatic,
                        }))
                    } else {
                        None
                    }
                })
                .collect();
            json_response(
                200,
                &json!({
                    "truncated": truncated,
                    "num_atoms": mol.atoms.len(),
                    "atoms": atoms,
                    "bonds": bonds,
                }),
            )
        }
        (Method::Get, "/api/elements") => {
            let items: Vec<Value> = elements::all()
                .iter()
                .map(|e| {
                    let rgb = elements::rgb(e.z);
                    json!({
                        "atomic_number": e.z,
                        "symbol": e.symbol,
                        "name": e.name,
                        "name_cn": e.name_cn,
                        "atomic_weight": e.weight,
                        "electronegativity": e.en,
                        "vdw_radius": e.vdw,
                        "covalent_radius": e.cov,
                        "electron_config": e.config,
                        "group": e.group,
                        "period": e.period,
                        "block": e.block,
                        "category": e.category,
                        "hex_color": hex_color(rgb),
                        "text_color": contrast_text(rgb),
                    })
                })
                .collect();
            json_response(200, &json!({ "elements": items }))
        }
        (Method::Get, "/api/fragments") => {
            let items: Vec<Value> = presets::fragment_catalog()
                .into_iter()
                .map(|f| {
                    json!({
                        "id": f.id,
                        "name_cn": f.label,
                        "name_en": f.label,
                        "formula": f.formula,
                        "category": f.category,
                        "smiles": "",
                        "attachment_bond_order": 1,
                        "num_atoms": f.atoms.len(),
                        "description": f.label,
                    })
                })
                .collect();
            json_response(200, &json!({ "fragments": items }))
        }
        (Method::Get, "/api/library/presets") => {
            let items: Vec<Value> = presets::preset_catalog()
                .into_iter()
                .filter_map(|p| {
                    let mol = presets::build_preset(p.id)?;
                    let (_, mult, _) = summary::resolve_spin_state(&mol);
                    let atoms_2d: Vec<Value> = mol
                        .atoms
                        .iter()
                        .enumerate()
                        .map(|(i, a)| {
                            json!({
                                "index": i,
                                "symbol": elements::symbol_of(a.z),
                                "atomic_num": a.z,
                                "x2": a.pos2[0],
                                "y2": a.pos2[1],
                                "color": elements::rgb(a.z),
                            })
                        })
                        .collect();
                    let bonds_2d: Vec<Value> = mol
                        .bonds
                        .iter()
                        .filter_map(|b| {
                            Some(json!({
                                "i": mol.atom_index(b.a)?,
                                "j": mol.atom_index(b.b)?,
                                "order": b.order,
                                "aromatic": b.aromatic,
                            }))
                        })
                        .collect();
                    Some(json!({
                        "id": p.id,
                        "name": p.name,
                        "label": p.name,
                        "category": p.category,
                        "smiles": p.smiles,
                        "formula": summary::formula(&mol),
                        "molecular_weight": summary::molecular_weight(&mol),
                        "num_atoms": mol.atoms.len(),
                        "num_bonds": mol.bonds.len(),
                        "multiplicity": mult,
                        "preview_2d": { "atoms": atoms_2d, "bonds": bonds_2d },
                    }))
                })
                .collect();
            json_response(200, &json!({ "items": items }))
        }
        (Method::Post, "/api/library/inspect_smiles") => {
            let body = read_json(req);
            let items: Vec<Value> = body["items"].as_array().cloned().unwrap_or_default();
            let st = state.lock().unwrap();
            let inspected = python_worker::inspect_smiles_batch_via_worker(st.python_exe.as_deref(), &items);
            json_response(200, &json!({ "ok": true, "items": inspected }))
        }
        (Method::Get, "/api/analysis/catalog") => json_response(
            200,
            &json!({
                "items": [
                    { "id": "CORE-01", "category": "基础拓扑", "title": "紧束缚 pi-MO 轨道与能隙", "engine": "molforge-core", "state": "ready", "note": "纯 Rust Huckel pi-MO 求解器" },
                    { "id": "PROP-MPP", "category": "有机半导体表征", "title": "分子平面性 MPP / SDP 与离面偏离", "engine": "molforge-core", "state": "ready", "note": "纯 Rust 重原子最小二乘平面拟合（无需外部依赖）" },
                    { "id": "PROP-TORSION", "category": "有机半导体表征", "title": "拓扑核-翼锐角二面角、环面夹角与构象锁", "engine": "molforge-core", "state": "ready", "note": "纯 Rust 最大稠环主核、四路径锐角择优 (|D|<=90°) 与非共价弱锁识别" },
                    { "id": "MD-RDF", "category": "分子动力学", "title": "径向分布函数 RDF g(r) 实算", "engine": "molforge-core", "state": "ready", "note": "纯 Rust 成对距离分布与配位数积分 g(r)/N(r)" },
                    { "id": "QC-01", "category": "从头算量子化学", "title": "CalChem v0.3.0 纯 Rust HF/DFT SCF", "engine": "calchem", "state": if cfg!(feature = "calchem") { "ready" } else { "disabled" }, "note": "进程内 HF/B3LYP/PBE/PBE0/CAM-B3LYP/wB97X-D 单点能与偶极" },
                    { "id": "QC-02", "category": "从头算量子化学", "title": "CalChem 几何结构优化", "engine": "calchem", "state": if cfg!(feature = "calchem") { "ready" } else { "disabled" }, "note": "纯 Rust 解析梯度几何优化" },
                    { "id": "XTB-01", "category": "半经验量子化学", "title": "GFN2-xTB 结构优化", "engine": "xtb", "state": "external", "note": "调用本机 xtb 可执行程序" },
                    { "id": "WFN-12", "category": "波函数分析", "title": "Multiwfn NCI/RDG 弱相互作用散点", "engine": "multiwfn", "state": "external", "note": "坐标走 promolecular，.fchk 走波函数 NCI/RDG" },
                    { "id": "WFN-01", "category": "波函数分析", "title": "Multiwfn 定量分子表面静电势 ESP", "engine": "multiwfn", "state": "external", "note": "需选择 .fchk/.wfn/.molden，输出 Vs,min/max、MPI、面积与表面极值" },
                    { "id": "WFN-06", "category": "波函数分析", "title": "Multiwfn Mayer 键级分析", "engine": "multiwfn", "state": "external", "note": "需选择 .fchk/.wfn/.molden，输出真实 Mayer 键级表" },
                    { "id": "WFN-08", "category": "波函数分析", "title": "Multiwfn ADCH 原子电荷", "engine": "multiwfn", "state": "external", "note": "需选择 .fchk/.wfn/.molden，输出原子偶极校正 Hirshfeld 电荷" }
                ]
            }),
        ),
        (Method::Get, "/api/engines/status") => {
            let st = state.lock().unwrap();
            let list = engines::probe_all(&st.engine_paths, st.python_exe.as_deref());
            json_response(
                200,
                &json!({
                    "engines": list,
                    "calchem_basis_sets": ["STO-3G", "3-21G", "6-31G", "6-31G*", "cc-pVDZ", "def2-SVP", "def2-TZVP"],
                }),
            )
        }
        (Method::Get, "/api/jobs") => {
            let jobs = {
                let st = state.lock().unwrap();
                st.jobs.clone()
            };
            json_response(200, &json!({ "jobs": jobs.list() }))
        }
        (Method::Get, "/api/preferences") => {
            let st = state.lock().unwrap();
            json_response(200, &st.preferences)
        }
        (Method::Post, "/api/preferences") => {
            let body = read_json(req);
            let mut st = state.lock().unwrap();
            if let (Some(dst), Some(src)) = (st.preferences.as_object_mut(), body.as_object()) {
                for (k, v) in src {
                    dst.insert(k.clone(), v.clone());
                }
            }
            json_response(200, &st.preferences)
        }
        (Method::Post, "/api/build/preset") => {
            let body = read_json(req);
            let name = body["id"]
                .as_str()
                .or_else(|| body["name"].as_str())
                .unwrap_or("caffeine");
            let Some(mol) = presets::build_preset(name) else {
                return err_response(404, format!("unknown preset '{name}'"));
            };
            let mut st = state.lock().unwrap();
            st.bus.replace_document(mol);
            json_response(200, &json!({ "ok": true, "document": st.doc_summary() }))
        }
        (Method::Post, "/api/build/smiles") => {
            let body = read_json(req);
            let smiles = body["smiles"].as_str().unwrap_or("").trim();
            if smiles.is_empty() {
                return err_response(400, "smiles is required");
            }
            let py = {
                let st = state.lock().unwrap();
                st.python_exe.clone()
            };
            match python_worker::build_smiles_optional(py.as_deref(), smiles) {
                Ok(mol) => {
                    let mut st = state.lock().unwrap();
                    st.bus.replace_document(mol);
                    json_response(200, &json!({ "ok": true, "document": st.doc_summary() }))
                }
                Err(e) => err_response(503, e.to_string()),
            }
        }
        (Method::Post, "/api/open") => {
            let body = read_json(req);
            let file_path = body["path"].as_str().unwrap_or("");
            let content_bytes = if let Some(b64) = body["content_base64"].as_str() {
                match base64::engine::general_purpose::STANDARD.decode(b64) {
                    Ok(b) => b,
                    Err(e) => return err_response(400, format!("invalid base64: {e}")),
                }
            } else if let Some(txt) = body["content"].as_str() {
                txt.as_bytes().to_vec()
            } else if !file_path.is_empty() {
                match std::fs::read(file_path) {
                    Ok(b) => b,
                    Err(e) => return err_response(400, format!("failed to read '{file_path}': {e}")),
                }
            } else {
                return err_response(400, "path or content is required");
            };

            let t0 = std::time::Instant::now();
            match io::open_by_extension(file_path, &content_bytes) {
                Ok(mol) => {
                    let mut st = state.lock().unwrap();
                    st.bus.replace_document(mol);
                    json_response(
                        200,
                        &json!({
                            "ok": true,
                            "parse_ms": t0.elapsed().as_secs_f64() * 1000.0,
                            "document": st.doc_summary(),
                        }),
                    )
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/export") => {
            let body = read_json(req);
            let fmt = body["format"].as_str().unwrap_or("xyz").to_ascii_lowercase();
            let out_path = body["path"].as_str();
            let st = state.lock().unwrap();
            let (charge, mult, _) = summary::resolve_spin_state(&st.bus.mol);
            let content = match fmt.as_str() {
                "xyz" => io::write_xyz(&st.bus.mol),
                "pdb" => io::write_pdb(&st.bus.mol),
                "mol" | "sdf" => io::write_mol_v2000(&st.bus.mol),
                "gjf" => io::write_gjf(&st.bus.mol, "B3LYP", "6-31G(d)", charge, mult, true),
                "inp" | "orca" => io::write_orca_inp(&st.bus.mol, "B3LYP", "def2-SVP", charge, mult, true),
                "rest" | "ctrl" => io::write_rest_ctrl(&st.bus.mol, "b3lyp", "def2-SVP", charge, mult),
                _ => return err_response(400, format!("unsupported export format '{fmt}'")),
            };
            if let Some(p) = out_path {
                if let Err(e) = std::fs::write(p, content.as_bytes()) {
                    return err_response(500, format!("failed to write '{p}': {e}"));
                }
            }
            let filename = format!("{}.{fmt}", st.bus.mol.name.replace(' ', "_"));
            json_response(
                200,
                &json!({ "ok": true, "format": fmt, "filename": filename, "content": content }),
            )
        }
        (Method::Post, "/api/project/export_mforge_bytes") => {
            let st = state.lock().unwrap();
            match io::export_mforge_bytes(&st.bus.mol) {
                Ok(bytes) => {
                    let b64 = base64::engine::general_purpose::STANDARD.encode(bytes);
                    json_response(200, &json!({ "ok": true, "base64": b64, "document": st.doc_summary() }))
                }
                Err(e) => err_response(500, e.to_string()),
            }
        }
        (Method::Post, "/api/project/import_mforge_bytes") => {
            let body = read_json(req);
            let raw = if let Some(b64) = body["base64"].as_str() {
                match base64::engine::general_purpose::STANDARD.decode(b64) {
                    Ok(b) => b,
                    Err(e) => return err_response(400, format!("invalid base64: {e}")),
                }
            } else {
                return err_response(400, "base64 is required");
            };
            match io::import_mforge_bytes(&raw) {
                Ok(mut mol) => {
                    if let Some(sp) = body["source_path"].as_str() {
                        mol.source_path = Some(sp.to_string());
                    }
                    let mut st = state.lock().unwrap();
                    st.bus.replace_document(mol);
                    json_response(200, &json!({ "ok": true, "document": st.doc_summary() }))
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/project/save_mforge") => {
            let body = read_json(req);
            let Some(p) = body["path"].as_str() else {
                return err_response(400, "path is required");
            };
            let st = state.lock().unwrap();
            match io::export_mforge_bytes(&st.bus.mol) {
                Ok(bytes) => match std::fs::write(p, bytes) {
                    Ok(_) => json_response(200, &json!({ "ok": true, "path": p })),
                    Err(e) => err_response(500, e.to_string()),
                },
                Err(e) => err_response(500, e.to_string()),
            }
        }
        (Method::Post, "/api/project/open_mforge") => {
            let body = read_json(req);
            let Some(p) = body["path"].as_str() else {
                return err_response(400, "path is required");
            };
            match std::fs::read(p).and_then(|b| {
                io::import_mforge_bytes(&b)
                    .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e.to_string()))
            }) {
                Ok(mut mol) => {
                    mol.source_path = Some(p.to_string());
                    let mut st = state.lock().unwrap();
                    st.bus.replace_document(mol);
                    json_response(200, &json!({ "ok": true, "document": st.doc_summary() }))
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/edit/clean_3d") => {
            let mut st = state.lock().unwrap();
            let positions = python_worker::clean_3d_via_worker(st.python_exe.as_deref(), &st.bus.mol);
            if !positions.is_empty() {
                let _ = st.bus.execute(EditCommand::ApplyGeometry { positions });
            }
            json_response(200, &json!({
                "ok": true,
                "message": "3D 几何优化完成",
                "document": st.doc_summary()
            }))
        }
        (Method::Post, "/api/edit/undo") => {
            let mut st = state.lock().unwrap();
            st.bus.undo();
            json_response(200, &json!({ "ok": true, "document": st.doc_summary() }))
        }
        (Method::Post, "/api/edit/redo") => {
            let mut st = state.lock().unwrap();
            st.bus.redo();
            json_response(200, &json!({ "ok": true, "document": st.doc_summary() }))
        }
        (Method::Post, "/api/edit/add_atom") => {
            let body = read_json(req);
            let z = body["atomic_num"]
                .as_u64()
                .or_else(|| body["z"].as_u64())
                .map(|v| v as u8)
                .or_else(|| {
                    body["symbol"]
                        .as_str()
                        .and_then(elements::by_symbol)
                        .map(|e| e.z)
                })
                .unwrap_or(6);
            let pos = parse_vec3(&body["pos"])
                .or_else(|| {
                    let arr = body["pos_2d"].as_array()?;
                    Some([arr.first()?.as_f64()?, arr.get(1)?.as_f64()?, 0.0])
                })
                .unwrap_or([0.0, 0.0, 0.0]);
            let bond_to = body["bond_to"].as_u64().map(|v| v as u32);
            let bond_order = body["bond_order"].as_u64().unwrap_or(1) as u8;
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::AddAtom {
                z,
                pos,
                pos2: [pos[0], pos[1]],
                bond_to,
                bond_order,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/add_bond") => {
            let body = read_json(req);
            let a = body["atom_a"].as_u64().or_else(|| body["a"].as_u64());
            let b = body["atom_b"].as_u64().or_else(|| body["b"].as_u64());
            let (Some(a), Some(b)) = (a, b) else {
                return err_response(400, "atom_a and atom_b required");
            };
            let order = body["order"].as_u64().unwrap_or(1) as u8;
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::AddBond {
                a: a as u32,
                b: b as u32,
                order,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/delete_bond") => {
            let body = read_json(req);
            let mut st = state.lock().unwrap();
            let pair = if let Some(bid) = body["bond_id"].as_u64() {
                st.bus.mol.bond(bid as u32).map(|b| (b.a, b.b))
            } else {
                body["a"].as_u64().zip(body["b"].as_u64()).map(|(a, b)| (a as u32, b as u32))
            };
            let Some((a, b)) = pair else {
                return err_response(400, "bond_id or (a, b) required");
            };
            match st.bus.execute(EditCommand::DeleteBond { a, b }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/cycle_bond_order") => {
            let body = read_json(req);
            let mut st = state.lock().unwrap();
            let pair = if let Some(bid) = body["bond_id"].as_u64() {
                st.bus.mol.bond(bid as u32).map(|b| (b.a, b.b))
            } else {
                body["a"].as_u64().zip(body["b"].as_u64()).map(|(a, b)| (a as u32, b as u32))
            };
            let Some((a, b)) = pair else {
                return err_response(400, "bond_id or (a, b) required");
            };
            match st.bus.execute(EditCommand::CycleBondOrder { a, b }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/change_element") => {
            let body = read_json(req);
            let Some(id) = body["atom_id"].as_u64().or_else(|| body["id"].as_u64()) else {
                return err_response(400, "atom_id required");
            };
            let new_z = body["atomic_num"]
                .as_u64()
                .or_else(|| body["z"].as_u64())
                .map(|v| v as u8)
                .or_else(|| body["symbol"].as_str().and_then(elements::by_symbol).map(|e| e.z))
                .unwrap_or(6);
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::ChangeElement {
                id: id as u32,
                new_z,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/move_atom") => {
            let body = read_json(req);
            let Some(id) = body["atom_id"].as_u64().or_else(|| body["id"].as_u64()) else {
                return err_response(400, "atom_id required");
            };
            // 2D 画布拖拽载荷 {pos_2d:{x,y}} / {pos2:[x,y]}：只改布局，不碰 3D
            let pos2 = body["pos_2d"]
                .as_object()
                .and_then(|o| {
                    Some([o.get("x")?.as_f64()?, o.get("y")?.as_f64()?])
                })
                .or_else(|| {
                    body["pos2"].as_array().and_then(|a| {
                        if a.len() >= 2 {
                            Some([a[0].as_f64()?, a[1].as_f64()?])
                        } else {
                            None
                        }
                    })
                });
            let mut st = state.lock().unwrap();
            if let Some(p2) = pos2 {
                return match st.bus.execute(EditCommand::MoveAtom2D {
                    id: id as u32,
                    new_pos2: p2,
                }) {
                    Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                    Err(e) => err_response(400, e.to_string()),
                };
            }
            let Some(pos) = parse_vec3(&body["pos"]) else {
                return err_response(400, "pos [x,y,z] or pos_2d {x,y} required");
            };
            match st.bus.execute(EditCommand::MoveAtom {
                id: id as u32,
                new_pos: pos,
                new_pos2: None,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/add_ring") => {
            let body = read_json(req);
            let size = body["size"].as_u64().unwrap_or(6) as u8;
            let aromatic = body["aromatic"].as_bool().unwrap_or(true);
            let attach_to = body["attach_to"].as_u64().map(|v| v as u32);
            // center 兼容 3D [x,y,z] 与前端 2D 载荷 center_2d {x,y}/[x,y]
            let center = parse_vec3(&body["center"])
                .or_else(|| {
                    body["center_2d"].as_object().and_then(|o| {
                        Some([o.get("x")?.as_f64()?, o.get("y")?.as_f64()?, 0.0])
                    })
                })
                .or_else(|| {
                    body["center_2d"].as_array().and_then(|a| {
                        if a.len() >= 2 {
                            Some([a[0].as_f64()?, a[1].as_f64()?, 0.0])
                        } else {
                            None
                        }
                    })
                })
                .unwrap_or([0.0, 0.0, 0.0]);
            // hetero: {"0": 16, ...} 环内序号 -> 原子序数（噻吩/吡咯/呋喃等）
            let hetero: Vec<(usize, u8)> = body["hetero"]
                .as_object()
                .map(|o| {
                    o.iter()
                        .filter_map(|(k, v)| {
                            Some((k.parse::<usize>().ok()?, v.as_u64()? as u8))
                        })
                        .collect()
                })
                .unwrap_or_default();
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::AddRing {
                size,
                aromatic,
                attach_to,
                center,
                hetero,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/set_bond_order") => {
            let body = read_json(req);
            let order = body["order"].as_u64().unwrap_or(0) as u8;
            if !(1..=4).contains(&order) {
                return err_response(400, "order must be 1/2/3/4(aromatic)");
            }
            let pair = if let Some(bid) = body["bond_id"].as_u64() {
                let st = state.lock().unwrap();
                st.bus.mol.bonds.iter().find(|b| b.id == bid as u32).map(|b| (b.a, b.b))
            } else {
                let a = body["a"].as_u64().or_else(|| body["atom_a"].as_u64());
                let b = body["b"].as_u64().or_else(|| body["atom_b"].as_u64());
                match (a, b) {
                    (Some(a), Some(b)) => Some((a as u32, b as u32)),
                    _ => None,
                }
            };
            let Some((a, b)) = pair else {
                return err_response(400, "bond_id or (a, b) required");
            };
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::SetBondOrder { a, b, order }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/insert_fragment") => {
            let body = read_json(req);
            let frag_id = body["fragment_id"].as_str().unwrap_or("").trim().to_ascii_lowercase();
            let anchor_atom_id = body["anchor_atom_id"].as_u64().map(|v| v as u32);
            let attach = body["attach_to_existing"].as_bool().unwrap_or(true);

            let catalog = presets::fragment_catalog();
            let spec = catalog.iter().find(|f| f.id.to_ascii_lowercase() == frag_id);

            let Some(spec) = spec else {
                return err_response(404, format!("未找到基团/片段: {frag_id}"));
            };

            let mut st = state.lock().unwrap();
            let mut offset = [0.0, 0.0, 0.0];
            let mut attach_target = None;

            if let Some(anchor_id) = anchor_atom_id {
                if let Some(target) = st.bus.mol.atom(anchor_id) {
                    attach_target = Some(anchor_id);
                    let mut dir = [1.45, 0.0, 0.0];
                    let neighbors: Vec<[f64; 3]> = st.bus.mol.bonds.iter()
                        .filter_map(|b| {
                            if b.a == anchor_id { st.bus.mol.atom(b.b).map(|a| a.pos) }
                            else if b.b == anchor_id { st.bus.mol.atom(b.a).map(|a| a.pos) }
                            else { None }
                        })
                        .collect();
                    if !neighbors.is_empty() {
                        let mut sum_v = [0.0, 0.0, 0.0];
                        for nb in &neighbors {
                            sum_v[0] += target.pos[0] - nb[0];
                            sum_v[1] += target.pos[1] - nb[1];
                            sum_v[2] += target.pos[2] - nb[2];
                        }
                        let len = (sum_v[0]*sum_v[0] + sum_v[1]*sum_v[1] + sum_v[2]*sum_v[2]).sqrt();
                        if len > 0.01 {
                            dir = [sum_v[0] / len * 1.48, sum_v[1] / len * 1.48, sum_v[2] / len * 1.48];
                        }
                    }
                    offset = [target.pos[0] + dir[0], target.pos[1] + dir[1], target.pos[2] + dir[2]];
                }
            } else if !st.bus.mol.atoms.is_empty() {
                let max_x = st.bus.mol.atoms.iter().map(|a| a.pos[0]).fold(f64::NEG_INFINITY, f64::max);
                offset = [max_x + 3.0, 0.0, 0.0];
            }

            let atoms: Vec<(u8, [f64; 3], [f64; 2])> = spec.atoms.iter().map(|&(z, p)| {
                let shifted = [p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]];
                (z, shifted, [shifted[0], shifted[1]])
            }).collect();

            let prev_atoms_count = st.bus.mol.atoms.len();
            match st.bus.execute(EditCommand::InsertFragment {
                atoms,
                bonds: spec.bonds.clone(),
            }) {
                Ok(_) => {
                    if attach && attach_target.is_some() && st.bus.mol.atoms.len() > prev_atoms_count {
                        let new_anchor = st.bus.mol.atoms[prev_atoms_count].id;
                        let _ = st.bus.execute(EditCommand::AddBond {
                            a: attach_target.unwrap(),
                            b: new_anchor,
                            order: 1,
                        });
                    }
                    json_response(200, &json!({
                        "ok": true,
                        "message": format!("已成功插入基团: {}", spec.label),
                        "document": st.doc_summary()
                    }))
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/delete_atoms") => {
            let body = read_json(req);
            // 兼容前端 {atom_ids:[…]} 与历史 {ids:[…]} 两种载荷
            let ids: Vec<u32> = body["ids"]
                .as_array()
                .or_else(|| body["atom_ids"].as_array())
                .map(|arr| arr.iter().filter_map(|v| v.as_u64().map(|x| x as u32)).collect())
                .unwrap_or_default();
            if ids.is_empty() {
                return err_response(400, "ids / atom_ids 不能为空（拒绝静默无操作）");
            }
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::DeleteAtoms { ids }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/delete_indices") => {
            let body = read_json(req);
            let indices: Vec<usize> = body["indices"]
                .as_array()
                .map(|arr| arr.iter().filter_map(|v| v.as_u64().map(|x| x as usize)).collect())
                .unwrap_or_default();
            let mut st = state.lock().unwrap();
            let ids: Vec<u32> = indices
                .iter()
                .filter_map(|&idx| st.bus.mol.atoms.get(idx).map(|a| a.id))
                .collect();
            match st.bus.execute(EditCommand::DeleteAtoms { ids }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/set_charge_spin") => {
            let body = read_json(req);
            let charge = body["charge"].as_i64().map(|v| v as i32);
            let multiplicity = body["multiplicity"].as_u64().map(|v| v as u32);
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::SetChargeSpin {
                charge,
                multiplicity,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/edit/set_atom_charge") => {
            let body = read_json(req);
            let Some(id) = body["atom_id"].as_u64().or_else(|| body["id"].as_u64()) else {
                return err_response(400, "atom_id required");
            };
            let Some(charge) = body["charge"].as_i64().map(|v| v as i32) else {
                return err_response(400, "charge (integer) required");
            };
            if !(-4..=4).contains(&charge) {
                return err_response(400, "charge out of range [-4, 4]");
            }
            let mut st = state.lock().unwrap();
            match st.bus.execute(EditCommand::SetAtomCharge {
                id: id as u32,
                charge,
            }) {
                Ok(_) => json_response(200, &json!({ "ok": true, "document": st.doc_summary() })),
                Err(e) => err_response(400, e.to_string()),
            }
        }

        (Method::Post, "/api/qc/tight_binding") => {
            let mol = {
                let st = state.lock().unwrap();
                st.bus.mol.clone()
            };
            match qc::run_tight_binding(&mol) {
                Ok(res) => json_response(200, &json!(res)),
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/qc/parse_log") => {
            let body = read_json(req);
            let text = if let Some(t) = body["text"].as_str() {
                t.to_string()
            } else if let Some(p) = body["path"].as_str() {
                match std::fs::read_to_string(p) {
                    Ok(s) => s,
                    Err(e) => return err_response(400, e.to_string()),
                }
            } else {
                return err_response(400, "text or path required");
            };
            match qc::parse_qc_log(&text) {
                Ok(res) => json_response(200, &json!(res)),
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/qc/export_input") => {
            let body = read_json(req);
            // 兼容前端 {kind} 与历史 {engine}
            let engine = body["engine"]
                .as_str()
                .or_else(|| body["kind"].as_str())
                .unwrap_or("gaussian");
            let method = body["method"].as_str().unwrap_or("B3LYP");
            let basis = body["basis"].as_str().unwrap_or("6-31G(d)");
            let st = state.lock().unwrap();
            let (charge, mult, _) = summary::resolve_spin_state(&st.bus.mol);
            let content = match engine.to_ascii_lowercase().as_str() {
                "orca" => io::write_orca_inp(&st.bus.mol, method, basis, charge, mult, true),
                "rest" => io::write_rest_ctrl(&st.bus.mol, method, basis, charge, mult),
                "xtb" => io::write_xtb_input(&st.bus.mol, method, charge, mult),
                _ => io::write_gjf(&st.bus.mol, method, basis, charge, mult, true),
            };
            json_response(200, &json!({ "ok": true, "engine": engine, "content": content }))
        }
        (Method::Post, "/api/qc/run_calchem") => {
            let body = read_json(req);
            let method = body["method"].as_str().unwrap_or("HF").to_string();
            let basis = body["basis"].as_str().unwrap_or("STO-3G").to_string();
            // 兼容前端 {mode:"opt"|"sp"} 与历史 {optimize:bool}
            let optimize = body["optimize"]
                .as_bool()
                .unwrap_or_else(|| body["mode"].as_str() == Some("opt"));
            let (mol, charge, mult) = {
                let st = state.lock().unwrap();
                let (c, m, _) = summary::resolve_spin_state(&st.bus.mol);
                (st.bus.mol.clone(), c, m as usize)
            };
            match qc::run_calchem(&mol, &method, &basis, charge, mult, optimize) {
                Ok(res) => {
                    if let Some(new_pos) = &res.optimized_positions {
                        let mut st = state.lock().unwrap();
                        let _ = st.bus.execute(EditCommand::ApplyGeometry {
                            positions: new_pos.clone(),
                        });
                    }
                    json_response(200, &format_calchem_json(&res, optimize))
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/qc/reorganization_energy") => {
            let body = read_json(req);
            let resolve_e = |val_key: &str, path_key: &str| -> std::result::Result<f64, String> {
                if let Some(v) = body[val_key].as_f64() {
                    return Ok(v);
                }
                if let Some(p) = body[path_key].as_str().filter(|s| !s.trim().is_empty()) {
                    return read_energy_from_qc_file(p.trim());
                }
                Err(format!("缺少 {val_key}（Hartree 数值）或 {path_key}（.log 文件路径）"))
            };
            let (e_nn, e_ni, e_ii, e_in) = match (
                resolve_e("e_n_n", "path_n_n"),
                resolve_e("e_n_i", "path_n_i"),
                resolve_e("e_i_i", "path_i_i"),
                resolve_e("e_i_n", "path_i_n"),
            ) {
                (Ok(a), Ok(b), Ok(c), Ok(d)) => (a, b, c, d),
                (Err(e), _, _, _) | (_, Err(e), _, _) | (_, _, Err(e), _) | (_, _, _, Err(e)) => {
                    return err_response(400, e);
                }
            };
            const HARTREE_TO_EV: f64 = 27.211386245988;
            const HARTREE_TO_KCAL: f64 = 627.5094740631;
            let l1_ha = e_ni - e_nn;
            let l2_ha = e_in - e_ii;
            let ltot_ha = l1_ha + l2_ha;
            json_response(
                200,
                &json!({
                    "ok": true,
                    "carrier": body["carrier"].as_str().unwrap_or("hole"),
                    "e_n_n": e_nn,
                    "e_n_i": e_ni,
                    "e_i_i": e_ii,
                    "e_i_n": e_in,
                    "lambda1_hartree": l1_ha,
                    "lambda2_hartree": l2_ha,
                    "lambda_total_hartree": ltot_ha,
                    "lambda1_ev": l1_ha * HARTREE_TO_EV,
                    "lambda2_ev": l2_ha * HARTREE_TO_EV,
                    "lambda_total_ev": ltot_ha * HARTREE_TO_EV,
                    "lambda_total_mev": ltot_ha * HARTREE_TO_EV * 1000.0,
                    "lambda_total_kcal": ltot_ha * HARTREE_TO_KCAL,
                }),
            )
        }
        (Method::Post, "/api/qc/run_xtb") => {
            let body = read_json(req);
            // 兼容前端 {gfn_level, apply_geometry} 与历史 {method, optimize}
            let method = body["method"]
                .as_str()
                .map(|s| s.to_string())
                .unwrap_or_else(|| format!("gfn{}", body["gfn_level"].as_i64().unwrap_or(2)));
            let optimize = body["optimize"]
                .as_bool()
                .or_else(|| body["apply_geometry"].as_bool())
                .unwrap_or(true);
            let (mol, charge, mult, paths) = {
                let st = state.lock().unwrap();
                let (c, m, _) = summary::resolve_spin_state(&st.bus.mol);
                (st.bus.mol.clone(), c, m, st.engine_paths.clone())
            };
            let uhf = mult.saturating_sub(1);
            match engines::run_xtb_native(&mol, &method, optimize, charge, uhf, &paths) {
                Ok(out) => {
                    if let Some(opt_xyz) = &out.optimized_xyz {
                        if let Ok(opt_mol) = io::parse_xyz(opt_xyz, &mol.name) {
                            let pairs: Vec<(u32, [f64; 3])> = mol
                                .atoms
                                .iter()
                                .zip(opt_mol.atoms.iter())
                                .map(|(orig, opt_a)| (orig.id, opt_a.pos))
                                .collect();
                            let mut st = state.lock().unwrap();
                            let _ = st.bus.execute(EditCommand::ApplyGeometry { positions: pairs });
                        }
                    }
                    // 与前端契约对齐：ok 由真实退出码+能量解析决定，失败诚实 error
                    let ok = out.exit_code == 0 && !out.timed_out && out.energy_hartree.is_some();
                    let tail: String = out
                        .stdout
                        .lines()
                        .rev()
                        .take(20)
                        .collect::<Vec<_>>()
                        .into_iter()
                        .rev()
                        .collect::<Vec<_>>()
                        .join("\n");
                    let message = if ok {
                        format!(
                            "GFN-xTB 实算完成：E = {:.6} Hartree{}",
                            out.energy_hartree.unwrap_or(0.0),
                            match out.converged {
                                Some(true) => "，几何已收敛",
                                Some(false) => "，几何未完全收敛",
                                None => "",
                            }
                        )
                    } else if out.timed_out {
                        "xtb 超时被护栏终止，未产出能量".to_string()
                    } else {
                        format!("xtb 退出码 {}，未解析到总能量", out.exit_code)
                    };
                    json_response(
                        200,
                        &json!({
                            "ok": ok,
                            "engine": out.engine,
                            "energy_hartree": out.energy_hartree,
                            "converged": out.converged,
                            "timed_out": out.timed_out,
                            "exit_code": out.exit_code,
                            "workdir": out.workdir,
                            "message": message,
                            "error": if ok { serde_json::Value::Null } else { json!(message) },
                            "stdout_tail": tail,
                        }),
                    )
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/qc/run_external") => {
            let body = read_json(req);
            let engine = body["engine"].as_str().unwrap_or("orca").to_ascii_lowercase();
            let keywords = body["keywords"].as_str().unwrap_or("");
            let method = body["method"].as_str().unwrap_or("B3LYP");
            let basis = body["basis"].as_str().unwrap_or("def2-SVP");
            let optimize = body["optimize"].as_bool().unwrap_or(false);
            let workdir = body["workdir"].as_str().map(|s| s.to_string());
            let (mol, paths) = {
                let st = state.lock().unwrap();
                (st.bus.mol.clone(), st.engine_paths.clone())
            };
            // 真实 spawn 外部引擎（带 600s 超时护栏），绝不返回假 completed
            match engines::run_external_native(
                &mol,
                &engine,
                keywords,
                method,
                basis,
                optimize,
                workdir.as_deref(),
                &paths,
            ) {
                Ok(out) => {
                    let status = if out.timed_out {
                        "timeout"
                    } else if out.exit_code == 0 {
                        "completed"
                    } else {
                        "failed"
                    };
                    let tail: String = out
                        .stdout
                        .lines()
                        .rev()
                        .take(20)
                        .collect::<Vec<_>>()
                        .into_iter()
                        .rev()
                        .collect::<Vec<_>>()
                        .join("\n");
                    json_response(200, &json!({
                        "ok": out.exit_code == 0 && !out.timed_out,
                        "status": status,
                        "engine": out.engine,
                        "command": format!("{} {}", engine, keywords),
                        "workdir": out.workdir,
                        "exit_code": out.exit_code,
                        "energy_hartree": out.energy_hartree,
                        "timed_out": out.timed_out,
                        "stdout_tail": tail,
                    }))
                }
                Err(e) => json_response(200, &json!({
                    "ok": false,
                    "status": "engine_not_found",
                    "engine": engine,
                    "command": "",
                    "workdir": workdir.unwrap_or_default(),
                    "stdout_tail": e.to_string(),
                })),
            }
        }
        (Method::Post, "/api/md/generate_gromacs") => {
            let body = read_json(req);
            let nsteps = body["nsteps_md"]
                .as_u64()
                .or_else(|| body["nsteps"].as_u64())
                .unwrap_or(50000);
            let dt = body["dt_ps"]
                .as_f64()
                .or_else(|| body["dt"].as_f64())
                .unwrap_or(0.002);
            let temp_k = body["temp_k"].as_f64().unwrap_or(300.0);
            let minim_mdp = format!(
                "; MolForge Studio Energy Minimization\nintegrator  = steep\nemtol       = 1000.0\nemstep      = 0.01\nnsteps      = 50000\n"
            );
            let nvt_mdp = engines::generate_gromacs_mdp("nvt", 50000, dt, temp_k);
            let npt_mdp = engines::generate_gromacs_mdp("npt", 50000, dt, temp_k);
            let md_mdp = engines::generate_gromacs_mdp("npt", nsteps, dt, temp_k);
            let gmx_path = {
                let st = state.lock().unwrap();
                engines::find_engine_path("gromacs", &st.engine_paths)
                    .map(|p| p.display().to_string())
            };
            let gmx_bin = gmx_path.as_deref().unwrap_or("gmx");
            let run_sh = format!(
                "#!/bin/bash\nset -e\nGMX=\"{gmx_bin}\"\n$GMX grompp -f minim.mdp -c system.gro -p topol.top -o em.tpr\n$GMX mdrun -v -deffnm em\n$GMX grompp -f nvt.mdp -c em.gro -p topol.top -o nvt.tpr\n$GMX mdrun -v -deffnm nvt\n$GMX grompp -f npt.mdp -c nvt.gro -p topol.top -o npt.tpr\n$GMX mdrun -v -deffnm npt\n$GMX grompp -f md.mdp -c npt.gro -p topol.top -o md.tpr\n$GMX mdrun -v -deffnm md\n"
            );
            json_response(
                200,
                &json!({
                    "ok": true,
                    "mdp": md_mdp,
                    "gmx_available": gmx_path.is_some(),
                    "gmx_path": gmx_path,
                    "files": {
                        "minim.mdp": minim_mdp,
                        "nvt.mdp": nvt_mdp,
                        "npt.mdp": npt_mdp,
                        "md.mdp": md_mdp,
                        "run_gmx.sh": run_sh,
                    }
                }),
            )
        }
        (Method::Post, "/api/analysis/run") => {
            let body = read_json(req);
            let analysis_id = body["analysis_id"].as_str().unwrap_or("CORE-01");
            let input_file = body["input_file"].as_str();
            let (mol, paths) = {
                let st = state.lock().unwrap();
                (st.bus.mol.clone(), st.engine_paths.clone())
            };
            match dispatch_analysis(&mol, analysis_id, input_file, &paths) {
                Ok((_, payload)) => json_response(200, &payload),
                Err(e) => err_response(400, e),
            }
        }
        (Method::Post, "/api/analysis/run_multiwfn") => {
            let body = read_json(req);
            let analysis_id = body["analysis_id"].as_str().unwrap_or("WFN-01");
            let input_file = body["input_file"].as_str();
            let (mol, paths) = {
                let st = state.lock().unwrap();
                (st.bus.mol.clone(), st.engine_paths.clone())
            };
            match engines::run_multiwfn_native(&mol, analysis_id, input_file, &paths) {
                Ok(res) => json_response(200, &json!(res)),
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/jobs/submit") => {
            let body = read_json(req);
            let kind = body["kind"].as_str().unwrap_or("tight_binding").to_string();
            let label = body["label"].as_str().unwrap_or("Background Job").to_string();
            let params = body["params"].clone();
            let (mol, jobs, doc_name, rev, paths, py_exe) = {
                let st = state.lock().unwrap();
                (
                    st.bus.mol.clone(),
                    st.jobs.clone(),
                    st.bus.mol.name.clone(),
                    st.bus.mol.revision,
                    st.engine_paths.clone(),
                    st.python_exe.clone(),
                )
            };
            let kind_bg = kind.clone();
            // 真实分派：每种后台任务都跑真引擎；缺失/失败诚实报错，绝不假完成。
            let job = jobs.submit(kind, label, doc_name, rev, params.clone(), move |_cancel| {
                let method = params["method"].as_str().unwrap_or("B3LYP");
                let basis = params["basis"].as_str().unwrap_or("def2-SVP");
                let optimize = params["optimize"].as_bool().unwrap_or(false);
                match kind_bg.as_str() {
                    "tight_binding" | "analysis_tb" => {
                        let res = qc::run_tight_binding(&mol).map_err(|e| e.to_string())?;
                        Ok(json!(res))
                    }
                    "analysis" => {
                        let aid = params["analysis_id"].as_str().unwrap_or("CORE-01");
                        let inp = params["input_file"].as_str();
                        let (ok, payload) = dispatch_analysis(&mol, aid, inp, &paths)?;
                        if !ok {
                            let summary = payload["result"]["summary"]
                                .as_str()
                                .or_else(|| payload["result"]["message"].as_str())
                                .unwrap_or("分析未产生可用结果")
                                .to_string();
                            return Err(summary);
                        }
                        Ok(payload["result"].clone())
                    }
                    "clean_3d" => {
                        let positions = python_worker::clean_3d_via_worker(py_exe.as_deref(), &mol);
                        if positions.is_empty() {
                            return Err("当前分子为空，无法执行 3D 构象弛豫".into());
                        }
                        Ok(json!({
                            "ok": true,
                            "relaxed_atoms": positions.len(),
                            "positions": positions,
                        }))
                    }
                    "xtb_opt" | "xtb_sp" | "xtb" => {
                        let (chg, mult, _) = summary::resolve_spin_state(&mol);
                        let res = engines::run_xtb_native(
                            &mol,
                            "gfn2",
                            kind_bg != "xtb_sp",
                            chg,
                            mult.saturating_sub(1),
                            &paths,
                        )
                        .map_err(|e| e.to_string())?;
                        if res.exit_code != 0 {
                            return Err(format!("xtb 退出码 {}", res.exit_code));
                        }
                        Ok(json!(res))
                    }
                    "orca_sp" | "orca_opt" | "gaussian_sp" | "gaussian_opt" => {
                        let engine = if kind_bg.starts_with("orca") { "orca" } else { "gaussian" };
                        let keywords = params["keywords"].as_str().unwrap_or("");
                        let res = engines::run_external_native(
                            &mol,
                            engine,
                            keywords,
                            method,
                            basis,
                            optimize || kind_bg.ends_with("_opt"),
                            None,
                            &paths,
                        )
                        .map_err(|e| e.to_string())?;
                        if res.timed_out {
                            return Err("外部引擎超时（600s 护栏）".into());
                        }
                        if res.exit_code != 0 {
                            let tail: String = res
                                .stdout
                                .lines()
                                .rev()
                                .take(8)
                                .collect::<Vec<_>>()
                                .into_iter()
                                .rev()
                                .collect::<Vec<_>>()
                                .join(" | ");
                            return Err(format!(
                                "{engine} 退出码 {}（workdir: {}）{}",
                                res.exit_code,
                                res.workdir,
                                if tail.is_empty() { String::new() } else { format!(" stdout尾: {tail}") }
                            ));
                        }
                        Ok(json!(res))
                    }
                    "calchem_sp" | "calchem_opt" => {
                        let (chg, mult, _) = summary::resolve_spin_state(&mol);
                        let cc_method = params["method"].as_str().unwrap_or("HF");
                        let cc_basis = params["basis"].as_str().unwrap_or("STO-3G");
                        let is_opt = optimize || kind_bg == "calchem_opt";
                        let res = qc::run_calchem(
                            &mol,
                            cc_method,
                            cc_basis,
                            chg,
                            mult as usize,
                            is_opt,
                        )
                        .map_err(|e| e.to_string())?;
                        if !res.available {
                            return Err(res.message);
                        }
                        Ok(format_calchem_json(&res, is_opt))
                    }
                    "md_rdf" | "trajectory_rdf" => {
                        let r_max = params["r_max"].as_f64().unwrap_or(12.0);
                        let n_bins = params["n_bins"].as_u64().unwrap_or(80) as usize;
                        let res = engines::compute_pairwise_rdf(&mol, r_max, n_bins)
                            .map_err(|e| e.to_string())?;
                        Ok(json!({
                            "ok": true,
                            "rdf": res,
                        }))
                    }
                    other => Err(format!("未知后台任务类型 '{other}'，拒绝假完成")),
                }
            });
            json_response(200, &json!({ "ok": true, "job": job }))
        }
        (Method::Post, "/api/engines/configure") => {
            let body = read_json(req);
            let Some(engine) = body["tool_id"].as_str().or_else(|| body["engine"].as_str()) else {
                return err_response(400, "tool_id is required");
            };
            let path = body["executable_path"]
                .as_str()
                .or_else(|| body["path"].as_str())
                .unwrap_or("")
                .trim();
            let mut st = state.lock().unwrap();
            if path.is_empty() {
                st.engine_paths.overrides.remove(engine);
            } else {
                st.engine_paths
                    .overrides
                    .insert(engine.to_string(), path.to_string());
            }
            let list = engines::probe_all(&st.engine_paths, st.python_exe.as_deref());
            json_response(
                200,
                &json!({
                    "ok": true,
                    "engines": list,
                    "calchem_basis_sets": ["STO-3G", "3-21G", "6-31G", "6-31G*", "cc-pVDZ", "def2-SVP", "def2-TZVP"],
                }),
            )
        }
        (Method::Post, "/api/jobs/cancel") => {
            let body = read_json(req);
            let id = body["job_id"]
                .as_str()
                .or_else(|| body["id"].as_str())
                .unwrap_or("");
            let jobs = {
                let st = state.lock().unwrap();
                st.jobs.clone()
            };
            match jobs.cancel(id) {
                Some(job) => json_response(200, &json!({ "ok": true, "job": job })),
                None => err_response(404, format!("job '{id}' not found")),
            }
        }
        (Method::Get, "/api/hub/resources") => {
            let query_str = req.url().split('?').nth(1).unwrap_or("");
            let mut q: Option<String> = None;
            let mut kind: Option<String> = None;
            for pair in query_str.split('&') {
                if let Some((k, v)) = pair.split_once('=') {
                    let decoded = v.replace('+', " ");
                    match k {
                        "query" | "q" => q = Some(decoded),
                        "kind" => kind = Some(decoded),
                        _ => {}
                    }
                }
            }
            let st = state.lock().unwrap();
            let items = st.hub.list_resources(
                &st.engine_paths,
                st.python_exe.as_deref(),
                q.as_deref(),
                kind.as_deref(),
            );
            json_response(200, &json!({ "ok": true, "items": items }))
        }
        (Method::Get, "/api/hub/capabilities") => {
            let st = state.lock().unwrap();
            let eng = engines::probe_all(&st.engine_paths, st.python_exe.as_deref());
            let caps = st.hub.capabilities(&eng);
            json_response(200, &json!({ "ok": true, "capabilities": caps }))
        }
        (Method::Post, "/api/hub/favorite") => {
            let body = read_json(req);
            let Some(id) = body["id"].as_str() else {
                return err_response(400, "id is required");
            };
            let mut st = state.lock().unwrap();
            let favorite = st.hub.toggle_favorite(id);
            json_response(200, &json!({ "ok": true, "id": id, "favorite": favorite }))
        }
        (Method::Post, "/api/hub/pin") => {
            let body = read_json(req);
            let Some(id) = body["id"].as_str() else {
                return err_response(400, "id is required");
            };
            let mut st = state.lock().unwrap();
            let pinned = st.hub.toggle_pin(id);
            json_response(200, &json!({ "ok": true, "id": id, "pinned": pinned }))
        }
        (Method::Post, "/api/hub/install") => {
            let body = read_json(req);
            let Some(id) = body["id"].as_str() else {
                return err_response(400, "id is required");
            };
            let mut st = state.lock().unwrap();
            let ok = st.hub.install_resource(id);
            json_response(200, &json!({ "ok": ok, "id": id }))
        }
        (Method::Post, "/api/hub/uninstall_impact") => {
            let body = read_json(req);
            let Some(id) = body["id"].as_str() else {
                return err_response(400, "id is required");
            };
            let st = state.lock().unwrap();
            let impact = st
                .hub
                .uninstall_impact(id, &st.engine_paths, st.python_exe.as_deref());
            json_response(200, &json!({ "ok": true, "impact": impact }))
        }
        (Method::Post, "/api/skills/import") => {
            let body = read_json(req);
            let markdown = body["markdown"].as_str().unwrap_or("");
            let source = body["source"].as_str().unwrap_or("local://imported-skill");
            let caps: Vec<String> = body["capabilities"]
                .as_array()
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                        .collect()
                })
                .unwrap_or_default();
            match skills::parse_skill_md(markdown, source, caps, false) {
                Ok(pkg) => {
                    let mut st = state.lock().unwrap();
                    st.hub.skills.retain(|s| s.id != pkg.id);
                    st.hub.skills.push(pkg.clone());
                    json_response(200, &json!({ "ok": true, "skill": pkg }))
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Get, "/api/workflows/catalog") => {
            json_response(200, &json!({ "ok": true, "workflows": workflow::builtin_workflows() }))
        }
        (Method::Get, "/api/workflows/runs") => {
            let st = state.lock().unwrap();
            json_response(200, &json!({ "ok": true, "runs": st.workflow_runs }))
        }
        (Method::Post, "/api/workflows/run") => {
            let body = read_json(req);
            let wf_id = body["workflow_id"].as_str().unwrap_or("");
            let approved = body["approved"].as_bool().unwrap_or(false);
            let param_overrides = body.get("params").cloned();
            let Some(spec) = workflow::builtin_workflows()
                .into_iter()
                .find(|w| w.id == wf_id)
            else {
                return err_response(404, format!("unknown workflow '{wf_id}'"));
            };
            let run = {
                let st = state.lock().unwrap();
                workflow::execute_workflow(
                    &spec,
                    &st.bus.mol,
                    &st.hub,
                    &st.engine_paths,
                    st.python_exe.as_deref(),
                    approved,
                    param_overrides.as_ref(),
                )
            };
            match run {
                Ok(r) => {
                    let mut st = state.lock().unwrap();
                    st.workflow_runs.insert(0, r.clone());
                    if st.workflow_runs.len() > 50 {
                        st.workflow_runs.truncate(50);
                    }
                    json_response(200, &json!({ "ok": true, "run": r }))
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/ai/chat") => {
            let body = read_json(req);
            let prompt = body["prompt"].as_str().unwrap_or("").trim().to_string();
            if prompt.is_empty() {
                return err_response(400, "提问内容不能为空");
            }

            let (doc_summary, prefs, mol_clone) = {
                let st = state.lock().unwrap();
                (st.doc_summary(), st.preferences.clone(), st.bus.mol.clone())
            };

            let mut reply_parts = Vec::new();
            let mut blocks = Vec::new();

            blocks.push(json!({
                "type": "metrics_card",
                "title": format!("{} · 结构化学态", doc_summary.name),
                "items": [
                    { "label": "化学式", "value": doc_summary.formula },
                    { "label": "原子 / 键数", "value": format!("{} / {}", doc_summary.num_atoms, doc_summary.num_bonds) },
                    { "label": "电荷 / 自旋态", "value": format!("{} / {}", doc_summary.charge, doc_summary.spin_label) },
                    { "label": "几何形态", "value": doc_summary.geometry_label }
                ]
            }));

            let tb_res = if mol_clone.atoms.len() >= 2 {
                qc::run_tight_binding(&mol_clone).ok()
            } else {
                None
            };

            if let Some(tb) = &tb_res {
                let h_val = tb.homo_ev.unwrap_or(0.0);
                let l_val = tb.lumo_ev.unwrap_or(0.0);
                let g_val = tb.gap_ev.unwrap_or((l_val - h_val).abs());
                let s1_str = if let Some(t) = tb.transitions.first() {
                    format!("{:.1} nm (f={:.3})", t.wavelength_nm, t.oscillator_f)
                } else {
                    "—".to_string()
                };

                blocks.push(json!({
                    "type": "orbital_card",
                    "title": format!("前线分子轨道 (紧束缚求解) · {}", doc_summary.name),
                    "homo_ev": (h_val * 1000.0).round() / 1000.0,
                    "lumo_ev": (l_val * 1000.0).round() / 1000.0,
                    "gap_ev": (g_val * 1000.0).round() / 1000.0,
                    "s1_text": s1_str,
                    "model_note": "杂原子紧束缚半经验模型（非 PM6 实算）"
                }));
            }

            blocks.push(json!({
                "type": "action_row",
                "title": "快捷科研操作建议",
                "actions": [
                    { "label": "3D 几何优化", "action": "clean_3d" },
                    { "label": "CalChem 密度泛函实算", "action": "run_calchem" },
                    { "label": "导出 Gaussian GJF 输入", "action": "export_gjf" }
                ]
            }));

            let lower = prompt.to_ascii_lowercase();
            // 仅显式"生成/构建/加载 + 预设名"才替换文档；"画/分析/轨道"等咨询绝不触碰文档
            let explicit_build = (lower.contains("生成") || lower.contains("构建") || lower.contains("加载") || lower.contains("build"))
                && !lower.contains("画") && !lower.contains("轨道") && !lower.contains("分析");
            let mut document_replaced = false;
            if explicit_build {
                let mut built_preset = None;
                if lower.contains("咖啡因") || lower.contains("caffeine") { built_preset = Some("caffeine"); }
                else if lower.contains("苯") || lower.contains("benzene") { built_preset = Some("benzene"); }
                else if lower.contains("阿司匹林") || lower.contains("aspirin") { built_preset = Some("aspirin"); }
                else if lower.contains("水") || lower.contains("water") { built_preset = Some("water"); }
                else if lower.contains("乙醇") || lower.contains("ethanol") { built_preset = Some("ethanol"); }

                if let Some(pname) = built_preset {
                    if let Some(new_mol) = presets::build_preset(pname) {
                        let mut st = state.lock().unwrap();
                        st.bus = CommandBus::new(new_mol);
                        document_replaced = true;
                        reply_parts.push(format!("已按您的显式指令加载并构建 **{pname}** 分子结构（文档已替换，可撤销历史已清空）。"));
                    }
                }
            }

            // 设置页字段(api_key/base_url/model)与历史字段(ai_*)双兼容；不再内置任何硬编码 Key
            let base_url = prefs["ai_base_url"]
                .as_str()
                .or_else(|| prefs["base_url"].as_str())
                .unwrap_or("https://api.deepseek.com/v1");
            let api_key = prefs["ai_api_key"]
                .as_str()
                .or_else(|| prefs["api_key"].as_str())
                .unwrap_or("");
            let model = prefs["ai_model"]
                .as_str()
                .or_else(|| prefs["model"].as_str())
                .unwrap_or("deepseek-chat");

            let sys_prompt = "你是 MolForge Studio 的 AI 科学计算副驾驶，专精于有机半导体、量子化学、分子动力学与材料设计。请以严谨简明的科研语言回答，对化学式与物理量使用 KaTeX/LaTeX 格式（如 $E_g$, $\\text{HOMO}$）。";
            let user_context = format!(
                "当前分子: {} (化学式: {}, {} 原子, {} 键, 电荷: {}, 自旋: {})。用户问题: {}",
                doc_summary.name, doc_summary.formula, doc_summary.num_atoms, doc_summary.num_bonds, doc_summary.charge, doc_summary.spin_label, prompt
            );

            let mut offline = false;
            let mut offline_reason = String::new();
            if api_key.trim().is_empty() {
                offline = true;
                offline_reason = "未配置 API Key（偏好设置 → AI 副驾驶）".into();
            } else {
                match python_worker::ai_chat_request(base_url, api_key, model, sys_prompt, &user_context) {
                    Ok(ai_reply) => {
                        reply_parts.push(ai_reply);
                    }
                    Err(e) => {
                        offline = true;
                        offline_reason = format!("DeepSeek 请求失败：{e}");
                    }
                }
            }
            if offline {
                // 诚实降级：明确标注离线模板，绝不冒充真实 AI 回答
                let local = if let Some(tb) = &tb_res {
                    let h_val = tb.homo_ev.unwrap_or(0.0);
                    let l_val = tb.lumo_ev.unwrap_or(0.0);
                    let g_val = tb.gap_ev.unwrap_or((l_val - h_val).abs());
                    format!(
                        "当前分子 **{}**（`{}`）经前线轨道紧束缚分析得到：$\\text{{HOMO}} = {:.3}\\text{{ eV}}$，$\\text{{LUMO}} = {:.3}\\text{{ eV}}$，基础能隙 $E_g = {:.3}\\text{{ eV}}$。建议检查分子共轭平面性以进一步提升吸收波长。",
                        doc_summary.name, doc_summary.formula, h_val, l_val, g_val
                    )
                } else {
                    format!(
                        "已分析当前分子 **{}**（`{}`）。当前包含 {} 个原子与 {} 条化学键。可执行“3D 几何优化”或“CalChem 量化计算”以获取精确基态物理参数。",
                        doc_summary.name, doc_summary.formula, doc_summary.num_atoms, doc_summary.num_bonds
                    )
                };
                reply_parts.push(format!("【离线降级·本地紧束缚模板，非 AI 生成】原因：{offline_reason}\n\n{local}"));
            }

            let latest_summary = {
                let st = state.lock().unwrap();
                st.doc_summary()
            };

            json_response(200, &json!({
                "ok": true,
                "reply": reply_parts.join("\n\n"),
                "a2ui_blocks": blocks,
                "offline": offline,
                "offline_reason": offline_reason,
                "document_replaced": document_replaced,
                "document": latest_summary
            }))
        }
        (Method::Post, "/api/geometry/orient") => {
            let body = read_json(req);
            let apply = body["apply"].as_bool().unwrap_or(false);
            let mol_snap = {
                let st = state.lock().unwrap();
                st.bus.mol.clone()
            };
            match topology::compute_core_first_orientation(&mol_snap) {
                Ok(ori) => {
                    let doc = if apply {
                        let positions: Vec<(u32, [f64; 3])> = mol_snap
                            .atoms
                            .iter()
                            .enumerate()
                            .filter_map(|(i, a)| ori.aligned_positions.get(i).map(|&p| (a.id, p)))
                            .collect();
                        let mut st = state.lock().unwrap();
                        let _ = st.bus.execute(EditCommand::ApplyGeometry { positions });
                        for (i, a) in st.bus.mol.atoms.iter_mut().enumerate() {
                            if let Some(&p) = ori.aligned_positions.get(i) {
                                a.pos2 = [p[0], p[1]];
                            }
                        }
                        Some(st.doc_summary())
                    } else {
                        None
                    };
                    json_response(
                        200,
                        &json!({
                            "ok": true,
                            "orientation": ori,
                            "document": doc,
                        }),
                    )
                }
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/geometry/align_batch") => {
            let body = read_json(req);
            let Some(ref_path) = body["reference_path"].as_str().map(|s| s.trim()).filter(|s| !s.is_empty()) else {
                return err_response(400, "reference_path is required");
            };
            let target_paths: Vec<String> = body["target_paths"]
                .as_array()
                .map(|a| a.iter().filter_map(|v| v.as_str().map(|s| s.trim().to_string())).collect())
                .unwrap_or_default();
            if target_paths.is_empty() {
                return err_response(400, "target_paths must be non-empty");
            }
            let allow_halogen_swap = body["allow_halogen_swap"].as_bool().unwrap_or(true);

            let ref_bytes = match std::fs::read(ref_path) {
                Ok(b) => b,
                Err(e) => return err_response(400, format!("failed to read reference '{ref_path}': {e}")),
            };
            let ref_mol = match io::open_by_extension(ref_path, &ref_bytes) {
                Ok(m) => m,
                Err(e) => return err_response(400, e.to_string()),
            };
            let ref_ori = match topology::compute_core_first_orientation(&ref_mol) {
                Ok(o) => o,
                Err(e) => return err_response(400, e.to_string()),
            };

            let mut results = Vec::with_capacity(target_paths.len());
            for tp in &target_paths {
                let bytes = match std::fs::read(tp) {
                    Ok(b) => b,
                    Err(e) => {
                        results.push(json!({ "path": tp, "ok": false, "error": e.to_string() }));
                        continue;
                    }
                };
                let mut mol = match io::open_by_extension(tp, &bytes) {
                    Ok(m) => m,
                    Err(e) => {
                        results.push(json!({ "path": tp, "ok": false, "error": e.to_string() }));
                        continue;
                    }
                };
                match topology::align_molecule_to_reference(&ref_mol, &mol, allow_halogen_swap) {
                    Ok(al) => {
                        for (idx, p) in al.aligned_positions.iter().enumerate() {
                            let s = [
                                p[0] - ref_ori.center_angstrom[0],
                                p[1] - ref_ori.center_angstrom[1],
                                p[2] - ref_ori.center_angstrom[2],
                            ];
                            let r = &ref_ori.rotation_3x3;
                            let rp = [
                                r[0][0] * s[0] + r[0][1] * s[1] + r[0][2] * s[2],
                                r[1][0] * s[0] + r[1][1] * s[1] + r[1][2] * s[2],
                                r[2][0] * s[0] + r[2][1] * s[1] + r[2][2] * s[2],
                            ];
                            mol.atoms[idx].pos = rp;
                            mol.atoms[idx].pos2 = [rp[0], rp[1]];
                        }
                        let planarity = summary::compute_planarity(&mol).ok();
                        let torsions = topology::compute_torsions(&mol).ok();
                        results.push(json!({
                            "path": tp,
                            "name": mol.name,
                            "ok": true,
                            "method": al.method,
                            "matched_count": al.matched_count,
                            "used_core_count": al.used_core_count,
                            "rmsd_angstrom": al.rmsd_angstrom,
                            "max_residual_angstrom": al.max_residual_angstrom,
                            "mpp_angstrom": planarity.as_ref().map(|p| p.mpp_angstrom),
                            "sdp_angstrom": planarity.as_ref().map(|p| p.sdp_angstrom),
                            "primary_torsion_deg": torsions.as_ref().and_then(|t| t.torsions.first().map(|x| x.angle)),
                            "torsions": torsions.map(|t| t.torsions),
                        }));
                    }
                    Err(e) => {
                        results.push(json!({ "path": tp, "ok": false, "error": e.to_string() }));
                    }
                }
            }
            json_response(
                200,
                &json!({
                    "ok": true,
                    "reference_name": ref_mol.name,
                    "reference_axis": ref_ori.axis_used,
                    "core_atoms": ref_ori.core_atoms,
                    "items": results,
                }),
            )
        }
        (Method::Post, "/api/delivery/build_package") => {
            let body = read_json(req);
            let req_pkg: delivery::DeliveryPackageRequest = match serde_json::from_value(body) {
                Ok(v) => v,
                Err(e) => return err_response(400, format!("invalid delivery request: {e}")),
            };
            match delivery::build_collaborator_delivery_package(&req_pkg) {
                Ok(res) => json_response(200, &json!(res)),
                Err(e) => err_response(400, e.to_string()),
            }
        }
        (Method::Post, "/api/ai/plan_workflow") => {
            let body = read_json(req);
            let query = body["query"].as_str().unwrap_or("");
            let st = state.lock().unwrap();
            let proposal = workflow::plan_workflow_from_intent(
                query,
                &st.hub,
                &st.engine_paths,
                st.python_exe.as_deref(),
            );
            json_response(200, &json!({ "ok": true, "proposal": proposal }))
        }
        _ => err_response(404, format!("unknown endpoint: {path}")),
    }
}

fn parse_vec3(v: &Value) -> Option<[f64; 3]> {
    let arr = v.as_array()?;
    if arr.len() < 3 {
        return None;
    }
    Some([arr[0].as_f64()?, arr[1].as_f64()?, arr[2].as_f64()?])
}
