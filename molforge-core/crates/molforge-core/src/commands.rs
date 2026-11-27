//! Undoable command bus for `Molecule` edits, preserving stable `AtomId` and `BondId`.

use crate::elements;
use crate::model::{Atom, AtomId, Bond, BondId, Molecule};
use crate::{CoreError, Result};

#[derive(Debug, Clone)]
pub enum EditCommand {
    AddAtom {
        z: u8,
        pos: [f64; 3],
        pos2: [f64; 2],
        bond_to: Option<AtomId>,
        bond_order: u8,
    },
    DeleteAtoms {
        ids: Vec<AtomId>,
    },
    AddBond {
        a: AtomId,
        b: AtomId,
        order: u8,
    },
    DeleteBond {
        a: AtomId,
        b: AtomId,
    },
    CycleBondOrder {
        a: AtomId,
        b: AtomId,
    },
    /// 精确设置键级（1/2/3；4=芳香键，置 aromatic 标志）。右键菜单专用，可撤销。
    SetBondOrder {
        a: AtomId,
        b: AtomId,
        order: u8,
    },
    /// 仅移动 2D 布局坐标（画布拖拽），不触碰 3D 构象，可撤销。
    MoveAtom2D {
        id: AtomId,
        new_pos2: [f64; 2],
    },
    ChangeElement {
        id: AtomId,
        new_z: u8,
    },
    MoveAtom {
        id: AtomId,
        new_pos: [f64; 3],
        new_pos2: Option<[f64; 2]>,
    },
    AddRing {
        size: u8,
        aromatic: bool,
        attach_to: Option<AtomId>,
        center: [f64; 3],
        /// 环内杂原子映射：(环内序号, 原子序数)，如噻吩 (0, 16)。
        hetero: Vec<(usize, u8)>,
    },
    InsertFragment {
        atoms: Vec<(u8, [f64; 3], [f64; 2])>,
        bonds: Vec<(usize, usize, u8)>,
    },
    SetChargeSpin {
        charge: Option<i32>,
        multiplicity: Option<u32>,
    },
    /// 单原子形式电荷（右键菜单电荷设置），可撤销。
    SetAtomCharge {
        id: AtomId,
        charge: i32,
    },
    ApplyGeometry {
        positions: Vec<(AtomId, [f64; 3])>,
    },
}

#[derive(Debug, Clone)]
enum UndoAction {
    /// Remove added atoms and added bonds on undo; re-insert on redo.
    AddedEntities {
        atoms: Vec<Atom>,
        bonds: Vec<Bond>,
    },
    /// Re-insert removed atoms and bonds on undo; remove again on redo.
    RemovedEntities {
        atoms: Vec<Atom>,
        bonds: Vec<Bond>,
    },
    /// Swap bond order & aromaticity.
    BondOrderChanged {
        bond_id: BondId,
        old_order: u8,
        old_aromatic: bool,
        new_order: u8,
        new_aromatic: bool,
    },
    /// Swap atom element Z.
    ElementChanged {
        id: AtomId,
        old_z: u8,
        new_z: u8,
    },
    /// Swap atom 3D/2D coordinates.
    AtomMoved {
        id: AtomId,
        old_pos: [f64; 3],
        old_pos2: [f64; 2],
        new_pos: [f64; 3],
        new_pos2: [f64; 2],
    },
    /// Swap charge & multiplicity.
    ChargeSpinChanged {
        old_charge: Option<i32>,
        old_mult: Option<u32>,
        new_charge: Option<i32>,
        new_mult: Option<u32>,
    },
    /// Swap single-atom formal charge.
    AtomChargeChanged {
        id: AtomId,
        old_charge: i32,
        new_charge: i32,
    },
    /// Batch geometry update.
    GeometryApplied {
        old_positions: Vec<(AtomId, [f64; 3])>,
        new_positions: Vec<(AtomId, [f64; 3])>,
    },
}

#[derive(Debug, Clone)]
struct UndoRecord {
    label: &'static str,
    action: UndoAction,
}

pub struct CommandBus {
    pub mol: Molecule,
    undo_stack: Vec<UndoRecord>,
    redo_stack: Vec<UndoRecord>,
    max_history: usize,
}

impl CommandBus {
    pub fn new(mol: Molecule) -> Self {
        Self {
            mol,
            undo_stack: Vec::new(),
            redo_stack: Vec::new(),
            max_history: 200,
        }
    }

    pub fn can_undo(&self) -> bool {
        !self.undo_stack.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo_stack.is_empty()
    }

    pub fn replace_document(&mut self, mut mol: Molecule) {
        mol.reindex();
        self.mol = mol;
        self.undo_stack.clear();
        self.redo_stack.clear();
    }

    fn push_record(&mut self, record: UndoRecord) {
        self.redo_stack.clear();
        self.undo_stack.push(record);
        if self.undo_stack.len() > self.max_history {
            let overflow = self.undo_stack.len() - self.max_history;
            self.undo_stack.drain(0..overflow);
        }
        self.mol.revision += 1;
    }

    pub fn execute(&mut self, cmd: EditCommand) -> Result<()> {
        match cmd {
            EditCommand::AddAtom {
                z,
                pos,
                pos2,
                bond_to,
                bond_order,
            } => {
                if elements::by_z(z).is_none() {
                    return Err(CoreError::UnknownElement(format!("Z={z}")));
                }
                if let Some(target) = bond_to {
                    if self.mol.atom(target).is_none() {
                        return Err(CoreError::AtomNotFound(target));
                    }
                }
                let atom = self.mol.alloc_atom(z, pos, pos2);
                let atom_id = atom.id;
                self.mol.atoms.push(atom.clone());
                self.mol.reindex();
                self.mol.has_3d = true;

                let mut added_bonds = Vec::new();
                if let Some(target) = bond_to {
                    let order = bond_order.clamp(1, 3);
                    let bond = self.mol.alloc_bond(atom_id, target, order, false);
                    self.mol.bonds.push(bond.clone());
                    added_bonds.push(bond);
                }

                self.push_record(UndoRecord {
                    label: "AddAtom",
                    action: UndoAction::AddedEntities {
                        atoms: vec![atom],
                        bonds: added_bonds,
                    },
                });
                Ok(())
            }
            EditCommand::DeleteAtoms { ids } => {
                let id_set: std::collections::HashSet<AtomId> = ids.into_iter().collect();
                let mut removed_atoms = Vec::new();
                for a in &self.mol.atoms {
                    if id_set.contains(&a.id) {
                        removed_atoms.push(a.clone());
                    }
                }
                if removed_atoms.is_empty() {
                    return Ok(());
                }
                let mut removed_bonds = Vec::new();
                for b in &self.mol.bonds {
                    if id_set.contains(&b.a) || id_set.contains(&b.b) {
                        removed_bonds.push(b.clone());
                    }
                }
                self.mol.atoms.retain(|a| !id_set.contains(&a.id));
                self.mol
                    .bonds
                    .retain(|b| !id_set.contains(&b.a) && !id_set.contains(&b.b));
                self.mol.reindex();

                self.push_record(UndoRecord {
                    label: "DeleteAtoms",
                    action: UndoAction::RemovedEntities {
                        atoms: removed_atoms,
                        bonds: removed_bonds,
                    },
                });
                Ok(())
            }
            EditCommand::AddBond { a, b, order } => {
                if a == b {
                    return Err(CoreError::InvalidOp("cannot bond an atom to itself".into()));
                }
                if self.mol.atom(a).is_none() {
                    return Err(CoreError::AtomNotFound(a));
                }
                if self.mol.atom(b).is_none() {
                    return Err(CoreError::AtomNotFound(b));
                }
                let ord = order.clamp(1, 3);
                if let Some(existing) = self.mol.bond_between(a, b).cloned() {
                    for bond in &mut self.mol.bonds {
                        if bond.id == existing.id {
                            bond.order = ord;
                            bond.aromatic = false;
                        }
                    }
                    self.push_record(UndoRecord {
                        label: "UpdateBond",
                        action: UndoAction::BondOrderChanged {
                            bond_id: existing.id,
                            old_order: existing.order,
                            old_aromatic: existing.aromatic,
                            new_order: ord,
                            new_aromatic: false,
                        },
                    });
                } else {
                    let bond = self.mol.alloc_bond(a, b, ord, false);
                    self.mol.bonds.push(bond.clone());
                    self.push_record(UndoRecord {
                        label: "AddBond",
                        action: UndoAction::AddedEntities {
                            atoms: Vec::new(),
                            bonds: vec![bond],
                        },
                    });
                }
                Ok(())
            }
            EditCommand::DeleteBond { a, b } => {
                let existing = self
                    .mol
                    .bond_between(a, b)
                    .cloned()
                    .ok_or(CoreError::BondPairNotFound(a, b))?;
                self.mol.bonds.retain(|x| x.id != existing.id);
                self.push_record(UndoRecord {
                    label: "DeleteBond",
                    action: UndoAction::RemovedEntities {
                        atoms: Vec::new(),
                        bonds: vec![existing],
                    },
                });
                Ok(())
            }
            EditCommand::CycleBondOrder { a, b } => {
                let existing = self
                    .mol
                    .bond_between(a, b)
                    .cloned()
                    .ok_or(CoreError::BondPairNotFound(a, b))?;
                let next_order = match existing.order {
                    1 => 2,
                    2 => 3,
                    _ => 1,
                };
                for bond in &mut self.mol.bonds {
                    if bond.id == existing.id {
                        bond.order = next_order;
                        bond.aromatic = false;
                    }
                }
                self.push_record(UndoRecord {
                    label: "CycleBondOrder",
                    action: UndoAction::BondOrderChanged {
                        bond_id: existing.id,
                        old_order: existing.order,
                        old_aromatic: existing.aromatic,
                        new_order: next_order,
                        new_aromatic: false,
                    },
                });
                Ok(())
            }
            EditCommand::SetBondOrder { a, b, order } => {
                let existing = self
                    .mol
                    .bond_between(a, b)
                    .cloned()
                    .ok_or(CoreError::BondPairNotFound(a, b))?;
                let aromatic = order == 4;
                let ord = if aromatic { 1 } else { order.clamp(1, 3) };
                for bond in &mut self.mol.bonds {
                    if bond.id == existing.id {
                        bond.order = ord;
                        bond.aromatic = aromatic;
                    }
                }
                self.push_record(UndoRecord {
                    label: "SetBondOrder",
                    action: UndoAction::BondOrderChanged {
                        bond_id: existing.id,
                        old_order: existing.order,
                        old_aromatic: existing.aromatic,
                        new_order: ord,
                        new_aromatic: aromatic,
                    },
                });
                Ok(())
            }
            EditCommand::MoveAtom2D { id, new_pos2 } => {
                let atom = self.mol.atom_mut(id).ok_or(CoreError::AtomNotFound(id))?;
                let old_pos = atom.pos;
                let old_pos2 = atom.pos2;
                atom.pos2 = new_pos2;
                self.push_record(UndoRecord {
                    label: "MoveAtom2D",
                    action: UndoAction::AtomMoved {
                        id,
                        old_pos,
                        old_pos2,
                        new_pos: old_pos,
                        new_pos2,
                    },
                });
                Ok(())
            }
            EditCommand::ChangeElement { id, new_z } => {
                if elements::by_z(new_z).is_none() {
                    return Err(CoreError::UnknownElement(format!("Z={new_z}")));
                }
                let atom = self.mol.atom_mut(id).ok_or(CoreError::AtomNotFound(id))?;
                let old_z = atom.z;
                if old_z == new_z {
                    return Ok(());
                }
                atom.z = new_z;
                atom.color = None;
                self.push_record(UndoRecord {
                    label: "ChangeElement",
                    action: UndoAction::ElementChanged { id, old_z, new_z },
                });
                Ok(())
            }
            EditCommand::MoveAtom {
                id,
                new_pos,
                new_pos2,
            } => {
                let atom = self.mol.atom_mut(id).ok_or(CoreError::AtomNotFound(id))?;
                let old_pos = atom.pos;
                let old_pos2 = atom.pos2;
                let target_pos2 = new_pos2.unwrap_or([new_pos[0], new_pos[1]]);
                atom.pos = new_pos;
                atom.pos2 = target_pos2;
                self.mol.has_3d = true;
                self.push_record(UndoRecord {
                    label: "MoveAtom",
                    action: UndoAction::AtomMoved {
                        id,
                        old_pos,
                        old_pos2,
                        new_pos,
                        new_pos2: target_pos2,
                    },
                });
                Ok(())
            }
            EditCommand::AddRing {
                size,
                aromatic,
                attach_to,
                center,
                hetero,
            } => {
                let n = size.clamp(3, 8) as usize;
                let bond_len = if aromatic { 1.39 } else { 1.54 };
                let radius = bond_len / (2.0 * (std::f64::consts::PI / n as f64).sin());

                let mut origin = center;
                if let Some(tid) = attach_to {
                    if let Some(target) = self.mol.atom(tid) {
                        origin = [
                            target.pos[0] + radius + 1.50,
                            target.pos[1],
                            target.pos[2],
                        ];
                    } else {
                        return Err(CoreError::AtomNotFound(tid));
                    }
                }

                let mut added_atoms = Vec::with_capacity(n);
                let mut added_bonds = Vec::with_capacity(n + 1);
                for i in 0..n {
                    let angle = 2.0 * std::f64::consts::PI * (i as f64) / (n as f64);
                    let x = origin[0] + radius * angle.cos();
                    let y = origin[1] + radius * angle.sin();
                    let z = origin[2];
                    let z_elem = hetero
                        .iter()
                        .find(|(idx, _)| *idx == i)
                        .map(|(_, zz)| *zz)
                        .unwrap_or(6);
                    if elements::by_z(z_elem).is_none() {
                        return Err(CoreError::UnknownElement(format!("Z={z_elem}")));
                    }
                    let mut atom = self.mol.alloc_atom(z_elem, [x, y, z], [x, y]);
                    atom.aromatic = aromatic;
                    self.mol.atoms.push(atom.clone());
                    added_atoms.push(atom);
                }
                self.mol.reindex();
                self.mol.has_3d = true;

                for i in 0..n {
                    let a = added_atoms[i].id;
                    let b = added_atoms[(i + 1) % n].id;
                    let order = if aromatic {
                        if i % 2 == 0 { 2 } else { 1 }
                    } else {
                        1
                    };
                    let bond = self.mol.alloc_bond(a, b, order, aromatic);
                    self.mol.bonds.push(bond.clone());
                    added_bonds.push(bond);
                }

                if let Some(tid) = attach_to {
                    // Connect to closest ring atom (index 3 or opposite side, or index n/2)
                    let closest = added_atoms
                        .iter()
                        .min_by(|u, v| {
                            let target = self.mol.atom(tid).unwrap().pos;
                            let du = dist2(u.pos, target);
                            let dv = dist2(v.pos, target);
                            du.partial_cmp(&dv).unwrap_or(std::cmp::Ordering::Equal)
                        })
                        .unwrap()
                        .id;
                    let link = self.mol.alloc_bond(tid, closest, 1, false);
                    self.mol.bonds.push(link.clone());
                    added_bonds.push(link);
                }

                self.push_record(UndoRecord {
                    label: "AddRing",
                    action: UndoAction::AddedEntities {
                        atoms: added_atoms,
                        bonds: added_bonds,
                    },
                });
                Ok(())
            }
            EditCommand::InsertFragment { atoms, bonds } => {
                let mut added_atoms = Vec::with_capacity(atoms.len());
                for (z, pos, pos2) in atoms {
                    let atom = self.mol.alloc_atom(z, pos, pos2);
                    self.mol.atoms.push(atom.clone());
                    added_atoms.push(atom);
                }
                self.mol.reindex();
                self.mol.has_3d = true;

                let mut added_bonds = Vec::with_capacity(bonds.len());
                for (ia, ib, order) in bonds {
                    if let (Some(a), Some(b)) = (added_atoms.get(ia), added_atoms.get(ib)) {
                        let bond = self.mol.alloc_bond(a.id, b.id, order.clamp(1, 3), false);
                        self.mol.bonds.push(bond.clone());
                        added_bonds.push(bond);
                    }
                }

                self.push_record(UndoRecord {
                    label: "InsertFragment",
                    action: UndoAction::AddedEntities {
                        atoms: added_atoms,
                        bonds: added_bonds,
                    },
                });
                Ok(())
            }
            EditCommand::SetChargeSpin {
                charge,
                multiplicity,
            } => {
                let old_charge = self.mol.charge;
                let old_mult = self.mol.multiplicity;
                self.mol.charge = charge;
                self.mol.multiplicity = multiplicity;
                self.push_record(UndoRecord {
                    label: "SetChargeSpin",
                    action: UndoAction::ChargeSpinChanged {
                        old_charge,
                        old_mult,
                        new_charge: charge,
                        new_mult: multiplicity,
                    },
                });
                Ok(())
            }
            EditCommand::SetAtomCharge { id, charge } => {
                let atom = self.mol.atom_mut(id).ok_or(CoreError::AtomNotFound(id))?;
                let old_charge = atom.charge as i32;
                if old_charge == charge {
                    return Ok(());
                }
                atom.charge = charge as i8;
                self.push_record(UndoRecord {
                    label: "SetAtomCharge",
                    action: UndoAction::AtomChargeChanged {
                        id,
                        old_charge,
                        new_charge: charge,
                    },
                });
                Ok(())
            }
            EditCommand::ApplyGeometry { positions } => {
                let mut old_positions = Vec::with_capacity(positions.len());
                let mut new_positions = Vec::with_capacity(positions.len());
                for (id, pos) in positions {
                    if let Some(a) = self.mol.atom_mut(id) {
                        old_positions.push((id, a.pos));
                        a.pos = pos;
                        a.pos2 = [pos[0], pos[1]];
                        new_positions.push((id, pos));
                    }
                }
                self.mol.has_3d = true;
                self.push_record(UndoRecord {
                    label: "ApplyGeometry",
                    action: UndoAction::GeometryApplied {
                        old_positions,
                        new_positions,
                    },
                });
                Ok(())
            }
        }
    }

    pub fn undo(&mut self) -> bool {
        let Some(rec) = self.undo_stack.pop() else {
            return false;
        };
        match &rec.action {
            UndoAction::AddedEntities { atoms, bonds } => {
                let a_ids: std::collections::HashSet<AtomId> = atoms.iter().map(|a| a.id).collect();
                let b_ids: std::collections::HashSet<BondId> = bonds.iter().map(|b| b.id).collect();
                self.mol.atoms.retain(|a| !a_ids.contains(&a.id));
                self.mol.bonds.retain(|b| !b_ids.contains(&b.id));
                self.mol.reindex();
            }
            UndoAction::RemovedEntities { atoms, bonds } => {
                for a in atoms {
                    self.mol.atoms.push(a.clone());
                }
                for b in bonds {
                    self.mol.bonds.push(b.clone());
                }
                self.mol.atoms.sort_by_key(|a| a.id);
                self.mol.bonds.sort_by_key(|b| b.id);
                self.mol.reindex();
            }
            UndoAction::BondOrderChanged {
                bond_id,
                old_order,
                old_aromatic,
                ..
            } => {
                if let Some(b) = self.mol.bonds.iter_mut().find(|b| b.id == *bond_id) {
                    b.order = *old_order;
                    b.aromatic = *old_aromatic;
                }
            }
            UndoAction::ElementChanged { id, old_z, .. } => {
                if let Some(a) = self.mol.atom_mut(*id) {
                    a.z = *old_z;
                    a.color = None;
                }
            }
            UndoAction::AtomMoved {
                id,
                old_pos,
                old_pos2,
                ..
            } => {
                if let Some(a) = self.mol.atom_mut(*id) {
                    a.pos = *old_pos;
                    a.pos2 = *old_pos2;
                }
            }
            UndoAction::ChargeSpinChanged {
                old_charge,
                old_mult,
                ..
            } => {
                self.mol.charge = *old_charge;
                self.mol.multiplicity = *old_mult;
            }
            UndoAction::AtomChargeChanged { id, old_charge, .. } => {
                if let Some(a) = self.mol.atom_mut(*id) {
                    a.charge = *old_charge as i8;
                }
            }
            UndoAction::GeometryApplied { old_positions, .. } => {
                for (id, pos) in old_positions {
                    if let Some(a) = self.mol.atom_mut(*id) {
                        a.pos = *pos;
                        a.pos2 = [pos[0], pos[1]];
                    }
                }
            }
        }
        self.mol.revision += 1;
        self.redo_stack.push(rec);
        true
    }

    pub fn redo(&mut self) -> bool {
        let Some(rec) = self.redo_stack.pop() else {
            return false;
        };
        match &rec.action {
            UndoAction::AddedEntities { atoms, bonds } => {
                for a in atoms {
                    self.mol.atoms.push(a.clone());
                }
                for b in bonds {
                    self.mol.bonds.push(b.clone());
                }
                self.mol.reindex();
            }
            UndoAction::RemovedEntities { atoms, bonds } => {
                let a_ids: std::collections::HashSet<AtomId> = atoms.iter().map(|a| a.id).collect();
                let b_ids: std::collections::HashSet<BondId> = bonds.iter().map(|b| b.id).collect();
                self.mol.atoms.retain(|a| !a_ids.contains(&a.id));
                self.mol.bonds.retain(|b| !b_ids.contains(&b.id));
                self.mol.reindex();
            }
            UndoAction::BondOrderChanged {
                bond_id,
                new_order,
                new_aromatic,
                ..
            } => {
                if let Some(b) = self.mol.bonds.iter_mut().find(|b| b.id == *bond_id) {
                    b.order = *new_order;
                    b.aromatic = *new_aromatic;
                }
            }
            UndoAction::ElementChanged { id, new_z, .. } => {
                if let Some(a) = self.mol.atom_mut(*id) {
                    a.z = *new_z;
                    a.color = None;
                }
            }
            UndoAction::AtomMoved {
                id,
                new_pos,
                new_pos2,
                ..
            } => {
                if let Some(a) = self.mol.atom_mut(*id) {
                    a.pos = *new_pos;
                    a.pos2 = *new_pos2;
                }
            }
            UndoAction::ChargeSpinChanged {
                new_charge,
                new_mult,
                ..
            } => {
                self.mol.charge = *new_charge;
                self.mol.multiplicity = *new_mult;
            }
            UndoAction::AtomChargeChanged { id, new_charge, .. } => {
                if let Some(a) = self.mol.atom_mut(*id) {
                    a.charge = *new_charge as i8;
                }
            }
            UndoAction::GeometryApplied { new_positions, .. } => {
                for (id, pos) in new_positions {
                    if let Some(a) = self.mol.atom_mut(*id) {
                        a.pos = *pos;
                        a.pos2 = [pos[0], pos[1]];
                    }
                }
            }
        }
        self.mol.revision += 1;
        let _ = rec.label;
        self.undo_stack.push(rec);
        true
    }
}

fn dist2(a: [f64; 3], b: [f64; 3]) -> f64 {
    let dx = a[0] - b[0];
    let dy = a[1] - b[1];
    let dz = a[2] - b[2];
    dx * dx + dy * dy + dz * dz
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_delete_undo_redo_preserves_ids() {
        let mut bus = CommandBus::new(Molecule::new("test"));
        bus.execute(EditCommand::AddAtom {
            z: 6,
            pos: [0.0, 0.0, 0.0],
            pos2: [0.0, 0.0],
            bond_to: None,
            bond_order: 1,
        })
        .unwrap();
        bus.execute(EditCommand::AddAtom {
            z: 8,
            pos: [1.2, 0.0, 0.0],
            pos2: [1.2, 0.0],
            bond_to: Some(0),
            bond_order: 2,
        })
        .unwrap();
        assert_eq!(bus.mol.atoms.len(), 2);
        assert_eq!(bus.mol.bonds.len(), 1);
        assert_eq!(bus.mol.bonds[0].order, 2);

        bus.execute(EditCommand::DeleteAtoms { ids: vec![1] }).unwrap();
        assert_eq!(bus.mol.atoms.len(), 1);
        assert_eq!(bus.mol.bonds.len(), 0);

        assert!(bus.undo());
        assert_eq!(bus.mol.atoms.len(), 2);
        assert_eq!(bus.mol.bonds.len(), 1);
        assert_eq!(bus.mol.atoms[1].id, 1);

        assert!(bus.redo());
        assert_eq!(bus.mol.atoms.len(), 1);
        assert_eq!(bus.mol.bonds.len(), 0);
    }

    #[test]
    fn add_benzene_ring() {
        let mut bus = CommandBus::new(Molecule::new("ring"));
        bus.execute(EditCommand::AddRing {
            size: 6,
            aromatic: true,
            attach_to: None,
            center: [0.0, 0.0, 0.0],
            hetero: vec![],
        })
        .unwrap();
        assert_eq!(bus.mol.atoms.len(), 6);
        assert_eq!(bus.mol.bonds.len(), 6);
        assert!(bus.undo());
        assert_eq!(bus.mol.atoms.len(), 0);
    }

    #[test]
    fn thiophene_ring_hetero_and_set_bond_order() {
        let mut bus = CommandBus::new(Molecule::new("hetero"));
        bus.execute(EditCommand::AddRing {
            size: 5,
            aromatic: true,
            attach_to: None,
            center: [5.0, 5.0, 0.0],
            hetero: vec![(0, 16)],
        })
        .unwrap();
        assert_eq!(bus.mol.atoms[0].z, 16);
        assert!((bus.mol.atoms[0].pos[0] - 5.0).abs() < 2.0);
        bus.execute(EditCommand::SetBondOrder {
            a: 0,
            b: 1,
            order: 3,
        })
        .unwrap();
        assert_eq!(bus.mol.bond_between(0, 1).unwrap().order, 3);
        bus.execute(EditCommand::SetBondOrder {
            a: 0,
            b: 1,
            order: 4,
        })
        .unwrap();
        assert!(bus.mol.bond_between(0, 1).unwrap().aromatic);
        assert!(bus.undo());
        assert_eq!(bus.mol.bond_between(0, 1).unwrap().order, 3);
    }
}
