"""Mol* 大分子视图 widget：离线 molstar.js + loadStructureFromData 加载 PDB。"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSlot, QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PyQt6.QtWebChannel import QWebChannel


class _Bridge(QObject):
    def __init__(self, on_status, on_picked, on_ready):
        super().__init__()
        self._on_status = on_status
        self._on_picked = on_picked
        self._on_ready = on_ready

    @pyqtSlot(str, bool)
    def onStatus(self, msg, is_error):
        self._on_status(msg, is_error)

    @pyqtSlot(str)
    def onPicked(self, loc):
        self._on_picked(loc)

    @pyqtSlot()
    def jsReady(self):
        self._on_ready()

    @pyqtSlot(str)
    def onLoaded(self, name):
        pass


class MolStarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._pending = None
        self.on_picked = None

        self.view = QWebEngineView(self)
        from ..runtime import data_dir
        root = data_dir()/"webengine"
        root.mkdir(exist_ok=True)
        self._profile = QWebEngineProfile(self)
        self._profile.setCachePath(str(root/"cache"))
        self._profile.setPersistentStoragePath(str(root/"storage"))
        self.view.setPage(QWebEnginePage(self._profile,self.view))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self._channel = QWebChannel()
        self._bridge = _Bridge(self._status, self._picked, self._ready_cb)
        self._channel.registerObject("pybridge", self._bridge)
        self.view.page().setWebChannel(self._channel)

        html = Path(__file__).parent.parent / "rendering" / "molstar_viewer2.html"
        self.view.setUrl(QUrl.fromLocalFile(str(html)))

    def _status(self, msg, is_error):
        print(f"[Mol*] {'ERR ' if is_error else ''}{msg}")

    def _picked(self, loc):
        if self.on_picked:
            self.on_picked(loc)

    def _ready_cb(self):
        self._ready = True
        if self._pending:
            text, name, fmt = self._pending
            self._pending = None
            self.load_pdb(text, name, fmt)

    def load_pdb(self, text: str, name: str = "structure", fmt: str = "pdb"):
        """加载 PDB/mmCIF 文本。未就绪时排队。fmt: 'pdb' 或 'mmcif'。"""
        if not self._ready:
            self._pending = (text, name, fmt)
            return
        js = f"loadStructure({_js_str(text)}, {_js_str(fmt)}, {_js_str(name)})"
        self.view.page().runJavaScript(js)

    def apply_preset(self, preset: str):
        """应用表示预设：cartoon / ball-and-stick / molecular-surface 等。"""
        if self._ready:
            self.view.page().runJavaScript(f"setPreset({_js_str(preset)})")

    def reset_camera(self):
        if self._ready:
            self.view.page().runJavaScript("resetCamera()")


def _js_str(s: str) -> str:
    import json
    return json.dumps(s)
