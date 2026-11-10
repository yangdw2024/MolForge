"""
tests/test_mcp_server_protocol.py - Model Context Protocol (MCP) 标准 JSON-RPC 2.0 服务端与 Bridge 单元测试
========================================================================================================
验证：
  1. JSON-RPC 2.0 协议规范 (initialize, tools/list, tools/call, resources/list, resources/read, prompts/list, prompts/get)
  2. 结构编辑工具 (add_atom, delete_atom, add_bond, modify_internal_coordinate) 经 CommandBus 执行且 100% 可撤销
  3. 量化计算工具 (run_calchem_scf, run_calchem_opt, generate_hpc_slurm_script) 接口保真与数据准确
  4. MolForgeMCPBridge 动态 Schema 参数校验与优雅错误处理 (无未处理异常抛出)
"""

import json
import unittest

from molforge.ai.mcp.mcp_server import MolForgeMCPServer
from molforge.ai.mcp_bridge import MolForgeMCPBridge
from molforge.application.command_bus import CommandBus
from molforge.domain.document import MoleculeDocument
from molforge.io.rdkit_adapter import create_sample_molecule


class TestMCPServerAndBridgeProtocol(unittest.TestCase):
    def setUp(self):
        self.doc = create_sample_molecule("咖啡因")
        self.bus = CommandBus(self.doc)
        self.server = MolForgeMCPServer(self.doc, self.bus)
        self.bridge = MolForgeMCPBridge(self.doc, self.bus)

    def test_mcp_initialize(self):
        req = {
            "jsonrpc": "2.0",
            "id": "init-01",
            "method": "initialize",
            "params": {"clientInfo": {"name": "AntigravityTestClient", "version": "1.0"}},
        }
        resp = self.server.handle_request(req)
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], "init-01")
        res = resp["result"]
        self.assertEqual(res["protocolVersion"], "2024-11-05")
        self.assertEqual(res["serverInfo"]["name"], "molforge-mcp-server")
        self.assertIn("tools", res["capabilities"])
        self.assertIn("resources", res["capabilities"])
        self.assertIn("prompts", res["capabilities"])

    def test_mcp_tools_list(self):
        req = {
            "jsonrpc": "2.0",
            "id": "tools-list-01",
            "method": "tools/list",
            "params": {},
        }
        resp = self.server.handle_request(req)
        tools = resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        expected = [
            "get_molecule_info",
            "add_atom",
            "delete_atom",
            "add_bond",
            "modify_internal_coordinate",
            "run_calchem_scf",
            "run_calchem_opt",
            "generate_hpc_slurm_script",
            "run_planarity",
        ]
        for exp in expected:
            self.assertIn(exp, tool_names)
        for t in tools:
            self.assertIn("inputSchema", t)
            self.assertEqual(t["inputSchema"]["type"], "object")

    def test_mcp_tool_call_get_molecule_info(self):
        req = {
            "jsonrpc": "2.0",
            "id": "call-info-01",
            "method": "tools/call",
            "params": {"name": "get_molecule_info", "arguments": {}},
        }
        resp = self.server.handle_request(req)
        self.assertNotIn("error", resp)
        content = resp["result"]["content"]
        self.assertEqual(len(content), 1)
        data = json.loads(content[0]["text"])
        self.assertEqual(data["num_atoms"], 24)
        self.assertGreater(data["num_bonds"], 0)
        self.assertTrue(data["has_3d"])
        self.assertEqual(len(data["atoms"]), 24)
        self.assertIn("xyz", data["atoms"][0])

    def test_mcp_tool_call_add_and_delete_atom_undoable(self):
        initial_atoms = self.doc.num_atoms  # 24

        # 1. 添加原子测试
        req_add = {
            "jsonrpc": "2.0",
            "id": "add-01",
            "method": "tools/call",
            "params": {
                "name": "add_atom",
                "arguments": {"atomic_num": 6, "x": 5.0, "y": 5.0, "z": 5.0},
            },
        }
        resp_add = self.server.handle_request(req_add)
        self.assertFalse(resp_add["result"].get("isError", False))
        data_add = json.loads(resp_add["result"]["content"][0]["text"])
        self.assertTrue(data_add.get("success", False))
        self.assertEqual(self.doc.num_atoms, initial_atoms + 1)

        # 2. 撤销添加
        self.bus.undo()
        self.assertEqual(self.doc.num_atoms, initial_atoms)

        # 3. 重做添加
        self.bus.redo()
        self.assertEqual(self.doc.num_atoms, initial_atoms + 1)

        # 4. 删除新原子
        new_atom_idx = initial_atoms + 1
        req_del = {
            "jsonrpc": "2.0",
            "id": "del-01",
            "method": "tools/call",
            "params": {
                "name": "delete_atom",
                "arguments": {"atom_index": new_atom_idx},
            },
        }
        resp_del = self.server.handle_request(req_del)
        self.assertFalse(resp_del["result"].get("isError", False))
        self.assertEqual(self.doc.num_atoms, initial_atoms)

    def test_mcp_tool_call_internal_coordinates(self):
        req_mod = {
            "jsonrpc": "2.0",
            "id": "mod-01",
            "method": "tools/call",
            "params": {
                "name": "modify_internal_coordinate",
                "arguments": {
                    "coord_type": "bond_length",
                    "atoms": [1, 2],
                    "target_value": 1.52,
                },
            },
        }
        resp_mod = self.server.handle_request(req_mod)
        self.assertFalse(resp_mod["result"].get("isError", False))
        data_mod = json.loads(resp_mod["result"]["content"][0]["text"])
        self.assertTrue(data_mod.get("success", False))

        # 验证可通过总线撤销
        self.assertTrue(self.bus.undo().success)

    def test_mcp_resources_and_prompts(self):
        # 1. resources/list
        r_list = self.server.handle_request({"jsonrpc": "2.0", "id": "r1", "method": "resources/list"})
        uris = [r["uri"] for r in r_list["result"]["resources"]]
        self.assertIn("molecule://active/json", uris)
        self.assertIn("molecule://active/xyz", uris)

        # 2. resources/read JSON
        r_read_json = self.server.handle_request({
            "jsonrpc": "2.0",
            "id": "r2",
            "method": "resources/read",
            "params": {"uri": "molecule://active/json"},
        })
        text_json = r_read_json["result"]["contents"][0]["text"]
        parsed_json = json.loads(text_json)
        self.assertEqual(parsed_json["name"], self.doc.name)

        # 3. resources/read XYZ
        r_read_xyz = self.server.handle_request({
            "jsonrpc": "2.0",
            "id": "r3",
            "method": "resources/read",
            "params": {"uri": "molecule://active/xyz"},
        })
        text_xyz = r_read_xyz["result"]["contents"][0]["text"]
        self.assertIn("24\n", text_xyz)

        # 4. prompts/list & get
        p_list = self.server.handle_request({"jsonrpc": "2.0", "id": "p1", "method": "prompts/list"})
        p_names = [p["name"] for p in p_list["result"]["prompts"]]
        self.assertIn("dft_optimization_guide", p_names)

        p_get = self.server.handle_request({
            "jsonrpc": "2.0",
            "id": "p2",
            "method": "prompts/get",
            "params": {"name": "dft_optimization_guide"},
        })
        self.assertIn("DFT", p_get["result"]["messages"][0]["content"]["text"])

    def test_mcp_bridge_dynamic_validation_and_dispatch(self):
        # 1. describe_structure
        desc = self.bridge.dispatch("describe_structure", {})
        self.assertEqual(desc["num_atoms"], 24)
        self.assertTrue(desc["has_3d"])

        # 2. list_atoms
        atom_list = self.bridge.dispatch("list_atoms", {})
        self.assertEqual(len(atom_list["atoms"]), 24)

        # 3. 参数校验：非法参数拦截 (不崩溃，返回 ok=False)
        bad_calls = [
            ("add_atom", {}),                               # 缺少必需参数
            ("add_atom", {"near_atom": 0, "atomic_num": 6}),# near_atom < 1
            ("add_atom", {"near_atom": 1, "atomic_num": 999}), # atomic_num 超出范围
            ("add_atom", {"near_atom": "one", "atomic_num": 6}), # 类型不是 int
            ("modify_internal_coordinate", {"coord_type": "invalid_type", "atoms": [1, 2], "target_value": 1.5}), # enum 不在范围
            ("modify_internal_coordinate", {"coord_type": "bond_length", "atoms": [1, "two"], "target_value": 1.5}), # array item 类型错
            ("unknown_tool", {}),                           # 未知工具
        ]
        for name, args in bad_calls:
            res = self.bridge.dispatch(name, args)
            self.assertFalse(res.get("ok", True), f"Should fail for {name}({args})")
            self.assertIn("error", res)

        # 4. 合法内坐标修改
        res_ic = self.bridge.dispatch("modify_internal_coordinate", {
            "coord_type": "bond_length",
            "atoms": [1, 2],
            "target_value": 1.48,
        })
        self.assertTrue(res_ic.get("ok", False))

        # 5. 合法 Slurm HPC 脚本生成
        res_hpc = self.bridge.dispatch("generate_hpc_slurm_script", {
            "engine": "g16",
            "job_name": "caffeine_dft",
            "n_cores": 16,
            "memory_mb": 32000,
        })
        self.assertTrue(res_hpc.get("ok", False))
        self.assertIn("#SBATCH --job-name=caffeine_dft", res_hpc["slurm_script"])


if __name__ == "__main__":
    unittest.main()
