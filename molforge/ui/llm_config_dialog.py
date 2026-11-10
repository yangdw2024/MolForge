"""
llm_config_dialog.py - LLM（OpenAI 兼容端点）配置对话框
=====================================================
让用户配置 base_url / api_key / model，持久化到 QSettings("MolForge","LLM")。
配置供 MolForgeMCPBridge 的 function-calling 对话循环使用。
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel, QDialogButtonBox,
)

from ..ai.mcp_bridge import get_llm_config, set_llm_config


class LlmConfigDialog(QDialog):
    """配置任意 OpenAI 兼容端点（本地 vLLM/Ollama/DeepSeek/OpenAI 等）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 接入设置（OpenAI 兼容端点）")
        self.resize(560, 240)
        cfg = get_llm_config()

        lay = QVBoxLayout(self)
        tip = QLabel(
            "填写任意 OpenAI 兼容端点地址。MolForge 会以 function calling 方式让大模型读取当前结构、"
            "通过命令总线编辑原子/键（可撤销）、并调用平面性等分析工具。"
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        form = QFormLayout()
        self.ed_url = QLineEdit(cfg["base_url"])
        self.ed_url.setPlaceholderText("如 http://127.0.0.1:8000/v1")
        form.addRow("Base URL：", self.ed_url)

        self.ed_key = QLineEdit(cfg["api_key"])
        self.ed_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_key.setPlaceholderText("本地服务可填 EMPTY")
        form.addRow("API Key：", self.ed_key)

        self.ed_model = QLineEdit(cfg["model"])
        self.ed_model.setPlaceholderText("如 qwen2.5 / deepseek-chat / gpt-4o-mini")
        form.addRow("模型名：", self.ed_model)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _save(self):
        url = self.ed_url.text().strip()
        if not url:
            url = "http://127.0.0.1:8000/v1"
        set_llm_config(url, self.ed_key.text().strip() or "EMPTY", self.ed_model.text().strip() or "default-model")
        self.accept()
