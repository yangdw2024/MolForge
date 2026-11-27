//! Strictly optional, isolated on-demand Python worker.
//!
//! Used ONLY for optional scientific extensions (RDKit SMILES -> 3D ETKDG,
//! cclib log parsing, MDAnalysis). MolForge Core never depends on Python for
//! startup, editing, IO, WebGPU streaming, CalChem QC, or external EXEs.

use crate::model::Molecule;
use crate::{CoreError, Result};
use serde::Deserialize;
use std::path::{Path, PathBuf};
use std::process::Command;

/// Locate an optional Python interpreter, or return `None` when disabled/absent.
/// Respects `MOLFORGE_PYTHON=""` (explicitly disabled for zero-Python mode).
pub fn discover_python() -> Option<PathBuf> {
    if let Ok(env_py) = std::env::var("MOLFORGE_PYTHON") {
        let trimmed = env_py.trim();
        if trimmed.is_empty() {
            return None;
        }
        let p = PathBuf::from(trimmed);
        return if p.is_file() { Some(p) } else { None };
    }

    // Check common local development / sibling webengine paths
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let bundled = dir.join("python").join("python.exe");
            if bundled.is_file() {
                return Some(bundled);
            }
        }
    }

    let dev_venv = Path::new(r"E:\YDW\Trae_Chemdraw\molforge-webengine\python.exe");
    if dev_venv.is_file() {
        return Some(dev_venv.to_path_buf());
    }

    let conda_venv = Path::new(r"D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe");
    if conda_venv.is_file() {
        return Some(conda_venv.to_path_buf());
    }

    if let Ok(path_var) = std::env::var("PATH") {
        for seg in path_var.split(';') {
            let p = Path::new(seg).join("python.exe");
            if p.is_file() {
                return Some(p);
            }
        }
    }

    None
}

#[derive(Deserialize)]
struct SmilesPayload {
    name: String,
    atoms: Vec<(u8, [f64; 3], [f64; 2])>,
    bonds: Vec<(usize, usize, u8, bool)>,
}

/// Build a 3D molecule from SMILES via an isolated on-demand RDKit Python subprocess.
pub fn build_smiles_optional(python: Option<&Path>, smiles: &str) -> Result<Molecule> {
    let py = python.ok_or_else(|| {
        CoreError::External(
            "Optional Python/RDKit worker is not configured; use presets or 3D builder".into(),
        )
    })?;

    let script = r#"
import json, sys
from rdkit import Chem
from rdkit.Chem import AllChem
smi = sys.argv[1]
mol = Chem.MolFromSmiles(smi)
if mol is None:
    raise SystemExit("Invalid SMILES")
mol = Chem.AddHs(mol)
AllChem.EmbedMolecule(mol, AllChem.ETKDGv3())
try:
    AllChem.MMFFOptimizeMolecule(mol)
except Exception:
    pass
conf = mol.GetConformer()
atoms = []
for i, a in enumerate(mol.GetAtoms()):
    p = conf.GetAtomPosition(i)
    atoms.append([a.GetAtomicNum(), [float(p.x), float(p.y), float(p.z)], [float(p.x), float(p.y)]])
bonds = []
for b in mol.GetBonds():
    ot = int(round(b.GetBondTypeAsDouble()))
    bonds.append([b.GetBeginAtomIdx(), b.GetEndAtomIdx(), max(1, min(3, ot)), bool(b.GetIsAromatic())])
print(json.dumps({"name": smi, "atoms": atoms, "bonds": bonds}))
"#;

    let out = Command::new(py).arg("-c").arg(script).arg(smiles).output()?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(CoreError::External(format!("RDKit worker failed: {err}")));
    }

    let payload: SmilesPayload = serde_json::from_slice(&out.stdout)
        .map_err(|e| CoreError::Parse(format!("invalid RDKit worker JSON: {e}")))?;

    let mut mol = Molecule::new(payload.name);
    let mut ids = Vec::with_capacity(payload.atoms.len());
    for (z, pos, pos2) in payload.atoms {
        let a = mol.alloc_atom(z, pos, pos2);
        ids.push(a.id);
        mol.atoms.push(a);
    }
    mol.reindex();
    for (ia, ib, ord, arom) in payload.bonds {
        if let (Some(&a), Some(&b)) = (ids.get(ia), ids.get(ib)) {
            let bond = mol.alloc_bond(a, b, ord, arom);
            mol.bonds.push(bond);
        }
    }
    mol.has_3d = true;
    mol.has_2d = true;
    Ok(mol)
}

/// Native spring-electrical force-field relaxation for 3D coordinates.
/// Guarantees zero crashes and immediate de-clashing even in zero-Python mode.
pub fn clean_3d_native(mol: &Molecule) -> Vec<(u32, [f64; 3])> {
    if mol.atoms.is_empty() {
        return Vec::new();
    }
    let n = mol.atoms.len();
    if n == 1 {
        return vec![(mol.atoms[0].id, mol.atoms[0].pos)];
    }

    let mut pos: Vec<[f64; 3]> = mol.atoms.iter().map(|a| a.pos).collect();
    let mut vel: Vec<[f64; 3]> = vec![[0.0, 0.0, 0.0]; n];

    // Map atom ID to index
    let mut id_map = std::collections::HashMap::with_capacity(n);
    for (i, a) in mol.atoms.iter().enumerate() {
        id_map.insert(a.id, i);
    }

    // Identify bonded pairs with target equilibrium distance
    let mut bonds = Vec::with_capacity(mol.bonds.len());
    for b in &mol.bonds {
        if let (Some(&i), Some(&j)) = (id_map.get(&b.a), id_map.get(&b.b)) {
            let za = mol.atoms[i].z;
            let zb = mol.atoms[j].z;
            let r0 = match (za, zb) {
                (1, 1) => 0.74,
                (1, 6) | (6, 1) => 1.09,
                (1, 7) | (7, 1) => 1.01,
                (1, 8) | (8, 1) => 0.96,
                (6, 6) => {
                    if b.order == 3 {
                        1.20
                    } else if b.order == 2 {
                        1.34
                    } else {
                        1.54
                    }
                }
                (6, 7) | (7, 6) => {
                    if b.order == 2 {
                        1.28
                    } else {
                        1.47
                    }
                }
                (6, 8) | (8, 6) => {
                    if b.order == 2 {
                        1.22
                    } else {
                        1.43
                    }
                }
                (6, 16) | (16, 6) => 1.82,
                _ => 1.48,
            };
            bonds.push((i, j, r0));
        }
    }

    // Force relaxation loop (160 iterations)
    let dt = 0.025;
    let damping = 0.82;
    for _ in 0..160 {
        let mut force: Vec<[f64; 3]> = vec![[0.0, 0.0, 0.0]; n];

        // 1. Bond spring forces
        for &(i, j, r0) in &bonds {
            let dx = pos[j][0] - pos[i][0];
            let dy = pos[j][1] - pos[i][1];
            let dz = pos[j][2] - pos[i][2];
            let mut dist = (dx * dx + dy * dy + dz * dz).sqrt();
            if dist < 0.001 {
                dist = 0.001;
            }
            let delta = dist - r0;
            let k = 80.0;
            let fx = k * delta * (dx / dist);
            let fy = k * delta * (dy / dist);
            let fz = k * delta * (dz / dist);

            force[i][0] += fx;
            force[i][1] += fy;
            force[i][2] += fz;
            force[j][0] -= fx;
            force[j][1] -= fy;
            force[j][2] -= fz;
        }

        // 2. Non-bonded repulsive forces (avoid atom overlap)
        for i in 0..n {
            for j in (i + 1)..n {
                let dx = pos[j][0] - pos[i][0];
                let dy = pos[j][1] - pos[i][1];
                let dz = pos[j][2] - pos[i][2];
                let mut dist2 = dx * dx + dy * dy + dz * dz;
                if dist2 < 0.0001 {
                    pos[j][0] += (j as f64 * 0.17).sin() * 0.2;
                    pos[j][1] += (j as f64 * 0.23).cos() * 0.2;
                    pos[j][2] += (j as f64 * 0.31).sin() * 0.2;
                    dist2 = 0.04;
                }
                let dist = dist2.sqrt();
                if dist < 2.2 {
                    let rep = 15.0 / (dist2 * dist2);
                    let fx = rep * (dx / dist);
                    let fy = rep * (dy / dist);
                    let fz = rep * (dz / dist);
                    force[i][0] -= fx;
                    force[i][1] -= fy;
                    force[i][2] -= fz;
                    force[j][0] += fx;
                    force[j][1] += fy;
                    force[j][2] += fz;
                }
            }
        }

        // 3. Integrate Verlet / Euler step
        for i in 0..n {
            vel[i][0] = (vel[i][0] + force[i][0] * dt) * damping;
            vel[i][1] = (vel[i][1] + force[i][1] * dt) * damping;
            vel[i][2] = (vel[i][2] + force[i][2] * dt) * damping;

            let speed = (vel[i][0] * vel[i][0] + vel[i][1] * vel[i][1] + vel[i][2] * vel[i][2]).sqrt();
            if speed > 2.0 {
                let s = 2.0 / speed;
                vel[i][0] *= s;
                vel[i][1] *= s;
                vel[i][2] *= s;
            }

            pos[i][0] += vel[i][0] * dt;
            pos[i][1] += vel[i][1] * dt;
            pos[i][2] += vel[i][2] * dt;
        }
    }

    mol.atoms
        .iter()
        .enumerate()
        .map(|(i, a)| (a.id, pos[i]))
        .collect()
}

/// 3D Geometry cleanup using RDKit MMFF94 / UFF with fallback to native relaxation.
pub fn clean_3d_via_worker(python: Option<&Path>, mol: &Molecule) -> Vec<(u32, [f64; 3])> {
    if mol.atoms.is_empty() {
        return Vec::new();
    }

    if let Some(py) = python {
        let script = r#"
import json, sys
from rdkit import Chem
from rdkit.Chem import AllChem

try:
    payload = json.loads(sys.stdin.read())
    atoms = payload.get("atoms", [])
    bonds = payload.get("bonds", [])
    rw = Chem.RWMol()
    conf = Chem.Conformer(len(atoms))
    for i, a in enumerate(atoms):
        ra = Chem.Atom(int(a["z"]))
        idx = rw.AddAtom(ra)
        p = a["pos"]
        from rdkit.Geometry import Point3D
        conf.SetAtomPosition(idx, Point3D(float(p[0]), float(p[1]), float(p[2])))
    for b in bonds:
        ord_val = int(b["order"])
        bt = Chem.BondType.SINGLE
        if ord_val == 2:
            bt = Chem.BondType.DOUBLE
        elif ord_val == 3:
            bt = Chem.BondType.TRIPLE
        rw.AddBond(int(b["begin"]), int(b["end"]), bt)
    m = rw.GetMol()
    m.AddConformer(conf, assignId=True)
    try:
        Chem.SanitizeMol(m)
        if AllChem.MMFFOptimizeMolecule(m, maxIters=400) != 0:
            AllChem.UFFOptimizeMolecule(m, maxIters=400)
    except Exception:
        AllChem.UFFOptimizeMolecule(m, maxIters=400)
    res_conf = m.GetConformer()
    out = []
    for i in range(m.GetNumAtoms()):
        pt = res_conf.GetAtomPosition(i)
        out.append([atoms[i]["id"], [round(float(pt.x), 4), round(float(pt.y), 4), round(float(pt.z), 4)]])
    print(json.dumps({"ok": True, "positions": out}))
except Exception as e:
    print(json.dumps({"ok": False, "error": str(e)}))
"#;

        let mut id_to_idx = std::collections::HashMap::new();
        let atoms_json: Vec<serde_json::Value> = mol
            .atoms
            .iter()
            .enumerate()
            .map(|(i, a)| {
                id_to_idx.insert(a.id, i);
                serde_json::json!({
                    "id": a.id,
                    "z": a.z,
                    "pos": a.pos
                })
            })
            .collect();

        let bonds_json: Vec<serde_json::Value> = mol
            .bonds
            .iter()
            .filter_map(|b| {
                let bi = id_to_idx.get(&b.a)?;
                let bj = id_to_idx.get(&b.b)?;
                Some(serde_json::json!({
                    "begin": bi,
                    "end": bj,
                    "order": b.order
                }))
            })
            .collect();

        let req_json = serde_json::json!({
            "atoms": atoms_json,
            "bonds": bonds_json
        });

        if let Ok(mut child) = Command::new(py)
            .arg("-c")
            .arg(script)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .spawn()
        {
            if let Some(mut stdin) = child.stdin.take() {
                let _ = serde_json::to_writer(&mut stdin, &req_json);
            }
            if let Ok(output) = child.wait_with_output() {
                if output.status.success() {
                    if let Ok(val) = serde_json::from_slice::<serde_json::Value>(&output.stdout) {
                        if val["ok"].as_bool() == Some(true) {
                            if let Some(arr) = val["positions"].as_array() {
                                let mut positions = Vec::with_capacity(arr.len());
                                for item in arr {
                                    if let (Some(id), Some(coords)) = (item[0].as_u64(), item[1].as_array()) {
                                        if coords.len() == 3 {
                                            let x = coords[0].as_f64().unwrap_or(0.0);
                                            let y = coords[1].as_f64().unwrap_or(0.0);
                                            let z = coords[2].as_f64().unwrap_or(0.0);
                                            positions.push((id as u32, [x, y, z]));
                                        }
                                    }
                                }
                                if !positions.is_empty() {
                                    return positions;
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Fallback to pure Rust native relaxation
    clean_3d_native(mol)
}

/// Inspect a batch of SMILES strings and return metadata + preview
pub fn inspect_smiles_batch_via_worker(
    python: Option<&Path>,
    items: &[serde_json::Value],
) -> Vec<serde_json::Value> {
    if items.is_empty() {
        return Vec::new();
    }

    if let Some(py) = python {
        let script = r#"
import json, sys, uuid
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

items = json.loads(sys.stdin.read())
results = []
for idx, row in enumerate(items[:200]):
    smi = str(row.get("smiles", "")).strip()
    name = str(row.get("name", "")).strip() or f"Molecule-{idx+1}"
    cat = str(row.get("category", "导入分子")).strip()
    if not smi:
        continue
    try:
        m = Chem.MolFromSmiles(smi)
        if m is None:
            results.append({"id": f"mol_{idx}", "ok": False, "name": name, "smiles": smi, "category": cat, "error": "Invalid SMILES"})
            continue
        formula = rdMolDescriptors.CalcMolFormula(m)
        mw = round(Descriptors.MolWt(m), 3)
        num_atoms = m.GetNumAtoms()
        num_bonds = m.GetNumBonds()

        drawer = rdMolDraw2D.MolDraw2DSVG(240, 180)
        drawer.DrawMolecule(m)
        drawer.FinishDrawing()
        svg = drawer.GetDrawingText()

        results.append({
            "id": f"custom_{idx}_{uuid.uuid4().hex[:6]}",
            "ok": True,
            "name": name,
            "label": f"{name} · {formula}",
            "category": cat,
            "smiles": smi,
            "formula": formula,
            "molecular_weight": mw,
            "num_atoms": num_atoms,
            "num_bonds": num_bonds,
            "multiplicity": 1,
            "preview_2d": svg,
        })
    except Exception as e:
        results.append({"id": f"mol_{idx}", "ok": False, "name": name, "smiles": smi, "category": cat, "error": str(e)})
print(json.dumps(results))
"#;

        if let Ok(mut child) = Command::new(py)
            .arg("-c")
            .arg(script)
            .stdin(std::process::Stdio::piped())
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::null())
            .spawn()
        {
            if let Some(mut stdin) = child.stdin.take() {
                let _ = serde_json::to_writer(&mut stdin, &items);
            }
            if let Ok(output) = child.wait_with_output() {
                if output.status.success() {
                    if let Ok(res) = serde_json::from_slice::<Vec<serde_json::Value>>(&output.stdout) {
                        return res;
                    }
                }
            }
        }
    }

    // Python 缺失时的诚实回退：明确报错，绝不伪造化学式/分子量估算值
    items
        .iter()
        .enumerate()
        .map(|(idx, row)| {
            let smi = row["smiles"].as_str().unwrap_or("").trim();
            let name = row["name"].as_str().unwrap_or("").trim();
            let cat = row["category"].as_str().unwrap_or("导入分子").trim();
            serde_json::json!({
                "id": format!("custom_{idx}"),
                "ok": false,
                "name": if name.is_empty() { format!("Molecule-{}", idx + 1) } else { name.to_string() },
                "label": name,
                "category": cat,
                "smiles": smi,
                "formula": null,
                "molecular_weight": null,
                "num_atoms": 0,
                "num_bonds": 0,
                "multiplicity": 1,
                "preview_2d": null,
                "error": "Python worker 未启用，无法真实解析 SMILES（拒绝返回估算值）。请配置 Python/RDKit 后重试。"
            })
        })
        .collect()
}

/// Call DeepSeek / OpenAI-compatible chat API via Windows curl.exe or Python
pub fn ai_chat_request(
    base_url: &str,
    api_key: &str,
    model: &str,
    system_prompt: &str,
    user_prompt: &str,
) -> Result<String> {
    let endpoint = format!("{}/chat/completions", base_url.trim_end_matches('/'));
    let payload = serde_json::json!({
        "model": model,
        "messages": [
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": user_prompt }
        ],
        "temperature": 0.3,
        "max_tokens": 800
    });
    let payload_str = payload.to_string();

    let mut cmd = Command::new("curl.exe");
    cmd.arg("-s")
        .arg("-X")
        .arg("POST")
        .arg(&endpoint)
        .arg("-H")
        .arg("Content-Type: application/json")
        .arg("--max-time")
        .arg("15");

    if !api_key.trim().is_empty() {
        cmd.arg("-H").arg(format!("Authorization: Bearer {}", api_key.trim()));
    }

    cmd.arg("-d").arg(&payload_str);

    let output = cmd.output().map_err(|e| {
        CoreError::External(format!("Failed to invoke curl.exe for AI request: {e}"))
    })?;

    if !output.status.success() {
        return Err(CoreError::External(format!(
            "AI request curl failed with exit code {:?}",
            output.status.code()
        )));
    }

    let val: serde_json::Value = serde_json::from_slice(&output.stdout).map_err(|e| {
        CoreError::Parse(format!(
            "Invalid AI JSON response: {e}; stdout: {}",
            String::from_utf8_lossy(&output.stdout)
        ))
    })?;

    if let Some(err_msg) = val["error"]["message"].as_str() {
        return Err(CoreError::External(format!("AI API returned error: {err_msg}")));
    }

    let reply = val["choices"][0]["message"]["content"]
        .as_str()
        .ok_or_else(|| CoreError::Parse("AI response missing choices[0].message.content".into()))?;

    Ok(reply.to_string())
}
