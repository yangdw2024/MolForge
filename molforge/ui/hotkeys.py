"""
ui/hotkeys.py - 2D 编辑器快捷键配置
====================================
专业化学软件的快捷键体系（参考 ChemDraw / MarvinSketch）。

约定：
  - 单字母无修饰 = 元素（C/N/O/S/P/F）或工具（V/B/R/E）
  - 翻转/旋转/视图等用 Ctrl，避免与元素键冲突
detect_conflicts() 可在启动时检查同一 (key, 修饰键组合) 是否被绑定多次。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hotkey:
    key: str
    modifiers: list[str] = field(default_factory=list)
    action: str = ""
    description: str = ""

    @property
    def chord(self) -> tuple[str, tuple[str, ...]]:
        return (self.key.lower(), tuple(sorted(self.modifiers)))


# 2D 编辑器快捷键（已消除冲突）
EDITOR_2D_HOTKEYS: list[Hotkey] = [
    # 工具切换（无修饰，不与元素重叠）
    Hotkey("V", [], "select", "选择工具"),
    Hotkey("B", [], "bond", "键工具"),
    Hotkey("R", [], "ring", "环工具"),
    Hotkey("E", [], "erase", "擦除工具"),

    # 元素（无修饰单字母）
    Hotkey("C", [], "atom_C", "碳"),
    Hotkey("N", [], "atom_N", "氮"),
    Hotkey("O", [], "atom_O", "氧"),
    Hotkey("S", [], "atom_S", "硫"),
    Hotkey("P", [], "atom_P", "磷"),
    Hotkey("F", [], "atom_F", "氟"),
    Hotkey("I", [], "atom_I", "碘"),
    Hotkey("H", [], "atom_H", "氢"),

    # 环模板（数字）
    Hotkey("1", [], "ring_benzene", "苯环"),
    Hotkey("2", [], "ring_cyclohexane", "环己烷"),
    Hotkey("3", [], "ring_cyclopentane", "环戊烷"),
    Hotkey("4", [], "ring_thiophene", "噻吩"),
    Hotkey("5", [], "ring_pyridine", "吡啶"),

    # 编辑操作（Ctrl）
    Hotkey("Z", ["Ctrl"], "undo", "撤销"),
    Hotkey("Y", ["Ctrl"], "redo", "重做"),
    Hotkey("C", ["Ctrl"], "copy", "复制"),
    Hotkey("X", ["Ctrl"], "cut", "剪切"),
    Hotkey("V", ["Ctrl"], "paste", "粘贴"),
    Hotkey("D", ["Ctrl"], "duplicate", "快速复制"),
    Hotkey("Delete", [], "delete", "删除选中"),

    # 视图 / 翻转 / 旋转（Ctrl，避免与元素 F 冲突）
    Hotkey("+", [], "zoom_in", "放大"),
    Hotkey("-", [], "zoom_out", "缩小"),
    Hotkey("0", [], "zoom_fit", "适应窗口"),
    Hotkey("F", ["Ctrl"], "flip_h", "水平翻转"),
    Hotkey("G", ["Ctrl"], "flip_v", "垂直翻转"),
    Hotkey("R", ["Ctrl"], "rotate", "旋转"),

    # 文件
    Hotkey("O", ["Ctrl"], "open", "打开文件"),
    Hotkey("S", ["Ctrl"], "save", "保存"),
    Hotkey("E", ["Ctrl", "Shift"], "export", "导出"),

    Hotkey("Space", [], "pan", "平移（按住）"),
    Hotkey("?", ["Shift"], "help", "快捷键帮助"),
]


GLOBAL_HOTKEYS: list[Hotkey] = [
    Hotkey("K", ["Ctrl"], "command_palette", "命令面板"),
    Hotkey("1", ["Ctrl"], "view_2d", "2D 视图"),
    Hotkey("2", ["Ctrl"], "view_3d", "3D 视图"),
    Hotkey("3", ["Ctrl"], "view_split", "分屏视图"),
    Hotkey("Tab", [], "switch_panel", "切换右侧面板"),
]


def detect_conflicts(hotkeys: list[Hotkey] | None = None) -> list[tuple]:
    """返回冲突列表：同一 (key, 修饰键) 绑定多个动作。"""
    if hotkeys is None:
        hotkeys = EDITOR_2D_HOTKEYS + GLOBAL_HOTKEYS
    seen: dict[tuple, list[str]] = {}
    for h in hotkeys:
        seen.setdefault(h.chord, []).append(h.action)
    return [(chord, acts) for chord, acts in seen.items() if len(acts) > 1]


def get_hotkey_map() -> dict[str, list[Hotkey]]:
    result: dict[str, list[Hotkey]] = {}
    for h in EDITOR_2D_HOTKEYS + GLOBAL_HOTKEYS:
        result.setdefault(h.action, []).append(h)
    return result


def format_hotkey(h: Hotkey) -> str:
    return "+".join(list(h.modifiers) + [h.key])
