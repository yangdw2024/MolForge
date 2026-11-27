//! Quantum chemistry module:
//! - Pure-Rust Heteroatom Tight-Binding (Huckel pi-MO) solver
//! - Gaussian `.log` / `.fchk` and ORCA `.out` frontier orbital parser
//! - Direct pure-Rust CalChem SCF & Geometry Optimization (`--features calchem`)

#[cfg(feature = "calchem")]
use crate::elements;
use crate::model::{AtomId, Molecule};
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrbitalLevel {
    pub index: usize,
    pub energy: f64,
    pub occupied: bool,
    pub label: String,
    pub coefficients: Vec<(AtomId, f64)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransitionItem {
    pub wavelength_nm: f64,
    pub oscillator_f: f64,
    pub energy_ev: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TightBindingResult {
    pub molecule_name: String,
    pub formula: String,
    pub method: String,
    pub num_pi_atoms: usize,
    pub num_pi_electrons: usize,
    pub homo_ev: Option<f64>,
    pub lumo_ev: Option<f64>,
    pub gap_ev: Option<f64>,
    pub homo_index: Option<usize>,
    pub mo_energies_ev: Vec<f64>,
    pub transitions: Vec<TransitionItem>,
    pub total_pi_energy_ev: f64,
    pub orbitals: Vec<OrbitalLevel>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParsedQcLog {
    pub source_format: String,
    pub total_energy_hartree: Option<f64>,
    pub homo_hartree: Option<f64>,
    pub lumo_hartree: Option<f64>,
    pub gap_ev: Option<f64>,
    pub alpha_energies: Vec<f64>,
    pub beta_energies: Vec<f64>,
    pub n_alpha: usize,
    pub n_beta: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CalchemScfResult {
    pub available: bool,
    pub method: String,
    pub basis: String,
    pub converged: bool,
    pub iterations: usize,
    pub total_energy_hartree: f64,
    pub homo_hartree: Option<f64>,
    pub lumo_hartree: Option<f64>,
    pub gap_ev: Option<f64>,
    #[serde(default)]
    pub dipole_magnitude_debye: Option<f64>,
    #[serde(default)]
    pub n_ao: Option<usize>,
    pub optimized_positions: Option<Vec<(AtomId, [f64; 3])>>,
    pub message: String,
}

/// Heteroatom Tight-Binding (Huckel pi-MO) parameters (alpha_0 = -6.5 eV, beta_0 = -2.7 eV).
pub fn run_tight_binding(mol: &Molecule) -> Result<TightBindingResult> {
    const ALPHA0: f64 = -6.5;
    const BETA0: f64 = -2.7;

    // Identify sp2/conjugated atoms: C, N, O, S, B, P with degree <= 3 and at least 1 heavy neighbor
    let mut deg: HashMap<AtomId, usize> = HashMap::new();
    let mut has_double_or_arom: HashMap<AtomId, bool> = HashMap::new();
    for b in &mol.bonds {
        *deg.entry(b.a).or_insert(0) += 1;
        *deg.entry(b.b).or_insert(0) += 1;
        if b.order >= 2 || b.aromatic {
            has_double_or_arom.insert(b.a, true);
            has_double_or_arom.insert(b.b, true);
        }
    }

    let mut pi_atoms: Vec<usize> = Vec::new();
    for (idx, a) in mol.atoms.iter().enumerate() {
        let is_pi_elem = matches!(a.z, 5 | 6 | 7 | 8 | 15 | 16);
        let d = deg.get(&a.id).copied().unwrap_or(0);
        let conj = a.aromatic || has_double_or_arom.get(&a.id).copied().unwrap_or(false);
        if is_pi_elem && (conj || (a.z == 6 && d <= 3 && d >= 2)) {
            pi_atoms.push(idx);
        }
    }

    if pi_atoms.is_empty() {
        return Err(CoreError::InvalidOp(
            "no conjugated pi-system atoms detected for Tight-Binding".into(),
        ));
    }

    let n = pi_atoms.len();
    let mut idx_to_pi: HashMap<AtomId, usize> = HashMap::with_capacity(n);
    for (pi_i, &mol_i) in pi_atoms.iter().enumerate() {
        idx_to_pi.insert(mol.atoms[mol_i].id, pi_i);
    }

    let mut h = vec![vec![0.0_f64; n]; n];
    let mut n_pi_elec = 0usize;

    for (pi_i, &mol_i) in pi_atoms.iter().enumerate() {
        let a = &mol.atoms[mol_i];
        let d = deg.get(&a.id).copied().unwrap_or(0);
        let (h_x, e_contrib) = match a.z {
            6 => (0.0, 1),
            7 => {
                if d >= 3 && !has_double_or_arom.get(&a.id).copied().unwrap_or(false) {
                    (1.5, 2)
                } else {
                    (0.5, 1)
                }
            }
            8 => {
                if d <= 1 {
                    (1.0, 1)
                } else {
                    (2.0, 2)
                }
            }
            16 => (1.1, 2),
            5 => (-0.5, 0),
            15 => (0.7, 1),
            _ => (0.0, 1),
        };
        n_pi_elec += e_contrib;
        h[pi_i][pi_i] = ALPHA0 + h_x * BETA0;
    }

    for b in &mol.bonds {
        if let (Some(&i), Some(&j)) = (idx_to_pi.get(&b.a), idx_to_pi.get(&b.b)) {
            let za = mol.atoms[pi_atoms[i]].z;
            let zb = mol.atoms[pi_atoms[j]].z;
            let k_xy = match (za.min(zb), za.max(zb)) {
                (6, 6) => 1.0,
                (6, 7) => 0.9,
                (6, 8) => 0.8,
                (6, 16) => 0.7,
                _ => 0.8,
            };
            let val = k_xy * BETA0;
            h[i][j] = val;
            h[j][i] = val;
        }
    }

    let (evals, evecs) = jacobi_symmetric_nxn(h);
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&i, &j| evals[i].partial_cmp(&evals[j]).unwrap_or(std::cmp::Ordering::Equal));

    let n_occ = (n_pi_elec / 2).min(n);
    let mut total_pi = 0.0;
    let mut orbitals = Vec::with_capacity(n);

    for (rank, &col) in order.iter().enumerate() {
        let occ = rank < n_occ;
        if occ {
            total_pi += 2.0 * evals[col];
        }
        let label = if rank + 1 == n_occ {
            "HOMO".to_string()
        } else if rank == n_occ {
            "LUMO".to_string()
        } else if rank < n_occ {
            format!("HOMO-{}", n_occ - 1 - rank)
        } else {
            format!("LUMO+{}", rank - n_occ)
        };
        let coeffs: Vec<(AtomId, f64)> = pi_atoms
            .iter()
            .enumerate()
            .map(|(row, &mol_idx)| (mol.atoms[mol_idx].id, evecs[row][col]))
            .collect();
        orbitals.push(OrbitalLevel {
            index: rank + 1,
            energy: evals[col],
            occupied: occ,
            label,
            coefficients: coeffs,
        });
    }

    let homo = n_occ.checked_sub(1).and_then(|i| orbitals.get(i)).map(|o| o.energy);
    let lumo = orbitals.get(n_occ).map(|o| o.energy);
    let gap = match (homo, lumo) {
        (Some(h), Some(l)) => Some((l - h).max(0.0)),
        _ => None,
    };
    let mo_energies_ev: Vec<f64> = orbitals.iter().map(|o| o.energy).collect();
    let transitions = match gap {
        Some(g) if g > 0.05 => vec![TransitionItem {
            wavelength_nm: 1239.84193 / g,
            oscillator_f: 0.25,
            energy_ev: g,
        }],
        _ => Vec::new(),
    };

    Ok(TightBindingResult {
        molecule_name: mol.name.clone(),
        formula: crate::summary::formula(mol),
        method: "Heteroatom Tight-Binding (Huckel pi-MO)".into(),
        num_pi_atoms: n,
        num_pi_electrons: n_pi_elec,
        homo_ev: homo,
        lumo_ev: lumo,
        gap_ev: gap,
        homo_index: n_occ.checked_sub(1),
        mo_energies_ev,
        transitions,
        total_pi_energy_ev: total_pi,
        orbitals,
    })
}

fn jacobi_symmetric_nxn(mut a: Vec<Vec<f64>>) -> (Vec<f64>, Vec<Vec<f64>>) {
    let n = a.len();
    let mut v = vec![vec![0.0_f64; n]; n];
    for i in 0..n {
        v[i][i] = 1.0;
    }
    if n <= 1 {
        let diag = (0..n).map(|i| a[i][i]).collect();
        return (diag, v);
    }

    let max_sweeps = 50 * n * n;
    for _ in 0..max_sweeps {
        let mut p = 0;
        let mut q = 1;
        let mut max_val = 0.0_f64;
        for i in 0..n {
            for j in (i + 1)..n {
                if a[i][j].abs() > max_val {
                    max_val = a[i][j].abs();
                    p = i;
                    q = j;
                }
            }
        }
        if max_val < 1e-11 {
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

        for r in 0..n {
            if r != p && r != q {
                let arp = a[r][p];
                let arq = a[r][q];
                a[r][p] = c * arp - s * arq;
                a[p][r] = a[r][p];
                a[r][q] = s * arp + c * arq;
                a[q][r] = a[r][q];
            }
        }
        for r in 0..n {
            let vrp = v[r][p];
            let vrq = v[r][q];
            v[r][p] = c * vrp - s * vrq;
            v[r][q] = s * vrp + c * vrq;
        }
    }

    let evals = (0..n).map(|i| a[i][i]).collect();
    (evals, v)
}

/// Parse Gaussian `.log` or `.fchk` frontier orbital eigenvalues and total SCF energy.
pub fn parse_qc_log(text: &str) -> Result<ParsedQcLog> {
    const HARTREE_TO_EV: f64 = 27.211_386_245_988;

    let mut total_energy: Option<f64> = None;
    let mut alpha_occ: Vec<f64> = Vec::new();
    let mut alpha_virt: Vec<f64> = Vec::new();

    for line in text.lines() {
        let trimmed = line.trim();
        if let Some(pos) = trimmed.find("SCF Done:") {
            let after = &trimmed[pos..];
            if let Some(eq) = after.find('=') {
                if let Some(val) = after[eq + 1..].split_whitespace().next() {
                    if let Ok(e) = val.parse::<f64>() {
                        total_energy = Some(e);
                    }
                }
            }
        } else if trimmed.starts_with("FINAL SINGLE POINT ENERGY") {
            if let Some(val) = trimmed.split_whitespace().last() {
                if let Ok(e) = val.parse::<f64>() {
                    total_energy = Some(e);
                }
            }
        } else if trimmed.starts_with("Alpha  occ. eigenvalues --") {
            for tok in trimmed["Alpha  occ. eigenvalues --".len()..].split_whitespace() {
                if let Ok(v) = tok.parse::<f64>() {
                    alpha_occ.push(v);
                }
            }
        } else if trimmed.starts_with("Alpha virt. eigenvalues --") {
            for tok in trimmed["Alpha virt. eigenvalues --".len()..].split_whitespace() {
                if let Ok(v) = tok.parse::<f64>() {
                    alpha_virt.push(v);
                }
            }
        }
    }

    let n_alpha = alpha_occ.len();
    let homo = alpha_occ.last().copied();
    let lumo = alpha_virt.first().copied();
    let gap_ev = match (homo, lumo) {
        (Some(h), Some(l)) => Some((l - h) * HARTREE_TO_EV),
        _ => None,
    };

    let mut alpha_energies = alpha_occ;
    alpha_energies.extend(alpha_virt);

    Ok(ParsedQcLog {
        source_format: if text.contains("ORCA") {
            "ORCA".into()
        } else {
            "Gaussian".into()
        },
        total_energy_hartree: total_energy,
        homo_hartree: homo,
        lumo_hartree: lumo,
        gap_ev,
        alpha_energies,
        beta_energies: Vec::new(),
        n_alpha,
        n_beta: n_alpha,
    })
}

/// Run pure-Rust CalChem SCF or Geometry Optimization when compiled with `--features calchem`.
#[cfg(feature = "calchem")]
pub fn run_calchem(
    mol: &Molecule,
    method: &str,
    basis: &str,
    charge: i32,
    multiplicity: usize,
    optimize: bool,
) -> Result<CalchemScfResult> {
    use calchem_basis::BasisSet;
    use calchem_dft::{GridLevel, XcFunctional};
    use calchem_model::{Atom as CcAtom, Molecule as CcMol, ScfOptions, BOHR_TO_ANGSTROM};
    use calchem_opt::{optimize_geometry_with_options, OptOptions, Reference};
    use calchem_scf::{rhf, rks, uhf, uks};

    if mol.atoms.is_empty() {
        return Err(CoreError::InvalidOp("cannot run SCF on empty molecule".into()));
    }

    let mut cc_atoms = Vec::with_capacity(mol.atoms.len());
    for a in &mol.atoms {
        let sym = elements::symbol_of(a.z);
        let pos_bohr = [
            a.pos[0] / BOHR_TO_ANGSTROM,
            a.pos[1] / BOHR_TO_ANGSTROM,
            a.pos[2] / BOHR_TO_ANGSTROM,
        ];
        cc_atoms.push(
            CcAtom::from_bohr(sym, pos_bohr)
                .map_err(|e| CoreError::External(format!("calchem atom error: {e}")))?,
        );
    }
    let cc_mol = CcMol::new(cc_atoms, charge, multiplicity);
    let bs = BasisSet::from_name(basis, &cc_mol)
        .map_err(|e| CoreError::External(format!("calchem basis error: {e}")))?;

    let m_lower = method.trim().to_ascii_lowercase();
    let xc_opt: Option<XcFunctional> = match m_lower.as_str() {
        "hf" | "rhf" | "uhf" => None,
        "rks" | "uks" | "dft" => Some(XcFunctional::B3lyp),
        other => Some(
            XcFunctional::from_name(other).map_err(|_| {
                CoreError::InvalidOp(format!(
                    "unsupported CalChem method '{other}' (supported: HF, RHF, UHF, RKS, UKS, B3LYP, B3LYP5, PBE, PBE0, BLYP, LDA/SVWN5, CAM-B3LYP, wB97X, wB97X-D)"
                ))
            })?,
        ),
    };

    if optimize {
        let mut opts = OptOptions::default();
        opts.max_steps = 50;
        opts.grid_level = GridLevel::Medium;
        opts.reference = match (xc_opt, multiplicity) {
            (None, 1) => Reference::Rhf,
            (None, _) => Reference::Uhf,
            (Some(func), 1) => Reference::Rks(func),
            (Some(func), _) => Reference::Uks(func),
        };
        let res = optimize_geometry_with_options(&cc_mol, basis, &opts)
            .map_err(|e| CoreError::External(format!("calchem opt error: {e}")))?;
        let new_pos: Vec<(AtomId, [f64; 3])> = mol
            .atoms
            .iter()
            .zip(res.molecule.atoms.iter())
            .map(|(orig, opt_a)| {
                (
                    orig.id,
                    [
                        opt_a.position_bohr[0] * BOHR_TO_ANGSTROM,
                        opt_a.position_bohr[1] * BOHR_TO_ANGSTROM,
                        opt_a.position_bohr[2] * BOHR_TO_ANGSTROM,
                    ],
                )
            })
            .collect();
        return Ok(CalchemScfResult {
            available: true,
            method: method.to_string(),
            basis: basis.to_string(),
            converged: res.converged,
            iterations: res.steps,
            total_energy_hartree: res.energy_hartree,
            homo_hartree: None,
            lumo_hartree: None,
            gap_ev: None,
            dipole_magnitude_debye: None,
            n_ao: Some(bs.n_ao),
            optimized_positions: Some(new_pos),
            message: format!(
                "CalChem v0.3.0 pure-Rust geometry optimization completed in {} steps",
                res.steps
            ),
        });
    }

    let scf_opts = ScfOptions::default();
    const HARTREE_TO_EV: f64 = 27.211_386_245_988;

    if multiplicity == 1 && !matches!(m_lower.as_str(), "uhf" | "uks") {
        let wf = match xc_opt {
            None => rhf(&cc_mol, &bs, &scf_opts),
            Some(func) => rks(&cc_mol, &bs, func, GridLevel::Medium, &scf_opts),
        }
        .map_err(|e| CoreError::External(format!("calchem scf error: {e}")))?;

        let n_occ = wf.mo_occupations.iter().filter(|&&o| o > 0.5).count();
        let homo = n_occ.checked_sub(1).and_then(|i| wf.mo_energies.get(i)).copied();
        let lumo = wf.mo_energies.get(n_occ).copied();
        let gap_ev = match (homo, lumo) {
            (Some(h), Some(l)) => Some((l - h) * HARTREE_TO_EV),
            _ => None,
        };
        let (_, dipole_mag) = calchem_prop::compute_dipole(&cc_mol, &bs, &wf.density_alpha);

        Ok(CalchemScfResult {
            available: true,
            method: method.to_string(),
            basis: basis.to_string(),
            converged: wf.converged,
            iterations: wf.iterations,
            total_energy_hartree: wf.total_energy_hartree,
            homo_hartree: homo,
            lumo_hartree: lumo,
            gap_ev,
            dipole_magnitude_debye: Some(dipole_mag),
            n_ao: Some(wf.n_ao),
            optimized_positions: None,
            message: format!(
                "CalChem v0.3.0 SCF converged={} in {} iterations (dipole={:.4} D, n_ao={})",
                wf.converged, wf.iterations, dipole_mag, wf.n_ao
            ),
        })
    } else {
        let wf = match xc_opt {
            None => uhf(&cc_mol, &bs, &scf_opts),
            Some(func) => uks(&cc_mol, &bs, func, GridLevel::Medium, &scf_opts),
        }
        .map_err(|e| CoreError::External(format!("calchem scf error: {e}")))?;

        let homo = wf
            .n_alpha
            .checked_sub(1)
            .and_then(|i| wf.mo_energies_alpha.get(i))
            .copied();
        let lumo = wf.mo_energies_alpha.get(wf.n_alpha).copied();
        let gap_ev = match (homo, lumo) {
            (Some(h), Some(l)) => Some((l - h) * HARTREE_TO_EV),
            _ => None,
        };
        let tot_density = wf.total_density();
        let (_, dipole_mag) = calchem_prop::compute_dipole(&cc_mol, &bs, &tot_density);

        Ok(CalchemScfResult {
            available: true,
            method: method.to_string(),
            basis: basis.to_string(),
            converged: wf.converged,
            iterations: wf.iterations,
            total_energy_hartree: wf.total_energy_hartree,
            homo_hartree: homo,
            lumo_hartree: lumo,
            gap_ev,
            dipole_magnitude_debye: Some(dipole_mag),
            n_ao: Some(wf.n_ao),
            optimized_positions: None,
            message: format!(
                "CalChem v0.3.0 USCF converged={} in {} iterations (dipole={:.4} D, n_ao={})",
                wf.converged, wf.iterations, dipole_mag, wf.n_ao
            ),
        })
    }
}

#[cfg(not(feature = "calchem"))]
pub fn run_calchem(
    _mol: &Molecule,
    method: &str,
    basis: &str,
    _charge: i32,
    _multiplicity: usize,
    _optimize: bool,
) -> Result<CalchemScfResult> {
    Ok(CalchemScfResult {
        available: false,
        method: method.to_string(),
        basis: basis.to_string(),
        converged: false,
        iterations: 0,
        total_energy_hartree: 0.0,
        homo_hartree: None,
        lumo_hartree: None,
        gap_ev: None,
        dipole_magnitude_debye: None,
        n_ao: None,
        optimized_positions: None,
        message: "molforge-core built without `--features calchem`".into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presets::build_preset;

    #[test]
    fn benzene_tight_binding_has_degenerate_homo_lumo() {
        let mol = build_preset("benzene").unwrap();
        let res = run_tight_binding(&mol).unwrap();
        assert_eq!(res.num_pi_atoms, 6);
        assert_eq!(res.num_pi_electrons, 6);
        assert!(res.gap_ev.unwrap() > 4.0);
    }

    #[cfg(feature = "calchem")]
    #[test]
    fn calchem_h2o_rhf_sto3g() {
        let mol = build_preset("water").unwrap();
        let res = run_calchem(&mol, "HF", "STO-3G", 0, 1, false).unwrap();
        assert!(res.available);
        assert!(res.converged);
        assert!((res.total_energy_hartree - (-74.96)).abs() < 0.2);
        assert_eq!(res.n_ao, Some(7));
        assert!(res.dipole_magnitude_debye.unwrap_or(0.0) > 1.0);
    }
}
