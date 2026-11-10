"""Export an inspectable workflow, never execute serialized Python commands."""
from pathlib import Path
from datetime import datetime
import json
import os


def export_history_skill(document, events, parent: Path) -> Path:
    parent = parent.resolve()
    if os.name == 'nt' and parent.drive.upper() not in ('D:', 'E:'):
        raise ValueError('技能与记录必须保存在 D/E 盘')
    if not events:
        raise ValueError('没有可导出的编辑命令')
    name = 'molforge-workflow-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder = parent / name
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'operations.json').write_text(json.dumps({
        'document_name': document.name, 'revision_at_export': document.revision,
        'scope': 'current session; document-specific IDs; chronological execute/undo/redo',
        'events': events,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    steps = '\n'.join(f"{i}. {event['action']}: {event['description']} ({event['command']}, r{event['revision']})" for i, event in enumerate(events, 1))
    description = json.dumps('Review and adapt this exported MolForge molecular editing workflow. Original document: ' + document.name, ensure_ascii=False)
    (folder/'SKILL.md').write_text(f'''---
name: {name}
description: {description}
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

{steps}

When the starting structure or mapping is unavailable, report that the workflow cannot yet be reproduced.
''', encoding='utf-8')
    return folder
