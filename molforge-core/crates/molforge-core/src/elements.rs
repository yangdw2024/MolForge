//! Periodic table (118 elements) generated from the MolForge reference data
//! (`tools/export_elements.py`), so the Rust core and the legacy Python code
//! share one source of truth for radii, masses and CPK colours.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::OnceLock;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Element {
    pub z: u8,
    pub symbol: String,
    pub name: String,
    pub name_cn: String,
    pub weight: f64,
    pub en: Option<f64>,
    pub vdw: f64,
    pub cov: f64,
    pub config: String,
    pub group: u8,
    pub period: u8,
    pub block: String,
    pub category: String,
    pub cpk: [f64; 3],
    pub studio: Option<[f64; 3]>,
}

#[derive(Deserialize)]
struct Table {
    default_vdw: f64,
    elements: Vec<Element>,
}

struct Loaded {
    table: Table,
    by_symbol: HashMap<String, usize>,
}

static LOADED: OnceLock<Loaded> = OnceLock::new();

fn loaded() -> &'static Loaded {
    LOADED.get_or_init(|| {
        let table: Table = serde_json::from_str(include_str!("data/elements.json"))
            .expect("embedded elements.json must be valid");
        let by_symbol = table
            .elements
            .iter()
            .enumerate()
            .map(|(i, e)| (e.symbol.to_ascii_lowercase(), i))
            .collect();
        Loaded { table, by_symbol }
    })
}

pub fn all() -> &'static [Element] {
    &loaded().table.elements
}

pub fn by_z(z: u8) -> Option<&'static Element> {
    all().iter().find(|e| e.z == z)
}

pub fn by_symbol(symbol: &str) -> Option<&'static Element> {
    let l = loaded();
    l.by_symbol
        .get(&symbol.trim().to_ascii_lowercase())
        .map(|&i| &l.table.elements[i])
}

pub fn symbol_of(z: u8) -> &'static str {
    by_z(z).map(|e| e.symbol.as_str()).unwrap_or("X")
}

pub fn default_vdw() -> f64 {
    loaded().table.default_vdw
}

/// Van der Waals radius in angstrom (falls back to the project default).
pub fn vdw(z: u8) -> f32 {
    by_z(z).map(|e| e.vdw as f32).unwrap_or(default_vdw() as f32)
}

pub fn covalent(z: u8) -> f64 {
    by_z(z).map(|e| e.cov).unwrap_or(1.5)
}

pub fn weight(z: u8) -> f64 {
    by_z(z).map(|e| e.weight).unwrap_or(0.0)
}

/// Studio colour: explicit MolForge override first, then CPK, then neutral grey.
/// Matches `api_bridge._build_luts` so the renderer output is unchanged.
pub fn rgb(z: u8) -> [u8; 3] {
    let to_u8 = |c: [f64; 3]| {
        [
            (c[0] * 255.0).round().clamp(0.0, 255.0) as u8,
            (c[1] * 255.0).round().clamp(0.0, 255.0) as u8,
            (c[2] * 255.0).round().clamp(0.0, 255.0) as u8,
        ]
    };
    match by_z(z) {
        Some(e) => to_u8(e.studio.unwrap_or(e.cpk)),
        None => [140, 158, 178],
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn has_118_elements_with_sane_data() {
        assert_eq!(all().len(), 118);
        let c = by_symbol("C").unwrap();
        assert_eq!(c.z, 6);
        assert!((c.weight - 12.011).abs() < 0.01);
        assert_eq!(by_symbol("pt").unwrap().z, 78);
        assert_eq!(symbol_of(8), "O");
        assert_eq!(symbol_of(200), "X");
    }

    #[test]
    fn colour_matches_python_lut_rules() {
        // unknown element -> grey default used by the Python bridge
        assert_eq!(rgb(0), [140, 158, 178]);
        // every known element yields a valid colour
        for e in all() {
            let _ = rgb(e.z);
        }
    }
}
