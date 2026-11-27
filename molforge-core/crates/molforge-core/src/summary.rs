//! Chemical & geometric summary calculations (`DocumentSummary`).

use crate::commands::CommandBus;
use crate::elements;
use crate::model::{Cell, Molecule};
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentSummary {
    pub document_id: String,
    pub name: String,
    pub formula: String,
    pub molecular_weight: f64,
    pub num_atoms: usize,
    pub num_bonds: usize,
    pub charge: i32,
    pub multiplicity: u32,
    pub spin_label: String,
    pub geometry_label: String,
    pub point_group: String,
    pub revision: u64,
    pub can_undo: bool,
    pub can_redo: bool,
    pub has_2d: bool,
    pub has_3d: bool,
    pub source_path: Option<String>,
    pub cell: Option<Cell>,
    pub box_origin: [f64; 3],
    pub presets: Vec<String>,
}

pub fn formula(mol: &Molecule) -> String {
    if mol.atoms.is_empty() {
        return String::new();
    }
    let mut counts: BTreeMap<&'static str, usize> = BTreeMap::new();
    for a in &mol.atoms {
        *counts.entry(elements::symbol_of(a.z)).or_insert(0) += 1;
    }
    let mut out = String::new();
    let push_sym = |out: &mut String, sym: &str, count: usize| {
        out.push_str(sym);
        if count > 1 {
            out.push_str(&count.to_string());
        }
    };
    if let Some(c) = counts.remove("C") {
        push_sym(&mut out, "C", c);
        if let Some(h) = counts.remove("H") {
            push_sym(&mut out, "H", h);
        }
    }
    for (sym, c) in counts {
        push_sym(&mut out, sym, c);
    }
    out
}

pub fn molecular_weight(mol: &Molecule) -> f64 {
    let sum: f64 = mol.atoms.iter().map(|a| elements::weight(a.z)).sum();
    (sum * 1000.0).round() / 1000.0
}

pub fn resolve_spin_state(mol: &Molecule) -> (i32, u32, String) {
    let charge = mol.charge.unwrap_or_else(|| {
        mol.atoms.iter().map(|a| a.charge as i32).sum()
    });
    let total_z: i32 = mol.atoms.iter().map(|a| a.z as i32).sum();
    let total_electrons = (total_z - charge).max(0);
    let parity = (total_electrons % 2) as u32;
    let mult = match mol.multiplicity {
        Some(m) if m >= 1 && (m - 1) % 2 == parity => m,
        _ => {
            if parity == 0 { 1 } else { 2 }
        }
    };
    let label = match mult {
        1 => "Singlet".to_string(),
        2 => "Doublet".to_string(),
        3 => "Triplet".to_string(),
        4 => "Quartet".to_string(),
        5 => "Quintet".to_string(),
        n => format!("{n}-let"),
    };
    (charge, mult, label)
}

/// Jacobi eigenvalues of a 3x3 symmetric covariance matrix to classify 3D shape.
pub fn analyze_geometry_shape(mol: &Molecule) -> String {
    let n = mol.atoms.len();
    if n == 0 {
        return "Empty".to_string();
    }
    if n == 1 {
        return "Single Atom".to_string();
    }
    if n == 2 {
        return "Linear".to_string();
    }

    let inv_n = 1.0 / n as f64;
    let mut mean = [0.0; 3];
    for a in &mol.atoms {
        mean[0] += a.pos[0];
        mean[1] += a.pos[1];
        mean[2] += a.pos[2];
    }
    mean[0] *= inv_n;
    mean[1] *= inv_n;
    mean[2] *= inv_n;

    let mut cov = [[0.0; 3]; 3];
    for a in &mol.atoms {
        let d = [a.pos[0] - mean[0], a.pos[1] - mean[1], a.pos[2] - mean[2]];
        for i in 0..3 {
            for j in 0..3 {
                cov[i][j] += d[i] * d[j];
            }
        }
    }
    for i in 0..3 {
        for j in 0..3 {
            cov[i][j] *= inv_n;
        }
    }

    let mut evals = jacobi_3x3_eigenvalues(cov);
    evals.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let rms = [
        evals[0].max(0.0).sqrt(),
        evals[1].max(0.0).sqrt(),
        evals[2].max(0.0).sqrt(),
    ];

    let tol = 0.12;
    if rms[1] < tol {
        "Linear".to_string()
    } else if rms[0] < tol {
        "Planar".to_string()
    } else {
        "3D Non-Planar".to_string()
    }
}

pub(crate) fn jacobi_3x3_eigen(mut a: [[f64; 3]; 3]) -> ([f64; 3], [[f64; 3]; 3]) {
    let mut v = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
    for _ in 0..40 {
        let mut p = 0;
        let mut q = 1;
        let mut max_off = a[0][1].abs();
        for &(i, j) in &[(0, 2), (1, 2)] {
            if a[i][j].abs() > max_off {
                max_off = a[i][j].abs();
                p = i;
                q = j;
            }
        }
        if max_off < 1e-12 {
            break;
        }
        let tau = (a[q][q] - a[p][p]) / (2.0 * a[p][q]);
        let t = if tau >= 0.0 {
            1.0 / (tau + (1.0 + tau * tau).sqrt())
        } else {
            -1.0 / (-tau + (1.0 + tau * tau).sqrt())
        };
        let c = 1.0 / (1.0 + t * t).sqrt();
        let s = t * c;
        let app = a[p][p];
        let aqq = a[q][q];
        let apq = a[p][q];
        a[p][p] = app - t * apq;
        a[q][q] = aqq + t * apq;
        a[p][q] = 0.0;
        a[q][p] = 0.0;
        let r = 3 - p - q;
        let arp = a[r][p];
        let arq = a[r][q];
        a[r][p] = c * arp - s * arq;
        a[p][r] = a[r][p];
        a[r][q] = s * arp + c * arq;
        a[q][r] = a[r][q];
        for row in &mut v {
            let vp = row[p];
            let vq = row[q];
            row[p] = c * vp - s * vq;
            row[q] = s * vp + c * vq;
        }
    }
    ([a[0][0], a[1][1], a[2][2]], v)
}

fn jacobi_3x3_eigenvalues(a: [[f64; 3]; 3]) -> [f64; 3] {
    jacobi_3x3_eigen(a).0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanarityResult {
    pub heavy_atom_count: usize,
    pub mpp_angstrom: f64,
    pub sdp_angstrom: f64,
    pub max_deviation_angstrom: f64,
    pub normal: [f64; 3],
    pub center_angstrom: [f64; 3],
    pub atom_indices: Vec<usize>,
    pub signed_deviations_angstrom: Vec<f64>,
}

/// Pure-Rust Molecular Planarity Parameter (MPP) & Span of Deviation from Plane (SDP)
/// via least-squares covariance SVD/Jacobi plane fitting over heavy atoms.
pub fn compute_planarity(mol: &Molecule) -> Result<PlanarityResult> {
    let mut indices: Vec<usize> = mol
        .atoms
        .iter()
        .enumerate()
        .filter_map(|(idx, a)| if a.z > 1 { Some(idx) } else { None })
        .collect();
    if indices.len() < 3 {
        indices = (0..mol.atoms.len()).collect();
    }
    if indices.len() < 3 {
        return Err(CoreError::InvalidOp(
            "平面性分析 (MPP/SDP) 至少需要 3 个重原子".into(),
        ));
    }

    let n = indices.len() as f64;
    let mut center = [0.0_f64; 3];
    for &idx in &indices {
        let p = mol.atoms[idx].pos;
        center[0] += p[0];
        center[1] += p[1];
        center[2] += p[2];
    }
    center[0] /= n;
    center[1] /= n;
    center[2] /= n;

    let mut cov = [[0.0_f64; 3]; 3];
    for &idx in &indices {
        let p = mol.atoms[idx].pos;
        let d = [p[0] - center[0], p[1] - center[1], p[2] - center[2]];
        for i in 0..3 {
            for j in 0..3 {
                cov[i][j] += d[i] * d[j];
            }
        }
    }

    let (evals, evecs) = jacobi_3x3_eigen(cov);
    let mut min_col = 0usize;
    if evals[1] < evals[min_col] {
        min_col = 1;
    }
    if evals[2] < evals[min_col] {
        min_col = 2;
    }
    let mut normal = [evecs[0][min_col], evecs[1][min_col], evecs[2][min_col]];
    let n_len = (normal[0] * normal[0] + normal[1] * normal[1] + normal[2] * normal[2]).sqrt();
    if n_len > 1e-12 {
        normal[0] /= n_len;
        normal[1] /= n_len;
        normal[2] /= n_len;
    }

    let mut signed = Vec::with_capacity(indices.len());
    let mut sq_sum = 0.0_f64;
    let mut max_abs = 0.0_f64;
    let mut min_d = f64::INFINITY;
    let mut max_d = f64::NEG_INFINITY;
    for &idx in &indices {
        let p = mol.atoms[idx].pos;
        let d = (p[0] - center[0]) * normal[0]
            + (p[1] - center[1]) * normal[1]
            + (p[2] - center[2]) * normal[2];
        let d_round = (d * 100000.0).round() / 100000.0;
        signed.push(d_round);
        sq_sum += d * d;
        max_abs = max_abs.max(d.abs());
        min_d = min_d.min(d);
        max_d = max_d.max(d);
    }

    Ok(PlanarityResult {
        heavy_atom_count: indices.len(),
        mpp_angstrom: (sq_sum / n).sqrt(),
        sdp_angstrom: max_d - min_d,
        max_deviation_angstrom: max_abs,
        normal,
        center_angstrom: center,
        atom_indices: indices.into_iter().map(|i| i + 1).collect(),
        signed_deviations_angstrom: signed,
    })
}

pub fn summarize(bus: &CommandBus, presets: Vec<String>) -> DocumentSummary {
    let mol = &bus.mol;
    let (charge, multiplicity, spin_label) = resolve_spin_state(mol);
    DocumentSummary {
        document_id: mol.document_id.clone(),
        name: mol.name.clone(),
        formula: formula(mol),
        molecular_weight: molecular_weight(mol),
        num_atoms: mol.atoms.len(),
        num_bonds: mol.bonds.len(),
        charge,
        multiplicity,
        spin_label,
        geometry_label: analyze_geometry_shape(mol),
        point_group: if mol.atoms.len() <= 1 {
            "K".to_string()
        } else {
            "C1".to_string()
        },
        revision: mol.revision,
        can_undo: bus.can_undo(),
        can_redo: bus.can_redo(),
        has_2d: mol.has_2d,
        has_3d: mol.has_3d,
        source_path: mol.source_path.clone(),
        cell: mol.cell.clone(),
        box_origin: mol.box_origin,
        presets,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::commands::{CommandBus, EditCommand};

    #[test]
    fn water_summary_and_spin() {
        let mut bus = CommandBus::new(Molecule::new("water"));
        bus.execute(EditCommand::AddAtom {
            z: 8,
            pos: [0.0, 0.0, 0.117],
            pos2: [0.0, 0.0],
            bond_to: None,
            bond_order: 1,
        })
        .unwrap();
        bus.execute(EditCommand::AddAtom {
            z: 1,
            pos: [0.0, 0.757, -0.469],
            pos2: [0.7, -0.5],
            bond_to: Some(0),
            bond_order: 1,
        })
        .unwrap();
        bus.execute(EditCommand::AddAtom {
            z: 1,
            pos: [0.0, -0.757, -0.469],
            pos2: [-0.7, -0.5],
            bond_to: Some(0),
            bond_order: 1,
        })
        .unwrap();

        let s = summarize(&bus, vec![]);
        assert_eq!(s.formula, "H2O");
        assert_eq!(s.spin_label, "Singlet");
        assert_eq!(s.geometry_label, "Planar");
        assert!((s.molecular_weight - 18.015).abs() < 0.02);
    }

    #[test]
    fn benzene_and_caffeine_planarity() {
        let benz = crate::presets::build_preset("benzene").unwrap();
        let p_benz = compute_planarity(&benz).unwrap();
        assert_eq!(p_benz.heavy_atom_count, 6);
        assert!(p_benz.mpp_angstrom < 0.01);

        let caf = crate::presets::build_preset("caffeine").unwrap();
        let p_caf = compute_planarity(&caf).unwrap();
        assert!(p_caf.heavy_atom_count >= 14);
        assert!(p_caf.mpp_angstrom.is_finite());
    }
}
