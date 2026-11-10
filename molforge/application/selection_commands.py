"""One user deletion is one undoable transaction, including attached hydrogens."""
from .commands import Command,CommandResult
from .builtin_commands import DeleteAtomCommand,DeleteBondCommand
class DeleteSelectionCommand(Command):
    description="删除选中的原子和键"
    requires_confirmation=True
    def __init__(self,atom_ids=(),bond_ids=()):
        self.atom_ids=tuple(atom_ids);self.bond_ids=tuple(bond_ids);self._applied=[]
    def do(self,doc):
        self._applied=[]
        atoms=sorted((a for a in self.atom_ids if a in doc.topology._atoms),key=lambda a:(doc.topology.get_atom(a).atomic_num==1,-a.value))
        for aid in atoms:
            if aid in doc.topology._atoms:
                cmd=DeleteAtomCommand(aid);result=cmd.do(doc)
                if not result.success:return self._rollback(doc,result)
                self._applied.append(cmd)
        for bid in self.bond_ids:
            if bid in doc.topology._bonds:
                cmd=DeleteBondCommand(bid);result=cmd.do(doc)
                if not result.success:return self._rollback(doc,result)
                self._applied.append(cmd)
        return CommandResult(success=True,changed=bool(self._applied),message="选中内容已作为一个操作删除")
    def _rollback(self,doc,result):
        for cmd in reversed(self._applied):cmd.undo(doc)
        self._applied=[]
        return result
    def undo(self,doc):
        for cmd in reversed(self._applied):
            result=cmd.undo(doc)
            if not result.success:return result
        return CommandResult(success=True,changed=bool(self._applied),message="已恢复整次删除")
