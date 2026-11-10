"""
ui/i18n.py - 国际化（中英文切换）
=====================================
支持中英文界面切换。

用法：
    from .i18n import t, set_language
    set_language("zh")
    print(t("file.open"))  # 打开文件
"""

from __future__ import annotations

from typing import Callable


# 翻译字典
TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        # 通用
        "app.name": "MolForge",
        "app.tagline": "AI-native 分子科学工作台",

        # 顶部栏
        "topbar.search": "搜索工具和命令...",
        "topbar.project": "工作区",
        "topbar.export": "导出",

        # 左侧导航
        "nav.workspace": "工作区",
        "nav.molecules": "分子",
        "nav.fragments": "片段",
        "nav.templates": "模板",
        "nav.jobs": "计算任务",
        "nav.results": "结果",

        # 分子列表
        "molecules.title": "分子",
        "molecules.quick_insert": "快速插入",

        # 中央工作区
        "workspace.breadcrumb": "分子工作区",
        "workspace.structure_browser": "结构浏览器",
        "workspace.view_2d": "二维",
        "workspace.view_3d": "三维",
        "workspace.view_split": "分屏",

        # 工具栏
        "toolbar.select": "选择",
        "toolbar.atom": "原子",
        "toolbar.bond": "键",
        "toolbar.ring": "环",
        "toolbar.measure": "测量",
        "toolbar.cleanup": "清理",
        "toolbar.ball_stick": "球棍",
        "toolbar.cpk": "CPK",
        "toolbar.surface": "表面",

        # 右侧面板
        "right.panel_title": "助手与属性检查器",
        "right.tab_inspector": "属性检查",
        "right.tab_ai": "AI 助手",
        "right.tab_jobs": "任务",
        "right.tab_history": "历史",
        "right.tab_settings": "设置",

        # AI 助手
        "ai.current_context": "当前分子上下文",
        "ai.assistant_title": "MolForge 助手",
        "ai.explore_structure": "探索此结构",
        "ai.explore_hint": "询问键合、几何、构象，或准备计算任务。",
        "ai.suggested_actions": "建议操作",
        "ai.check_functional_groups": "检查官能团",
        "ai.generate_conformer": "生成构象",
        "ai.prepare_dft": "准备 DFT 计算",
        "ai.input_placeholder": "询问关于分子的问题...",

        # 状态栏
        "status.renderer": "渲染器",
        "status.fps": "FPS",
        "status.atoms": "原子",
        "status.bonds": "键",

        # 对话框
        "dialog.open_file": "打开文件",
        "dialog.save_file": "保存文件",
        "dialog.confirm": "确认",
        "dialog.cancel": "取消",
        "dialog.yes": "是",
        "dialog.no": "否",

        # 警告/错误
        "warning.stale": "数据已过期",
        "warning.topology_changed": "拓扑已改变，所有构象和计算结果已过期",
        "error.file_not_found": "文件不存在",
        "error.invalid_format": "无效的文件格式",

        # 设置
        "settings.theme": "主题",
        "settings.theme_dark": "深色",
        "settings.theme_light": "浅色",
        "settings.language": "语言",
        "settings.font_size": "字体大小",
        "settings.atom_scale": "原子大小",
        "settings.bond_radius": "键粗细",
    },

    "en": {
        # General
        "app.name": "MolForge",
        "app.tagline": "AI-native Molecular Workbench",

        # Top bar
        "topbar.search": "Search tools and commands...",
        "topbar.project": "Workspace",
        "topbar.export": "Export",

        # Left nav
        "nav.workspace": "Workspace",
        "nav.molecules": "Molecules",
        "nav.fragments": "Fragments",
        "nav.templates": "Templates",
        "nav.jobs": "Jobs",
        "nav.results": "Results",

        # Molecule list
        "molecules.title": "Molecules",
        "molecules.quick_insert": "Quick Insert",

        # Center workspace
        "workspace.breadcrumb": "Molecule Workspace",
        "workspace.structure_browser": "Structure Browser",
        "workspace.view_2d": "2D",
        "workspace.view_3d": "3D",
        "workspace.view_split": "Split",

        # Toolbar
        "toolbar.select": "Select",
        "toolbar.atom": "Atom",
        "toolbar.bond": "Bond",
        "toolbar.ring": "Ring",
        "toolbar.measure": "Measure",
        "toolbar.cleanup": "Cleanup",
        "toolbar.ball_stick": "Ball & Stick",
        "toolbar.cpk": "CPK",
        "toolbar.surface": "Surface",

        # Right panel
        "right.panel_title": "Assistant & Inspector",
        "right.tab_inspector": "Inspector",
        "right.tab_ai": "AI Assistant",
        "right.tab_jobs": "Jobs",
        "right.tab_history": "History",
        "right.tab_settings": "Settings",

        # AI Assistant
        "ai.current_context": "Current Molecule Context",
        "ai.assistant_title": "MolForge Assistant",
        "ai.explore_structure": "Explore Structure",
        "ai.explore_hint": "Ask about bonding, geometry, conformers, or prepare calculations.",
        "ai.suggested_actions": "Suggested Actions",
        "ai.check_functional_groups": "Check Functional Groups",
        "ai.generate_conformer": "Generate Conformer",
        "ai.prepare_dft": "Prepare DFT Calculation",
        "ai.input_placeholder": "Ask a question about the molecule...",

        # Status bar
        "status.renderer": "Renderer",
        "status.fps": "FPS",
        "status.atoms": "Atoms",
        "status.bonds": "Bonds",

        # Dialogs
        "dialog.open_file": "Open File",
        "dialog.save_file": "Save File",
        "dialog.confirm": "Confirm",
        "dialog.cancel": "Cancel",
        "dialog.yes": "Yes",
        "dialog.no": "No",

        # Warnings/Errors
        "warning.stale": "Data is stale",
        "warning.topology_changed": "Topology changed, all conformers and results are stale",
        "error.file_not_found": "File not found",
        "error.invalid_format": "Invalid file format",

        # Settings
        "settings.theme": "Theme",
        "settings.theme_dark": "Dark",
        "settings.theme_light": "Light",
        "settings.language": "Language",
        "settings.font_size": "Font Size",
        "settings.atom_scale": "Atom Scale",
        "settings.bond_radius": "Bond Radius",
    },
}


_current_language: str = "zh"
_listeners: list[Callable[[str], None]] = []


def set_language(lang: str) -> None:
    """设置当前语言。"""
    global _current_language
    if lang in TRANSLATIONS:
        _current_language = lang
        for listener in _listeners:
            listener(lang)


def get_language() -> str:
    """获取当前语言。"""
    return _current_language


def t(key: str, default: str | None = None) -> str:
    """翻译一个键。"""
    lang_dict = TRANSLATIONS.get(_current_language, {})
    if key in lang_dict:
        return lang_dict[key]
    # 回退到英文
    en_dict = TRANSLATIONS.get("en", {})
    if key in en_dict:
        return en_dict[key]
    # 回退到默认值或键本身
    return default if default is not None else key


def add_language_listener(listener: Callable[[str], None]) -> None:
    """添加语言切换监听器。"""
    _listeners.append(listener)


def get_available_languages() -> list[str]:
    """获取可用语言列表。"""
    return list(TRANSLATIONS.keys())
