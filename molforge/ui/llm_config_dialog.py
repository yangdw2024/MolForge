"""
llm_config_dialog.py - LLM（OpenAI 兼容端点）配置对话框
=====================================================
让用户配置 base_url / api_key / model，持久化到 QSettings("MolForge","LLM")。
配置供 MolForgeMCPBridge 的 function-calling 对话循环使用。
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel,
    QDialogButtonBox, QComboBox, QMessageBox
)

from ..ai.mcp_bridge import get_llm_config, set_llm_config, fetch_remote_models


class LlmConfigDialog(QDialog):
    """配置任意 OpenAI 兼容端点（本地 vLLM/Ollama/DeepSeek/OpenAI 等）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 接入设置（OpenAI 兼容端点）")
        self.resize(560, 260)
        cfg = get_llm_config()

        lay = QVBoxLayout(self)
        tip = QLabel(
            "💡 说明：当前已自动加载主面板中的大模型端点与密钥。在此处调整并保存后将全局同步生效。"
        )
        tip.setStyleSheet("color: #66DEC9; font-weight: 600; padding: 4px 0;")
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

        row_m = QHBoxLayout()
        self.ed_model = QComboBox()
        self.ed_model.setEditable(True)
        self.ed_model.addItem(cfg["model"])
        self.ed_model.setCurrentText(cfg["model"])
        self.ed_model.lineEdit().setPlaceholderText("如 gemini-3.8-flash / deepseek-chat")
        row_m.addWidget(self.ed_model, 1)

        self.btn_fetch = QPushButton("🔄 获取模型")
        self.btn_fetch.setToolTip("请求所填 Base URL 的 /v1/models 接口，拉取当前端点所有可用模型")
        self.btn_fetch.clicked.connect(self._fetch_models)
        row_m.addWidget(self.btn_fetch)

        form.addRow("模型名：", row_m)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _fetch_models(self):
        url = self.ed_url.text().strip()
        key = self.ed_key.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先填写 Base URL")
            return
        try:
            models = fetch_remote_models(url, key)
            if not models:
                QMessageBox.information(self, "提示", f"已连接至端点，但未返回模型列表。")
                return
            self.ed_model.clear()
            for m in models:
                self.ed_model.addItem(m)
            if "gemini-3.8-flash" in models:
                self.ed_model.setCurrentText("gemini-3.8-flash")
            elif "deepseek-chat" in models:
                self.ed_model.setCurrentText("deepseek-chat")
            QMessageBox.information(self, "获取模型成功", f"成功拉取到 {len(models)} 个可用模型！")
        except Exception as e:
            QMessageBox.warning(self, "获取失败", f"无法连接端点获取模型列表:\n{e}")

    def _save(self):
        url = self.ed_url.text().strip()
        if not url:
            url = "http://127.0.0.1:8045/v1"
        m_txt = self.ed_model.currentText().strip()
        if not m_txt or m_txt in ("default-model", "antigravity"):
            m_txt = "gemini-3.8-flash"
        cfg = get_llm_config()
        set_llm_config(
            url,
            self.ed_key.text().strip() or "EMPTY",
            m_txt,
            temperature=float(cfg.get("temperature", 0.3)),
            max_tokens=int(cfg.get("max_tokens", 4096)),
            reasoning_effort=str(cfg.get("reasoning_effort", "none")),
        )
        self.accept()
