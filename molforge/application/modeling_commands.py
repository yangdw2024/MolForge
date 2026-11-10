"""Undoable atom constraints and visual effects; scientific coordinates stay separate."""
from copy import deepcopy
import math
from .commands import Command, CommandResult
from typing import Iterable
from ..domain.document import MoleculeDocument
from ..domain.ids import AtomId, BondId


def connected_atoms(document: MoleculeDocument, seed: AtomId, blocked_bonds: Iterable[BondId] = ()) -> set[AtomId]:
    """Topology-connected component (not an inferred chemical functional group)."""
    found, pending = set(), [seed]
    while pending:
        aid = pending.pop()
        if aid in found or aid not in document.topology._atoms:
            continue
        found.add(aid)
        pending.extend(n for n in document.topology.neighbors_of(aid)
                       if document.topology.bond_between(aid,n) not in blocked_bonds)
    return found


class SetAtomPropertiesCommand(Command):
    affects_geometry = False
    description = '修改选中原子约束/显示效果'

    def __init__(self, atom_ids: Iterable[AtomId], *, frozen: bool | None = None, opacity: float | None = None,
                 glow_color: tuple[float,float,float] | None = None, glow: float | None = None) -> None:
        self.atom_ids = list(atom_ids)
        self.updates = {}
        if frozen is not None:
            self.updates['frozen'] = bool(frozen)
        for key, value in (('opacity', opacity), ('glow', glow)):
            if value is not None:
                value = float(value)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError(key + ' must be between 0 and 1')
                self.updates[key] = value
        if glow_color is not None:
            rgb = tuple(float(v) for v in glow_color)
            if len(rgb) != 3 or not all(math.isfinite(v) and 0 <= v <= 1 for v in rgb):
                raise ValueError('invalid glow RGB')
            self.updates['glow_color'] = list(rgb)
        self._before = {}

    def do(self, doc: MoleculeDocument) -> CommandResult:
        targets = [aid for aid in self.atom_ids if aid in doc.topology._atoms]
        if not targets or not self.updates:
            return CommandResult(False, message='没有目标原子或属性')
        for aid in targets:
            atom = doc.topology.get_atom(aid)
            if aid not in self._before:
                self._before[aid] = deepcopy(atom.properties)
            atom.properties.update(self.updates)
        return CommandResult(True, changed=True, message=f'已更新 {len(targets)} 个原子')

    def undo(self, doc: MoleculeDocument) -> CommandResult:
        for aid, values in self._before.items():
            if aid in doc.topology._atoms:
                doc.topology.get_atom(aid).properties = deepcopy(values)
        return CommandResult(True, changed=True)
