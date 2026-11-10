"""构象生成与力场工作流（RDKit ETKDG + MMFF/UFF）。

设计要点：
- 相同 seed 可复现；
- 记录随机种子、力场、能量单位、失败原因；
- 输出多构象及其能量，可按 RMSD 去重。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ConformerResult:
    """单个构象。"""
    index: int
    coords: np.ndarray            # (N, 3)
    energy: Optional[float] = None   # kcal/mol
    energy_unit: str = "kcal/mol"
    minimized: bool = False


@dataclass
class ConformerEnsemble:
    """构象集合及其来源信息。"""
    method: str
    seed: int
    num_requested: int
    forcefield: Optional[str]
    conformers: list[ConformerResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.conformers)


def generate_conformers(rdkit_mol,
                        num_confs: int = 10,
                        seed: int = 42,
                        forcefield: str = "MMFF94",
                        minimize: bool = True,
                        rmsd_thresh: float = 0.5):
    """对 RDKit 分子生成多构象。

    参数
    ----
    rdkit_mol : rdkit Mol（会被复制，不修改原分子）
    num_confs : 期望构象数
    seed : 随机种子（相同 seed 可复现）
    forcefield : "MMFF94" / "UFF" / None（不做力场优化）
    minimize : 是否做力场能量最小化
    rmsd_thresh : RMSD 去重阈值（Å），<=0 表示不去重
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolDescriptors

    ensemble = ConformerEnsemble(
        method="ETKDGv3", seed=seed, num_requested=num_confs,
        forcefield=forcefield if minimize else None)

    # 原始输入原子数（保留输入顺序及已显式存在的氢）
    n_input = rdkit_mol.GetNumAtoms()
    mol = Chem.RWMol(rdkit_mol)
    mol = Chem.AddHs(mol)  # 加 H 提高嵌入成功率与力场稳定性

    params = AllChem.ETKDGv3()
    params.randomSeed = int(seed)
    params.numThreads = 1  # 单线程保证可复现

    ids = AllChem.EmbedMultipleConfs(mol, numConfs=int(num_confs), params=params)
    if not ids:
        ensemble.failures.append("ETKDG 嵌入失败：可能是结构过于复杂或受限")
        return ensemble, mol

    # 力场可用性
    ff_name = None
    if minimize:
        if forcefield and forcefield.upper().startswith("MMFF"):
            if AllChem.MMFFHasAllMoleculeParams(mol):
                ff_name = "MMFF94"
            else:
                ensemble.failures.append("MMFF 不适用该结构，回退 UFF")
                ff_name = "UFF"
        else:
            ff_name = "UFF"

    ensemble.forcefield = ff_name
    energies = {}
    converged = {}
    if minimize and ff_name:
        for cid in ids:
            try:
                if ff_name == "MMFF94":
                    result = AllChem.MMFFOptimizeMolecule(mol, confId=cid, maxIters=1000)
                    props = AllChem.MMFFGetMoleculeProperties(mol)
                    ff = AllChem.MMFFGetMoleculeForceField(mol, props, confId=cid)
                    energies[cid] = ff.CalcEnergy()
                else:
                    result = AllChem.UFFOptimizeMolecule(mol, confId=cid, maxIters=1000)
                    ff = AllChem.UFFGetMoleculeForceField(mol, confId=cid)
                    energies[cid] = ff.CalcEnergy()
                converged[cid] = result == 0
                if result != 0:
                    ensemble.failures.append(f"构象 {cid} 力场未收敛（状态 {result}）")
            except Exception as e:  # 单个构象失败不影响整体
                ensemble.failures.append(f"构象 {cid} 优化失败: {e}")

    # 收集构象（只取输入原子坐标，前 n_input 个），按能量排序
    raw = []
    for cid in ids:
        conf = mol.GetConformer(cid)
        all_coords = np.array(conf.GetPositions(), dtype=float)
        coords = all_coords[:n_input]
        raw.append((cid, coords, energies.get(cid)))

    if any(e is not None for _, _, e in raw):
        raw.sort(key=lambda x: (x[2] is None, x[2]))

    # Fixed atom correspondence, heavy atoms only. Kabsch does not mutate conformers.
    # This intentionally does not claim symmetry-equivalent permutations are searched.
    heavy = [i for i,a in enumerate(rdkit_mol.GetAtoms()) if a.GetAtomicNum() > 1]
    if not heavy: heavy = list(range(n_input))
    def aligned_rmsd(a,b):
        x=a[heavy]-a[heavy].mean(axis=0);y=b[heavy]-b[heavy].mean(axis=0)
        u,_,vt=np.linalg.svd(x.T@y);d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt)
        return float(np.sqrt(np.mean(np.sum((x@u@d@vt-y)**2,axis=1))))
    kept=[]
    for cid,coords,energy in raw:
        if rmsd_thresh and rmsd_thresh>0 and any(aligned_rmsd(coords,kcoords)<rmsd_thresh for _,kcoords,_ in kept):
            continue
        kept.append((cid,coords,energy))

    for i, (cid, coords, energy) in enumerate(kept):
        ensemble.conformers.append(ConformerResult(
            index=i, coords=coords,
            energy=energy,
            minimized=bool(converged.get(cid,False))))

    return ensemble, mol
