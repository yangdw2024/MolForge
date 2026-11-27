# MolForge Studio 8.1.0

Unified Molecular Science & Quantum Chemistry Workstation (**Electron 35 + React 19 + TypeScript + WebGPU + Pure Rust Core**).

## Architecture Overview

- **`desktop/`** — Cross-platform desktop workstation (React 19, Zustand, Tailwind CSS, WGSL WebGPU 3D viewport, 2D chemical sketcher, Multiwfn / CalChem / Gaussian / ORCA / REST / GROMACS workbench & floating HUDs).
- **`molforge-core/`** — Pure Rust backend (`molforge-server`) providing chemistry modeling, SMILES/MOL/SDF/PDB/XYZ/GJF/CIF I/O, tight-binding frontier orbitals, pure-Rust **MPP/SDP** planarity (`PROP-MPP`) & pairwise **RDF** (`MD-RDF`), **OSC 4-point reorganization energy**, **Multiwfn 3.8** (`WFN-01` ESP, `WFN-06` Mayer, `WFN-08` ADCH, `WFN-12` NCI/RDG), and native **CalChem v0.3.0** (`HF/RHF/UHF/RKS/UKS`, `B3LYP`, `B3LYP5`, `PBE`, `PBE0`, `BLYP`, `LDA/SVWN5`, `CAM-B3LYP`, `wB97X`, `wB97X-D` + dipole moments).
- **`pypi/`** — PyPI launcher & HTTP client CLI (`molforge-studio` `8.1.0`).
- **`npm/`** — npm Node.js CLI & programmatic wrapper (`@yangdw2024/molforge` `8.1.0`).

> Legacy PyQt6 `v7.4.3` codebase history is preserved on branch `legacy-v7` / tag `v7.4.3`.

## Quick Install

- **Windows Desktop Releases**: Download `MolForge-Studio-8.1.0-win-x64-setup.exe` or `MolForge-Studio-8.1.0-win-x64-portable.exe` from [GitHub Releases](https://github.com/yangdw2024/MolForge/releases/tag/v8.1.0).
- **npm CLI**:
  ```bash
  npx @yangdw2024/molforge --status
  npx @yangdw2024/molforge --server
  ```
- **PyPI CLI**:
  ```bash
  pip install -U molforge-studio
  molforge --status
  ```

## Local Development

```powershell
# Rust core server (with CalChem v0.3.0 sibling workspace)
cd molforge-core
cargo test --features calchem
cargo build --release --features calchem

# Desktop frontend & Electron
cd ../desktop
npm install
npm run typecheck
npm run lint
npm test
npm run pack:win
```

## License

Apache License 2.0 — see [LICENSE](./LICENSE).
