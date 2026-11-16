"""End-to-end localhost/stdio MCP binding to the active desktop document."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from molforge.ai.mcp.desktop_service import DesktopMCPService
from molforge.application.command_bus import CommandBus
from molforge.domain.document import MoleculeDocument


class DesktopMCPBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # This service drives GUI documents in production.  Using QCoreApplication
        # here would poison later QWidget tests that reuse QApplication.instance().
        cls.app = QApplication.instance() or QApplication(["desktop_mcp_test"])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = Path(self.temp.name) / "desktop.json"
        self.doc_a = MoleculeDocument(name="Desktop-A")
        self.doc_b = MoleculeDocument(name="Desktop-B")
        self.bus_a = CommandBus(self.doc_a)
        self.bus_b = CommandBus(self.doc_b)
        self.current = [self.doc_a]
        self.service = DesktopMCPService(
            lambda: self.current[0],
            lambda: self.bus_a if self.current[0] is self.doc_a else self.bus_b,
            connection_path=self.connection,
        )
        self.service.start()

    def tearDown(self):
        self.service.stop()
        self.app.processEvents()
        self.temp.cleanup()

    def _external_stdio(self, requests):
        env = os.environ.copy()
        root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = root + os.pathsep + env.get("PYTHONPATH", "")
        process = subprocess.Popen(
            [sys.executable, "-m", "molforge.ai.mcp.mcp_server", "--desktop", "--connection", str(self.connection)],
            cwd=root,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        result = {}

        def communicate():
            payload = "\n".join(json.dumps(request) for request in requests) + "\n"
            stdout, stderr = process.communicate(payload, timeout=20)
            result["stdout"] = stdout
            result["stderr"] = stderr

        thread = threading.Thread(target=communicate, daemon=True)
        thread.start()
        while thread.is_alive():
            self.app.processEvents()
            thread.join(0.005)
        thread.join(1)
        self.assertFalse(thread.is_alive(), "external MCP stdio process did not finish")
        self.assertEqual(process.returncode, 0, result.get("stderr", ""))
        return [json.loads(line) for line in result["stdout"].splitlines() if line.strip()]

    def test_external_stdio_edits_and_follows_current_document(self):
        info = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_molecule_info", "arguments": {}}}
        add = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "add_atom", "arguments": {"atomic_num": 8, "x": 1.0, "y": 2.0, "z": 3.0}}}
        responses = self._external_stdio([info, add, info])
        first = json.loads(responses[0]["result"]["content"][0]["text"])
        last = json.loads(responses[2]["result"]["content"][0]["text"])
        self.assertEqual(first["name"], "Desktop-A")
        self.assertEqual(first["num_atoms"], 0)
        self.assertEqual(last["num_atoms"], 1)
        self.assertEqual(self.doc_a.num_atoms, 1)
        self.assertEqual(self.doc_b.num_atoms, 0)
        self.assertTrue(self.bus_a.undo().success)
        self.assertEqual(self.doc_a.num_atoms, 0)

        self.current[0] = self.doc_b
        switched = self._external_stdio([info])
        current = json.loads(switched[0]["result"]["content"][0]["text"])
        self.assertEqual(current["name"], "Desktop-B")
        self.assertEqual(current["num_atoms"], 0)


if __name__ == "__main__":
    unittest.main()
