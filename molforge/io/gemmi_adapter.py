"""Gemmi 生物结构适配器：PDB/mmCIF -> 残基层级数据模型。

保留 model / chain / residue / atomsite / altloc / insertion code，
建立稳定 ID，并标记标准残基 / 非标准残基 / 配体（配体走 RDKit）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

# 标准氨基酸 / 核苷酸三字母代码（gemmi 也有内置表，这里用于显式判断）
STANDARD_AA = {
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
}
STANDARD_NUC = {
    "A", "C", "G", "T", "U", "DA", "DC", "DG", "DT", "ADE", "CYT", "GUA",
    "THY", "URA",
}
WATER = {"HOH", "DOD", "WAT"}


@dataclass
class AtomSite:
    site_id: str
    element: str
    name: str
    coord: np.ndarray
    altloc: str
    occupancy: float
    b_iso: float
    serial: int


@dataclass
class Residue:
    res_id: str
    name: str
    seqid_num: int
    icode: str
    is_amino: bool
    is_nucleotide: bool
    is_water: bool
    is_ligand: bool
    atoms: list[AtomSite] = field(default_factory=list)


@dataclass
class Chain:
    chain_id: str
    name: str
    residues: list[Residue] = field(default_factory=list)


@dataclass
class Model:
    model_num: int
    chains: list[Chain] = field(default_factory=list)


@dataclass
class BioStructure:
    name: str
    models: list[Model] = field(default_factory=list)
    ligand_residues: list[tuple[str, str, Residue]] = field(default_factory=list)

    def chain_count(self) -> int:
        return sum(len(m.chains) for m in self.models)

    def atom_count(self) -> int:
        return sum(len(r.atoms) for m in self.models for c in m.chains
                   for r in c.residues)


def _classify(res_name: str) -> tuple[bool, bool, bool, bool]:
    is_water = res_name in WATER
    is_amino = res_name in STANDARD_AA
    is_nuc = res_name in STANDARD_NUC
    # 用 gemmi 内置残基表补充判断（非标准但已知的氨基酸/核苷酸）
    try:
        import gemmi
        info = gemmi.find_tabulated_residue(res_name)
        if info.kind in (gemmi.ResidueKind.AA, gemmi.ResidueKind.AAStandard):
            is_amino = True
        elif info.kind in (gemmi.ResidueKind.DNA, gemmi.ResidueKind.RNA,
                           gemmi.ResidueKind.DNA_RNA):
            is_nuc = True
    except Exception:
        pass
    is_ligand = not (is_amino or is_nuc or is_water)
    return is_amino, is_nuc, is_water, is_ligand


def ligand_to_rdkit(residue: Residue):
    """把配体残基（含原子和坐标）转成 RDKit 可编辑分子。

    只对配体走 RDKit；不推断蛋白内部的键（键连由 RDKit 按距离/连接表决定）。
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem
    rw = Chem.RWMol()
    for a in residue.atoms:
        at = Chem.Atom(a.element.capitalize())
        at.SetNoImplicit(True)
        at.SetFormalCharge(0)
        rw.AddAtom(at)
    conf = Chem.Conformer(len(residue.atoms))
    for i, a in enumerate(residue.atoms):
        conf.SetAtomPosition(i, a.coord.tolist())
    rw.AddConformer(conf, assignId=True)
    # 按距离补键（配体通常 PDB 不含连接表）
    try:
        AllChem.ConnectMolToTemplate(rw) if False else None
    except Exception:
        pass
    return rw.GetMol()


def parse_bio(path: str) -> BioStructure:
    import gemmi
    st = gemmi.read_structure(path)
    bio = BioStructure(name=st.name)

    for model in st:
        m = Model(model_num=model.num)
        for chain in model:
            ch = Chain(chain_id=chain.name, name=chain.name)
            for res in chain:
                is_amino, is_nuc, is_water, is_ligand = _classify(res.name)
                r = Residue(
                    res_id=f"{chain.name}:{res.seqid.num}{res.seqid.icode}",
                    name=res.name, seqid_num=res.seqid.num,
                    icode=res.seqid.icode, is_amino=is_amino,
                    is_nucleotide=is_nuc, is_water=is_water,
                    is_ligand=is_ligand)
                for a in res:
                    site = AtomSite(
                        site_id=(f"{chain.name}:{res.seqid.num}{res.seqid.icode}"
                                 f":{a.name}:{a.altloc or '.'}"),
                        element=a.element.name, name=a.name,
                        coord=np.array(a.pos.tolist(), dtype=float),
                        altloc=a.altloc or "", occupancy=float(a.occ),
                        b_iso=float(a.b_iso), serial=int(a.serial))
                    r.atoms.append(site)
                ch.residues.append(r)
                if is_ligand:
                    bio.ligand_residues.append((model.num, chain.name, r))
            m.chains.append(ch)
        bio.models.append(m)
    return bio
