//! MolForge native scientific core.
//!
//! Owns molecular state, undoable editing commands, periodic table & studio
//! color LUTs, file IO, binary `MOLF` scene serialization, geometric &
//! chemical summaries, quantum chemistry (Tight-Binding & optional CalChem
//! pure-Rust SCF/OPT), external engine orchestration, and an optional isolated
//! Python worker for RDKit/cclib/MDAnalysis extensions.

pub mod binary;
pub mod commands;
pub mod elements;
pub mod engines;
pub mod hub;
pub mod io;
pub mod jobs;
pub mod model;
pub mod presets;
pub mod python_worker;
pub mod qc;
pub mod skills;
pub mod summary;
pub mod workflow;

use thiserror::Error;

#[derive(Debug, Error)]
pub enum CoreError {
    #[error("atom {0} not found")]
    AtomNotFound(model::AtomId),
    #[error("bond {0} not found")]
    BondNotFound(model::BondId),
    #[error("bond between {0} and {1} not found")]
    BondPairNotFound(model::AtomId, model::AtomId),
    #[error("unknown element: {0}")]
    UnknownElement(String),
    #[error("invalid operation: {0}")]
    InvalidOp(String),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("parse error: {0}")]
    Parse(String),
    #[error("external tool error: {0}")]
    External(String),
}

pub type Result<T> = std::result::Result<T, CoreError>;
