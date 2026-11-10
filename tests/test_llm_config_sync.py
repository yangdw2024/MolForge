"""
tests/test_llm_config_sync.py - LLM 与 AI 助手端点配置统一性单元测试
=====================================================================
验证：
  1. set_llm_config 与 get_llm_config 全局单点真理与双向同步
  2. 面板配置与独立弹窗端点配置完全统一，消除分裂与二次配置
  3. 单元测试自动备份与恢复，绝不污染真实用户的持久化配置
"""

import unittest
from molforge.ai.mcp_bridge import get_llm_config, set_llm_config, MolForgeMCPBridge
from molforge.application.command_bus import CommandBus
from molforge.io.rdkit_adapter import create_sample_molecule


class TestLlmConfigSync(unittest.TestCase):
    def setUp(self):
        self.doc = create_sample_molecule("咖啡因")
        self.bus = CommandBus(self.doc)
        # 备份真实配置，确保测试不污染用户环境
        self._orig_cfg = get_llm_config()

    def tearDown(self):
        # 恢复真实配置
        if hasattr(self, "_orig_cfg") and self._orig_cfg:
            set_llm_config(
                self._orig_cfg.get("base_url", "http://127.0.0.1:8000/v1"),
                self._orig_cfg.get("api_key", "EMPTY"),
                self._orig_cfg.get("model", "default-model"),
            )

    def test_set_and_get_config_unification(self):
        # 1. 模拟用户配置自定义端点与自定义模型名
        test_url = "http://127.0.0.1:8045/v1"
        test_key = "sk-custom-test-key-999"
        test_model = "test-custom-model-v1"

        set_llm_config(test_url, test_key, test_model)

        # 2. 从全局读取验证
        cfg = get_llm_config()
        self.assertEqual(cfg["base_url"], test_url)
        self.assertEqual(cfg["api_key"], test_key)
        self.assertEqual(cfg["model"], test_model)

        # 3. 验证 Bridge 实例化时使用最新统一配置
        bridge = MolForgeMCPBridge(self.doc, self.bus)
        self.assertEqual(bridge.config["base_url"], test_url)
        self.assertEqual(bridge.config["api_key"], test_key)
        self.assertEqual(bridge.config["model"], test_model)

    def test_empty_key_normalization(self):
        set_llm_config("http://localhost:11434/v1", "", "qwen2.5:14b")
        cfg = get_llm_config()
        self.assertEqual(cfg["base_url"], "http://localhost:11434/v1")
        self.assertEqual(cfg["api_key"], "EMPTY")
        self.assertEqual(cfg["model"], "qwen2.5:14b")


if __name__ == "__main__":
    unittest.main()
