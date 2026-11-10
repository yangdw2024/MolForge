"""
application/plugins.py - 插件 SDK
=============================================
一切皆模块、一切皆插件。

插件系统：
  - 每个插件有 manifest（名称、版本、能力）
  - 生命周期 hook（init / activate / deactivate / shutdown）
  - 权限控制（只读 / 可编辑 / 可调用工具）
  - 故障隔离（插件崩溃不影响主程序）
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class PluginPermission(Enum):
    """插件权限级别。"""
    READ_ONLY = "read_only"      # 只读（不能修改文档）
    TOOL_CALL = "tool_call"      # 可以调用已授权工具
    FULL_ACCESS = "full_access"  # 完全访问（不推荐第三方插件）


@dataclass
class PluginManifest:
    """插件清单。"""
    name: str
    version: str
    description: str
    author: str
    api_version: str = "1.0"          # 插件针对的 SDK API 版本
    permissions: PluginPermission = PluginPermission.READ_ONLY
    capabilities: list[str] = field(default_factory=dict)  # 插件提供的能力


# 本 SDK 支持的 API 版本
SUPPORTED_API_VERSIONS = ("1.0",)


class ReadOnlyContext:
    """只读安全上下文：只暴露读取方法，不暴露任何修改入口。

    第三方只读插件拿到的是这个对象，无法改核心状态，也没有外发通道。
    """

    def __init__(self, document) -> None:
        self._document = document

    def num_atoms(self) -> int:
        return self._document.num_atoms

    def num_bonds(self) -> int:
        return self._document.num_bonds

    def atomic_numbers(self) -> list[int]:
        return [self._document.topology.get_atom(a).atomic_num
                for a in self._document.topology.atom_ids]

    def coordinates(self):
        cur = self._document.coordinates.current
        return cur.coords if cur is not None else None


def safe_invoke(func: Callable, *args, **kwargs):
    """故障隔离：调用插件 hook，捕获所有异常，不传播到主程序。"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"[plugin] hook 异常已隔离: {e}")
        return None


class Plugin:
    """
    插件基类。

    第三方插件应该继承这个类，实现自己的逻辑。
    """

    def __init__(self, manifest: PluginManifest) -> None:
        self.manifest = manifest
        self._activated = False

    def init(self, context: dict[str, Any]) -> None:
        """初始化插件（加载时调用一次）。"""
        pass

    def activate(self) -> None:
        """激活插件（用户启用时调用）。"""
        self._activated = True

    def deactivate(self) -> None:
        """停用插件（用户禁用时调用）。"""
        self._activated = False

    def shutdown(self) -> None:
        """关闭插件（程序退出时调用）。"""
        pass

    @property
    def is_activated(self) -> bool:
        return self._activated


class PluginManager:
    """
    插件管理器：加载、卸载、管理插件。

    用法：
        manager = PluginManager()
        manager.load_plugin("my_plugin")
        manager.activate_plugin("my_plugin")
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._context: dict[str, Any] = {}

    def set_context(self, context: dict[str, Any]) -> None:
        """设置插件上下文（文档、命令总线等）。"""
        self._context = context

    def load_plugin(self, plugin_module_path: str) -> Plugin:
        """
        加载插件。

        Args:
            plugin_module_path: 插件模块路径（如 "my_plugin.plugin"）

        Returns:
            Plugin 实例
        """
        # 动态导入模块
        module = importlib.import_module(plugin_module_path)

        # 找到 Plugin 子类
        plugin_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                plugin_class = obj
                break

        if plugin_class is None:
            raise ValueError(f"模块 {plugin_module_path} 中没有找到 Plugin 子类")

        # 创建插件实例
        plugin = plugin_class()

        # 版本检查：API 不兼容则拒绝加载
        if plugin.manifest.api_version not in SUPPORTED_API_VERSIONS:
            raise ValueError(
                f"插件 {plugin.manifest.name} 针对 API "
                f"{plugin.manifest.api_version}，本程序支持 "
                f"{SUPPORTED_API_VERSIONS}，拒绝加载")

        # 按权限给上下文：只读插件拿到受限上下文，不能改核心
        if plugin.manifest.permissions == PluginPermission.READ_ONLY:
            doc = self._context.get("document")
            ctx = ReadOnlyContext(doc) if doc is not None else {}
        else:
            ctx = self._context
        safe_invoke(plugin.init, ctx)

        self._plugins[plugin.manifest.name] = plugin
        return plugin

    def activate_plugin(self, name: str) -> None:
        """激活插件。"""
        plugin = self._plugins.get(name)
        if plugin:
            safe_invoke(plugin.activate)

    def deactivate_plugin(self, name: str) -> None:
        """停用插件。"""
        plugin = self._plugins.get(name)
        if plugin:
            safe_invoke(plugin.deactivate)

    def unload_plugin(self, name: str) -> None:
        """卸载插件。"""
        plugin = self._plugins.get(name)
        if plugin:
            safe_invoke(plugin.shutdown)
            del self._plugins[name]

    def get_plugin(self, name: str) -> Plugin | None:
        """获取插件。"""
        return self._plugins.get(name)

    def list_plugins(self) -> list[PluginManifest]:
        """列出所有已加载插件的清单。"""
        return [p.manifest for p in self._plugins.values()]
