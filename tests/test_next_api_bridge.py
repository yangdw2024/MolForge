"""Integration tests for MolForge Next Python HTTP + binary bridge."""
from __future__ import annotations

import json
import struct
import threading
import unittest
import urllib.request

from molforge.server.api_bridge import MAGIC_MOLF, start_bridge_server


class ApiBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.state = start_bridge_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _get_json(self, path: str):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_health_binary_stream_and_qc_endpoints(self):
        health = self._get_json("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["document"]["num_atoms"], 24)

        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/document/binary", timeout=5) as resp:
            raw = resp.read()
        hdr = struct.unpack("<8I", raw[:32])
        self.assertEqual(hdr[0], MAGIC_MOLF)
        self.assertEqual(hdr[2], 24)
        self.assertEqual(hdr[3], 25)

        tb = self._post_json("/api/qc/tight_binding", {})
        self.assertAlmostEqual(tb["homo_ev"], -5.9647, places=2)
        self.assertGreater(tb["gap_ev"], 1.0)

        ai = self._post_json("/api/ai/chat", {"prompt": "分析当前分子的能级与结构"})
        types = [b["type"] for b in ai["a2ui_blocks"]]
        self.assertIn("metrics_card", types)
        self.assertIn("orbital_card", types)

    def test_smiles_build_export_and_preset_switch(self):
        built = self._post_json("/api/build/smiles", {"smiles": "c1ccccc1", "name": "Benzene"})
        self.assertTrue(built["ok"])
        self.assertEqual(built["document"]["num_atoms"], 12)

        gjf = self._post_json("/api/qc/export_input", {"kind": "gaussian"})
        self.assertIn("#p", gjf["content"])

        rest = self._post_json("/api/qc/export_input", {"kind": "rest"})
        self.assertIn("[ctrl]", rest["content"])
        self.assertIn("[geom]", rest["content"])

    def test_interactive_editing_export_and_analysis_catalog(self):
        # Start on Benzene
        self._post_json("/api/build/smiles", {"smiles": "c1ccccc1", "name": "Benzene"})
        add_r = self._post_json("/api/edit/add_atom", {"atomic_num": 8, "pos_2d": [3.0, 0.0]})
        self.assertTrue(add_r["ok"])
        self.assertEqual(add_r["document"]["num_atoms"], 13)

        undo_r = self._post_json("/api/edit/undo", {})
        self.assertTrue(undo_r["ok"])
        self.assertEqual(undo_r["document"]["num_atoms"], 12)

        redo_r = self._post_json("/api/edit/redo", {})
        self.assertTrue(redo_r["ok"])
        self.assertEqual(redo_r["document"]["num_atoms"], 13)

        ring_r = self._post_json("/api/edit/add_ring", {"size": 6, "aromatic": True, "center_2d": [5.0, 2.0]})
        self.assertTrue(ring_r["ok"])
        self.assertGreaterEqual(ring_r["document"]["num_atoms"], 19)

        exp = self._post_json("/api/export", {"format": "xyz"})
        self.assertTrue(exp["ok"])
        self.assertIn("C", exp["content"])

        cat = self._get_json("/api/analysis/catalog")
        self.assertGreaterEqual(len(cat["items"]), 70)
        el_res = self._get_json("/api/elements")
        self.assertEqual(len(el_res["elements"]), 118)
        run_r = self._post_json("/api/analysis/run", {"analysis_id": "CORE-01"})
        self.assertTrue(run_r["ok"])
        self.assertIn("CORE-01", run_r["result"]["analysis_id"])


if __name__ == "__main__":
    unittest.main()
