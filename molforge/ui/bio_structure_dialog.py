"""生物结构浏览对话框：显示 model / chain / residue 层级树与统计。"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QHBoxLayout)
from PyQt6.QtCore import Qt

from molforge.io.gemmi_adapter import BioStructure


class BioStructureDialog(QDialog):
    def __init__(self, bio: BioStructure, parent=None):
        super().__init__(parent)
        self.setWindowTitle("生物结构层级")
        self.resize(560, 620)
        layout = QVBoxLayout(self)

        summary = (
            f"<b>{bio.name}</b>　模型 {len(bio.models)}　"
            f"链 {bio.chain_count()}　原子 {bio.atom_count()}　"
            f"配体 {len(bio.ligand_residues)}")
        layout.addWidget(QLabel(summary))

        tree = QTreeWidget()
        tree.setHeaderLabels(["层级", "类型 / 数量"])
        for m in bio.models:
            mit = QTreeWidgetItem(tree, [f"模型 {m.model_num}",
                                         f"{len(m.chains)} 条链"])
            for c in m.chains:
                n_aa = sum(1 for r in c.residues if r.is_amino)
                n_w = sum(1 for r in c.residues if r.is_water)
                n_l = sum(1 for r in c.residues if r.is_ligand)
                cit = QTreeWidgetItem(mit, [
                    f"链 {c.chain_id}",
                    f"残基 {n_aa} · 水 {n_w} · 配体 {n_l}"])
                for r in c.residues:
                    if r.is_amino:
                        tag = "氨基酸"
                    elif r.is_nucleotide:
                        tag = "核苷酸"
                    elif r.is_water:
                        tag = "水"
                    else:
                        tag = "配体（RDKit）"
                    rit = QTreeWidgetItem(cit, [
                        f"{r.name} {r.seqid_num}{r.icode}",
                        f"{tag} · {len(r.atoms)} 原子"])
        tree.expandToDepth(1)
        layout.addWidget(tree)

        btns = QHBoxLayout()
        btns.addStretch()
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        layout.addLayout(btns)
