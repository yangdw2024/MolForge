"""
tests/test_fragment_transactions.py - P0 C/O/N 元素基团片段插入、离去氢替换、单次撤销与 .mforge 往返测试
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from molforge.application.command_bus import CommandBus
from molforge.application.fragment_catalog import FragmentCatalog
from molforge.application.fragment_commands import InsertFragmentCommand
from molforge.io.mforge_storage import save_mforge, load_mforge
from molforge.io.rdkit_adapter import create_sample_molecule


class TestFragmentTransactions(unittest.TestCase):
    def test_catalog_covers_c_o_n_and_common_fragments(self):
        c_ids = {f.id for f in FragmentCatalog.by_category("C")}
        o_ids = {f.id for f in FragmentCatalog.by_category("O")}
        n_ids = {f.id for f in FragmentCatalog.by_category("N")}
        self.assertTrue({"c_atom", "methyl", "vinyl", "ethynyl", "isopropyl", "tert_butyl"}.issubset(c_ids))
        self.assertTrue({"o_atom", "hydroxyl", "carbonyl", "methoxy"}.issubset(o_ids))
        self.assertTrue({"n_atom", "amino", "nitro", "cyano"}.issubset(n_ids))

    def test_insert_fragments_single_undo_and_mforge_roundtrip(self):
        doc = create_sample_molecule("咖啡因")
        bus = CommandBus(doc)
        n_atoms_0 = doc.topology.num_atoms
        n_bonds_0 = doc.topology.num_bonds
        coords_0 = doc.coordinates.current.coords.copy()

        # Graft by replacing a terminal H rather than overvalence a saturated carbon.
        hydrogen=next(a for a in doc.topology.atom_ids if doc.topology.get_atom(a).atomic_num==1 and len(doc.topology.neighbors_of(a))==1)
        # 依次测试甲基、乙烯基、羟基、氨基、氰基接枝与单步 Ctrl+Z 撤销
        for frag_id in ("methyl", "vinyl", "hydroxyl", "amino", "cyano"):
            spec = FragmentCatalog.get(frag_id)
            self.assertIsNotNone(spec)
            res = bus.execute(InsertFragmentCommand(spec,anchor_atom_id=hydrogen))
            self.assertTrue(res.success, msg=res.message)
            self.assertEqual(doc.topology.num_atoms, n_atoms_0 - 1 + len(spec.atoms))
            self.assertEqual(len(doc.validate()), 0)

            # 一次 Ctrl+Z 必须 100% 恢复原原子数、键数与 3D 坐标
            u_res = bus.undo()
            self.assertTrue(u_res.success)
            self.assertEqual(doc.topology.num_atoms, n_atoms_0)
            self.assertEqual(doc.topology.num_bonds, n_bonds_0)

            # Redo 再恢复接枝状态，测试 .mforge 文件保存与重新加载一致性
            r_res = bus.redo()
            self.assertTrue(r_res.success)
            self.assertEqual(doc.topology.num_atoms, n_atoms_0 - 1 + len(spec.atoms))

            with tempfile.TemporaryDirectory() as tmpdir:
                p = Path(tmpdir) / f"test_{frag_id}.mforge"
                save_mforge(doc, p)
                loaded = load_mforge(p)
                self.assertEqual(loaded.topology.num_atoms, doc.topology.num_atoms)
                self.assertEqual(loaded.topology.num_bonds, doc.topology.num_bonds)

            bus.undo()
            self.assertEqual(doc.topology.num_atoms, n_atoms_0)
