---
name: molforge-workflow-20261103-190831-744973
description: "Review and adapt this exported MolForge molecular editing workflow. Original document: test"
---

# Recorded molecular editing workflow

Read operations.json for exact parameters, units and the chronological execute/undo/redo sequence.
The export describes edits in one session. It is not an executable macro or a universal chemistry recipe.
Before adapting, open the intended starting structure, verify elements, connectivity and atom IDs,
and save a new project on D/E. The current exported revision is the final state, not a starting snapshot.
IDs belong to the original document; map them explicitly before applying commands to another molecule.
Apply approved edits through CommandBus and verify counts, bonds, coordinates and undo after each step.
Reproduce undo/redo events as such; do not apply every listed command as a new forward edit.
Do not run serialized commands as Python or silently change imported coordinates.

## Recorded sequence

1. execute: 添加原子 (AddAtomCommand, r1)
2. execute: 添加原子 (AddAtomCommand, r2)
3. undo: 添加原子 (AddAtomCommand, r3)
4. redo: 添加原子 (AddAtomCommand, r4)

When the starting structure or mapping is unavailable, report that the workflow cannot yet be reproduced.
