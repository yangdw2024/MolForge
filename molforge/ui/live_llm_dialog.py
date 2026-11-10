"""Live document tools: network runs in a worker, document commands run on Qt thread."""
from __future__ import annotations
import html
import threading
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QMessageBox, QLabel
from ..ai.mcp_bridge import MolForgeMCPBridge, get_llm_config


class _ChatWorker(QThread):
    tool_requested = pyqtSignal(str, object, object)
    reply = pyqtSignal(str)

    def __init__(self, bridge, text, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.text = text

    def execute_tool(self, name, args):
        packet = {"event": threading.Event(), "result": None}
        self.tool_requested.emit(name, args, packet)
        if not packet["event"].wait(300):
            return {"ok": False, "error": "等待界面处理工具调用超时"}
        return packet["result"]

    def run(self):
        try:
            self.reply.emit(self.bridge.chat(self.text, tool_executor=self.execute_tool))
        except Exception as exc:
            self.reply.emit(f"对话失败：{exc}")


class LiveLlmDialog(QDialog):
    def __init__(self, parent, doc_provider):
        super().__init__(parent)
        self.provider = doc_provider
        self.bridge = None
        self.worker = None
        self.setWindowTitle("LLM 当前分子工具对话 (独立窗口)")
        self.resize(740, 560)
        lay = QVBoxLayout(self)

        cfg = get_llm_config()
        self.info_lbl = QLabel(f"接入端点: {cfg['base_url']}  |  模型: {cfg['model']}")
        self.info_lbl.setStyleSheet("color: #66DEC9; font-size: 11px; padding: 2px 0;")
        lay.addWidget(self.info_lbl)

        lay.addWidget(QLabel("网络请求在后台运行；修改结构先显示确认，经命令总线执行，可撤销。"))
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        lay.addWidget(self.history)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("读取当前分子、列出原子、运行平面性或提出修改指令...")
        self.send = QPushButton("发送")
        self.config = QPushButton("端点配置")
        row.addWidget(self.input, 1)
        row.addWidget(self.send)
        row.addWidget(self.config)
        lay.addLayout(row)

        self.send.clicked.connect(self.ask)
        self.input.returnPressed.connect(self.ask)
        self.config.clicked.connect(self.settings)

    def settings(self):
        from .llm_config_dialog import LlmConfigDialog
        dlg = LlmConfigDialog(self)
        if dlg.exec():
            cfg = get_llm_config()
            self.info_lbl.setText(f"接入端点: {cfg['base_url']}  |  模型: {cfg['model']}")
            if self.bridge:
                self.bridge.config = cfg

    def ask(self):
        text = self.input.text().strip()
        if not text or (self.worker and self.worker.isRunning()):
            return
        doc = self.provider()
        if doc is None:
            QMessageBox.warning(self, "无分子", "当前没有打开的分子文档")
            return
        owner = self.parent()
        bus = getattr(owner, 'command_bus', None)
        if bus is None or bus.document is not doc:
            QMessageBox.warning(self, "未连接", "当前窗口的命令总线与文档不一致")
            return
        if self.bridge is None or self.bridge.document is not doc:
            self.bridge = MolForgeMCPBridge(doc, bus)
        # 始终同步最新大模型配置
        self.bridge.config = get_llm_config()

        self.input.clear()
        self.history.append("你：" + html.escape(text))
        self.send.setEnabled(False)
        self.config.setEnabled(False)

        self.worker = _ChatWorker(self.bridge, text, self)
        self.worker.tool_requested.connect(self.tool)
        self.worker.reply.connect(self.answer)
        self.worker.finished.connect(lambda: self.send.setEnabled(True))
        self.worker.finished.connect(lambda: self.config.setEnabled(True))
        self.worker.start()

    def tool(self, name, args, packet):
        try:
            if name in {'add_atom', 'delete_atom', 'add_bond'}:
                allowed = QMessageBox.question(
                    self,
                    "确认分子修改",
                    f"模型请求 {name}\n参数：{args}\n对当前分子执行？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if allowed != QMessageBox.StandardButton.Yes:
                    packet['result'] = {'ok': False, 'error': '用户拒绝修改'}
                    return
            packet['result'] = self.bridge.dispatch(name, args)
            self.history.append("工具 " + html.escape(name) + "：" + html.escape(str(packet['result'])[:140]))
        except Exception as exc:
            packet['result'] = {'ok': False, 'error': str(exc)}
        finally:
            packet['event'].set()

    def answer(self, text):
        self.history.append("模型：" + html.escape(text))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "对话进行中", "请等待当前请求结束后关闭。")
            event.ignore()
            return
        super().closeEvent(event)
