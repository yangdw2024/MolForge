"""Regression unit tests for PDB serial collisions, element alignment, topology caching, SVG/MoveMultiAtoms3D commands, LLM history rollback, and internal import integrity."""
from __future__ import annotations

import ast
import importlib
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import numpy as np

from molforge.runtime import configure_runtime

configure_runtime()

from molforge.ai.mcp_bridge import MolForgeMCPBridge, get_llm_config, set_llm_config
from molforge.application.builtin_commands import MoveMultiAtoms3DCommand
from molforge.application.command_bus import CommandBus
from molforge.domain.document import MoleculeDocument
from molforge.io.rdkit_adapter import _parse_pdb_atom_element, parse_pdb_to_document
from molforge.io.writers.svg_writer import write_svg_2d


class BugfixRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pdb_element_column_alignment_rules(self):
        cases = [
            (" CA ", "", 6),
            (" CD1", "", 6),
            (" CE ", "", 6),
            (" PA ", "", 15),
            ("1H  ", "", 1),
            ("2HB ", "", 1),
            ("HG11", "", 1),
            ("HE21", "", 1),
            ("FE  ", "", 26),
            ("CA  ", "", 20),
            (" Cl ", "", 17),
            ("CA  ", "CA", 20),
            (" CA ", " C", 6),
        ]
        for raw_name, elem_col, expected_z in cases:
            self.assertEqual(
                _parse_pdb_atom_element(raw_name, elem_col),
                expected_z,
                msg=f"Failed for raw_name={raw_name!r}, elem_col={elem_col!r}",
            )

    def test_pdb_serial_collision_disambiguation(self):
        """Simulate decimal '20000' and colliding hex '20000' far apart in 3D space (Packmol >99999 pattern)."""
        lines = []
        # Cluster A (far negative coordinates) at early indices, using serial '19999', '20000', '20001'
        lines.append(f"ATOM  19999  C   RES A   1    {0.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00  0.00           C")
        lines.append(f"ATOM  20000  C   RES A   1    {1.500:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00  0.00           C")
        lines.append(f"ATOM  20001  C   RES A   1    {3.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00  0.00           C")
        # Cluster B (200 A away) with >99999 hex transition serials '1FFFF', '20000', '20001'
        lines.append(f"ATOM  1FFFF  C   RES B   2    {200.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00  0.00           C")
        lines.append(f"ATOM  20000  C   RES B   2    {201.500:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00  0.00           C")
        lines.append(f"ATOM  20001  C   RES B   2    {203.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00  0.00           C")
        # CONECT section with colliding serials in sequential order
        lines.append("CONECT1999920000")
        lines.append("CONECT200001999920001")
        lines.append("CONECT2000120000")
        lines.append("CONECT1FFFF20000")
        lines.append("CONECT200001FFFF20001")
        lines.append("CONECT2000120000")
        pdb_path = self.root / "collide.pdb"
        pdb_path.write_text("\n".join(lines) + "\nEND\n", encoding="utf-8")

        doc = parse_pdb_to_document(pdb_path)
        self.assertEqual(doc.topology.num_atoms, 6)
        self.assertEqual(doc.topology.num_bonds, 4)

        _, id_to_idx = doc.topology.atom_index_map()
        coords = doc.coordinates.current.coords
        for bid in doc.topology.bond_ids:
            b = doc.topology.get_bond(bid)
            d = float(np.linalg.norm(coords[id_to_idx[b.begin]] - coords[id_to_idx[b.end]]))
            self.assertLess(d, 2.5, msg=f"Cross-box bond collision detected: length={d}")

    def test_topology_index_cache_and_invalidation(self):
        doc = MoleculeDocument("cache_test")
        a1 = doc.topology.add_atom(6)
        a2 = doc.topology.add_atom(8)
        doc.ensure_coordinates().add_frame(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]], dtype=np.float32))

        idx_list_1, map_1 = doc.topology.atom_index_map()
        idx_list_2, map_2 = doc.topology.atom_index_map()
        self.assertIs(idx_list_1, idx_list_2)
        self.assertIs(map_1, map_2)
        self.assertEqual(doc.topology.index_of_atom(a2), 1)
        np.testing.assert_allclose(doc.get_atom_3d_pos(a2), [4.0, 5.0, 6.0])

        # Mutation must invalidate cache
        removed_atom = doc.topology.get_atom(a1)
        doc.topology.remove_atom(a1)
        idx_list_3, map_3 = doc.topology.atom_index_map()
        self.assertIsNot(idx_list_1, idx_list_3)
        self.assertEqual(map_3[a2], 0)

        doc.topology.restore_atom(removed_atom, index=0)
        self.assertEqual(doc.topology.index_of_atom(a1), 0)
        self.assertEqual(doc.topology.index_of_atom(a2), 1)

        b1 = doc.topology.add_bond(a1, a2, order=2)
        bl1, bm1 = doc.topology.bond_index_map()
        self.assertEqual(bm1[b1], 0)
        doc.topology.remove_bond(b1)
        bl2, bm2 = doc.topology.bond_index_map()
        self.assertEqual(len(bl2), 0)
        self.assertIsNot(bl1, bl2)

    def test_move_multi_atoms_3d_command_and_undo(self):
        doc = MoleculeDocument("move_multi")
        a1 = doc.topology.add_atom(6)
        a2 = doc.topology.add_atom(6)
        store = doc.ensure_coordinates()
        store.add_frame(np.array([[0.0, 0.0, 0.0], [1.5, 0.0, 0.0]], dtype=np.float32))
        doc.coords_2d[a1] = (0.0, 0.0)
        doc.coords_2d[a2] = (1.5, 0.0)

        bus = CommandBus(doc)
        old_pos = {a1: doc.get_atom_3d_pos(a1), a2: doc.get_atom_3d_pos(a2)}
        new_pos = {
            a1: np.array([2.0, 3.0, 0.0], dtype=np.float32),
            a2: np.array([3.5, 3.0, 0.0], dtype=np.float32),
        }
        cmd = MoveMultiAtoms3DCommand(
            old_pos,
            new_pos,
            description="批量平移",
            old_coords_2d={a1: (0.0, 0.0), a2: (1.5, 0.0)},
        )
        res = bus.execute(cmd)
        self.assertTrue(res.success)
        np.testing.assert_allclose(doc.get_atom_3d_pos(a1), [2.0, 3.0, 0.0])

        bus.undo()
        np.testing.assert_allclose(doc.get_atom_3d_pos(a1), [0.0, 0.0, 0.0])
        self.assertEqual(doc.coords_2d[a1], (0.0, 0.0))

    def test_write_svg_2d_outputs_valid_svg(self):
        doc = MoleculeDocument("water")
        o = doc.topology.add_atom(8)
        h1 = doc.topology.add_atom(1)
        h2 = doc.topology.add_atom(1)
        doc.topology.add_bond(o, h1, 1)
        doc.topology.add_bond(o, h2, 1)
        doc.coords_2d[o] = (0.0, 0.0)
        doc.coords_2d[h1] = (0.95, 0.0)
        doc.coords_2d[h2] = (-0.24, 0.92)
        svg_path = self.root / "water.svg"
        write_svg_2d(doc, svg_path)
        self.assertTrue(svg_path.is_file())
        self.assertIn("<svg", svg_path.read_text(encoding="utf-8").lower())

    def test_mcp_bridge_chat_rolls_back_history_on_http_error(self):
        doc = MoleculeDocument("bridge_test")
        doc.topology.add_atom(6)
        bridge = MolForgeMCPBridge(doc, CommandBus(doc))
        bridge.config = {
            "base_url": "http://127.0.0.1:8045/v1",
            "api_key": "EMPTY",
            "model": "gemini-3.8-flash",
            "temperature": 0.3,
            "max_tokens": 256,
            "reasoning_effort": "none",
        }
        initial_len = len(bridge.history)
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
            reply = bridge.chat("hello")
        self.assertIn("无法连接", reply)
        self.assertEqual(len(bridge.history), initial_len)

    def test_set_llm_config_preserves_model_params(self):
        orig = get_llm_config()
        try:
            set_llm_config(
                orig["base_url"],
                orig["api_key"],
                "gemini-3.8-flash",
                temperature=0.65,
                max_tokens=8192,
                reasoning_effort="medium",
            )
            cur = get_llm_config()
            self.assertAlmostEqual(cur["temperature"], 0.65, places=2)
            self.assertEqual(cur["max_tokens"], 8192)
            self.assertEqual(cur["reasoning_effort"], "medium")
        finally:
            set_llm_config(
                orig["base_url"],
                orig["api_key"],
                orig["model"],
                temperature=orig.get("temperature", 0.3),
                max_tokens=orig.get("max_tokens", 4096),
                reasoning_effort=orig.get("reasoning_effort", "none"),
            )

    def test_no_broken_internal_imports(self):
        pkg_root = Path(__file__).resolve().parents[1] / "molforge"
        errors = []
        for p in pkg_root.rglob("*.py"):
            if "workflows" in p.parts and "assets" in p.parts:
                continue
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            rel_parts = p.relative_to(pkg_root.parent).with_suffix("").parts
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if node.level > 0:
                        base = list(rel_parts[:-node.level])
                        full = ".".join(base + ([mod] if mod else []))
                    else:
                        full = mod
                    if not full.startswith("molforge"):
                        continue
                    for alias in node.names:
                        if alias.name == "*":
                            continue
                        try:
                            m = importlib.import_module(full)
                        except Exception as exc:
                            if "vtk" in str(exc) or "PyQt6" in str(exc):
                                continue
                            errors.append(f"{p.name}:{node.lineno} ImportError {full}: {exc}")
                            continue
                        if not hasattr(m, alias.name):
                            errors.append(f"{p.name}:{node.lineno} Missing {alias.name} in {full}")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
