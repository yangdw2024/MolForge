# MolForge scientific workflow adapters

`assets/` keeps the user supplied scripts and workflow notes for traceability. Runners in `scientific_workflows.py` are the supported entry points; the old scripts include workstation placeholders and should not be run directly without reviewing them.

## Connected in Results

- **ESP surface**: Gaussian `.fchk` → serial Multiwfn cube/surface passes → VMD rendering. Requires configured `MOLFORGE_MULTIWFN_PATH` and `MOLFORGE_VMD_PATH`. Original fchk and all process logs are preserved in a newly created output folder. ESP cube inputs are different grids by design. Descriptors are emitted only when their fields are found in the actual engine output.
- **HOMO/LUMO**: streamed alpha orbital extraction from fchk; optional same-name Gaussian log validation; Multiwfn cube generation and VMD rendering run sequentially. Outputs levels CSV/JSON/SVG and orbital BMPs. Open-shell jobs are currently not recommended for this closed-shell frontier workflow.
- **OSC levels**: requires at least two matching fchk/log pairs; discrepancies above 0.05 eV stop the workflow. Writes three editable SVG level layouts, CSV/JSON, Excel and PowerPoint when `requirements-workflows.txt` is installed.
- **Planarity**: best-fit plane on heavy atoms directly from fchk coordinates; writes RMSD, maximum absolute deviation, span, plane normal, and center.
- **Dipole**: reads the total vector from Gaussian fchk and reports a.u. and Debye. Fragment dipoles still need explicit fragment atom ranges and are not inferred.
- **Intermolecular contacts**: two 3D documents; reports explicit-H N/O/S hydrogen bonds and cross-molecule heavy atom contacts. Aromatic parallel/T-shaped ring stacks are detected when RDKit can identify aromatic rings.
- **MD**: optional MDAnalysis; outputs Kabsch-aligned RMSD and radius of gyration per frame, hydrogen-bond occupancy when topology permits, and coarse clustering by RMSD/Rg features. Unwrap periodic boundaries before analysis where required.
- **GROMACS component difference**: a CSV calculator for `E_AB - E_A - E_B` per shared energy component. This is force-field rerun decomposition and is not sobEDA.

Install optional scientific exports and MD support with `pip install -r requirements-workflows.txt`. Gaussian, Multiwfn, VMD, and GROMACS are not installed by MolForge; configure their existing executable paths in Engine Status. The ESP/HOMO workflows run one Multiwfn process at a time and keep their logs. No external process is launched in parallel.
