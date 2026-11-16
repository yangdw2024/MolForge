"""
domain/custom_fragments.py - 用户自定义结构砌块、分子与官能团片段分组管理
========================================================================
支持将当前编辑的分子或选中的结构片段保存为自定义砌块，支持自定义分组（文件夹分类），
空分组持久化保存与展示，跨会话持久化存储在 user_data 中。
"""
from __future__ import annotations

import json
from pathlib import Path
from ..runtime import data_dir

_DEFAULT_FRAGMENTS = [
    {
        "name": "咔唑 (Carbazole)",
        "smiles": "c1ccc2c(c1)[nH]c1ccccc12",
        "description": "经典空穴传输 / OSC 给体共轭单元",
        "group": "🌟 常用共轭骨架",
        "type": "fragment",
    },
    {
        "name": "芴核心 (Fluorene)",
        "smiles": "c1ccc2c(c1)Cc1ccccc12",
        "description": "聚芴类光电材料骨架",
        "group": "🌟 常用共轭骨架",
        "type": "fragment",
    },
    {
        "name": "并噻吩 (Thieno[3,2-b]thiophene)",
        "smiles": "c1sc2sccc2c1",
        "description": "高迁移率共轭高分子构筑基元",
        "group": "🌟 常用共轭骨架",
        "type": "fragment",
    },
    {
        "name": "苯并二噻吩 (BDT Core)",
        "smiles": "c1sc2c(c1)sc1ccsc12",
        "description": "非富勒烯受体与聚合物给体核心骨架",
        "group": "🌟 常用共轭骨架",
        "type": "fragment",
    },
]

DEFAULT_GROUP = "🌟 默认分组"
_INITIAL_GROUPS = [DEFAULT_GROUP, "🌟 常用共轭骨架", "📁 自定义分子", "📁 反应砌块"]


def _get_storage_path() -> Path:
    d = data_dir()
    return d / "custom_fragments.json"


def _get_groups_storage_path() -> Path:
    d = data_dir()
    return d / "custom_groups.json"


def load_custom_groups() -> list[str]:
    """读取所有已注册的自定义分组列表（包含空分组）。"""
    p = _get_groups_storage_path()
    groups: list[str] = []
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for g in data:
                        gs = str(g).strip()
                        if gs and gs not in groups:
                            groups.append(gs)
        except Exception:
            pass

    if not groups:
        groups = list(_INITIAL_GROUPS)

    # 确保已有砌块中的分组也被自动纳入
    frags = load_custom_fragments()
    for item in frags:
        grp = str(item.get("group", DEFAULT_GROUP)).strip() or DEFAULT_GROUP
        if grp not in groups:
            groups.append(grp)

    if DEFAULT_GROUP not in groups:
        groups.insert(0, DEFAULT_GROUP)

    return groups


def save_custom_groups(groups: list[str]) -> bool:
    """持久化保存分组列表。"""
    p = _get_groups_storage_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        cleaned = []
        for g in groups:
            gs = str(g).strip()
            if gs and gs not in cleaned:
                cleaned.append(gs)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_custom_groups() -> list[str]:
    """获取所有已定义的分组名称列表（保持顺序去重）。"""
    return load_custom_groups()


def add_custom_group(name: str) -> bool:
    """新建自定义分组并持久化存储（即便目前为空也能被即时渲染）。"""
    name = str(name).strip()
    if not name:
        return False
    groups = load_custom_groups()
    if name not in groups:
        groups.append(name)
        return save_custom_groups(groups)
    return True


def delete_custom_group(group_name: str) -> bool:
    """删除指定分组及其下的所有砌块。"""
    group_name = str(group_name).strip()
    # 1. 从分组列表中删除
    groups = load_custom_groups()
    groups = [g for g in groups if g != group_name]
    save_custom_groups(groups)

    # 2. 从砌块中删除该分组下的所有内容
    frags = load_custom_fragments()
    new_frags = [f for f in frags if str(f.get("group", "")).strip() != group_name]
    save_custom_fragments(new_frags)
    return True


def rename_custom_group(old_name: str, new_name: str) -> bool:
    """重命名分组。"""
    old_name = str(old_name).strip()
    new_name = str(new_name).strip()
    if not old_name or not new_name or old_name == new_name:
        return False

    groups = load_custom_groups()
    changed = False
    for i, g in enumerate(groups):
        if g == old_name:
            groups[i] = new_name
            changed = True
    if changed:
        save_custom_groups(groups)

    frags = load_custom_fragments()
    f_changed = False
    for f in frags:
        if str(f.get("group", "")).strip() == old_name:
            f["group"] = new_name
            f_changed = True
    if f_changed:
        save_custom_fragments(frags)
    return True


def load_custom_fragments() -> list[dict]:
    """读取已保存的自定义砌块列表，自动补齐 group 字段。"""
    p = _get_storage_path()
    if not p.exists():
        save_custom_fragments(_DEFAULT_FRAGMENTS)
        return [dict(x) for x in _DEFAULT_FRAGMENTS]
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            frags: list[dict] = []
            if isinstance(data, list):
                frags = data
            elif isinstance(data, dict) and "fragments" in data:
                frags = data["fragments"]
            for item in frags:
                if not item.get("group"):
                    item["group"] = DEFAULT_GROUP
            return frags
    except Exception:
        pass
    return [dict(x) for x in _DEFAULT_FRAGMENTS]


def save_custom_fragments(fragments: list[dict]) -> bool:
    """持久化保存自定义砌块列表。"""
    p = _get_storage_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(fragments, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_grouped_custom_fragments() -> dict[str, list[dict]]:
    """按分组整理的自定义砌块字典：{分组名: [砌块信息列表]}，确保所有已注册分组均呈现。"""
    all_groups = load_custom_groups()
    grouped: dict[str, list[dict]] = {g: [] for g in all_groups}
    frags = load_custom_fragments()
    for f in frags:
        grp = str(f.get("group", DEFAULT_GROUP)).strip() or DEFAULT_GROUP
        if grp not in grouped:
            grouped[grp] = []
        grouped[grp].append(f)
    return grouped


def add_custom_fragment(
    name: str,
    smiles: str,
    description: str = "",
    group: str = DEFAULT_GROUP,
    frag_type: str = "fragment",
) -> bool:
    """新增自定义砌块（若重名则覆盖更新其属性与分组）。"""
    name = name.strip()
    smiles = smiles.strip()
    group = group.strip() or DEFAULT_GROUP
    if not name or not smiles:
        return False

    # 确保该分组已在分组管理器中注册
    add_custom_group(group)

    frags = load_custom_fragments()
    for item in frags:
        if item.get("name") == name:
            item["smiles"] = smiles
            item["description"] = description
            item["group"] = group
            item["type"] = frag_type
            return save_custom_fragments(frags)
    frags.insert(0, {
        "name": name,
        "smiles": smiles,
        "description": description,
        "group": group,
        "type": frag_type,
    })
    return save_custom_fragments(frags)


def remove_custom_fragment(name: str) -> bool:
    """删除指定的自定义砌块。"""
    frags = load_custom_fragments()
    new_frags = [f for f in frags if f.get("name") != name]
    if len(new_frags) != len(frags):
        return save_custom_fragments(new_frags)
    return False
