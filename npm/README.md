# @yangdw2024/molforge

> Cross-platform CLI & Node.js wrapper for **MolForge Studio v7.4.0** — Unified molecular science workstation.

---

## Features
- **2D Chemical Sketcher**: ChemDraw-grade 2D molecular drawing with aromatic rings, customizable functional groups, and SVG/PDF export.
- **3D Modeling & Quantum Chemistry**: Chem3D / GaussView alternative with interactive bond angle/dihedral measurement, Gaussian 16 / ORCA / Multiwfn job generation and post-processing.
- **2D-3D Bidirectional Live Sync**: Real-time SVD 3D-to-2D projection and force-field geometry optimization.
- **Massive System & MD Box Support**: High-performance PDB parser supporting 300,000+ atoms with CONECT bond reconstruction in seconds.
- **LLM / MCP Assistant Integration**: Direct AI agent molecular editing with undoable CommandBus transactions.

---

## Instant Execution via npx

Launch MolForge Studio directly without cloning the repository:

```bash
# Launch MolForge Workspace
npx @yangdw2024/molforge

# Launch 2D Chemical Sketcher directly
npx @yangdw2024/molforge --mode 2d

# Launch 3D Modeling directly
npx @yangdw2024/molforge --mode 3d

# Launch 2D-3D Live Split Screen
npx @yangdw2024/molforge --mode split

# Open a molecular file (.mforge, .gjf, .log, .xyz, .mol, .sdf, .pdb)
npx @yangdw2024/molforge molecule.pdb
```

---

## Python Runtime Requirements
MolForge requires Python 3.10+ with `PyQt6`, `rdkit`, `numpy`, and `pyvista`.
If running via `npx`, the wrapper will automatically detect existing Python/Conda environments or install `molforge-studio` via pip.

---

## License
Apache-2.0 License. Copyright 2026 MolForge Team (yangdw2024).
