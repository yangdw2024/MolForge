import sys, traceback
sys.path.insert(0, r"E:\YDW\Trae_Chemdraw\MolForge")
out = open(r"E:\YDW\Trae_Chemdraw\MolForge\qa_evidence\_tmp_load.txt", "w", encoding="utf-8")
try:
    from molforge.io.rdkit_adapter import load_molecule_document as L
    d = L(r"E:\YDW\Trae_Chemdraw\MolForge\samples\bio\4HHB.pdb")
    d = d[0] if isinstance(d, tuple) else d
    out.write(f"原子 {d.num_atoms} 键 {d.topology.num_bonds}\n")
except Exception:
    out.write("ERROR\n" + traceback.format_exc())
finally:
    out.close()
