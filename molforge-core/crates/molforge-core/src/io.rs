//! Native file IO for XYZ, PDB (including CRYST1 & CONECT), V2000 MOL,
//! QC input files (GJF, ORCA, REST), and `.mforge` v1.1 ZIP archives.

use crate::elements;
use crate::model::{Cell, Molecule};
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{Cursor, Read, Write};
use zip::write::SimpleFileOptions;
use zip::{ZipArchive, ZipWriter};

/// Fast O(N) spatial-hash bond perception using covalent radii.
pub fn infer_bonds_spatial(mol: &mut Molecule) {
    if mol.atoms.len() < 2 {
        return;
    }
    const CELL_SIZE: f64 = 2.8;
    let mut grid: HashMap<(i32, i32, i32), Vec<usize>> = HashMap::with_capacity(mol.atoms.len());
    for (idx, a) in mol.atoms.iter().enumerate() {
        let key = (
            (a.pos[0] / CELL_SIZE).floor() as i32,
            (a.pos[1] / CELL_SIZE).floor() as i32,
            (a.pos[2] / CELL_SIZE).floor() as i32,
        );
        grid.entry(key).or_default().push(idx);
    }

    let mut pairs: Vec<(usize, usize)> = Vec::new();
    for (idx, a) in mol.atoms.iter().enumerate() {
        let gx = (a.pos[0] / CELL_SIZE).floor() as i32;
        let gy = (a.pos[1] / CELL_SIZE).floor() as i32;
        let gz = (a.pos[2] / CELL_SIZE).floor() as i32;
        let r_a = elements::covalent(a.z);

        for dx in -1..=1 {
            for dy in -1..=1 {
                for dz in -1..=1 {
                    if let Some(bucket) = grid.get(&(gx + dx, gy + dy, gz + dz)) {
                        for &jdx in bucket {
                            if jdx <= idx {
                                continue;
                            }
                            let b = &mol.atoms[jdx];
                            // Skip H-H bonds unless both are H in H2
                            if a.z == 1 && b.z == 1 && mol.atoms.len() > 2 {
                                continue;
                            }
                            let cutoff = (r_a + elements::covalent(b.z)) * 1.22;
                            let ddx = a.pos[0] - b.pos[0];
                            let ddy = a.pos[1] - b.pos[1];
                            let ddz = a.pos[2] - b.pos[2];
                            let d2 = ddx * ddx + ddy * ddy + ddz * ddz;
                            if d2 > 0.16 && d2 <= cutoff * cutoff {
                                pairs.push((idx, jdx));
                            }
                        }
                    }
                }
            }
        }
    }

    for (ia, ib) in pairs {
        let aid = mol.atoms[ia].id;
        let bid = mol.atoms[ib].id;
        let bond = mol.alloc_bond(aid, bid, 1, false);
        mol.bonds.push(bond);
    }
}

pub fn parse_xyz(text: &str, name: &str) -> Result<Molecule> {
    let mut lines = text.lines();
    let count_line = lines
        .next()
        .ok_or_else(|| CoreError::Parse("empty XYZ file".into()))?;
    let n: usize = count_line
        .trim()
        .parse()
        .map_err(|_| CoreError::Parse(format!("invalid XYZ atom count: {count_line}")))?;
    let comment = lines.next().unwrap_or("").trim();

    let mut mol = Molecule::new(if name.is_empty() && !comment.is_empty() {
        comment
    } else if name.is_empty() {
        "XYZ Molecule"
    } else {
        name
    });

    for line in lines.take(n) {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() < 4 {
            continue;
        }
        let z = if let Ok(num) = parts[0].parse::<u8>() {
            num
        } else {
            elements::by_symbol(parts[0])
                .map(|e| e.z)
                .ok_or_else(|| CoreError::UnknownElement(parts[0].to_string()))?
        };
        let x: f64 = parts[1]
            .parse()
            .map_err(|_| CoreError::Parse(format!("invalid x: {}", parts[1])))?;
        let y: f64 = parts[2]
            .parse()
            .map_err(|_| CoreError::Parse(format!("invalid y: {}", parts[2])))?;
        let zc: f64 = parts[3]
            .parse()
            .map_err(|_| CoreError::Parse(format!("invalid z: {}", parts[3])))?;
        let atom = mol.alloc_atom(z, [x, y, zc], [x, y]);
        mol.atoms.push(atom);
    }
    mol.reindex();
    mol.has_3d = true;
    if mol.atoms.len() <= 50_000 {
        infer_bonds_spatial(&mut mol);
    }
    Ok(mol)
}

pub fn write_xyz(mol: &Molecule) -> String {
    let mut out = String::with_capacity(mol.atoms.len() * 48 + 64);
    out.push_str(&format!("{}\n{}\n", mol.atoms.len(), mol.name));
    for a in &mol.atoms {
        out.push_str(&format!(
            "{:<3} {:>12.6} {:>12.6} {:>12.6}\n",
            elements::symbol_of(a.z),
            a.pos[0],
            a.pos[1],
            a.pos[2]
        ));
    }
    out
}

pub fn parse_pdb(text: &str, name: &str) -> Result<Molecule> {
    let mut mol = Molecule::new(if name.is_empty() { "PDB Structure" } else { name });
    let mut serial_to_id: HashMap<u32, u32> = HashMap::new();
    let mut conect_pairs: Vec<(u32, u32)> = Vec::new();

    for line in text.lines() {
        if line.starts_with("CRYST1") && line.len() >= 54 {
            let a = line[6..15].trim().parse::<f64>().ok();
            let b = line[15..24].trim().parse::<f64>().ok();
            let c = line[24..33].trim().parse::<f64>().ok();
            let alpha = line[33..40].trim().parse::<f64>().ok();
            let beta = line[40..47].trim().parse::<f64>().ok();
            let gamma = line[47..54].trim().parse::<f64>().ok();
            if let (Some(a), Some(b), Some(c), Some(alpha), Some(beta), Some(gamma)) =
                (a, b, c, alpha, beta, gamma)
            {
                let sg = if line.len() >= 66 {
                    line[55..66].trim().to_string()
                } else {
                    "P 1".to_string()
                };
                let cell = Cell {
                    a,
                    b,
                    c,
                    alpha,
                    beta,
                    gamma,
                    space_group: sg,
                };
                if cell.is_valid() {
                    mol.cell = Some(cell);
                }
            }
        } else if (line.starts_with("ATOM  ") || line.starts_with("HETATM")) && line.len() >= 54 {
            let serial: u32 = line[6..11].trim().parse().unwrap_or(0);
            let x: f64 = line[30..38]
                .trim()
                .parse()
                .map_err(|_| CoreError::Parse("invalid PDB x".into()))?;
            let y: f64 = line[38..46]
                .trim()
                .parse()
                .map_err(|_| CoreError::Parse("invalid PDB y".into()))?;
            let zc: f64 = line[46..54]
                .trim()
                .parse()
                .map_err(|_| CoreError::Parse("invalid PDB z".into()))?;

            let elem_raw = if line.len() >= 78 {
                line[76..78].trim()
            } else {
                ""
            };
            let z = if !elem_raw.is_empty() {
                elements::by_symbol(elem_raw).map(|e| e.z).unwrap_or(6)
            } else {
                let aname = line[12..16].trim().trim_start_matches(|c: char| c.is_ascii_digit());
                let two: String = aname.chars().take(2).collect();
                let one: String = aname.chars().take(1).collect();
                elements::by_symbol(&one)
                    .or_else(|| elements::by_symbol(&two))
                    .map(|e| e.z)
                    .unwrap_or(6)
            };

            let atom = mol.alloc_atom(z, [x, y, zc], [x, y]);
            if serial > 0 {
                serial_to_id.insert(serial, atom.id);
            }
            mol.atoms.push(atom);
        } else if line.starts_with("CONECT") {
            let nums: Vec<u32> = line[6..]
                .split_whitespace()
                .filter_map(|s| s.parse::<u32>().ok())
                .collect();
            if let Some(&src) = nums.first() {
                for &dst in &nums[1..] {
                    if src < dst {
                        conect_pairs.push((src, dst));
                    }
                }
            }
        }
    }

    mol.reindex();
    mol.has_3d = true;
    for (s1, s2) in conect_pairs {
        if let (Some(&id1), Some(&id2)) = (serial_to_id.get(&s1), serial_to_id.get(&s2)) {
            if mol.bond_between(id1, id2).is_none() {
                let b = mol.alloc_bond(id1, id2, 1, false);
                mol.bonds.push(b);
            }
        }
    }
    if mol.bonds.is_empty() && mol.atoms.len() <= 80_000 {
        infer_bonds_spatial(&mut mol);
    }
    Ok(mol)
}

pub fn write_pdb(mol: &Molecule) -> String {
    let mut out = String::with_capacity(mol.atoms.len() * 82 + 128);
    if let Some(c) = &mol.cell {
        out.push_str(&format!(
            "CRYST1{:9.3}{:9.3}{:9.3}{:7.2}{:7.2}{:7.2} {:<11}1\n",
            c.a, c.b, c.c, c.alpha, c.beta, c.gamma, c.space_group
        ));
    }
    for (idx, a) in mol.atoms.iter().enumerate() {
        let sym = elements::symbol_of(a.z);
        out.push_str(&format!(
            "HETATM{:5} {:<4} MOL A   1    {:8.3}{:8.3}{:8.3}  1.00  0.00          {:>2}\n",
            (idx + 1) % 100_000,
            sym,
            a.pos[0],
            a.pos[1],
            a.pos[2],
            sym
        ));
    }
    out.push_str("END\n");
    out
}

pub fn parse_mol_v2000(text: &str, name: &str) -> Result<Molecule> {
    let lines: Vec<&str> = text.lines().collect();
    if lines.len() < 4 {
        return Err(CoreError::Parse("MOL file too short".into()));
    }
    let mol_name = if !name.is_empty() {
        name
    } else if !lines[0].trim().is_empty() {
        lines[0].trim()
    } else {
        "MOL Molecule"
    };
    let counts = lines[3];
    let n_atoms: usize = counts
        .get(0..3)
        .and_then(|s| s.trim().parse().ok())
        .or_else(|| counts.split_whitespace().next()?.parse().ok())
        .ok_or_else(|| CoreError::Parse("invalid MOL atom count".into()))?;
    let n_bonds: usize = counts
        .get(3..6)
        .and_then(|s| s.trim().parse().ok())
        .or_else(|| counts.split_whitespace().nth(1)?.parse().ok())
        .unwrap_or(0);

    let mut mol = Molecule::new(mol_name);
    let mut ids = Vec::with_capacity(n_atoms);
    for line in lines.iter().skip(4).take(n_atoms) {
        let parts: Vec<&str> = line.split_whitespace().collect();
        if parts.len() < 4 {
            return Err(CoreError::Parse("invalid MOL atom line".into()));
        }
        let x: f64 = parts[0].parse().unwrap_or(0.0);
        let y: f64 = parts[1].parse().unwrap_or(0.0);
        let zc: f64 = parts[2].parse().unwrap_or(0.0);
        let z = elements::by_symbol(parts[3]).map(|e| e.z).unwrap_or(6);
        let atom = mol.alloc_atom(z, [x, y, zc], [x, y]);
        ids.push(atom.id);
        mol.atoms.push(atom);
    }
    mol.reindex();
    mol.has_3d = mol.atoms.iter().any(|a| a.pos[2].abs() > 1e-4);
    mol.has_2d = true;

    for line in lines.iter().skip(4 + n_atoms).take(n_bonds) {
        let a1 = line.get(0..3).and_then(|s| s.trim().parse::<usize>().ok());
        let a2 = line.get(3..6).and_then(|s| s.trim().parse::<usize>().ok());
        let ord = line.get(6..9).and_then(|s| s.trim().parse::<u8>().ok());
        let (a1, a2, ord) = match (a1, a2, ord) {
            (Some(a), Some(b), Some(o)) => (a, b, o),
            _ => {
                let p: Vec<usize> = line
                    .split_whitespace()
                    .filter_map(|s| s.parse().ok())
                    .collect();
                if p.len() >= 3 {
                    (p[0], p[1], p[2] as u8)
                } else {
                    continue;
                }
            }
        };
        if a1 >= 1 && a2 >= 1 && a1 <= ids.len() && a2 <= ids.len() {
            let aromatic = ord == 4;
            let order = if aromatic { 1 } else { ord.clamp(1, 3) };
            let b = mol.alloc_bond(ids[a1 - 1], ids[a2 - 1], order, aromatic);
            mol.bonds.push(b);
        }
    }
    Ok(mol)
}

pub fn write_mol_v2000(mol: &Molecule) -> String {
    let mut out = String::new();
    out.push_str(&format!("{}\n  MolForge-Rust\n\n", mol.name));
    out.push_str(&format!(
        "{:3}{:3}  0  0  0  0  0  0  0  0999 V2000\n",
        mol.atoms.len(),
        mol.bonds.len()
    ));
    for a in &mol.atoms {
        out.push_str(&format!(
            "{:10.4}{:10.4}{:10.4} {:<3} 0  0  0  0  0  0  0  0  0  0  0  0\n",
            a.pos[0],
            a.pos[1],
            a.pos[2],
            elements::symbol_of(a.z)
        ));
    }
    for b in &mol.bonds {
        if let (Some(ia), Some(ib)) = (mol.atom_index(b.a), mol.atom_index(b.b)) {
            let ord = if b.aromatic { 4 } else { b.order };
            out.push_str(&format!("{:3}{:3}{:3}  0  0  0  0\n", ia + 1, ib + 1, ord));
        }
    }
    out.push_str("M  END\n");
    out
}

pub fn write_gjf(mol: &Molecule, method: &str, basis: &str, charge: i32, mult: u32, optimize: bool) -> String {
    let route = if optimize { format!("#p {method}/{basis} Opt") } else { format!("#p {method}/{basis}") };
    let mut out = format!("%nprocshared=4\n%mem=2GB\n{route}\n\n{}\n\n{charge} {mult}\n", mol.name);
    for a in &mol.atoms {
        out.push_str(&format!(
            "{:<3} {:>12.6} {:>12.6} {:>12.6}\n",
            elements::symbol_of(a.z),
            a.pos[0],
            a.pos[1],
            a.pos[2]
        ));
    }
    out.push('\n');
    out
}

pub fn write_orca_inp(mol: &Molecule, method: &str, basis: &str, charge: i32, mult: u32, optimize: bool) -> String {
    // 串行默认（本机无 MPI 时 %pal nprocs>1 会直接退出）；并行度由环境变量显式开启
    let nprocs: usize = std::env::var("MOLFORGE_ORCA_NPROCS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(1);
    let pal = if nprocs > 1 { format!("%pal nprocs {nprocs} end\n") } else { String::new() };
    let route = if optimize { format!("! {method} {basis} Opt") } else { format!("! {method} {basis}") };
    let mut out = format!("{route}\n{pal}* xyz {charge} {mult}\n");
    for a in &mol.atoms {
        out.push_str(&format!(
            "{:<3} {:>12.6} {:>12.6} {:>12.6}\n",
            elements::symbol_of(a.z),
            a.pos[0],
            a.pos[1],
            a.pos[2]
        ));
    }
    out.push_str("*\n");
    out
}

pub fn write_xtb_input(mol: &Molecule, method: &str, charge: i32, mult: u32) -> String {
    let gfn = match method.to_ascii_lowercase().as_str() {
        "gfn1" | "gfn1-xtb" => "1",
        "gfnff" => "ff",
        _ => "2",
    };
    let uhf = mult.saturating_sub(1);
    let mut out = format!(
        "# xTB input generated by MolForge Studio\n# run: xtb input.xyz --gfn {gfn} --opt --chrg {charge} --uhf {uhf}\n"
    );
    out.push_str(&write_xyz(mol));
    out
}

pub fn write_rest_ctrl(mol: &Molecule, xc: &str, basis: &str, charge: i32, mult: u32) -> String {
    let mut geom = String::new();
    for a in &mol.atoms {
        geom.push_str(&format!(
            "  {:<3} {:>12.6} {:>12.6} {:>12.6}\n",
            elements::symbol_of(a.z),
            a.pos[0],
            a.pos[1],
            a.pos[2]
        ));
    }
    format!(
        "[ctrl]\nxc = \"{xc}\"\nbasis = \"{basis}\"\ncharge = {charge}\nspin = {mult}\n\n[geom]\nunit = \"angstrom\"\nposition = '''\n{geom}'''\n"
    )
}

#[derive(Serialize, Deserialize)]
struct MforgeManifest {
    format: String,
    version: String,
    name: String,
    document_id: String,
}

pub fn export_mforge_bytes(mol: &Molecule) -> Result<Vec<u8>> {
    let mut buf = Cursor::new(Vec::new());
    {
        let mut zip = ZipWriter::new(&mut buf);
        let opts = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

        let manifest = MforgeManifest {
            format: "molforge-project".into(),
            version: "1.1".into(),
            name: mol.name.clone(),
            document_id: mol.document_id.clone(),
        };
        zip.start_file("manifest.json", opts)
            .map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(
            serde_json::to_string_pretty(&manifest)
                .map_err(|e| CoreError::Parse(e.to_string()))?
                .as_bytes(),
        )?;

        zip.start_file("molecule.json", opts)
            .map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(
            serde_json::to_string(mol)
                .map_err(|e| CoreError::Parse(e.to_string()))?
                .as_bytes(),
        )?;

        zip.start_file("structure.xyz", opts)
            .map_err(|e| CoreError::External(e.to_string()))?;
        zip.write_all(write_xyz(mol).as_bytes())?;

        zip.finish().map_err(|e| CoreError::External(e.to_string()))?;
    }
    Ok(buf.into_inner())
}

pub fn import_mforge_bytes(bytes: &[u8]) -> Result<Molecule> {
    let reader = Cursor::new(bytes);
    let mut archive =
        ZipArchive::new(reader).map_err(|e| CoreError::Parse(format!("invalid .mforge zip: {e}")))?;

    if let Ok(mut f) = archive.by_name("molecule.json") {
        let mut s = String::new();
        f.read_to_string(&mut s)?;
        let mut mol: Molecule =
            serde_json::from_str(&s).map_err(|e| CoreError::Parse(e.to_string()))?;
        mol.reindex();
        return Ok(mol);
    }

    if let Ok(mut f) = archive.by_name("structure.xyz") {
        let mut s = String::new();
        f.read_to_string(&mut s)?;
        return parse_xyz(&s, "Imported Project");
    }

    Err(CoreError::Parse(
        ".mforge archive missing molecule.json and structure.xyz".into(),
    ))
}

pub fn open_by_extension(path: &str, content: &[u8]) -> Result<Molecule> {
    let lower = path.to_ascii_lowercase();
    let stem = std::path::Path::new(path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("Structure");

    let mut mol = if lower.ends_with(".mforge") {
        import_mforge_bytes(content)?
    } else {
        let text = String::from_utf8_lossy(content);
        if lower.ends_with(".pdb") || lower.ends_with(".ent") {
            parse_pdb(&text, stem)?
        } else if lower.ends_with(".mol") || lower.ends_with(".sdf") {
            parse_mol_v2000(&text, stem)?
        } else {
            parse_xyz(&text, stem)?
        }
    };
    mol.source_path = Some(path.to_string());
    Ok(mol)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presets::build_preset;

    #[test]
    fn roundtrip_mforge_and_xyz() {
        let mol = build_preset("caffeine").unwrap();
        let bytes = export_mforge_bytes(&mol).unwrap();
        let restored = import_mforge_bytes(&bytes).unwrap();
        assert_eq!(restored.atoms.len(), mol.atoms.len());
        assert_eq!(restored.bonds.len(), mol.bonds.len());

        let xyz = write_xyz(&mol);
        let parsed = parse_xyz(&xyz, "caffeine").unwrap();
        assert_eq!(parsed.atoms.len(), mol.atoms.len());
    }
}
