//! Pure-Rust Molecular Topology, Core-First Deterministic Orientation,
//! Automated Geometry Inspector (`PROP-TORSION`), and Order-Independent MCS + Kabsch Alignment.
//!
//! Faithfully implements Modules 1 & 2 from `MolForge_可视化与定向架构参考.md`
//! and `rep_pipeline.py`:
//! - Covalent-radii connectivity & elementary ring perception
//! - Largest fused ring component (`_largest_fused_component`)
//! - Core-First canonical coordinate frame (long->+Y, mid->-X, normal->+Z, det=+1)
//! - `core-wing` / `wing-wing` / `core-core` classification + 4-path acute dihedral selector
//! - Least-squares ring interplanar angle + intramolecular non-covalent short contacts
//! - Order-independent MCS subgraph matching + robust trimmed Kabsch rigid alignment

use crate::elements;
use crate::model::Molecule;
use crate::summary::jacobi_3x3_eigen;
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};

const CORE_MAX_ASPECT: f64 = 0.65;
const ALIGN_KEEP_FRAC: f64 = 0.70;
const ALIGN_DIRECT_RMSD_OK: f64 = 0.60;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CoreOrientationResult {
    pub rotation_3x3: [[f64; 3]; 3],
    pub center_angstrom: [f64; 3],
    pub axis_used: String,
    /// 1-based atom indices forming the largest fused ring component.
    pub core_atoms: Vec<usize>,
    pub core_eig_ratio: [f64; 2],
    pub core_tilt_in_pca_deg: f64,
    pub core_vs_pca_rot_deg: f64,
    pub aligned_positions: Vec<[f64; 3]>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TorsionBond {
    #[serde(rename = "type")]
    pub bond_type: String,
    pub side: String,
    /// 1-based atom indices `[p1, c_idx, w_idx, p2]`.
    pub atoms: [usize; 4],
    /// Selected acute torsion angle in degrees (`|angle| <= 90` when any path is acute).
    pub angle: f64,
    pub all_acute_angles: Vec<f64>,
    pub bond_length_a: f64,
    pub interplanar_deg: Option<f64>,
    pub ring1: usize,
    pub ring2: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShortContact {
    pub kind: String,
    /// 1-based atom indices `[i, j]`.
    pub atoms: [usize; 2],
    pub distance_a: f64,
    pub threshold_a: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TorsionAnalysisResult {
    pub core_atoms: Vec<usize>,
    pub axis_used: String,
    pub torsions: Vec<TorsionBond>,
    pub short_contacts: Vec<ShortContact>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AlignmentResult {
    pub method: String,
    pub matched_count: usize,
    pub used_core_count: usize,
    pub rmsd_angstrom: f64,
    pub max_residual_angstrom: f64,
    pub rotation_3x3: [[f64; 3]; 3],
    pub translation: [f64; 3],
    pub aligned_positions: Vec<[f64; 3]>,
}

fn cov_radius(z: u8) -> f64 {
    match z {
        1 => 0.31,
        5 => 0.84,
        6 => 0.76,
        7 => 0.71,
        8 => 0.66,
        9 => 0.57,
        14 => 1.11,
        15 => 1.07,
        16 => 1.05,
        17 => 1.02,
        35 => 1.20,
        53 => 1.39,
        _ => elements::by_z(z).map(|e| e.cov).unwrap_or(0.80),
    }
}

#[inline]
fn dist3(a: [f64; 3], b: [f64; 3]) -> f64 {
    let dx = a[0] - b[0];
    let dy = a[1] - b[1];
    let dz = a[2] - b[2];
    (dx * dx + dy * dy + dz * dz).sqrt()
}

#[inline]
fn cross(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]
}

#[inline]
fn dot(a: [f64; 3], b: [f64; 3]) -> f64 {
    a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
}

#[inline]
fn normalize(v: [f64; 3]) -> [f64; 3] {
    let l = dot(v, v).sqrt();
    if l > 1e-12 {
        [v[0] / l, v[1] / l, v[2] / l]
    } else {
        [0.0, 0.0, 1.0]
    }
}

#[inline]
fn mat3_mul(a: [[f64; 3]; 3], b: [[f64; 3]; 3]) -> [[f64; 3]; 3] {
    let mut out = [[0.0_f64; 3]; 3];
    for i in 0..3 {
        for j in 0..3 {
            out[i][j] = a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j];
        }
    }
    out
}

#[inline]
fn mat3_vec(r: [[f64; 3]; 3], p: [f64; 3]) -> [f64; 3] {
    [
        r[0][0] * p[0] + r[0][1] * p[1] + r[0][2] * p[2],
        r[1][0] * p[0] + r[1][1] * p[1] + r[1][2] * p[2],
        r[2][0] * p[0] + r[2][1] * p[1] + r[2][2] * p[2],
    ]
}

#[inline]
fn mat3_transpose(a: [[f64; 3]; 3]) -> [[f64; 3]; 3] {
    [
        [a[0][0], a[1][0], a[2][0]],
        [a[0][1], a[1][1], a[2][1]],
        [a[0][2], a[1][2], a[2][2]],
    ]
}

#[inline]
fn mat3_det(a: [[f64; 3]; 3]) -> f64 {
    a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0])
}

/// Build covalent single-bond graph (ignoring RDKit bond orders which misclassify
/// inter-ring C-C bonds in large conjugated frameworks as DOUBLE).
pub fn build_covalent_graph(mol: &Molecule) -> (Vec<Vec<usize>>, Vec<(usize, usize)>) {
    let n = mol.atoms.len();
    let mut adj: Vec<Vec<usize>> = vec![Vec::new(); n];
    let mut edge_set: BTreeSet<(usize, usize)> = BTreeSet::new();

    for i in 0..n {
        let ri = cov_radius(mol.atoms[i].z);
        for j in (i + 1)..n {
            if mol.atoms[i].z == 1 && mol.atoms[j].z == 1 && n > 2 {
                continue;
            }
            let d = dist3(mol.atoms[i].pos, mol.atoms[j].pos);
            let lim = 1.25 * (ri + cov_radius(mol.atoms[j].z));
            if d > 0.4 && d < lim {
                edge_set.insert((i, j));
            }
        }
    }
    for b in &mol.bonds {
        if let (Some(i), Some(j)) = (mol.atom_index(b.a), mol.atom_index(b.b)) {
            if i != j {
                edge_set.insert((i.min(j), i.max(j)));
            }
        }
    }

    let edges: Vec<(usize, usize)> = edge_set.into_iter().collect();
    for &(i, j) in &edges {
        adj[i].push(j);
        adj[j].push(i);
    }
    (adj, edges)
}

/// Perceive elementary rings (size 3..=8) by per-edge BFS shortest path with the direct edge blocked.
pub fn perceive_rings(adj: &[Vec<usize>], edges: &[(usize, usize)]) -> Vec<HashSet<usize>> {
    let n = adj.len();
    let mut seen: HashSet<Vec<usize>> = HashSet::new();
    let mut rings: Vec<HashSet<usize>> = Vec::new();

    for &(u, v) in edges {
        // BFS from u to v avoiding direct edge (u, v) with max depth 7 (ring size <= 8)
        let mut parent = vec![usize::MAX; n];
        let mut depth = vec![usize::MAX; n];
        let mut q = VecDeque::new();
        parent[u] = u;
        depth[u] = 0;
        q.push_back(u);

        let mut found = false;
        while let Some(cur) = q.pop_front() {
            if cur == v {
                found = true;
                break;
            }
            if depth[cur] >= 7 {
                continue;
            }
            for &nxt in &adj[cur] {
                if (cur == u && nxt == v) || (cur == v && nxt == u) {
                    continue;
                }
                if depth[nxt] == usize::MAX {
                    depth[nxt] = depth[cur] + 1;
                    parent[nxt] = cur;
                    q.push_back(nxt);
                }
            }
        }
        if found {
            let mut cycle = Vec::new();
            let mut cur = v;
            while cur != u && cur != usize::MAX {
                cycle.push(cur);
                cur = parent[cur];
            }
            if cur == u {
                cycle.push(u);
                if (3..=8).contains(&cycle.len()) {
                    let mut key = cycle.clone();
                    key.sort_unstable();
                    if seen.insert(key) {
                        rings.push(cycle.into_iter().collect());
                    }
                }
            }
        }
    }
    rings
}

/// Return the single fused ring system (rings sharing >= 2 atoms) with maximum heavy atoms.
pub fn largest_fused_component(mol: &Molecule, rings: &[HashSet<usize>]) -> HashSet<usize> {
    let fused: Vec<&HashSet<usize>> = rings
        .iter()
        .enumerate()
        .filter(|&(idx, r)| {
            rings
                .iter()
                .enumerate()
                .any(|(idx2, r2)| idx != idx2 && r.intersection(r2).count() >= 2)
        })
        .map(|(_, r)| r)
        .collect();
    if fused.is_empty() {
        return HashSet::new();
    }

    let mut visited = vec![false; fused.len()];
    let mut comps: Vec<HashSet<usize>> = Vec::new();
    for i in 0..fused.len() {
        if visited[i] {
            continue;
        }
        let mut comp = fused[i].clone();
        visited[i] = true;
        loop {
            let mut changed = false;
            for j in 0..fused.len() {
                if !visited[j] && comp.intersection(fused[j]).count() >= 2 {
                    for &a in fused[j] {
                        comp.insert(a);
                    }
                    visited[j] = true;
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
        comps.push(comp);
    }

    comps
        .into_iter()
        .max_by_key(|c| c.iter().filter(|&&i| mol.atoms[i].z > 1).count())
        .unwrap_or_default()
}

fn principal_frame(points: &[[f64; 3]]) -> ([f64; 3], [[f64; 3]; 3], [f64; 3]) {
    let n = points.len().max(1) as f64;
    let mut mean = [0.0; 3];
    for p in points {
        mean[0] += p[0];
        mean[1] += p[1];
        mean[2] += p[2];
    }
    mean[0] /= n;
    mean[1] /= n;
    mean[2] /= n;

    let mut cov = [[0.0_f64; 3]; 3];
    for p in points {
        let d = [p[0] - mean[0], p[1] - mean[1], p[2] - mean[2]];
        for r in 0..3 {
            for c in 0..3 {
                cov[r][c] += d[r] * d[c];
            }
        }
    }
    let (evals, evecs) = jacobi_3x3_eigen(cov);
    let mut order = [0usize, 1, 2];
    order.sort_by(|&a, &b| evals[b].partial_cmp(&evals[a]).unwrap_or(std::cmp::Ordering::Equal));

    let e_long = normalize([evecs[0][order[0]], evecs[1][order[0]], evecs[2][order[0]]]);
    let e_mid = normalize([evecs[0][order[1]], evecs[1][order[1]], evecs[2][order[1]]]);
    let mut e_short = normalize([evecs[0][order[2]], evecs[1][order[2]], evecs[2][order[2]]]);
    if dot(cross(e_long, e_mid), e_short) < 0.0 {
        e_short = [-e_short[0], -e_short[1], -e_short[2]];
    }
    // Canonical mapping M: long -> +Y, mid -> -X, short -> +Z  (det = +1)
    let rot = [
        [-e_mid[0], -e_mid[1], -e_mid[2]],
        [e_long[0], e_long[1], e_long[2]],
        [e_short[0], e_short[1], e_short[2]],
    ];
    let sorted_evals = [
        evals[order[0]].max(1e-12),
        evals[order[1]].max(0.0),
        evals[order[2]].max(0.0),
    ];
    (mean, rot, sorted_evals)
}

/// Compute Core-First canonical coordinate frame (long->+Y, mid->-X, normal->+Z).
pub fn compute_core_first_orientation(mol: &Molecule) -> Result<CoreOrientationResult> {
    if mol.atoms.len() < 2 {
        return Err(CoreError::InvalidOp("定向至少需要 2 个原子".into()));
    }
    let heavy_indices: Vec<usize> = {
        let h: Vec<usize> = mol
            .atoms
            .iter()
            .enumerate()
            .filter_map(|(i, a)| if a.z > 1 { Some(i) } else { None })
            .collect();
        if h.len() >= 2 {
            h
        } else {
            (0..mol.atoms.len()).collect()
        }
    };
    let heavy_pts: Vec<[f64; 3]> = heavy_indices.iter().map(|&i| mol.atoms[i].pos).collect();
    let (mol_center, r_pca, _) = principal_frame(&heavy_pts);

    let (adj, edges) = build_covalent_graph(mol);
    let rings = perceive_rings(&adj, &edges);
    let main_core = largest_fused_component(mol, &rings);
    let mut core_heavy: Vec<usize> = main_core
        .iter()
        .copied()
        .filter(|&i| mol.atoms[i].z > 1)
        .collect();
    core_heavy.sort_unstable();

    let (mut rot, axis_used, core_eig_ratio, core_tilt_in_pca_deg, core_vs_pca_rot_deg) =
        if core_heavy.len() >= 6 {
            let core_pts: Vec<[f64; 3]> = core_heavy.iter().map(|&i| mol.atoms[i].pos).collect();
            let (_, r_core_base, w_core) = principal_frame(&core_pts);
            let ratio1 = w_core[1] / w_core[0];
            let ratio2 = w_core[2] / w_core[0];
            if ratio1 <= CORE_MAX_ASPECT {
                // Pick among the 4 SO(3) sign flips the one closest to whole-molecule R_pca
                let signs: [[f64; 3]; 4] = [
                    [1.0, 1.0, 1.0],
                    [1.0, -1.0, -1.0],
                    [-1.0, 1.0, -1.0],
                    [-1.0, -1.0, 1.0],
                ];
                let mut best_score = f64::NEG_INFINITY;
                let mut best_r = r_core_base;
                for s in signs {
                    let candidate = [
                        [r_core_base[0][0] * s[0], r_core_base[0][1] * s[0], r_core_base[0][2] * s[0]],
                        [r_core_base[1][0] * s[1], r_core_base[1][1] * s[1], r_core_base[1][2] * s[1]],
                        [r_core_base[2][0] * s[2], r_core_base[2][1] * s[2], r_core_base[2][2] * s[2]],
                    ];
                    let mut trace = 0.0;
                    for r in 0..3 {
                        for c in 0..3 {
                            trace += candidate[r][c] * r_pca[r][c];
                        }
                    }
                    if trace > best_score {
                        best_score = trace;
                        best_r = candidate;
                    }
                }
                // Core long axis in core frame is row 1 (+Y); recover original e_long
                let e_long_orig = [best_r[1][0], best_r[1][1], best_r[1][2]];
                let e_img = mat3_vec(r_pca, e_long_orig);
                let mut tilt = e_img[0].atan2(e_img[1]).to_degrees();
                if tilt > 90.0 {
                    tilt -= 180.0;
                }
                if tilt <= -90.0 {
                    tilt += 180.0;
                }
                let rel = mat3_mul(best_r, mat3_transpose(r_pca));
                let tr = rel[0][0] + rel[1][1] + rel[2][2];
                let rot_diff = ((tr - 1.0) * 0.5).clamp(-1.0, 1.0).acos().to_degrees();
                (
                    best_r,
                    "core".to_string(),
                    [(ratio1 * 10000.0).round() / 10000.0, (ratio2 * 10000.0).round() / 10000.0],
                    (tilt * 100.0).round() / 100.0,
                    (rot_diff * 100.0).round() / 100.0,
                )
            } else {
                (
                    r_pca,
                    "pca_fallback".to_string(),
                    [(ratio1 * 10000.0).round() / 10000.0, (ratio2 * 10000.0).round() / 10000.0],
                    0.0,
                    0.0,
                )
            }
        } else {
            (r_pca, "pca_fallback".to_string(), [0.0, 0.0], 0.0, 0.0)
        };

    if mat3_det(rot) < 0.0 {
        rot[2] = [-rot[2][0], -rot[2][1], -rot[2][2]];
    }

    let aligned_positions: Vec<[f64; 3]> = mol
        .atoms
        .iter()
        .map(|a| {
            let shifted = [
                a.pos[0] - mol_center[0],
                a.pos[1] - mol_center[1],
                a.pos[2] - mol_center[2],
            ];
            mat3_vec(rot, shifted)
        })
        .collect();

    Ok(CoreOrientationResult {
        rotation_3x3: rot,
        center_angstrom: mol_center,
        axis_used,
        core_atoms: core_heavy.into_iter().map(|i| i + 1).collect(),
        core_eig_ratio,
        core_tilt_in_pca_deg,
        core_vs_pca_rot_deg,
        aligned_positions,
    })
}

fn dihedral_deg(a: [f64; 3], b: [f64; 3], c: [f64; 3], d: [f64; 3]) -> Option<f64> {
    let b1 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    let b2 = [c[0] - b[0], c[1] - b[1], c[2] - b[2]];
    let b3 = [d[0] - c[0], d[1] - c[1], d[2] - c[2]];
    let n1 = cross(b1, b2);
    let n2 = cross(b2, b3);
    let m1 = dot(n1, n1).sqrt();
    let m2 = dot(n2, n2).sqrt();
    let mb2 = dot(b2, b2).sqrt();
    if m1 < 1e-8 || m2 < 1e-8 || mb2 < 1e-8 {
        return None;
    }
    let cos_phi = (dot(n1, n2) / (m1 * m2)).clamp(-1.0, 1.0);
    let mut phi = cos_phi.acos().to_degrees();
    if dot(cross(n1, n2), b2) < 0.0 {
        phi = -phi;
    }
    Some(phi)
}

fn least_squares_normal(pts: &[[f64; 3]]) -> [f64; 3] {
    let (_, rot, _) = principal_frame(pts);
    rot[2]
}

fn ring_interplanar_deg(mol: &Molecule, r1: &HashSet<usize>, r2: &HashSet<usize>) -> f64 {
    let p1: Vec<[f64; 3]> = r1.iter().map(|&i| mol.atoms[i].pos).collect();
    let p2: Vec<[f64; 3]> = r2.iter().map(|&i| mol.atoms[i].pos).collect();
    if p1.len() < 3 || p2.len() < 3 {
        return 0.0;
    }
    let n1 = least_squares_normal(&p1);
    let n2 = least_squares_normal(&p2);
    dot(n1, n2).abs().clamp(0.0, 1.0).acos().to_degrees()
}

fn graph_distance_at_least(adj: &[Vec<usize>], start: usize, goal: usize, min_hops: usize) -> bool {
    let mut dist = vec![usize::MAX; adj.len()];
    let mut q = VecDeque::new();
    dist[start] = 0;
    q.push_back(start);
    while let Some(u) = q.pop_front() {
        if u == goal {
            return dist[u] >= min_hops;
        }
        if dist[u] >= min_hops {
            continue;
        }
        for &v in &adj[u] {
            if dist[v] == usize::MAX {
                dist[v] = dist[u] + 1;
                q.push_back(v);
            }
        }
    }
    true
}

/// Module 2: Pure-Rust Geometry Auto-Inspector (`PROP-TORSION`).
pub fn compute_torsions(mol: &Molecule) -> Result<TorsionAnalysisResult> {
    if mol.atoms.len() < 4 {
        return Err(CoreError::InvalidOp("二面角自动分析至少需要 4 个原子".into()));
    }
    let (adj, edges) = build_covalent_graph(mol);
    let rings = perceive_rings(&adj, &edges);
    let main_core = largest_fused_component(mol, &rings);
    let orient = compute_core_first_orientation(mol)?;

    let mut atom_in_ring = vec![false; mol.atoms.len()];
    for r in &rings {
        for &i in r {
            atom_in_ring[i] = true;
        }
    }

    let edge_in_same_ring = |i: usize, j: usize| -> bool {
        rings.iter().any(|r| r.contains(&i) && r.contains(&j))
    };

    let mut items: Vec<(usize, f64, TorsionBond)> = Vec::new();
    for &(i1, i2) in &edges {
        if !(atom_in_ring[i1] && atom_in_ring[i2]) || edge_in_same_ring(i1, i2) {
            continue;
        }
        let in1 = main_core.contains(&i1);
        let in2 = main_core.contains(&i2);
        let (btype, c_idx, w_idx) = if in1 && !in2 {
            ("core-wing", i1, i2)
        } else if in2 && !in1 {
            ("core-wing", i2, i1)
        } else if in1 && in2 {
            ("core-core", i1, i2)
        } else {
            ("wing-wing", i1, i2)
        };

        let n1: Vec<usize> = adj[c_idx]
            .iter()
            .copied()
            .filter(|&k| k != w_idx && atom_in_ring[k])
            .collect();
        let n2: Vec<usize> = adj[w_idx]
            .iter()
            .copied()
            .filter(|&k| k != c_idx && atom_in_ring[k])
            .collect();
        if n1.is_empty() || n2.is_empty() {
            continue;
        }

        let mut paths: Vec<([usize; 4], f64)> = Vec::new();
        for &p1 in &n1 {
            for &p2 in &n2 {
                if let Some(ang) = dihedral_deg(
                    mol.atoms[p1].pos,
                    mol.atoms[c_idx].pos,
                    mol.atoms[w_idx].pos,
                    mol.atoms[p2].pos,
                ) {
                    paths.push(([p1 + 1, c_idx + 1, w_idx + 1, p2 + 1], ang));
                }
            }
        }
        if paths.is_empty() {
            continue;
        }

        let acute: Vec<([usize; 4], f64)> = paths
            .iter()
            .copied()
            .filter(|&(_, a)| a.abs() <= 90.0)
            .collect();
        let chosen = if !acute.is_empty() {
            *acute
                .iter()
                .min_by(|a, b| a.1.abs().partial_cmp(&b.1.abs()).unwrap_or(std::cmp::Ordering::Equal))
                .unwrap()
        } else {
            *paths
                .iter()
                .min_by(|a, b| a.1.abs().partial_cmp(&b.1.abs()).unwrap_or(std::cmp::Ordering::Equal))
                .unwrap()
        };

        let blen = dist3(mol.atoms[c_idx].pos, mol.atoms[w_idx].pos);
        let rc = rings.iter().find(|r| r.contains(&c_idx));
        let rw = rings.iter().find(|r| r.contains(&w_idx));
        let inter_deg = match (rc, rw) {
            (Some(a), Some(b)) => Some((ring_interplanar_deg(mol, a, b) * 100.0).round() / 100.0),
            _ => None,
        };
        let mid_x = 0.5 * (orient.aligned_positions[c_idx][0] + orient.aligned_positions[w_idx][0]);
        let rank = match btype {
            "core-wing" => 0,
            "wing-wing" => 1,
            _ => 2,
        };
        items.push((
            rank,
            mid_x,
            TorsionBond {
                bond_type: btype.to_string(),
                side: if mid_x < 0.0 { "left".into() } else { "right".into() },
                atoms: chosen.0,
                angle: (chosen.1 * 10000.0).round() / 10000.0,
                all_acute_angles: acute.iter().map(|x| (x.1 * 10000.0).round() / 10000.0).collect(),
                bond_length_a: (blen * 10000.0).round() / 10000.0,
                interplanar_deg: inter_deg,
                ring1: rc.map(|r| r.len()).unwrap_or(0),
                ring2: rw.map(|r| r.len()).unwrap_or(0),
            },
        ));
    }

    items.sort_by(|a, b| {
        a.0.cmp(&b.0)
            .then_with(|| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
    });
    let torsions: Vec<TorsionBond> = items.into_iter().map(|x| x.2).collect();

    // Non-covalent intramolecular conformational locks
    let mut short_contacts = Vec::new();
    let n = mol.atoms.len();
    for i in 0..n {
        for j in (i + 1)..n {
            let za = mol.atoms[i].z;
            let zb = mol.atoms[j].z;
            let pair = (za.min(zb), za.max(zb));
            let spec: Option<(&str, f64)> = match pair {
                (8, 16) => Some(("S···O", 3.00)),
                (9, 16) => Some(("S···F", 3.10)),
                (7, 16) => Some(("S···N", 3.10)),
                (1, 9) => Some(("F···H", 2.60)),
                (1, 8) => Some(("O···H", 2.60)),
                (1, 17) => Some(("Cl···H", 2.85)),
                (1, 7) => Some(("N···H", 2.60)),
                _ => None,
            };
            if let Some((kind, thresh)) = spec {
                let d = dist3(mol.atoms[i].pos, mol.atoms[j].pos);
                if d < thresh && d > 1.2 && graph_distance_at_least(&adj, i, j, 3) {
                    short_contacts.push(ShortContact {
                        kind: kind.to_string(),
                        atoms: [i + 1, j + 1],
                        distance_a: (d * 1000.0).round() / 1000.0,
                        threshold_a: thresh,
                    });
                }
            }
        }
    }

    Ok(TorsionAnalysisResult {
        core_atoms: orient.core_atoms,
        axis_used: orient.axis_used,
        torsions,
        short_contacts,
    })
}

/// Proper 3x3 rigid Kabsch rotation `q * a + t ≈ b` minimizing sum ||R a_k + t - b_k||^2.
fn solve_kabsch(a_pts: &[[f64; 3]], b_pts: &[[f64; 3]]) -> ([[f64; 3]; 3], [f64; 3]) {
    let n = a_pts.len().max(1) as f64;
    let mut ca = [0.0; 3];
    let mut cb = [0.0; 3];
    for (a, b) in a_pts.iter().zip(b_pts.iter()) {
        for k in 0..3 {
            ca[k] += a[k];
            cb[k] += b[k];
        }
    }
    for k in 0..3 {
        ca[k] /= n;
        cb[k] /= n;
    }

    // Covariance matrix H = sum (b_k - cb)(a_k - ca)^T so R = argmin ||R a_c - b_c||^2
    let mut h = [[0.0_f64; 3]; 3];
    for (a, b) in a_pts.iter().zip(b_pts.iter()) {
        let da = [a[0] - ca[0], a[1] - ca[1], a[2] - ca[2]];
        let db = [b[0] - cb[0], b[1] - cb[1], b[2] - cb[2]];
        for r in 0..3 {
            for c in 0..3 {
                h[r][c] += db[r] * da[c];
            }
        }
    }

    // Polar decomposition via H^T H = V Sigma^2 V^T; U = H V Sigma^{-1}; R = U D V^T
    let hth = mat3_mul(mat3_transpose(h), h);
    let (evals, v) = jacobi_3x3_eigen(hth);
    let mut order = [0usize, 1, 2];
    order.sort_by(|&i, &j| evals[j].partial_cmp(&evals[i]).unwrap_or(std::cmp::Ordering::Equal));

    let v_sorted = [
        [v[0][order[0]], v[0][order[1]], v[0][order[2]]],
        [v[1][order[0]], v[1][order[1]], v[1][order[2]]],
        [v[2][order[0]], v[2][order[1]], v[2][order[2]]],
    ];
    let svals = [
        evals[order[0]].max(0.0).sqrt(),
        evals[order[1]].max(0.0).sqrt(),
        evals[order[2]].max(0.0).sqrt(),
    ];

    let hv = mat3_mul(h, v_sorted);
    let mut u = [[0.0_f64; 3]; 3];
    for col in 0..2 {
        let inv = if svals[col] > 1e-10 { 1.0 / svals[col] } else { 0.0 };
        let vec = if inv > 0.0 {
            [hv[0][col] * inv, hv[1][col] * inv, hv[2][col] * inv]
        } else if col == 0 {
            [1.0, 0.0, 0.0]
        } else {
            [0.0, 1.0, 0.0]
        };
        let norm_v = normalize(vec);
        u[0][col] = norm_v[0];
        u[1][col] = norm_v[1];
        u[2][col] = norm_v[2];
    }
    // Enforce SO(3): 3rd column of U = u0 x u1, adjusted by det(U0*V^T)
    let u0 = [u[0][0], u[1][0], u[2][0]];
    let mut u1 = [u[0][1], u[1][1], u[2][1]];
    let proj = dot(u0, u1);
    u1 = normalize([u1[0] - proj * u0[0], u1[1] - proj * u0[1], u1[2] - proj * u0[2]]);
    u[0][1] = u1[0];
    u[1][1] = u1[1];
    u[2][1] = u1[2];
    let mut u2 = cross(u0, u1);
    if mat3_det(v_sorted) < 0.0 {
        u2 = [-u2[0], -u2[1], -u2[2]];
    }
    u[0][2] = u2[0];
    u[1][2] = u2[1];
    u[2][2] = u2[2];

    // Check chirality against direct H columns when third singular value is nonzero
    if svals[2] > 1e-8 {
        let hv2 = [hv[0][2], hv[1][2], hv[2][2]];
        if dot(hv2, u2) < 0.0 && mat3_det(v_sorted) * mat3_det(u) < 0.0 {
            u[0][2] = -u2[0];
            u[1][2] = -u2[1];
            u[2][2] = -u2[2];
        }
    }
    let mut rot = mat3_mul(u, mat3_transpose(v_sorted));
    if mat3_det(rot) < 0.0 {
        // Flip smallest singular vector column
        u[0][2] = -u[0][2];
        u[1][2] = -u[1][2];
        u[2][2] = -u[2][2];
        rot = mat3_mul(u, mat3_transpose(v_sorted));
    }

    let rca = mat3_vec(rot, ca);
    let trans = [cb[0] - rca[0], cb[1] - rca[1], cb[2] - rca[2]];
    (rot, trans)
}

fn trimmed_kabsch(pairs: &[(usize, usize)], ref_mol: &Molecule, tgt_mol: &Molecule) -> ([[f64; 3]; 3], [f64; 3], f64, f64, usize) {
    let m = pairs.len();
    let nkeep = (m as f64 * ALIGN_KEEP_FRAC).round().max(6.0).min(m as f64) as usize;
    let mut keep = vec![true; m];
    let mut rot = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
    let mut trans = [0.0; 3];
    let mut res = vec![0.0; m];

    for _ in 0..20 {
        let mut a_sub = Vec::with_capacity(nkeep);
        let mut b_sub = Vec::with_capacity(nkeep);
        for (idx, &(ri, ti)) in pairs.iter().enumerate() {
            if keep[idx] {
                a_sub.push(tgt_mol.atoms[ti].pos);
                b_sub.push(ref_mol.atoms[ri].pos);
            }
        }
        let (r_new, t_new) = solve_kabsch(&a_sub, &b_sub);
        rot = r_new;
        trans = t_new;
        for (idx, &(ri, ti)) in pairs.iter().enumerate() {
            let rp = mat3_vec(rot, tgt_mol.atoms[ti].pos);
            let p_aligned = [rp[0] + trans[0], rp[1] + trans[1], rp[2] + trans[2]];
            res[idx] = dist3(p_aligned, ref_mol.atoms[ri].pos);
        }
        if nkeep >= m {
            break;
        }
        let mut order: Vec<usize> = (0..m).collect();
        order.sort_by(|&i, &j| res[i].partial_cmp(&res[j]).unwrap_or(std::cmp::Ordering::Equal));
        let mut next_keep = vec![false; m];
        for &k in order.iter().take(nkeep) {
            next_keep[k] = true;
        }
        if next_keep == keep {
            break;
        }
        keep = next_keep;
    }

    let mut sq_sum = 0.0;
    let mut cnt = 0usize;
    let mut max_res = 0.0_f64;
    for (idx, &d) in res.iter().enumerate() {
        if keep[idx] {
            sq_sum += d * d;
            cnt += 1;
            max_res = max_res.max(d);
        }
    }
    let rmsd = if cnt > 0 { (sq_sum / cnt as f64).sqrt() } else { 0.0 };
    (rot, trans, rmsd, max_res, cnt)
}

#[inline]
fn elements_compatible(z1: u8, z2: u8, allow_halogen_swap: bool) -> bool {
    if z1 == z2 {
        return true;
    }
    if allow_halogen_swap {
        let is_hal = |z: u8| matches!(z, 9 | 17 | 35);
        return is_hal(z1) && is_hal(z2);
    }
    false
}

fn core_subgraph_mcs(
    ref_mol: &Molecule,
    ref_core: &[usize],
    ref_adj: &[Vec<usize>],
    tgt_mol: &Molecule,
    tgt_core: &[usize],
    tgt_adj: &[Vec<usize>],
    allow_halogen_swap: bool,
) -> Vec<(usize, usize)> {
    let nr = ref_core.len();
    let nt = tgt_core.len();
    if nr < 4 || nt < 4 {
        return Vec::new();
    }
    let r_pos: HashMap<usize, usize> = ref_core.iter().enumerate().map(|(i, &a)| (a, i)).collect();
    let t_pos: HashMap<usize, usize> = tgt_core.iter().enumerate().map(|(i, &a)| (a, i)).collect();

    let mut r_sub_adj = vec![vec![false; nr]; nr];
    let mut r_deg = vec![0usize; nr];
    for (ui, &a) in ref_core.iter().enumerate() {
        for &nb in &ref_adj[a] {
            if let Some(&vi) = r_pos.get(&nb) {
                r_sub_adj[ui][vi] = true;
                r_deg[ui] += 1;
            }
        }
    }
    let mut t_sub_adj = vec![vec![false; nt]; nt];
    let mut t_deg = vec![0usize; nt];
    for (ui, &a) in tgt_core.iter().enumerate() {
        for &nb in &tgt_adj[a] {
            if let Some(&vi) = t_pos.get(&nb) {
                t_sub_adj[ui][vi] = true;
                t_deg[ui] += 1;
            }
        }
    }

    // Order ref core vertices by descending degree (hub-first BFS order improves pruning)
    let mut r_order: Vec<usize> = (0..nr).collect();
    r_order.sort_by(|&a, &b| r_deg[b].cmp(&r_deg[a]).then_with(|| a.cmp(&b)));

    struct SearchState<'a> {
        nr: usize,
        nt: usize,
        r_order: &'a [usize],
        r_sub_adj: &'a [Vec<bool>],
        t_sub_adj: &'a [Vec<bool>],
        ref_mol: &'a Molecule,
        tgt_mol: &'a Molecule,
        ref_core: &'a [usize],
        tgt_core: &'a [usize],
        r_deg: &'a [usize],
        t_deg: &'a [usize],
        allow_halogen_swap: bool,
        best: Vec<(usize, usize)>,
        steps: usize,
    }

    fn dfs(
        pos: usize,
        cur: &mut Vec<(usize, usize)>,
        used_t: &mut Vec<bool>,
        st: &mut SearchState<'_>,
    ) {
        if st.steps >= 50_000 || cur.len() + (st.nr - pos) <= st.best.len() {
            return;
        }
        st.steps += 1;
        if pos == st.nr {
            if cur.len() > st.best.len() {
                st.best = cur.clone();
            }
            return;
        }
        let ru = st.r_order[pos];
        let rz = st.ref_mol.atoms[st.ref_core[ru]].z;

        // Collect feasible target candidates connected consistently with already mapped vertices
        let mut cands = Vec::new();
        for tu in 0..st.nt {
            if used_t[tu] {
                continue;
            }
            let tz = st.tgt_mol.atoms[st.tgt_core[tu]].z;
            if !elements_compatible(rz, tz, st.allow_halogen_swap) {
                continue;
            }
            let mut consistent = true;
            let mut connected_matches = 0usize;
            for &(mr, mt) in cur.iter() {
                if st.r_sub_adj[ru][mr] != st.t_sub_adj[tu][mt] {
                    consistent = false;
                    break;
                }
                if st.r_sub_adj[ru][mr] {
                    connected_matches += 1;
                }
            }
            if consistent && (cur.is_empty() || connected_matches > 0) {
                let deg_diff = st.r_deg[ru].abs_diff(st.t_deg[tu]);
                cands.push((std::cmp::Reverse(connected_matches), deg_diff, tu));
            }
        }
        cands.sort_unstable();

        for (_, _, tu) in cands {
            used_t[tu] = true;
            cur.push((ru, tu));
            dfs(pos + 1, cur, used_t, st);
            cur.pop();
            used_t[tu] = false;
            if st.best.len() == st.nr || st.steps >= 50_000 {
                return;
            }
        }
        // Branch where ru is skipped (only if upper bound still beats best)
        if cur.len() + (st.nr - pos - 1) > st.best.len() {
            dfs(pos + 1, cur, used_t, st);
        }
    }

    let mut st = SearchState {
        nr,
        nt,
        r_order: &r_order,
        r_sub_adj: &r_sub_adj,
        t_sub_adj: &t_sub_adj,
        ref_mol,
        tgt_mol,
        ref_core,
        tgt_core,
        r_deg: &r_deg,
        t_deg: &t_deg,
        allow_halogen_swap,
        best: Vec::new(),
        steps: 0,
    };
    let mut cur = Vec::with_capacity(nr);
    let mut used_t = vec![false; nt];
    dfs(0, &mut cur, &mut used_t, &mut st);
    if cur.len() > st.best.len() {
        st.best = cur;
    }

    st.best
        .into_iter()
        .map(|(ru, tu)| (ref_core[ru], tgt_core[tu]))
        .collect()
}

/// Module 1B: Multi-Molecule Rigid Alignment (`target -> ref` frame) via direct fast-path
/// followed by order-independent MCS subgraph matching + robust trimmed Kabsch.
pub fn align_molecule_to_reference(
    ref_mol: &Molecule,
    tgt_mol: &Molecule,
    allow_halogen_swap: bool,
) -> Result<AlignmentResult> {
    if ref_mol.atoms.len() < 3 || tgt_mol.atoms.len() < 3 {
        return Err(CoreError::InvalidOp("刚体对齐至少需要 3 个原子".into()));
    }
    let (ref_adj, ref_edges) = build_covalent_graph(ref_mol);
    let ref_rings = perceive_rings(&ref_adj, &ref_edges);
    let ref_core_set = largest_fused_component(ref_mol, &ref_rings);
    let mut ref_core: Vec<usize> = ref_core_set
        .iter()
        .copied()
        .filter(|&i| ref_mol.atoms[i].z > 1)
        .collect();
    if ref_core.len() < 6 {
        ref_core = (0..ref_mol.atoms.len())
            .filter(|&i| ref_mol.atoms[i].z > 1)
            .collect();
    }
    ref_core.sort_unstable();

    let (tgt_adj, tgt_edges) = build_covalent_graph(tgt_mol);
    let tgt_rings = perceive_rings(&tgt_adj, &tgt_edges);
    let tgt_core_set = largest_fused_component(tgt_mol, &tgt_rings);
    let mut tgt_core: Vec<usize> = tgt_core_set
        .iter()
        .copied()
        .filter(|&i| tgt_mol.atoms[i].z > 1)
        .collect();
    if tgt_core.len() < 6 {
        tgt_core = (0..tgt_mol.atoms.len())
            .filter(|&i| tgt_mol.atoms[i].z > 1)
            .collect();
    }
    tgt_core.sort_unstable();

    // Fast path: identical atom counts & compatible element indexing on core
    let mut chosen_pairs: Option<(Vec<(usize, usize)>, &str)> = None;
    if ref_mol.atoms.len() == tgt_mol.atoms.len() && ref_core.len() >= 6 {
        let same_elem = ref_core
            .iter()
            .all(|&i| elements_compatible(ref_mol.atoms[i].z, tgt_mol.atoms[i].z, allow_halogen_swap));
        if same_elem {
            let direct: Vec<(usize, usize)> = ref_core.iter().map(|&i| (i, i)).collect();
            let (_, _, rmsd, _, _) = trimmed_kabsch(&direct, ref_mol, tgt_mol);
            if rmsd <= ALIGN_DIRECT_RMSD_OK {
                chosen_pairs = Some((direct, "direct_kabsch"));
            }
        }
    }

    let (pairs, method) = match chosen_pairs {
        Some(v) => v,
        None => {
            let mcs_pairs = core_subgraph_mcs(
                ref_mol,
                &ref_core,
                &ref_adj,
                tgt_mol,
                &tgt_core,
                &tgt_adj,
                allow_halogen_swap,
            );
            if mcs_pairs.len() < 4 {
                return Err(CoreError::InvalidOp(format!(
                    "核心最大公共子结构匹配原子不足 4 个 (仅匹配 {} 个)",
                    mcs_pairs.len()
                )));
            }
            (mcs_pairs, "mcs_kabsch")
        }
    };

    let (rot, trans, rmsd, max_res, used_count) = trimmed_kabsch(&pairs, ref_mol, tgt_mol);
    let aligned_positions: Vec<[f64; 3]> = tgt_mol
        .atoms
        .iter()
        .map(|a| {
            let rp = mat3_vec(rot, a.pos);
            [rp[0] + trans[0], rp[1] + trans[1], rp[2] + trans[2]]
        })
        .collect();

    Ok(AlignmentResult {
        method: method.to_string(),
        matched_count: pairs.len(),
        used_core_count: used_count,
        rmsd_angstrom: (rmsd * 100000.0).round() / 100000.0,
        max_residual_angstrom: (max_res * 100000.0).round() / 100000.0,
        rotation_3x3: rot,
        translation: trans,
        aligned_positions,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presets::build_preset;

    fn make_rotated_shifted_mol(src: &Molecule, deg_z: f64, deg_x: f64, shift: [f64; 3], reverse_order: bool) -> Molecule {
        let cz = deg_z.to_radians().cos();
        let sz = deg_z.to_radians().sin();
        let cx = deg_x.to_radians().cos();
        let sx = deg_x.to_radians().sin();
        let mut out = Molecule::new(&format!("{}_rot", src.name));
        let mut idxs: Vec<usize> = (0..src.atoms.len()).collect();
        if reverse_order {
            idxs.reverse();
        }
        for i in idxs {
            let p = src.atoms[i].pos;
            let p1 = [cz * p[0] - sz * p[1], sz * p[0] + cz * p[1], p[2]];
            let p2 = [
                p1[0] + shift[0],
                cx * p1[1] - sx * p1[2] + shift[1],
                sx * p1[1] + cx * p1[2] + shift[2],
            ];
            let a = out.alloc_atom(src.atoms[i].z, p2, [p2[0], p2[1]]);
            out.atoms.push(a);
        }
        out.reindex();
        out.has_3d = true;
        out
    }

    #[test]
    fn core_first_and_torsions_biphenyl_and_locks() {
        // Naphthalene fused core + twisted phenyl wing (~42 deg dihedral) + F···H close contact
        let mut mol = Molecule::new("NaphthylPhenylTest");
        // 10-atom naphthalene core in XY plane
        let nap_coords = [
            [-1.21, 0.70, 0.0], // 0
            [0.00, 1.40, 0.0],  // 1
            [1.21, 0.70, 0.0],  // 2
            [1.21, -0.70, 0.0], // 3
            [0.00, -1.40, 0.0], // 4
            [-1.21, -0.70, 0.0],// 5
            [2.42, 1.40, 0.0],  // 6
            [3.63, 0.70, 0.0],  // 7
            [3.63, -0.70, 0.0], // 8
            [2.42, -1.40, 0.0], // 9
        ];
        for p in nap_coords {
            let a = mol.alloc_atom(6, p, [p[0], p[1]]);
            mol.atoms.push(a);
        }
        // Attach phenyl ring at atom 7 (3.63, 0.70, 0) rotated 42 deg around bond along +X
        let theta = 42.0_f64.to_radians();
        let bx = 5.10;
        let ph_local = [
            [bx, 0.70, 0.0],                                      // 10 ipso C
            [bx + 0.70, 0.70 + 1.21 * theta.cos(), 1.21 * theta.sin()],   // 11
            [bx + 2.10, 0.70 + 1.21 * theta.cos(), 1.21 * theta.sin()],   // 12
            [bx + 2.80, 0.70, 0.0],                               // 13 para
            [bx + 2.10, 0.70 - 1.21 * theta.cos(), -1.21 * theta.sin()],  // 14
            [bx + 0.70, 0.70 - 1.21 * theta.cos(), -1.21 * theta.sin()],  // 15
        ];
        for p in ph_local {
            let a = mol.alloc_atom(6, p, [p[0], p[1]]);
            mol.atoms.push(a);
        }
        // Add F on atom 6 and H on atom 11 within 2.35 Å (F···H lock)
        let f_atom = mol.alloc_atom(9, [2.42, 2.74, 0.0], [2.42, 2.74]);
        let h_atom = mol.alloc_atom(1, [4.60, 2.35, 0.85], [4.60, 2.35]);
        mol.atoms.push(f_atom); // 16
        mol.atoms.push(h_atom); // 17
        mol.reindex();

        let tor = compute_torsions(&mol).expect("torsion analysis");
        assert_eq!(tor.core_atoms.len(), 10, "largest fused component should be 10-atom naphthalene");
        assert_eq!(tor.axis_used, "core");
        let cw = tor.torsions.iter().find(|t| t.bond_type == "core-wing").expect("core-wing bond");
        assert!(cw.angle.abs() <= 90.0, "must choose acute path, got {}", cw.angle);
        assert!((cw.angle.abs() - 42.0).abs() < 3.5, "expected ~42 deg, got {}", cw.angle);
        assert!((cw.bond_length_a - 1.47).abs() < 0.05);
        assert!(cw.interplanar_deg.unwrap_or(0.0) > 35.0);
        assert!(
            tor.short_contacts.iter().any(|c| c.kind == "F···H" && c.distance_a < 2.6),
            "expected F···H conformational lock"
        );
    }

    #[test]
    fn mcs_kabsch_scrambled_atom_order_sub_001_rmsd() {
        let caffeine = build_preset("caffeine").expect("caffeine preset");
        let orient = compute_core_first_orientation(&caffeine).expect("caffeine orientation");
        assert!(orient.core_atoms.len() >= 9);

        // Reverse atom ordering + arbitrary 3D rotation + translation
        let scrambled = make_rotated_shifted_mol(&caffeine, 127.0, -43.0, [14.2, -8.7, 5.3], true);
        let res = align_molecule_to_reference(&caffeine, &scrambled, true).expect("MCS alignment");
        assert_eq!(res.method, "mcs_kabsch");
        assert!(res.matched_count >= 9, "matched {}", res.matched_count);
        assert!(
            res.rmsd_angstrom < 0.01,
            "expected < 0.01 A RMSD on scrambled copy, got {}",
            res.rmsd_angstrom
        );
    }
}
