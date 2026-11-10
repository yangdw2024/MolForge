"""
rendering/ketcher_bridge.py - Ketcher 2D 编辑器桥接
====================================================
基于 QWebEngineView + Ketcher 的离线 2D 编辑器。

Ketcher 是一款开源的 Web 端化学结构编辑器。
官方网站：https://github.com/epam/ketcher
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSlot, QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout

# WebEngine 可能因 DLL 缺失加载失败，优雅降级
_WEBENGINE_AVAILABLE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
    _WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    QWebChannel = None


def is_ketcher_available() -> bool:
    """检查 Ketcher 是否可用。"""
    return _WEBENGINE_AVAILABLE


class _KetcherBridge(QObject):
    """Python ↔ Ketcher JS 桥接对象。"""

    def __init__(
        self,
        on_ready: Callable[[], None],
        on_change: Callable[[str], None],
        on_error: Callable[[str], None],
    ):
        super().__init__()
        self._on_ready = on_ready
        self._on_change = on_change
        self._on_error = on_error

    @pyqtSlot()
    def onReady(self):
        """Ketcher 初始化完成。"""
        self._on_ready()

    @pyqtSlot(str)
    def onMolfileChanged(self, molfile: str):
        """分子结构改变。"""
        self._on_change(molfile)

    @pyqtSlot(str)
    def onError(self, message: str):
        """错误回调。"""
        self._on_error(message)


class KetcherWidget(QWidget):
    """
    Ketcher 2D 编辑器组件。

    用法：
        widget = KetcherWidget()
        widget.load_molfile("C1=CC=CC=C1")  # 加载苯环
        molfile = widget.get_molfile()  # 获取 MOL 文件
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = None
        self._bridge = None
        self._ready = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _WEBENGINE_AVAILABLE:
            self._view = QWebEngineView()
            layout.addWidget(self._view)

            # WebChannel
            self._channel = QWebChannel()
            self._bridge = _KetcherBridge(
                on_ready=self._on_ready,
                on_change=self._on_change,
                on_error=self._on_error,
            )
            self._channel.registerObject("pyBridge", self._bridge)
            self._view.page().setWebChannel(self._channel)

            # 加载本地 Ketcher HTML
            html_path = Path(__file__).parent / "assets" / "ketcher" / "index.html"
            if html_path.exists():
                self._view.setUrl(QUrl.fromLocalFile(str(html_path)))
            else:
                # TODO: 显示占位符
                pass

    def _on_ready(self):
        """Ketcher 初始化完成。"""
        self._ready = True

    def _on_change(self, molfile: str):
        """分子结构改变。"""
        pass

    def _on_error(self, message: str):
        """错误。"""
        print(f"Ketcher 错误: {message}")

    def load_molfile(self, molfile: str):
        """加载 MOL 文件。"""
        if not self._ready or self._view is None:
            return
        js_code = f"ketcher.setMolecule(`{molfile}`)"
        self._view.page().runJavaScript(js_code)

    def get_molfile(self, callback: Callable[[str], None]):
        """获取 MOL 文件。"""
        if not self._ready or self._view is None:
            callback("")
            return
        self._view.page().runJavaScript(
            "ketcher.getMolfile()",
            callback,
        )
