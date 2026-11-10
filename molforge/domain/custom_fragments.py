"""
domain/custom_fragments.py - 用户自定义结构砌块与官能团片段管理
============================================================
支持将当前编辑的分子或选中的结构片段保存为自定义砌块，跨会话持久化存储在 user_data 中。
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
    },
    {
        "name": "芴核心 (Fluorene)",
        "smiles": "c1ccc2c(c1)Cc1ccccc12",
        "description": "聚芴类光电材料骨架",
    },
    {
        "name": "并噻吩 (Thieno[3,2-b]thiophene)",
        "smiles": "c1sc2sccc2c1",
        "description": "高迁移率共轭高分子构筑基元",
    },
    {
        "name": "苯并二噻吩 (BDT Core)",
        "smiles": "c1sc2c(c1)sc1ccsc12",
        "description": "非富勒烯受体与聚合物给体核心骨架",
    },
]


def _get_storage_path() -> Path:
    d = data_dir()
    return d / "custom_fragments.json"


def load_custom_fragments() -> list[dict]:
    """读取已保存的自定义砌块列表。"""
    p = _get_storage_path()
    if not p.exists():
        save_custom_fragments(_DEFAULT_FRAGMENTS)
        return list(_DEFAULT_FRAGMENTS)
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "fragments" in data:
                return data["fragments"]
    except Exception:
        pass
    return list(_DEFAULT_FRAGMENTS)


def save_custom_fragments(fragments: list[dict]) -> bool:
    """持久化保存自定义砌块列表。"""
    p = _get_storage_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(fragments, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def add_custom_fragment(name: str, smiles: str, description: str = "") -> bool:
    """新增自定义砌块（若重名则覆盖更新）。"""
    name = name.strip()
    smiles = smiles.strip()
    if not name or not smiles:
        return False
    frags = load_custom_fragments()
    for item in frags:
        if item.get("name") == name:
            item["smiles"] = smiles
            item["description"] = description
            return save_custom_fragments(frags)
    frags.insert(0, {"name": name, "smiles": smiles, "description": description})
    return save_custom_fragments(frags)


def remove_custom_fragment(name: str) -> bool:
    """删除指定的自定义砌块。"""
    frags = load_custom_fragments()
    new_frags = [f for f in frags if f.get("name") != name]
    if len(new_frags) != len(frags):
        return save_custom_fragments(new_frags)
    return False
