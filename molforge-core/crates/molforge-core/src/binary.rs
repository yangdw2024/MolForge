//! Binary `MOLF` v1 scene encoder matching `desktop/src/services/api.ts`.

use crate::elements;
use crate::model::Molecule;

pub const MAGIC_MOLF: u32 = 0x4D4F_4C46;

pub fn encode_molf_v1(mol: &Molecule) -> Vec<u8> {
    let n_atoms = mol.atoms.len();
    let valid_bonds: Vec<(u32, u32, u8)> = mol
        .bonds
        .iter()
        .filter_map(|b| {
            let ia = mol.atom_index(b.a)? as u32;
            let ib = mol.atom_index(b.b)? as u32;
            Some((ia, ib, b.order))
        })
        .collect();
    let n_bonds = valid_bonds.len();

    let cell_mat = mol.cell.as_ref().and_then(|c| c.matrix());
    let has_cell: u32 = if cell_mat.is_some() { 1 } else { 0 };

    let z_pad = (4 - (n_atoms % 4)) % 4;
    let bo_pad = (4 - (n_bonds % 4)) % 4;
    let total_bytes = 32
        + n_atoms * 12
        + n_atoms
        + z_pad
        + n_atoms * 4
        + n_atoms * 4
        + n_bonds * 8
        + n_bonds
        + bo_pad
        + if has_cell == 1 { 48 } else { 0 };

    let mut buf = Vec::with_capacity(total_bytes);

    // Header: <8I
    for word in [
        MAGIC_MOLF,
        1u32,
        n_atoms as u32,
        n_bonds as u32,
        mol.revision as u32,
        has_cell,
        0u32,
        0u32,
    ] {
        buf.extend_from_slice(&word.to_le_bytes());
    }

    // f32[n_atoms * 3] positions
    for a in &mol.atoms {
        buf.extend_from_slice(&(a.pos[0] as f32).to_le_bytes());
        buf.extend_from_slice(&(a.pos[1] as f32).to_le_bytes());
        buf.extend_from_slice(&(a.pos[2] as f32).to_le_bytes());
    }

    // u8[n_atoms] atomic numbers + 4-byte align pad
    for a in &mol.atoms {
        buf.push(a.z);
    }
    buf.resize(buf.len() + z_pad, 0);

    // f32[n_atoms] vdw radii
    for a in &mol.atoms {
        let r = elements::vdw(a.z) * a.scale.max(0.1);
        buf.extend_from_slice(&r.to_le_bytes());
    }

    // u8[n_atoms * 4] RGBA
    for a in &mol.atoms {
        let rgb = a.color.unwrap_or_else(|| elements::rgb(a.z));
        let alpha = (a.opacity.clamp(0.0, 1.0) * 255.0).round() as u8;
        buf.extend_from_slice(&[rgb[0], rgb[1], rgb[2], alpha]);
    }

    // u32[n_bonds * 2] atom index pairs
    for &(ia, ib, _) in &valid_bonds {
        buf.extend_from_slice(&ia.to_le_bytes());
        buf.extend_from_slice(&ib.to_le_bytes());
    }

    // u8[n_bonds] bond orders + 4-byte align pad
    for &(_, _, ord) in &valid_bonds {
        buf.push(ord);
    }
    buf.resize(buf.len() + bo_pad, 0);

    // Optional unit cell: f32[3] box_origin + f32[9] matrix
    if let Some(m) = cell_mat {
        for v in mol.box_origin {
            buf.extend_from_slice(&(v as f32).to_le_bytes());
        }
        for row in m {
            for v in row {
                buf.extend_from_slice(&(v as f32).to_le_bytes());
            }
        }
    }

    buf
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::commands::{CommandBus, EditCommand};

    #[test]
    fn binary_header_and_alignment() {
        let mut bus = CommandBus::new(Molecule::new("dimer"));
        bus.execute(EditCommand::AddAtom {
            z: 6,
            pos: [0.0, 0.0, 0.0],
            pos2: [0.0, 0.0],
            bond_to: None,
            bond_order: 1,
        })
        .unwrap();
        bus.execute(EditCommand::AddAtom {
            z: 6,
            pos: [1.5, 0.0, 0.0],
            pos2: [1.5, 0.0],
            bond_to: Some(0),
            bond_order: 1,
        })
        .unwrap();
        let bytes = encode_molf_v1(&bus.mol);
        assert_eq!(bytes.len() % 4, 0);
        assert_eq!(u32::from_le_bytes(bytes[0..4].try_into().unwrap()), MAGIC_MOLF);
        assert_eq!(u32::from_le_bytes(bytes[8..12].try_into().unwrap()), 2);
        assert_eq!(u32::from_le_bytes(bytes[12..16].try_into().unwrap()), 1);
    }
}
