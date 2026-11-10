"""
application/command_bus.py - 命令总线（支持无污染副本预览 + 自定义验证器 + 强不变量保证）
========================================================================================
"""

from __future__ import annotations

import copy
from typing import Callable

from ..domain.document import MoleculeDocument
from .commands import Command, CommandResult
from .history import UndoHistory


class CommandBus:
    """
    命令总线：所有修改的统一入口。
    """

    def __init__(self, document: MoleculeDocument) -> None:
        self.document = document
        self.history = UndoHistory(max_depth=100)
        self._listeners: list[Callable[[MoleculeDocument], None]] = []
        self._validators: list[Callable[[MoleculeDocument], list[str]]] = []

    def add_listener(self, listener: Callable[[MoleculeDocument], None]) -> None:
        """注册文档变更监听器（UI/渲染刷新用）。"""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[MoleculeDocument], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def add_validator(self, validator: Callable[[MoleculeDocument], list[str]]) -> None:
        """注册化学验证器。"""
        self._validators.append(validator)

    def _run_validators(self, doc: MoleculeDocument) -> list[str]:
        """运行文档内置验证与所有注册验证器。"""
        errors = list(doc.validate())
        for validator in self._validators:
            res = validator(doc)
            if res:
                errors.extend(res)
        return errors

    def preview(self, command: Command) -> tuple[CommandResult, list[str]]:
        """
        在深拷贝文档与深拷贝命令对象上预执行，绝不污染真实命令对象的内部状态（如 _added_atom_id）。
        """
        doc_copy = copy.deepcopy(self.document)
        cmd_copy = copy.deepcopy(command)
        result = cmd_copy.do(doc_copy)
        errors = self._run_validators(doc_copy)
        if getattr(command, "affects_geometry", True):
            import numpy as np
            for aid in self.document.topology.atom_ids:
                atom = self.document.topology.get_atom(aid)
                if not atom.properties.get("frozen") or aid not in doc_copy.topology._atoms:
                    continue
                before, after = self.document.get_atom_3d_pos(aid), doc_copy.get_atom_3d_pos(aid)
                if before is not None and (after is None or not np.allclose(before, after, atol=1e-5, rtol=0)):
                    errors.append(f"原子 {aid.value+1} 已冻结；请先解冻再改变其3D坐标")
        return result, errors

    def execute(self, command: Command) -> CommandResult:
        """执行命令：预览校验 -> 真实执行 -> 同步坐标 -> 入栈 -> 通知监听者。"""
        preview_result, errors = self.preview(command)
        if not preview_result.success:
            return preview_result

        if errors:
            return CommandResult(
                success=False,
                changed=False,
                message=f"化学验证失败: {'; '.join(errors)}",
                data={"errors": errors},
            )

        result = command.do(self.document)
        if result.success and result.changed:
            if self.document.has_3d:
                self.document.ensure_coordinates()
            if getattr(command, "affects_geometry", True):
                self.document.sync_2d_coords_from_3d()
            self.history.push(command)
            self.document.bump_revision()
            self.history.record("execute", command, self.document)
            self._notify_change()

        return result

    def undo(self) -> CommandResult:
        """撤销上一条命令。"""
        command = self.history.pop_undo()
        if command is None:
            return CommandResult(success=False, message="没有可撤销的操作")

        result = command.undo(self.document)
        if result.success:
            if self.document.has_3d:
                self.document.ensure_coordinates()
            if getattr(command, "affects_geometry", True):
                self.document.sync_2d_coords_from_3d()
            self.document.bump_revision()
            self.history.record("undo", command, self.document)
            self._notify_change()
        return result

    def redo(self) -> CommandResult:
        """重做下一条命令。"""
        command = self.history.pop_redo()
        if command is None:
            return CommandResult(success=False, message="没有可重做的操作")

        result = command.do(self.document)
        if result.success:
            if self.document.has_3d:
                self.document.ensure_coordinates()
            if getattr(command, "affects_geometry", True):
                self.document.sync_2d_coords_from_3d()
            self.document.bump_revision()
            self.history.record("redo", command, self.document)
            self._notify_change()
        return result

    @property
    def can_undo(self) -> bool:
        return self.history.can_undo

    @property
    def can_redo(self) -> bool:
        return self.history.can_redo

    def _notify_change(self) -> None:
        for listener in self._listeners:
            listener(self.document)
