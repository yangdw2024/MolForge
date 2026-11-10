---
name: molforge-maintenance
description: Diagnose and repair MolForge molecular editing, desktop layout, chemistry display, and workflow-history regressions in the Trae_Chemdraw project. Use for this project's implementation and verification tasks.
---

# MolForge maintenance

The project is at E:/YDW/Trae_Chemdraw/MolForge. All generated files, temporary data,
backups and installations must stay on D/E; C is read-only. The existing Python is
D:/YDW/Trae_Gromacs/miniconda3/envs/molforge-webengine/python.exe. Use -B and
configure_runtime() before Qt/settings/temp-file work. Do not install another environment by default.

Read current docs/ISSUE_MATRIX_20261103.md and the newest dated repair report before
interpreting old completion claims. Save the current state, test criteria and a hashed
backup on E before important edits. Preserve user calculations and unsaved windows.

Molecular edits go through application/command_bus.py. Preserve stable AtomId/BondId;
displayed IDs are AtomId.value+1, not contiguous row positions. Selection bulk actions
should be one undoable transaction. Rebinding views must remove prior listeners.
Never call VTK Render or molecular mutation synchronously from QVTK input-event stacks;
use the existing deferred command path. Keep domain/application free of GUI imports.

For clipped controls, check natural size, layout minimum size and scrollbar height
together; a QScrollArea alone still permits compression. Test narrow windows and DPI.
Numbering requires painted output plus camera/resize/update checks, not only a true flag.
Use domain/elements.py as the shared radius source. Coordinates and measurements are Å;
CPK uses vdW radii at scale 1, ball-and-stick uses illustrative scaling. A covalent-radius
sum is a construction estimate; never silently normalize imported geometry.

Run targeted counterexamples, then affected existing scripts and tests. Distinguish
offscreen Qt checks from native desktop evidence. For native interaction, load the
available computer-use skill and use its window-selection and observe/action loop;
do not substitute custom Windows UI automation. User has two screens. If screenshot
capture fails, record that limitation and do not report a visual pass from UIA text.

For MD/quantum/LLM changes, read [references/scientific-boundaries.md](references/scientific-boundaries.md).
For operation-history skills, export actual CommandBus events with io/history_skill.py;
an undo stack alone is not a chronological history. Exported atom IDs require explicit
mapping and an original starting structure before reproduction. Never eval command JSON.
