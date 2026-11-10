"""
rendering/molstar_backend.py - Mol* 渲染后端
==============================================
基于 QWebEngineView + Mol* (WebGL) 的渲染后端。
实现 Renderer3D 接口，与 VtkRendererBackend 做 A/B 竞选。

技术栈：
  - QWebEngineView 嵌入 Mol* 网页
  - QWebChannel 实现 Python ↔ JS 双向通信
  - CDN 加载 Mol* JS（不需要本地安装）
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Sequence

from PyQt6.QtCore import QObject, pyqtSlot, QUrl

# WebEngine 可能因 DLL 缺失加载失败，优雅降级
_WEBENGINE_AVAILABLE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
    _WEBENGINE_AVAILABLE = True
except ImportError:
    QWebEngineView = None
    QWebChannel = None

from .contracts import Renderer3D, RenderSnapshot, RepresentationMode
from ..domain.ids import AtomId, BondId


def is_webengine_available() -> bool:
    """检查 WebEngine 是否可用（用于 A/B 竞选时判断）。"""
    return _WEBENGINE_AVAILABLE


class _PyBridge(QObject):
    """Python ↔ JS 桥接对象，注册到 WebChannel。"""

    def __init__(
        self,
        on_atom_click: Callable[[str, int], None],
        on_status: Callable[[str, bool], None],
        on_molecule_loaded: Callable[[int], None],
    ):
        super().__init__()
        self._on_atom_click = on_atom_click
        self._on_status = on_status
        self._on_molecule_loaded = on_molecule_loaded

    @pyqtSlot(str, int)
    def onAtomClicked(self, element: str, atomIndex: int):
        """JS 端点击原子时调用：传回元素符号和索引。"""
        self._on_atom_click(element, atomIndex)

    @pyqtSlot(str, bool)
    def onStatus(self, message: str, isError: bool):
        """JS 端状态日志回调。"""
        self._on_status(message, isError)

    @pyqtSlot(int)
    def onMoleculeLoaded(self, atomCount: int):
        """JS 端分子加载完成回调。"""
        self._on_molecule_loaded(atomCount)


class MolStarRendererBackend(Renderer3D):
    """
    Mol* 渲染后端（WebGL 路线）。

    与 VtkRendererBackend 实现同一个接口，用于 A/B 对比测试。
    """

    def __init__(self) -> None:
        self._view = None  # QWebEngineView
        self._channel = None
        self._bridge = None
        self._mode = RepresentationMode.BALL_AND_STICK
        self._selected: set[AtomId] = set()

        # 回调
        self._on_atom_click: Callable[[str, int], None] | None = None
        self._on_status: Callable[[str, bool], None] = lambda msg, err: print(f"[Mol*] {'ERROR: ' if err else ''}{msg}")
        self._on_molecule_loaded: Callable[[int], None] = lambda n: print(f"[Mol*] 分子加载完成，{n} 个原子")

        # 状态
        self._is_initialized = False
        self._atom_count = 0

    def attach(self, widget) -> None:
        """把渲染器挂到 QWebEngineView 上。"""
        if not _WEBENGINE_AVAILABLE:
            raise RuntimeError("WebEngine 不可用，无法初始化 Mol* 后端")

        self._view = QWebEngineView(widget)
        layout = widget.layout()
        if layout is None:
            from PyQt6.QtWidgets import QVBoxLayout
            layout = QVBoxLayout(widget)
            widget.setLayout(layout)
        layout.addWidget(self._view)

        # 加载 HTML
        html_path = Path(__file__).parent / "molstar_viewer.html"
        self._view.setUrl(QUrl.fromLocalFile(str(html_path)))

        # 设置 WebChannel
        self._channel = QWebChannel()
        self._bridge = _PyBridge(
            on_atom_click=self._handle_atom_click,
            on_status=self._handle_status,
            on_molecule_loaded=self._handle_molecule_loaded,
        )
        self._channel.registerObject("pybridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

    def set_snapshot(self, snapshot: RenderSnapshot) -> None:
        """设置渲染数据：从 snapshot 生成 SDF，发给 JS。"""
        if self._view is None:
            return

        # 从 snapshot 生成 SDF
        sdf_text = self._snapshot_to_sdf(snapshot)
        self.load_sdf(sdf_text)

    def _snapshot_to_sdf(self, snapshot: RenderSnapshot) -> str:
        """把 RenderSnapshot 转成 SDF 字符串。"""
        lines = []
        n = snapshot.num_atoms
        bonds = snapshot.bonds

        # SDF 头
        lines.append("MolForge snapshot")
        lines.append("  RDKit")
        lines.append("")

        # 原子计数行
        lines.append(f"{n:3d}{len(bonds):3d}  0  0  0  0  0  0  0  0999 V2000")

        # 原子坐标
        element_map = {1: 'H', 6: 'C', 7: 'N', 8: 'O', 9: 'F', 15: 'P', 16: 'S', 17: 'Cl'}
        for i in range(n):
            x, y, z = snapshot.coordinates[i]
            elem = element_map.get(int(snapshot.atomic_numbers[i]), 'C')
            lines.append(f" {x:10.4f} {y:10.4f} {z:10.4f} {elem:<3s} 0  0  0  0  0  0  0  0  0  0  0  0")

        # 键
        for begin, end, order in bonds:
            lines.append(f"{begin+1:3d}{end+1:3d}{order:3d}  0  0  0  0")

        lines.append("M  END")
        lines.append("$$$$")

        return "\n".join(lines)

    def load_sdf(self, sdf_text: str) -> None:
        """直接加载 SDF 字符串。"""
        if self._view is None:
            return

        # 通过 JS 调用加载
        escaped = sdf_text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
        js = f"loadMoleculeSDF('{escaped}')"
        self._view.page().runJavaScript(js)

    def update_coordinates(self, coordinates) -> None:
        """只更新坐标（轨迹播放用）。"""
        # TODO: 实现坐标更新
        pass

    def set_mode(self, mode: RepresentationMode) -> None:
        """切换表示模式。"""
        self._mode = mode
        mode_map = {
            RepresentationMode.BALL_AND_STICK: 'ball_and_stick',
            RepresentationMode.CPK: 'cpk',
            RepresentationMode.SURFACE: 'surface',
            RepresentationMode.LINE: 'line',
        }
        js_mode = mode_map.get(mode, 'ball_and_stick')
        self._view.page().runJavaScript(f"setRepresentation('{js_mode}')")

    def set_selection(
        self,
        selected: set[AtomId],
        selected_bonds: set[BondId] | None = None,
        measure_chain: Sequence[AtomId] | None = None,
    ) -> None:
        """设置选中原子高亮。"""
        self._selected = selected
        # 高亮第一个选中的原子（演示用）
        if selected:
            first_idx = next(iter(selected)).value
            self._view.page().runJavaScript(f"highlightAtom({first_idx})")

    def highlight_atom(self, atom_index: int) -> None:
        """高亮指定索引的原子。"""
        self._view.page().runJavaScript(f"highlightAtom({atom_index})")

    # ---------- 回调注册 ----------

    def set_atom_click_callback(self, callback: Callable[[str, int], None]) -> None:
        """注册原子点击回调：接收 (元素符号, 原子索引)。"""
        self._on_atom_click = callback

    def set_status_callback(self, callback: Callable[[str, bool], None]) -> None:
        """注册状态日志回调：接收 (消息, 是否错误)。"""
        self._on_status = callback

    def set_molecule_loaded_callback(self, callback: Callable[[int], None]) -> None:
        """注册分子加载完成回调：接收 (原子数)。"""
        self._on_molecule_loaded = callback

    # ---------- 内部处理 ----------

    def _handle_atom_click(self, element: str, atom_index: int) -> None:
        """处理 JS 端的原子点击。"""
        if self._on_atom_click:
            self._on_atom_click(element, atom_index)

    def _handle_status(self, message: str, is_error: bool) -> None:
        """处理 JS 端的状态日志。"""
        self._on_status(message, is_error)

    def _handle_molecule_loaded(self, atom_count: int) -> None:
        """处理分子加载完成。"""
        self._atom_count = atom_count
        self._is_initialized = True
        self._on_molecule_loaded(atom_count)

    # ---------- 其他 ----------

    def reset_camera(self) -> None:
        if self._view:
            self._view.page().runJavaScript("resetCamera()")

    def export_image(self, path: str, width: int = 1920, height: int = 1080) -> None:
        # TODO: Mol* 截图功能
        pass

    def render(self) -> None:
        # Mol* 自动渲染，不需要手动触发
        pass
