//! Native molecule document model. The Rust core owns molecular state; no
//! Python object is needed to keep a molecule alive.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

pub type AtomId = u32;
pub type BondId = u32;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Atom {
    pub id: AtomId,
    pub z: u8,
    pub charge: i8,
    pub aromatic: bool,
    /// 3D position in angstrom.
    pub pos: [f64; 3],
    /// 2D drawing position (same length unit as the 3D coordinates).
    pub pos2: [f64; 2],
    pub color: Option<[u8; 3]>,
    pub scale: f32,
    pub opacity: f32,
}

impl Atom {
    pub fn new(id: AtomId, z: u8, pos: [f64; 3], pos2: [f64; 2]) -> Self {
        Self {
            id,
            z,
            charge: 0,
            aromatic: false,
            pos,
            pos2,
            color: None,
            scale: 1.0,
            opacity: 1.0,
        }
    }

    pub fn symbol(&self) -> &'static str {
        crate::elements::symbol_of(self.z)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Bond {
    pub id: BondId,
    pub a: AtomId,
    pub b: AtomId,
    pub order: u8,
    pub aromatic: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Cell {
    pub a: f64,
    pub b: f64,
    pub c: f64,
    pub alpha: f64,
    pub beta: f64,
    pub gamma: f64,
    pub space_group: String,
}

impl Cell {
    /// Row vectors a, b, c (angstrom). Same convention as the Python `UnitCell.matrix`.
    pub fn matrix(&self) -> Option<[[f64; 3]; 3]> {
        let (ar, br, gr) = (
            self.alpha.to_radians(),
            self.beta.to_radians(),
            self.gamma.to_radians(),
        );
        let sg = gr.sin();
        if sg.abs() < 1e-12 {
            return None;
        }
        let av = [self.a, 0.0, 0.0];
        let bv = [self.b * gr.cos(), self.b * sg, 0.0];
        let cx = self.c * br.cos();
        let cy = self.c * (ar.cos() - br.cos() * gr.cos()) / sg;
        let cz2 = self.c * self.c - cx * cx - cy * cy;
        if cz2 <= 1e-12 {
            return None;
        }
        Some([av, bv, [cx, cy, cz2.sqrt()]])
    }

    pub fn is_valid(&self) -> bool {
        let lens = [self.a, self.b, self.c];
        let angs = [self.alpha, self.beta, self.gamma];
        lens.iter().all(|v| v.is_finite() && *v > 0.0)
            && angs.iter().all(|v| v.is_finite() && *v > 0.0 && *v < 180.0)
            && self.matrix().is_some()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Molecule {
    pub document_id: String,
    pub name: String,
    pub atoms: Vec<Atom>,
    pub bonds: Vec<Bond>,
    pub next_atom: AtomId,
    pub next_bond: BondId,
    pub has_3d: bool,
    pub has_2d: bool,
    pub charge: Option<i32>,
    pub multiplicity: Option<u32>,
    pub revision: u64,
    pub cell: Option<Cell>,
    pub box_origin: [f64; 3],
    pub source_path: Option<String>,
    #[serde(skip)]
    index: HashMap<AtomId, usize>,
}

fn new_document_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    static COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let c = COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    format!("mf-{:x}-{:x}", t, c)
}

impl Molecule {
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            document_id: new_document_id(),
            name: name.into(),
            atoms: Vec::new(),
            bonds: Vec::new(),
            next_atom: 0,
            next_bond: 0,
            has_3d: false,
            has_2d: false,
            charge: None,
            multiplicity: None,
            revision: 0,
            cell: None,
            box_origin: [0.0; 3],
            source_path: None,
            index: HashMap::new(),
        }
    }

    pub fn reindex(&mut self) {
        self.index.clear();
        self.index.reserve(self.atoms.len());
        for (i, a) in self.atoms.iter().enumerate() {
            self.index.insert(a.id, i);
        }
    }

    pub fn atom_index(&self, id: AtomId) -> Option<usize> {
        self.index.get(&id).copied()
    }

    pub fn atom(&self, id: AtomId) -> Option<&Atom> {
        self.atom_index(id).map(|i| &self.atoms[i])
    }

    pub fn atom_mut(&mut self, id: AtomId) -> Option<&mut Atom> {
        match self.atom_index(id) {
            Some(i) => Some(&mut self.atoms[i]),
            None => None,
        }
    }

    pub fn bond(&self, id: BondId) -> Option<&Bond> {
        self.bonds.iter().find(|b| b.id == id)
    }

    pub fn bond_between(&self, a: AtomId, b: AtomId) -> Option<&Bond> {
        self.bonds
            .iter()
            .find(|x| (x.a == a && x.b == b) || (x.a == b && x.b == a))
    }

    pub fn neighbors(&self, id: AtomId) -> Vec<AtomId> {
        self.bonds
            .iter()
            .filter_map(|b| {
                if b.a == id {
                    Some(b.b)
                } else if b.b == id {
                    Some(b.a)
                } else {
                    None
                }
            })
            .collect()
    }

    /// Allocate an atom with a fresh, never-reused id (not yet inserted).
    pub fn alloc_atom(&mut self, z: u8, pos: [f64; 3], pos2: [f64; 2]) -> Atom {
        let id = self.next_atom;
        self.next_atom += 1;
        Atom::new(id, z, pos, pos2)
    }

    pub fn alloc_bond(&mut self, a: AtomId, b: AtomId, order: u8, aromatic: bool) -> Bond {
        let id = self.next_bond;
        self.next_bond += 1;
        Bond {
            id,
            a,
            b,
            order,
            aromatic,
        }
    }

    /// Build-time helper used by file readers (not undoable).
    pub fn push_atom(&mut self, z: u8, pos: [f64; 3], pos2: [f64; 2]) -> AtomId {
        let atom = self.alloc_atom(z, pos, pos2);
        let id = atom.id;
        self.index.insert(id, self.atoms.len());
        self.atoms.push(atom);
        id
    }

    pub fn push_bond(&mut self, a: AtomId, b: AtomId, order: u8, aromatic: bool) -> Option<BondId> {
        if a == b || self.atom(a).is_none() || self.atom(b).is_none() {
            return None;
        }
        if self.bond_between(a, b).is_some() {
            return None;
        }
        let bond = self.alloc_bond(a, b, order.clamp(1, 4), aromatic);
        let id = bond.id;
        self.bonds.push(bond);
        Some(id)
    }

    pub fn centroid(&self) -> [f64; 3] {
        if self.atoms.is_empty() {
            return [0.0; 3];
        }
        let mut s = [0.0; 3];
        for a in &self.atoms {
            for k in 0..3 {
                s[k] += a.pos[k];
            }
        }
        let n = self.atoms.len() as f64;
        [s[0] / n, s[1] / n, s[2] / n]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn push_and_lookup() {
        let mut m = Molecule::new("t");
        let a = m.push_atom(8, [0.0, 0.0, 0.0], [0.0, 0.0]);
        let b = m.push_atom(1, [0.96, 0.0, 0.0], [1.0, 0.0]);
        assert!(m.push_bond(a, b, 1, false).is_some());
        assert!(m.push_bond(b, a, 1, false).is_none(), "duplicate bond rejected");
        assert!(m.push_bond(a, a, 1, false).is_none(), "self bond rejected");
        assert_eq!(m.neighbors(a), vec![b]);
        assert_eq!(m.atom(b).unwrap().symbol(), "H");
    }

    #[test]
    fn cell_matrix_orthorhombic() {
        let c = Cell {
            a: 10.0,
            b: 20.0,
            c: 30.0,
            alpha: 90.0,
            beta: 90.0,
            gamma: 90.0,
            space_group: String::new(),
        };
        let m = c.matrix().unwrap();
        assert!((m[0][0] - 10.0).abs() < 1e-9);
        assert!((m[1][1] - 20.0).abs() < 1e-9);
        assert!((m[2][2] - 30.0).abs() < 1e-9);
        assert!(c.is_valid());
    }
}
