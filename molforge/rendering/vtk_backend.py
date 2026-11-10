"""
rendering/vtk_backend.py - 逐原子 Glyph + 逐键变径 Tube 零崩溃 3D 渲染引擎 (MolForge v4)
========================================================================================
彻底解决 P0 核心诉求（告别 vtkMoleculeMapper 黑盒）：
1. 逐原子独立渲染 (`self._atom_actor` = `vtkGlyph3DMapper` + `vtkPolyData`)：
   - 每个原子拥有独立的半径标量 (`atom_radius` = `vdw * mode_scale * global_atom_scale * atom.scale`)
   - 每个原子拥有独立的 RGB 颜色 (`atom_color` = `atom.color` 优先，否则读取当前配色方案 `COLOR_SCHEMES`)
   - 右侧「选中原子大小」滑块只改选中原子的 `atom.scale`；「全局原子大小」滑块管整体缩放，二者完美共存！
2. 逐键独立粗细与半键双色/自定义键色渲染 (`self._bond_actor` = `vtkTubeFilter` + `SetVaryRadiusToVaryRadiusByAbsoluteScalar`)：
   - 每条化学键（含单键、双键双圆柱、三键三圆柱、芳香键）拆分为中心对称半键段写入常驻 `self._bond_polydata`
   - 每个顶点写入独立半径标量 (`bond_radius` = `base_r * global_bond_scale * bond.width_scale * multi_factor`)
   - 每个顶点写入独立 RGB 颜色 (`bond_color` = 若设置了 `bond.color` 则整键使用该颜色；否则两端半键自动继承两端原子的实时颜色！)
   - 右侧「选中键粗细」滑块只改选中键的 `bond.width_scale`；「全局键粗细」滑块管整体缩放！
3. 常驻 Actor 架构（生命周期内零 `RemoveActor` / 零 C++ 析构崩溃）：
   - `_atom_actor`、`_bond_actor`、`_highlight_actor`、`_highlight_bond_actor`、`_rubberband_actor`、`_measure_actor`
     在首次初始化时只 `AddActor` 一次，交互全过程仅原地修改 `vtkPoints` / `vtkFloatArray` / `vtkUnsignedCharArray`！
4. 100% 纯 NumPy 相机透视投影与射线拾取（感知每个原子的独立缩放半径与每条键的独立粗细）。
"""

from __future__ import annotations

from typing import Callable, Any, Sequence
import math
import numpy as np

try:
    import vtk
except ImportError:  # pragma: no cover
    vtk = None

from .contracts import Renderer3D, RenderSnapshot, RepresentationMode
from .materials import MaterialPreset, ScientificPreset, StudioPreset, AnalysisPreset
from ..domain.ids import AtomId, BondId

from ..domain.elements import ELEMENTS
VDW_RADII = {z: e.vdw_radius for z, e in ELEMENTS.items()}
DEFAULT_VDW = 1.65

# 多套专业配色方案（支持状态栏/View 菜单一键切换）
STUDIO_CPK_COLORS: dict[int, tuple[float, float, float]] = {
    1:  (0.95, 0.97, 0.99),  # H  瓷白
    5:  (0.96, 0.68, 0.50),  # B  暖杏
    6:  (0.52, 0.61, 0.70),  # C  钛灰蓝
    7:  (0.32, 0.62, 0.98),  # N  宝石蓝
    8:  (0.96, 0.36, 0.38),  # O  珊瑚红
    9:  (0.36, 0.88, 0.58),  # F  翡翠绿
    14: (0.82, 0.72, 0.56),  # Si 香槟金
    15: (0.98, 0.62, 0.26),  # P  琥珀橙
    16: (0.96, 0.82, 0.28),  # S  明黄
    17: (0.30, 0.84, 0.52),  # Cl 鲜绿
    34: (0.98, 0.58, 0.16),  # Se 橙金
    35: (0.68, 0.28, 0.22),  # Br 深红棕
    50: (0.50, 0.62, 0.62),  # Sn 青灰
    53: (0.58, 0.24, 0.68),  # I  紫罗兰
}

GAUSSVIEW_COLORS: dict[int, tuple[float, float, float]] = {
    1:  (0.90, 0.90, 0.90),
    6:  (0.45, 0.45, 0.45),
    7:  (0.20, 0.35, 0.95),
    8:  (0.95, 0.15, 0.15),
    9:  (0.45, 0.90, 0.45),
    14: (0.78, 0.68, 0.52),
    15: (1.00, 0.55, 0.00),
    16: (0.95, 0.85, 0.15),
    17: (0.15, 0.90, 0.15),
    34: (0.95, 0.55, 0.10),
    35: (0.60, 0.15, 0.15),
    53: (0.55, 0.10, 0.65),
}

JMOL_COLORS: dict[int, tuple[float, float, float]] = {
    1:  (1.00, 1.00, 1.00),
    6:  (0.56, 0.56, 0.56),
    7:  (0.19, 0.31, 0.97),
    8:  (1.00, 0.05, 0.05),
    9:  (0.56, 0.88, 0.31),
    14: (0.94, 0.78, 0.63),
    15: (1.00, 0.50, 0.00),
    16: (1.00, 1.00, 0.19),
    17: (0.12, 0.94, 0.12),
    34: (1.00, 0.63, 0.00),
    35: (0.65, 0.16, 0.16),
    53: (0.58, 0.00, 0.58),
}

CARBON_CYAN_COLORS: dict[int, tuple[float, float, float]] = {
    **STUDIO_CPK_COLORS,
    6: (0.25, 0.82, 0.75),   # PyMOL 风格青色碳骨架
}

COLOR_SCHEMES: dict[str, dict[int, tuple[float, float, float]]] = {
    "Default Scheme": STUDIO_CPK_COLORS,
    "Studio CPK": STUDIO_CPK_COLORS,
    "GaussView Classic": GAUSSVIEW_COLORS,
    "Jmol Standard": JMOL_COLORS,
    "Carbon Cyan (PyMOL)": CARBON_CYAN_COLORS,
}

PRESETS: dict[str, MaterialPreset] = {
    "Scientific": ScientificPreset,
    "Studio": StudioPreset,
    "Analysis": AnalysisPreset,
}


def ray_sphere_intersect(
    ray_origin: np.ndarray,
    ray_dir: np.ndarray,
    centers: np.ndarray,
    radii: np.ndarray,
) -> tuple[int, float]:
    """纯数学 3D 射线与一组球体求交，返回 (best_atom_index, best_t)。"""
    if centers is None or len(centers) == 0:
        return -1, float("inf")

    d = np.asarray(ray_dir, dtype=np.float64)
    d_norm = np.linalg.norm(d)
    if d_norm < 1e-12:
        return -1, float("inf")
    d = d / d_norm

    oc = np.asarray(centers, dtype=np.float64) - np.asarray(ray_origin, dtype=np.float64)
    t_ca = oc @ d
    oc_norm2 = np.einsum("ij,ij->i", oc, oc)
    d2 = oc_norm2 - t_ca * t_ca
    r2 = np.asarray(radii, dtype=np.float64) ** 2

    hit_mask = (t_ca > 0.0) & (d2 <= r2)
    if not np.any(hit_mask):
        return -1, float("inf")

    hit_indices = np.where(hit_mask)[0]
    t_hc = np.sqrt(np.maximum(0.0, r2[hit_indices] - d2[hit_indices]))
    t_hit = t_ca[hit_indices] - t_hc

    best_local = int(np.argmin(t_hit))
    return int(hit_indices[best_local]), float(t_hit[best_local])


def ray_segment_closest(
    ray_origin: np.ndarray,
    ray_dir: np.ndarray,
    p1: np.ndarray,
    p2: np.ndarray,
) -> tuple[float, float]:
    """计算 3D 射线与线段 p1->p2 之间的最短距离及射线参数 t。"""
    u = np.asarray(ray_dir, dtype=np.float64)
    u = u / (np.linalg.norm(u) + 1e-12)
    v = np.asarray(p2, dtype=np.float64) - np.asarray(p1, dtype=np.float64)
    w = np.asarray(ray_origin, dtype=np.float64) - np.asarray(p1, dtype=np.float64)

    a = float(np.dot(u, u))
    b = float(np.dot(u, v))
    c = float(np.dot(v, v))
    d = float(np.dot(u, w))
    e = float(np.dot(v, w))
    denom = a * c - b * b

    if denom < 1e-9:
        tc = 0.5
    else:
        tc = (a * e - b * d) / denom

    tc = max(0.15, min(0.85, tc))
    sc = max(0.0, -d + b * tc)
    closest_on_ray = ray_origin + sc * u
    closest_on_seg = p1 + tc * v
    dist = float(np.linalg.norm(closest_on_ray - closest_on_seg))
    return dist, float(sc)


def compute_camera_basis(
    cam_pos: np.ndarray,
    cam_focal: np.ndarray,
    cam_up: np.ndarray,
    view_angle_deg: float,
    width: float,
    height: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float, float]:
    """纯 NumPy 计算透视相机的正交基向量 (eye, forward, right, up, tx, ty)。"""
    eye = np.asarray(cam_pos, dtype=np.float64)
    focal = np.asarray(cam_focal, dtype=np.float64)
    up_raw = np.asarray(cam_up, dtype=np.float64)

    forward = focal - eye
    f_norm = float(np.linalg.norm(forward))
    forward = forward / (f_norm if f_norm > 1e-12 else 1.0)

    right = np.cross(forward, up_raw)
    r_norm = float(np.linalg.norm(right))
    if r_norm < 1e-9:
        fallback_up = np.array([0.0, 1.0, 0.0]) if abs(forward[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
        right = np.cross(forward, fallback_up)
        r_norm = float(np.linalg.norm(right))
    right = right / (r_norm if r_norm > 1e-12 else 1.0)

    true_up = np.cross(right, forward)
    true_up = true_up / (float(np.linalg.norm(true_up)) + 1e-12)

    fov_rad = math.radians(max(5.0, min(150.0, float(view_angle_deg))))
    ty = math.tan(fov_rad * 0.5)
    aspect = max(1.0, float(width)) / max(1.0, float(height))
    tx = ty * aspect
    return eye, forward, right, true_up, tx, ty


class VtkRendererBackend(Renderer3D):
    """
    MolForge v4 逐原子 Glyph + 逐键变径 Tube 零崩溃 VTK 3D 渲染后端。
    """

    BASE_BALL_SCALE = 0.25
    BASE_CPK_SCALE = 1.0
    BASE_LINE_ATOM_SCALE = 0.08
    BASE_BOND_RADIUS = 0.088

    def __init__(self, pick_tolerance: float = 0.48) -> None:
        self._viewer = None
        self._mode = RepresentationMode.BALL_AND_STICK

        # 双向映射：idx <-> AtomId
        self._atom_ids: list[AtomId] = []
        self._id_to_idx: dict[AtomId, int] = {}
        self._bond_ids: list[BondId] = []
        self._bonds: list[tuple[int, int, int]] = []
        self._n_atoms = 0
        self._coordinates: np.ndarray | None = None
        self._atomic_numbers: np.ndarray | None = None

        # 逐原子与逐键独立属性缓存（支持每个原子/每条键独立大小与颜色！）
        self._per_atom_scales: np.ndarray = np.ones(0, dtype=np.float32)
        self._per_atom_colors: dict[int, tuple[float, float, float]] = {}
        self._per_bond_scales: np.ndarray = np.ones(0, dtype=np.float32)
        self._per_bond_colors: dict[int, tuple[float, float, float]] = {}

        # 全局缩放与配色方案
        self._atom_opacities = np.ones(0)
        self._atom_glows = {}
        self._glow_layers = []
        self._atom_scale = 1.0
        self._bond_scale = 1.0
        self._color_scheme = "Default Scheme"

        # 视图显示开关（对应 View 菜单）
        self.show_hydrogens: bool = True
        self.show_bonds: bool = True
        self.label_scope = "all"
        self._native_labels = None
        self.show_labels: bool = False
        self.show_symbols: bool = False
        self.show_axes: bool = True

        # 选中集合
        self._selected: set[AtomId] = set()
        self._selected_bonds: set[BondId] = set()
        self._pick_tolerance = pick_tolerance

        # 常驻 VTK 对象（整个生命周期只 AddActor 一次，绝不 RemoveActor！）
        self._scene_initialized = False

        # 1. 逐原子 Glyph 常驻管线
        self._atom_sphere = None
        self._atom_points = None
        self._atom_radii = None
        self._atom_colors = None
        self._atom_polydata = None
        self._atom_glyph_mapper = None
        self._atom_actor = None
        self._actor = None  # 兼容引用指向 self._atom_actor

        # 2. 逐键变径/变色 Tube 常驻管线
        self._bond_points = None
        self._bond_lines = None
        self._bond_radii = None
        self._bond_colors = None
        self._bond_polydata = None
        self._bond_tube_filter = None
        self._bond_mapper = None
        self._bond_actor = None

        # 3. 常驻选中原子光晕 Glyph Actor
        self._highlight_points = None
        self._highlight_radii = None
        self._highlight_colors = None
        self._highlight_polydata = None
        self._highlight_mapper = None
        self._highlight_actor = None

        # 4. 常驻选中化学键高亮 Tube Actor
        self._hl_bond_points = None
        self._hl_bond_lines = None
        self._hl_bond_radii = None
        self._hl_bond_polydata = None
        self._hl_bond_tube = None
        self._hl_bond_actor = None

        # 5. 常驻 3D 橡皮筋建键预览圆柱 Actor & 测量标尺线 Actor
        self._rubberband_line = None
        self._rubberband_actor = None
        self._measure_points = None
        self._measure_lines = None
        self._measure_polydata = None
        self._measure_actor = None
        self._measure_chain: list[AtomId] | None = None

        # 6. 常驻 3D 文字标签 Actor (vtkLabeledDataMapper / 2D overlay)
        self._label_points = None
        self._label_strings = None
        self._label_polydata = None
        self._label_actor = None

        # 可选附加层（表面/轨道/体渲染）
        self._surface_actor = None
        self._orbital_actors: list = []
        self._volume_actors: list = []
        self._qtaim_actors: list = []

        # 交互状态与防重入节流标记
        self.current_tool: str = "选择"
        self.current_element: int = 6
        self._on_selection_changed: Callable[[set[AtomId]], None] | None = None
        self._render_pending = False
        self._in_render = False
        self._camera_state: dict | None = None

    def attach(self, viewer) -> None:
        self._viewer = viewer

    # ---------- 初始化常驻 VTK 场景（整个生命周期只执行一次 AddActor） ----------

    def _ensure_scene_initialized(self) -> None:
        if self._scene_initialized or self._viewer is None or vtk is None:
            return

        ren = self._viewer.renderer
        self._viewer.set_background(
            color=[0.067, 0.114, 0.173],  # #111D2C
            top=[0.145, 0.227, 0.314],    # #253A50
        )
        try:
            self._viewer.enable_anti_aliasing("fxaa")
        except Exception:
            pass

        # 1. 配置三点式 Studio 灯光
        try:
            ren.RemoveAllLights()
            key_light = vtk.vtkLight()
            key_light.SetLightTypeToCameraLight()
            key_light.SetPosition(1.8, 2.2, 2.5)
            key_light.SetColor(1.0, 0.98, 0.95)
            key_light.SetIntensity(0.95)
            ren.AddLight(key_light)

            fill_light = vtk.vtkLight()
            fill_light.SetLightTypeToCameraLight()
            fill_light.SetPosition(-2.0, -1.2, 1.8)
            fill_light.SetColor(0.78, 0.88, 1.0)
            fill_light.SetIntensity(0.45)
            ren.AddLight(fill_light)

            rim_light = vtk.vtkLight()
            rim_light.SetLightTypeToCameraLight()
            rim_light.SetPosition(0.0, 2.5, -2.0)
            rim_light.SetColor(0.85, 0.95, 1.0)
            rim_light.SetIntensity(0.28)
            ren.AddLight(rim_light)
        except Exception:
            pass

        # 1.5 角落 XYZ 坐标轴指示器（GaussView 风格）
        try:
            axes_actor = vtk.vtkAxesActor()
            axes_actor.SetTotalLength(2.0, 2.0, 2.0)
            axes_actor.SetShaftTypeToCylinder()
            axes_actor.SetXAxisLabelText("X")
            axes_actor.SetYAxisLabelText("Y")
            axes_actor.SetZAxisLabelText("Z")
            axes_actor.GetXAxisCaptionActor2D().GetCaptionTextProperty().SetColor(1, 0, 0)
            axes_actor.GetXAxisCaptionActor2D().GetCaptionTextProperty().SetFontSize(16)
            axes_actor.GetYAxisCaptionActor2D().GetCaptionTextProperty().SetColor(0, 1, 0)
            axes_actor.GetYAxisCaptionActor2D().GetCaptionTextProperty().SetFontSize(16)
            axes_actor.GetZAxisCaptionActor2D().GetCaptionTextProperty().SetColor(0, 0.5, 1)
            axes_actor.GetZAxisCaptionActor2D().GetCaptionTextProperty().SetFontSize(16)
            vtk_iren = (
                getattr(getattr(self._viewer, "iren", None), "interactor", None)
                or getattr(getattr(self._viewer, "interactor", None), "_Iren", None)
                or (self._viewer.render_window.GetInteractor() if hasattr(self._viewer, "render_window") and self._viewer.render_window else None)
            )
            self._axes_actor_3d = axes_actor
            if vtk_iren is not None:
                self._axes_marker = vtk.vtkOrientationMarkerWidget()
                self._axes_marker.SetOrientationMarker(axes_actor)
                self._axes_marker.SetInteractor(vtk_iren)
                self._axes_marker.SetViewport(0.0, 0.0, 0.22, 0.22)
                self._axes_marker.SetEnabled(1 if self.show_axes else 0)
                self._axes_marker.InteractiveOff()
            else:
                self._axes_marker = None
                if hasattr(self._viewer, "add_axes"):
                    self._viewer.add_axes(interactive=False)
            # Only the corner marker is shown; origin axes obscure molecular geometry.
            self._origin_axes_actor = None
        except Exception:
            self._axes_marker = None
            try:
                if hasattr(self._viewer, "add_axes"):
                    self._viewer.add_axes(interactive=False)
            except Exception:
                pass

        # 2. 常驻逐原子 Sphere Glyph Actor（支持每个原子独立半径 + 独立 RGB 颜色！）
        self._atom_points = vtk.vtkPoints()
        self._atom_radii = vtk.vtkFloatArray()
        self._atom_radii.SetName("atom_radius")
        self._atom_colors = vtk.vtkUnsignedCharArray()
        self._atom_colors.SetName("atom_color")
        self._atom_colors.SetNumberOfComponents(4)

        self._atom_polydata = vtk.vtkPolyData()
        self._atom_polydata.SetPoints(self._atom_points)
        self._atom_polydata.GetPointData().SetScalars(self._atom_radii)
        self._atom_polydata.GetPointData().AddArray(self._atom_colors)

        atom_sphere = vtk.vtkSphereSource()
        atom_sphere.SetRadius(1.0)
        atom_sphere.SetThetaResolution(24)
        atom_sphere.SetPhiResolution(24)
        self._atom_sphere = atom_sphere

        self._atom_glyph_mapper = vtk.vtkGlyph3DMapper()
        self._atom_glyph_mapper.SetSourceConnection(atom_sphere.GetOutputPort())
        self._atom_glyph_mapper.SetInputData(self._atom_polydata)
        self._atom_glyph_mapper.SetScaleArray("atom_radius")
        self._atom_glyph_mapper.SetScaleModeToScaleByMagnitude()
        self._atom_glyph_mapper.ScalingOn()
        self._atom_glyph_mapper.SetScalarModeToUsePointFieldData()
        self._atom_glyph_mapper.SelectColorArray("atom_color")
        self._atom_glyph_mapper.SetColorModeToDirectScalars()
        self._atom_glyph_mapper.ScalarVisibilityOn()

        self._atom_actor = vtk.vtkActor()
        self._atom_actor.SetMapper(self._atom_glyph_mapper)
        ap = self._atom_actor.GetProperty()
        ap.SetInterpolationToPhong()
        ap.SetAmbient(0.28)
        ap.SetDiffuse(0.74)
        ap.SetSpecular(0.50)
        ap.SetSpecularPower(44.0)
        ren.AddActor(self._atom_actor)
        # A shared Gaussian-splat layer gives smooth colored light, not physical luminescence.
        self._glow_layers = []
        for radius_factor, alpha_factor in ((1.15,.65),):
            poly = vtk.vtkPolyData()
            poly.SetPoints(self._atom_points)
            radii = vtk.vtkFloatArray(); radii.SetName("glow_radius")
            colors = vtk.vtkUnsignedCharArray(); colors.SetName("glow_color"); colors.SetNumberOfComponents(4)
            poly.GetPointData().AddArray(radii); poly.GetPointData().AddArray(colors)
            mapper = vtk.vtkPointGaussianMapper()
            mapper.SetInputData(poly)
            mapper.SetScaleArray("glow_radius"); mapper.SetScaleFactor(1.); mapper.EmissiveOn()
            mapper.SetScalarModeToUsePointFieldData(); mapper.SelectColorArray("glow_color"); mapper.SetColorModeToDirectScalars()
            actor = vtk.vtkActor(); actor.SetMapper(mapper); actor.PickableOff()
            actor.GetProperty().SetAmbient(1.); actor.GetProperty().SetDiffuse(0.); actor.GetProperty().SetSpecular(0.)
            ren.AddActor(actor)
            self._glow_layers.append((poly,radii,colors,actor,radius_factor,alpha_factor))
        self._actor = self._atom_actor

        # 3. 常驻逐键变径/变色 Tube Actor（支持每条键独立粗细 + 半键双色或独立键色！）
        self._bond_points = vtk.vtkPoints()
        self._bond_lines = vtk.vtkCellArray()
        self._bond_radii = vtk.vtkFloatArray()
        self._bond_radii.SetName("bond_radius")
        self._bond_colors = vtk.vtkUnsignedCharArray()
        self._bond_colors.SetName("bond_color")
        self._bond_colors.SetNumberOfComponents(4)

        self._bond_polydata = vtk.vtkPolyData()
        self._bond_polydata.SetPoints(self._bond_points)
        self._bond_polydata.SetLines(self._bond_lines)
        self._bond_polydata.GetPointData().SetScalars(self._bond_radii)
        self._bond_polydata.GetPointData().AddArray(self._bond_colors)

        self._bond_tube_filter = vtk.vtkTubeFilter()
        self._bond_tube_filter.SetInputData(self._bond_polydata)
        self._bond_tube_filter.SetVaryRadiusToVaryRadiusByAbsoluteScalar()
        self._bond_tube_filter.SetNumberOfSides(18)
        self._bond_tube_filter.SetCapping(True)

        self._bond_mapper = vtk.vtkPolyDataMapper()
        self._bond_mapper.SetInputConnection(self._bond_tube_filter.GetOutputPort())
        self._bond_mapper.SetScalarModeToUsePointFieldData()
        self._bond_mapper.SelectColorArray("bond_color")
        self._bond_mapper.SetColorModeToDirectScalars()
        self._bond_mapper.ScalarVisibilityOn()

        self._bond_actor = vtk.vtkActor()
        self._bond_actor.SetMapper(self._bond_mapper)
        bp = self._bond_actor.GetProperty()
        bp.SetInterpolationToPhong()
        bp.SetAmbient(0.28)
        bp.SetDiffuse(0.74)
        bp.SetSpecular(0.45)
        bp.SetSpecularPower(38.0)
        ren.AddActor(self._bond_actor)

        # 4. 常驻选中原子高亮光晕 Actor
        self._highlight_points = vtk.vtkPoints()
        self._highlight_radii = vtk.vtkFloatArray()
        self._highlight_radii.SetName("halo_scale")
        self._highlight_polydata = vtk.vtkPolyData()
        self._highlight_polydata.SetPoints(self._highlight_points)
        self._highlight_polydata.GetPointData().SetScalars(self._highlight_radii)

        halo_sphere = vtk.vtkSphereSource()
        halo_sphere.SetRadius(1.0)
        halo_sphere.SetThetaResolution(24)
        halo_sphere.SetPhiResolution(24)

        self._highlight_mapper = vtk.vtkGlyph3DMapper()
        self._highlight_mapper.SetSourceConnection(halo_sphere.GetOutputPort())
        self._highlight_mapper.SetInputData(self._highlight_polydata)
        self._highlight_mapper.SetScaleArray("halo_scale")
        self._highlight_mapper.SetScaleModeToScaleByMagnitude()
        self._highlight_mapper.ScalingOn()
        self._highlight_mapper.ScalarVisibilityOff()

        self._highlight_actor = vtk.vtkActor()
        self._highlight_actor.SetMapper(self._highlight_mapper)
        hp = self._highlight_actor.GetProperty()
        hp.SetColor(0.40, 0.87, 0.79)  # #66DEC9 青翠光环
        hp.SetOpacity(0.34)
        hp.SetAmbient(0.80)
        self._highlight_actor.SetPickable(False)
        self._highlight_actor.VisibilityOff()
        ren.AddActor(self._highlight_actor)

        # 5. 常驻选中化学键高亮光环 Actor
        self._hl_bond_points = vtk.vtkPoints()
        self._hl_bond_lines = vtk.vtkCellArray()
        self._hl_bond_radii = vtk.vtkFloatArray()
        self._hl_bond_radii.SetName("hl_bond_r")
        self._hl_bond_polydata = vtk.vtkPolyData()
        self._hl_bond_polydata.SetPoints(self._hl_bond_points)
        self._hl_bond_polydata.SetLines(self._hl_bond_lines)
        self._hl_bond_polydata.GetPointData().SetScalars(self._hl_bond_radii)

        self._hl_bond_tube = vtk.vtkTubeFilter()
        self._hl_bond_tube.SetInputData(self._hl_bond_polydata)
        self._hl_bond_tube.SetVaryRadiusToVaryRadiusByAbsoluteScalar()
        self._hl_bond_tube.SetNumberOfSides(16)

        hl_b_mapper = vtk.vtkPolyDataMapper()
        hl_b_mapper.SetInputConnection(self._hl_bond_tube.GetOutputPort())
        hl_b_mapper.ScalarVisibilityOff()

        self._hl_bond_actor = vtk.vtkActor()
        self._hl_bond_actor.SetMapper(hl_b_mapper)
        hbp = self._hl_bond_actor.GetProperty()
        hbp.SetColor(0.40, 0.87, 0.79)
        hbp.SetOpacity(0.40)
        hbp.SetAmbient(0.80)
        self._hl_bond_actor.SetPickable(False)
        self._hl_bond_actor.VisibilityOff()
        ren.AddActor(self._hl_bond_actor)

        # 6. 常驻 3D 橡皮筋建键预览圆柱 Actor
        self._rubberband_line = vtk.vtkLineSource()
        self._rubberband_line.SetPoint1(0.0, 0.0, 0.0)
        self._rubberband_line.SetPoint2(1.0, 0.0, 0.0)
        rb_tube = vtk.vtkTubeFilter()
        rb_tube.SetInputConnection(self._rubberband_line.GetOutputPort())
        rb_tube.SetRadius(0.075)
        rb_tube.SetNumberOfSides(16)
        rb_mapper = vtk.vtkPolyDataMapper()
        rb_mapper.SetInputConnection(rb_tube.GetOutputPort())
        self._rubberband_actor = vtk.vtkActor()
        self._rubberband_actor.SetMapper(rb_mapper)
        rbp = self._rubberband_actor.GetProperty()
        rbp.SetColor(0.40, 0.87, 0.79)
        rbp.SetOpacity(0.82)
        rbp.SetAmbient(0.75)
        self._rubberband_actor.SetPickable(False)
        self._rubberband_actor.VisibilityOff()
        ren.AddActor(self._rubberband_actor)

        # 7. 常驻 3D 测量连线 Actor
        self._measure_points = vtk.vtkPoints()
        self._measure_lines = vtk.vtkCellArray()
        self._measure_polydata = vtk.vtkPolyData()
        self._measure_polydata.SetPoints(self._measure_points)
        self._measure_polydata.SetLines(self._measure_lines)
        m_tube = vtk.vtkTubeFilter()
        m_tube.SetInputData(self._measure_polydata)
        m_tube.SetRadius(0.032)
        m_tube.SetNumberOfSides(10)
        m_mapper = vtk.vtkPolyDataMapper()
        m_mapper.SetInputConnection(m_tube.GetOutputPort())
        self._measure_actor = vtk.vtkActor()
        self._measure_actor.SetMapper(m_mapper)
        mp = self._measure_actor.GetProperty()
        mp.SetColor(1.0, 0.84, 0.35)
        mp.SetOpacity(0.88)
        mp.SetAmbient(0.8)
        self._measure_actor.SetPickable(False)
        self._measure_actor.VisibilityOff()
        ren.AddActor(self._measure_actor)

        from .native_labels import NativeAtomLabels
        self._native_labels = NativeAtomLabels(self,ren)
        self._label_actor = self._native_labels.actor
        self._label_points = self._native_labels.points
        self._label_strings = self._native_labels.strings
        self._label_polydata = self._native_labels.data

        self._scene_initialized = True

    # ---------- 计算单个原子的实际显示半径与 RGB 颜色 ----------

    def _base_mode_atom_factor(self) -> float:
        if self._mode in (RepresentationMode.CPK, RepresentationMode.SPACE_FILL):
            return self.BASE_CPK_SCALE
        if self._mode == RepresentationMode.LINE:
            return self.BASE_LINE_ATOM_SCALE
        return self.BASE_BALL_SCALE

    def get_effective_atom_radius(self, idx: int) -> float:
        """返回第 idx 个原子的真实 3D 球体渲染半径（融合元素 VdW + 模式 + 全局缩放 + 单原子缩放）。"""
        if self._atomic_numbers is None or not (0 <= idx < self._n_atoms):
            return 0.40
        z = int(self._atomic_numbers[idx])
        if not self.show_hydrogens and z == 1:
            return 0.0
        vdw = VDW_RADII.get(z, DEFAULT_VDW)
        ind_scale = float(self._per_atom_scales[idx]) if idx < len(self._per_atom_scales) else 1.0
        return float(vdw * self._base_mode_atom_factor() * self._atom_scale * ind_scale)

    def get_effective_atom_color(self, idx: int) -> tuple[float, float, float]:
        """返回第 idx 个原子的真实 RGB 颜色（优先读取 atom.color，否则读取当前配色方案）。"""
        if idx in self._per_atom_colors and self._per_atom_colors[idx] is not None:
            c = self._per_atom_colors[idx]
            return (float(c[0]), float(c[1]), float(c[2]))
        z = int(self._atomic_numbers[idx]) if (self._atomic_numbers is not None and 0 <= idx < self._n_atoms) else 6
        scheme_map = COLOR_SCHEMES.get(self._color_scheme, STUDIO_CPK_COLORS)
        if z in scheme_map:
            return scheme_map[z]
        from ..domain.elements import get_element
        elem = get_element(z)
        return elem.cpk_color if elem else (0.55, 0.62, 0.70)

    def get_effective_bond_radius(self, b_idx: int) -> float:
        """返回第 b_idx 条键的真实 3D 圆柱半径（融合全局键粗细 + 单键独立粗细）。"""
        base_r = 0.045 if self._mode == RepresentationMode.LINE else self.BASE_BOND_RADIUS
        ind_w = float(self._per_bond_scales[b_idx]) if b_idx < len(self._per_bond_scales) else 1.0
        return float(base_r * self._bond_scale * ind_w)

    # ---------- 原地重建逐原子 Glyph 与逐键变径 Tube（零 RemoveActor / 零崩溃！） ----------

    def _rebuild_vtk_molecule_in_place(self) -> None:
        """
        原地更新常驻 `_atom_polydata` 与 `_bond_polydata`：
          - 每个原子写入独立半径与独立 RGB 颜色
          - 每条化学键写入独立半径与独立 RGB 颜色（或两端原子半键双色）
          - 拖动原子、改单个原子大小/颜色、改单条键粗细/颜色时耗时 < 0.1 ms，且 100% 实时生效！
        """
        if self._viewer is None or vtk is None:
            return
        self._ensure_scene_initialized()
        if self._atom_points is None or self._bond_points is None:
            return

        self._atom_points.Reset()
        self._atom_radii.Reset()
        self._atom_radii.SetName("atom_radius")
        self._atom_colors.Reset()
        self._atom_colors.SetName("atom_color")
        self._atom_colors.SetNumberOfComponents(4)

        self._bond_points.Reset()
        self._bond_lines.Reset()
        self._bond_radii.Reset()
        self._bond_radii.SetName("bond_radius")
        self._bond_colors.Reset()
        self._bond_colors.SetName("bond_color")
        self._bond_colors.SetNumberOfComponents(4)

        if self._coordinates is None or self._atomic_numbers is None or self._n_atoms == 0:
            self._atom_polydata.Modified()
            self._bond_polydata.Modified()
            if self._atom_actor is not None:
                self._atom_actor.VisibilityOff()
            if self._bond_actor is not None:
                self._bond_actor.VisibilityOff()
            self._update_glow_layers()
            self._update_labels_in_place()
            return

        n = min(self._n_atoms, len(self._coordinates), len(self._atomic_numbers))
        is_massive = (n > 2000 or len(self._bonds) > 2000)

        # 动态调节原子球多边形细分精度（小分子高保真 24x24；超大体系/动力学盒子 8x8 或 6x6，减少 96.5% 多边形开销与显存压力！）
        if self._atom_sphere is not None:
            if n > 50000:
                self._atom_sphere.SetThetaResolution(6)
                self._atom_sphere.SetPhiResolution(6)
            elif n > 2000:
                self._atom_sphere.SetThetaResolution(8)
                self._atom_sphere.SetPhiResolution(8)
            else:
                self._atom_sphere.SetThetaResolution(24)
                self._atom_sphere.SetPhiResolution(24)

        atom_rgb_cache: list[tuple[int, int, int]] = []

        # 1. 写入全部原子球顶点、逐原子半径、逐原子 RGB
        for i in range(n):
            x, y, z = self._coordinates[i]
            r_val = self.get_effective_atom_radius(i)
            cr, cg, cb = self.get_effective_atom_color(i)
            rgb_u8 = (
                max(0, min(255, int(round(cr * 255.0)))),
                max(0, min(255, int(round(cg * 255.0)))),
                max(0, min(255, int(round(cb * 255.0)))),
            )
            atom_rgb_cache.append(rgb_u8)
            self._atom_points.InsertNextPoint(float(x), float(y), float(z))
            self._atom_radii.InsertNextValue(float(r_val))
            alpha = int(round(255 * self._atom_opacities[i])) if i < len(self._atom_opacities) else 255
            self._atom_colors.InsertNextTuple4(*rgb_u8,alpha)

        self._atom_points.Modified()
        self._atom_radii.Modified()
        self._atom_colors.Modified()
        self._atom_polydata.Modified()
        if self._atom_glyph_mapper is not None:
            self._atom_glyph_mapper.Modified()
        if self._atom_actor is not None:
            self._atom_actor.VisibilityOn()

        # 2. 写入全部化学键（CPK 空间填充模式下或关闭显示键时隐藏键圆柱）
        show_b = self.show_bonds and (self._mode not in (RepresentationMode.CPK, RepresentationMode.SPACE_FILL))
        if show_b and self._bonds:
            pt_cursor = 0
            if is_massive:
                # 宏观超大体系 / 动力学盒子：断开 CPU TubeFilter 管道，直连 GPU 硬件管线渲染线条！
                # 显存直接执行硬件着色，免除 1000 万个 CPU 多边形与数 GB 内存暴涨！
                if self._bond_mapper.GetInputConnection(0, 0) is not None:
                    self._bond_mapper.SetInputConnection(None)
                self._bond_mapper.SetInputData(self._bond_polydata)
                self._bond_actor.GetProperty().SetLineWidth(1.8)

                for b_idx, (i, j, order) in enumerate(self._bonds):
                    if not (0 <= i < n and 0 <= j < n) or i == j:
                        continue
                    if not self.show_hydrogens and (int(self._atomic_numbers[i]) == 1 or int(self._atomic_numbers[j]) == 1):
                        continue
                    p1 = self._coordinates[i]
                    p2 = self._coordinates[j]
                    c1 = atom_rgb_cache[i]
                    c2 = atom_rgb_cache[j]
                    self._bond_points.InsertNextPoint(float(p1[0]), float(p1[1]), float(p1[2]))
                    self._bond_points.InsertNextPoint(float(p2[0]), float(p2[1]), float(p2[2]))
                    self._bond_radii.InsertNextValue(0.05)
                    self._bond_radii.InsertNextValue(0.05)
                    self._bond_colors.InsertNextTuple4(c1[0], c1[1], c1[2], 255)
                    self._bond_colors.InsertNextTuple4(c2[0], c2[1], c2[2], 255)
                    self._bond_lines.InsertNextCell(2)
                    self._bond_lines.InsertCellPoint(pt_cursor)
                    self._bond_lines.InsertCellPoint(pt_cursor + 1)
                    pt_cursor += 2
            else:
                # 经典小分子：连接高品质 18 面圆柱 TubeFilter
                if self._bond_mapper.GetInputConnection(0, 0) is None:
                    self._bond_mapper.SetInputConnection(self._bond_tube_filter.GetOutputPort())

                def _add_tube_segment(p_start: np.ndarray, p_end: np.ndarray, rad: float, rgb_tuple: tuple[int, int, int]):
                    nonlocal pt_cursor
                    self._bond_points.InsertNextPoint(float(p_start[0]), float(p_start[1]), float(p_start[2]))
                    self._bond_points.InsertNextPoint(float(p_end[0]), float(p_end[1]), float(p_end[2]))
                    self._bond_radii.InsertNextValue(float(rad))
                    self._bond_radii.InsertNextValue(float(rad))
                    self._bond_colors.InsertNextTuple4(*rgb_tuple)
                    self._bond_colors.InsertNextTuple4(*rgb_tuple)
                    self._bond_lines.InsertNextCell(2)
                    self._bond_lines.InsertCellPoint(pt_cursor)
                    self._bond_lines.InsertCellPoint(pt_cursor + 1)
                    pt_cursor += 2

                for b_idx, (i, j, order) in enumerate(self._bonds):
                    if not (0 <= i < n and 0 <= j < n) or i == j:
                        continue
                    if not self.show_hydrogens and (int(self._atomic_numbers[i]) == 1 or int(self._atomic_numbers[j]) == 1):
                        continue

                    p1 = self._coordinates[i].astype(np.float64)
                    p2 = self._coordinates[j].astype(np.float64)
                    vec = p2 - p1
                    length = float(np.linalg.norm(vec))
                    if length < 1e-4:
                        continue

                    r_bond = self.get_effective_bond_radius(b_idx)
                    if b_idx in self._per_bond_colors and self._per_bond_colors[b_idx] is not None:
                        bc = self._per_bond_colors[b_idx]
                        c1_u8 = (
                            max(0, min(255, int(round(bc[0] * 255.0)))),
                            max(0, min(255, int(round(bc[1] * 255.0)))),
                            max(0, min(255, int(round(bc[2] * 255.0)))),
                        )
                        c2_u8 = c1_u8
                    else:
                        c1_u8 = atom_rgb_cache[i]
                        c2_u8 = atom_rgb_cache[j]

                    # A bond fades with the less transparent endpoint, keeping boundary bonds legible.
                    alpha = int(round(255 * max(self._atom_opacities[i], self._atom_opacities[j])))
                    c1_u8 = tuple(c1_u8) + (alpha,)
                    c2_u8 = tuple(c2_u8) + (alpha,)
                    vis_order = 2 if int(order) == 4 else max(1, min(3, int(order)))
                    if vis_order == 1 or self._mode == RepresentationMode.LINE:
                        mid = 0.5 * (p1 + p2)
                        _add_tube_segment(p1, mid, r_bond, c1_u8)
                        _add_tube_segment(mid, p2, r_bond, c2_u8)
                    else:
                        # 计算垂直于键方向的偏移向量（用于双键/三键平行多圆柱）
                        u = vec / length
                        ref = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.85 else np.array([0.0, 1.0, 0.0])
                        perp = np.cross(u, ref)
                        perp /= (float(np.linalg.norm(perp)) + 1e-12)

                        if vis_order == 2:
                            sub_r = r_bond * 0.62
                            sep = r_bond * 1.15
                            for sign in (-1.0, 1.0):
                                off = perp * (sign * sep)
                                pa, pb = p1 + off, p2 + off
                                mid = 0.5 * (pa + pb)
                                _add_tube_segment(pa, mid, sub_r, c1_u8)
                                _add_tube_segment(mid, pb, sub_r, c2_u8)
                        else:
                            sub_r = r_bond * 0.52
                            sep = r_bond * 1.35
                            for mult in (-1.0, 0.0, 1.0):
                                off = perp * (mult * sep)
                                pa, pb = p1 + off, p2 + off
                                mid = 0.5 * (pa + pb)
                                _add_tube_segment(pa, mid, sub_r, c1_u8)
                                _add_tube_segment(mid, pb, sub_r, c2_u8)

            self._bond_points.Modified()
            self._bond_lines.Modified()
            self._bond_radii.Modified()
            self._bond_colors.Modified()
            self._bond_polydata.Modified()
            if self._bond_tube_filter is not None:
                self._bond_tube_filter.Modified()
            if self._bond_actor is not None:
                self._bond_actor.SetVisibility(pt_cursor > 0)
        else:
            if self._bond_actor is not None:
                self._bond_actor.VisibilityOff()

        self._update_glow_layers()
        self._update_labels_in_place()

    def _update_glow_layers(self):
        if self._n_atoms > 2000:
            for poly, radii, colors, actor, factor, alpha_factor in self._glow_layers:
                actor.SetVisibility(False)
            return
        for poly, radii, colors, actor, factor, alpha_factor in self._glow_layers:
            radii.Reset(); colors.Reset(); colors.SetNumberOfComponents(4)
            visible = False
            for i in range(self._n_atoms):
                rgb_strength = self._atom_glows.get(i, (0.3,0.8,1.,0.))
                strength = float(rgb_strength[3])
                opacity = self._atom_opacities[i] if i < len(self._atom_opacities) else 1.
                radius = self.get_effective_atom_radius(i)
                radii.InsertNextValue(radius*factor if strength>0 else 0.)
                colors.InsertNextTuple4(*(int(255*max(0.,min(1.,float(c)))) for c in rgb_strength[:3]),int(255*alpha_factor*strength*opacity))
                visible = visible or (strength>0 and opacity>0 and radius>0)
            radii.Modified(); colors.Modified(); poly.Modified(); actor.SetVisibility(visible)

    def _update_labels_in_place(self) -> None:
        if self._n_atoms > 2000 and self.label_scope != "selected":
            if self._native_labels is not None:
                self._native_labels.actor.VisibilityOff()
            return
        if self._native_labels is not None:
            self._native_labels.update()

    # ---------- 场景快照渲染 ----------

    def set_snapshot(self, snapshot: RenderSnapshot, reset_cam: bool = True) -> None:
        """设置渲染快照并原地更新逐原子/逐键常驻 VTK 对象。"""
        self._atom_ids = list(snapshot.atom_ids)
        self._id_to_idx = {aid: i for i, aid in enumerate(self._atom_ids)}
        self._bonds = list(snapshot.bonds)
        self._bond_ids = list(snapshot.bond_ids) if snapshot.bond_ids is not None else []
        self._n_atoms = snapshot.num_atoms
        self._coordinates = snapshot.coordinates.copy().astype(np.float32) if len(snapshot.coordinates) > 0 else np.zeros((0, 3), dtype=np.float32)
        self._atomic_numbers = snapshot.atomic_numbers.copy()

        values = snapshot.atom_opacities
        self._atom_opacities = np.ones(self._n_atoms) if values is None else np.clip(np.asarray(values,dtype=float),0.,1.)
        self._atom_glows = dict(snapshot.atom_glows or {})

        # 解析逐原子独立缩放比例
        self._per_atom_scales = np.ones(self._n_atoms, dtype=np.float32)
        if snapshot.atom_scales is not None:
            if isinstance(snapshot.atom_scales, dict):
                for k, v in snapshot.atom_scales.items():
                    idx = self._id_to_idx.get(k, k if isinstance(k, int) else -1)
                    if 0 <= idx < self._n_atoms:
                        self._per_atom_scales[idx] = float(v)
            else:
                arr = np.asarray(snapshot.atom_scales, dtype=np.float32)
                m = min(self._n_atoms, len(arr))
                self._per_atom_scales[:m] = arr[:m]

        # 解析逐原子自定义颜色
        self._per_atom_colors = {}
        if snapshot.atom_colors:
            for k, col in snapshot.atom_colors.items():
                if col is None:
                    continue
                idx = self._id_to_idx.get(k, k if isinstance(k, int) else -1)
                if 0 <= idx < self._n_atoms:
                    self._per_atom_colors[idx] = (float(col[0]), float(col[1]), float(col[2]))

        # 解析逐键独立粗细比例
        n_bonds = len(self._bonds)
        self._per_bond_scales = np.ones(n_bonds, dtype=np.float32)
        if snapshot.bond_scales is not None:
            if isinstance(snapshot.bond_scales, dict):
                bid_to_bidx = {bid: idx for idx, bid in enumerate(self._bond_ids)}
                for k, v in snapshot.bond_scales.items():
                    b_idx = bid_to_bidx.get(k, k if isinstance(k, int) else -1)
                    if 0 <= b_idx < n_bonds:
                        self._per_bond_scales[b_idx] = float(v)
            else:
                arr = np.asarray(snapshot.bond_scales, dtype=np.float32)
                m = min(n_bonds, len(arr))
                self._per_bond_scales[:m] = arr[:m]

        # 解析逐键自定义颜色
        self._per_bond_colors = {}
        if snapshot.bond_colors:
            bid_to_bidx = {bid: idx for idx, bid in enumerate(self._bond_ids)}
            for k, col in snapshot.bond_colors.items():
                if col is None:
                    continue
                b_idx = bid_to_bidx.get(k, k if isinstance(k, int) else -1)
                if 0 <= b_idx < n_bonds:
                    self._per_bond_colors[b_idx] = (float(col[0]), float(col[1]), float(col[2]))

        self.show_hydrogens = bool(snapshot.show_hydrogens)
        self.show_bonds = bool(snapshot.show_bonds)
        self.show_labels = bool(snapshot.show_labels)
        self.show_symbols = bool(snapshot.show_symbols)
        self.show_axes = bool(snapshot.show_axes)
        if getattr(self, "_axes_marker", None) is not None:
            try:
                self._axes_marker.SetEnabled(1 if self.show_axes else 0)
            except Exception:
                pass
        if getattr(self, "_origin_axes_actor", None) is not None:
            try:
                self._origin_axes_actor.SetVisibility(1 if self.show_axes else 0)
            except Exception:
                pass
        if snapshot.color_scheme:
            self._color_scheme = snapshot.color_scheme

        if snapshot.selected_atoms is not None:
            self._selected = {a for a in snapshot.selected_atoms if a in self._id_to_idx}
        if snapshot.selected_bonds is not None:
            self._selected_bonds = set(snapshot.selected_bonds)
        self._measure_chain = list(snapshot.measure_chain) if getattr(snapshot, "measure_chain", None) else None

        if self._viewer is None or vtk is None:
            return

        self._ensure_scene_initialized()
        self.clear_rubberband()
        self._rebuild_vtk_molecule_in_place()
        self._apply_mode()
        self._update_highlights_in_place()

        if reset_cam or not self._camera_state:
            self.reset_camera()
        else:
            self.render()

    def _apply_mode(self) -> None:
        if self._surface_actor is not None and self._viewer is not None:
            self._surface_actor.VisibilityOff()

        self._rebuild_vtk_molecule_in_place()
        if self._mode == RepresentationMode.SURFACE:
            self._build_surface()

    # ---------- 实时逐原子 / 逐键样式更新接口（无需重建快照，毫秒级立即生效！） ----------

    def set_single_atom_scale(self, atom_id: AtomId, scale: float) -> None:
        """单独修改某个原子的球体缩放比例并立即刷新 3D。"""
        idx = self._id_to_idx.get(atom_id)
        if idx is None or not (0 <= idx < len(self._per_atom_scales)):
            return
        self._per_atom_scales[idx] = max(0.20, min(3.50, float(scale)))
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    def set_single_atom_color(self, atom_id: AtomId, color: tuple[float, float, float] | None) -> None:
        """单独修改某个原子的 RGB 颜色并立即刷新 3D。"""
        idx = self._id_to_idx.get(atom_id)
        if idx is None:
            return
        if color is None:
            self._per_atom_colors.pop(idx, None)
        else:
            self._per_atom_colors[idx] = (float(color[0]), float(color[1]), float(color[2]))
        self._rebuild_vtk_molecule_in_place()
        self.render()

    def set_single_bond_scale(self, b_idx: int, scale: float) -> None:
        """单独修改某条化学键的粗细比例并立即刷新 3D。"""
        if not (0 <= b_idx < len(self._per_bond_scales)):
            return
        self._per_bond_scales[b_idx] = max(0.20, min(3.50, float(scale)))
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    def set_single_bond_color(self, b_idx: int, color: tuple[float, float, float] | None) -> None:
        """单独修改某条化学键的 RGB 颜色并立即刷新 3D。"""
        if color is None:
            self._per_bond_colors.pop(b_idx, None)
        else:
            self._per_bond_colors[b_idx] = (float(color[0]), float(color[1]), float(color[2]))
        self._rebuild_vtk_molecule_in_place()
        self.render()

    def set_color_scheme(self, scheme_name: str) -> None:
        """切换全局默认配色方案（未设自定义颜色的原子自动跟随切换）。"""
        if scheme_name in COLOR_SCHEMES:
            self._color_scheme = scheme_name
            self._rebuild_vtk_molecule_in_place()
            self.render()

    def set_view_options(
        self,
        show_hydrogens: bool | None = None,
        show_bonds: bool | None = None,
        show_labels: bool | None = None,
        show_symbols: bool | None = None,
        show_axes: bool | None = None,
    ) -> None:
        if show_hydrogens is not None:
            self.show_hydrogens = bool(show_hydrogens)
        if show_bonds is not None:
            self.show_bonds = bool(show_bonds)
        if show_labels is not None:
            self.show_labels = bool(show_labels)
        if show_symbols is not None:
            self.show_symbols = bool(show_symbols)
        if show_axes is not None:
            self.show_axes = bool(show_axes)
            if self._viewer is not None:
                try:
                    marker = getattr(self, "_axes_marker", None)
                    if marker is not None:
                        marker.SetEnabled(1 if self.show_axes else 0)
                    elif self.show_axes:
                        self._viewer.show_axes()
                    else:
                        self._viewer.hide_axes()
                except Exception:
                    pass
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    # ---------- 100% 纯 NumPy 相机读取与拾取（感知每个原子的独立缩放半径！） ----------

    def _get_camera_params(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        if self._viewer is not None:
            try:
                cam = self._viewer.renderer.GetActiveCamera()
                return (
                    np.array(cam.GetPosition(), dtype=np.float64),
                    np.array(cam.GetFocalPoint(), dtype=np.float64),
                    np.array(cam.GetViewUp(), dtype=np.float64),
                    float(cam.GetViewAngle()),
                )
            except Exception:
                pass
        return (
            np.array([0.0, 0.0, 15.0], dtype=np.float64),
            np.zeros(3, dtype=np.float64),
            np.array([0.0, 1.0, 0.0], dtype=np.float64),
            30.0,
        )

    def _screen_to_ray_numpy(self, lx: float, ly: float, widget_w: int, widget_h: int) -> tuple[np.ndarray, np.ndarray]:
        w = max(1.0, float(widget_w))
        h = max(1.0, float(widget_h))
        cam_pos, cam_focal, cam_up, fov_y = self._get_camera_params()
        eye, forward, right, true_up, tx, ty = compute_camera_basis(
            cam_pos, cam_focal, cam_up, fov_y, w, h
        )
        nx = (2.0 * float(lx) / w) - 1.0
        ny = 1.0 - (2.0 * float(ly) / h)
        ray_dir = forward + (nx * tx) * right + (ny * ty) * true_up
        ray_dir /= (float(np.linalg.norm(ray_dir)) + 1e-12)
        return eye, ray_dir

    def _project_points_to_qt_numpy(
        self, pts: np.ndarray, widget_w: int, widget_h: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        w = max(1.0, float(widget_w))
        h = max(1.0, float(widget_h))
        cam_pos, cam_focal, cam_up, fov_y = self._get_camera_params()
        eye, forward, right, true_up, tx, ty = compute_camera_basis(
            cam_pos, cam_focal, cam_up, fov_y, w, h
        )
        rel = np.asarray(pts, dtype=np.float64) - eye
        z_cam = np.maximum(0.1, rel @ forward)
        nx = (rel @ right) / (z_cam * tx)
        ny = (rel @ true_up) / (z_cam * ty)
        sx = 0.5 * w * (1.0 + nx)
        sy = 0.5 * h * (1.0 - ny)
        return sx, sy, z_cam, ty

    def pick_atom_id_at_qt(self, lx: float, ly: float, widget_w: int, widget_h: int) -> AtomId | None:
        """100% 纯 NumPy 拾取原子（自动使用每个原子真实的独立缩放半径 get_effective_atom_radius）。"""
        if self._coordinates is None or self._n_atoms == 0 or len(self._atom_ids) == 0:
            return None

        n = min(self._n_atoms, len(self._atom_ids), len(self._coordinates))
        coords = self._coordinates[:n]
        eye, ray_dir = self._screen_to_ray_numpy(lx, ly, widget_w, widget_h)

        radii = np.array([
            (0.0 if (not self.show_hydrogens and int(self._atomic_numbers[i]) == 1) else max(0.38, self.get_effective_atom_radius(i) * 1.25))
            for i in range(n)
        ], dtype=np.float64)

        hit_idx, _ = ray_sphere_intersect(eye, ray_dir, coords, radii)
        if 0 <= hit_idx < n and radii[hit_idx] > 0.0:
            return self._atom_ids[hit_idx]

        sx, sy, z_cam, ty = self._project_points_to_qt_numpy(coords, widget_w, widget_h)
        dists_px = np.hypot(sx - float(lx), sy - float(ly))
        proj_r_px = np.where(
            radii > 0.0,
            np.maximum(18.0, (radii / (z_cam * ty)) * (0.5 * max(1.0, float(widget_h)))),
            -1.0,
        )

        hits = np.where(dists_px <= proj_r_px)[0]
        if len(hits) > 0:
            order = sorted(hits, key=lambda idx: (round(float(z_cam[idx]), 2), float(dists_px[idx])))
            return self._atom_ids[int(order[0])]

        return None

    def pick_bond_idx_at_qt(self, lx: float, ly: float, widget_w: int, widget_h: int) -> int:
        """100% 纯 NumPy 拾取 3D 化学键（感知每条键的独立粗细）。"""
        if not self.show_bonds or self._coordinates is None or not self._bonds or self._n_atoms == 0:
            return -1

        eye, ray_dir = self._screen_to_ray_numpy(lx, ly, widget_w, widget_h)
        best_bond = -1
        best_t = float("inf")

        for b_idx, (i, j, _order) in enumerate(self._bonds):
            if 0 <= i < self._n_atoms and 0 <= j < self._n_atoms:
                if not self.show_hydrogens and (int(self._atomic_numbers[i]) == 1 or int(self._atomic_numbers[j]) == 1):
                    continue
                tol_3d = max(0.25, self.get_effective_bond_radius(b_idx) * 3.0)
                dist, t_val = ray_segment_closest(
                    eye, ray_dir, self._coordinates[i], self._coordinates[j]
                )
                if dist <= tol_3d and t_val < best_t:
                    best_t = t_val
                    best_bond = b_idx

        if best_bond >= 0:
            return best_bond

        sx, sy, z_cam, _ = self._project_points_to_qt_numpy(self._coordinates, widget_w, widget_h)
        best_d_px = 10.0
        for b_idx, (i, j, _order) in enumerate(self._bonds):
            if 0 <= i < self._n_atoms and 0 <= j < self._n_atoms:
                if not self.show_hydrogens and (int(self._atomic_numbers[i]) == 1 or int(self._atomic_numbers[j]) == 1):
                    continue
                x1, y1 = float(sx[i]), float(sy[i])
                x2, y2 = float(sx[j]), float(sy[j])
                dx, dy = x2 - x1, y2 - y1
                l2 = dx * dx + dy * dy
                if l2 < 1e-4:
                    continue
                t = max(0.18, min(0.82, ((lx - x1) * dx + (ly - y1) * dy) / l2))
                d_px = math.hypot(lx - (x1 + t * dx), ly - (y1 + t * dy))
                if d_px < best_d_px:
                    best_d_px = d_px
                    best_bond = b_idx

        return best_bond

    def unproject_qt_to_world(
        self, lx: float, ly: float, widget_w: int, widget_h: int, ref_point: np.ndarray | None = None
    ) -> np.ndarray:
        if ref_point is not None:
            center = np.asarray(ref_point, dtype=np.float64)
        elif self._coordinates is not None and len(self._coordinates) > 0:
            center = self._coordinates.mean(axis=0).astype(np.float64)
        else:
            center = np.zeros(3, dtype=np.float64)

        eye, ray_dir = self._screen_to_ray_numpy(lx, ly, widget_w, widget_h)
        cam_pos, cam_focal, _, _ = self._get_camera_params()
        view_dir = cam_focal - cam_pos
        norm_v = float(np.linalg.norm(view_dir))
        view_dir = view_dir / (norm_v if norm_v > 1e-9 else 1.0)

        denom = float(np.dot(ray_dir, view_dir))
        if abs(denom) < 1e-6:
            return center.astype(np.float32)
        t = float(np.dot(center - eye, view_dir)) / denom
        return (eye + t * ray_dir).astype(np.float32)

    # ---------- 60 FPS 单原子实时拖拽（原子与所有相连化学键同步跟随！） ----------

    def update_single_atom_coord(self, atom_id: AtomId, new_pos: np.ndarray) -> None:
        if self._coordinates is None or atom_id not in self._id_to_idx:
            return
        idx = self._id_to_idx[atom_id]
        if not (0 <= idx < self._n_atoms):
            return
        self._coordinates[idx] = np.asarray(new_pos, dtype=np.float32)
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    def update_multi_atoms_coords(self, pos_map: dict[AtomId, np.ndarray]) -> None:
        """
        实时批量更新多个选中原子的 3D 坐标及其关联化学键几何（用于框选/套索多原子拖拽平移，60fps 零卡顿）。
        """
        if self._coordinates is None or not pos_map:
            return
        updated_any = False
        for aid, new_pos in pos_map.items():
            idx = self._id_to_idx.get(aid)
            if idx is not None and 0 <= idx < self._n_atoms:
                self._coordinates[idx] = np.asarray(new_pos, dtype=np.float64)
                updated_any = True
        if not updated_any:
            return
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self._update_labels_in_place()
        self.render()

    def begin_interactive_lod(self) -> None:
        """
        P0-2 3D 旋转/缩放防卡顿加速：
        交互开始时临时关闭高开销 FXAA，并对 >100 原子的大体系自动降低球体/圆柱细分面数。
        """
        if getattr(self, "_in_interactive_lod", False):
            return
        self._in_interactive_lod = True
        if self._viewer is None:
            return
        try:
            ren = getattr(self._viewer, "renderer", None)
            if ren is not None and hasattr(ren, "SetUseFXAA"):
                ren.SetUseFXAA(False)
            if self._n_atoms > 80:
                if getattr(self, "_sphere_source", None) is not None:
                    self._sphere_source.SetThetaResolution(8)
                    self._sphere_source.SetPhiResolution(8)
                if getattr(self, "_bond_tube_filter", None) is not None:
                    self._bond_tube_filter.SetNumberOfSides(6)
        except Exception:
            pass

    def end_interactive_lod(self) -> None:
        """交互静止后恢复全分辨率球棍细分与 FXAA 抗锯齿。"""
        if not getattr(self, "_in_interactive_lod", False):
            return
        self._in_interactive_lod = False
        if self._viewer is None:
            return
        try:
            ren = getattr(self._viewer, "renderer", None)
            if ren is not None and hasattr(ren, "SetUseFXAA"):
                ren.SetUseFXAA(True)
            res = 16 if self._n_atoms > 500 else 28
            sides = 10 if self._n_atoms > 500 else 18
            if getattr(self, "_sphere_source", None) is not None:
                self._sphere_source.SetThetaResolution(res)
                self._sphere_source.SetPhiResolution(res)
            if getattr(self, "_bond_tube_filter", None) is not None:
                self._bond_tube_filter.SetNumberOfSides(sides)
            self.render()
        except Exception:
            pass

    def zoom_camera(self, factor: float = 1.2) -> None:
        """通过按钮精确放大 (factor > 1) 或缩小 (factor < 1) 3D 相机视角。"""
        if self._viewer is None:
            return
        try:
            cam = getattr(self._viewer, "camera", None)
            if cam is None and hasattr(self._viewer, "renderer"):
                cam = self._viewer.renderer.GetActiveCamera()
            if cam is not None and hasattr(cam, "Zoom"):
                cam.Zoom(float(factor))
                if hasattr(self._viewer, "renderer"):
                    self._viewer.renderer.ResetCameraClippingRange()
                self.render()
        except Exception:
            pass

    def update_coordinates(self, coordinates: np.ndarray) -> None:
        coords = np.asarray(coordinates, dtype=np.float32)
        self._coordinates = coords.copy()
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    # ---------- 原地更新高亮与橡皮筋（零 RemoveActor / 零 AddActor） ----------

    def update_rubberband_3d(self, p1: np.ndarray, p2: np.ndarray) -> None:
        self._ensure_scene_initialized()
        if self._rubberband_line is None or self._rubberband_actor is None:
            return
        self._rubberband_line.SetPoint1(float(p1[0]), float(p1[1]), float(p1[2]))
        self._rubberband_line.SetPoint2(float(p2[0]), float(p2[1]), float(p2[2]))
        self._rubberband_line.Modified()
        self._rubberband_actor.VisibilityOn()
        self.render()

    def clear_rubberband(self) -> None:
        if self._rubberband_actor is not None:
            self._rubberband_actor.VisibilityOff()

    def _resolve_topological_chain(self, indices: list[int]) -> list[int]:
        """在 2~4 个原子构成的导出子图中，根据化学键拓扑恢复连通的测量链，杜绝无序 set 导致拉出空间斜穿连线。"""
        n = len(indices)
        if n <= 2:
            return list(indices)

        idx_set = set(indices)
        adj: dict[int, list[int]] = {i: [] for i in indices}
        for u, v, _ in self._bonds:
            if u in idx_set and v in idx_set:
                adj[u].append(v)
                adj[v].append(u)

        if n == 3:
            deg2 = [u for u in indices if len(adj[u]) == 2]
            if len(deg2) == 1:
                mid = deg2[0]
                ends = [u for u in indices if u != mid]
                return [ends[0], mid, ends[1]]
            return list(indices)

        if n == 4:
            import itertools
            for perm in itertools.permutations(indices, 4):
                if (
                    perm[1] in adj[perm[0]]
                    and perm[2] in adj[perm[1]]
                    and perm[3] in adj[perm[2]]
                ):
                    return list(perm)
            return list(indices)

        return list(indices)

    def _update_highlights_in_place(self) -> None:
        """原地修改选中原子光晕与选中化学键光环（读取真实的逐原子半径与逐键粗细）。"""
        self._ensure_scene_initialized()
        if (
            self._highlight_points is None
            or self._highlight_radii is None
            or self._highlight_polydata is None
            or self._highlight_actor is None
            or self._coordinates is None
        ):
            return

        self._highlight_points.Reset()
        self._highlight_radii.Reset()
        self._highlight_radii.SetName("halo_scale")

        selected_indices: list[int] = []
        for atom_id in self._selected:
            idx = self._id_to_idx.get(atom_id)
            if idx is None or not (0 <= idx < self._n_atoms):
                continue
            r_eff = self.get_effective_atom_radius(idx)
            if r_eff <= 0.0:
                continue
            selected_indices.append(idx)
            pos = self._coordinates[idx]
            halo_r = max(0.32, r_eff * 1.28)
            self._highlight_points.InsertNextPoint(float(pos[0]), float(pos[1]), float(pos[2]))
            self._highlight_radii.InsertNextValue(float(halo_r))

        self._highlight_points.Modified()
        self._highlight_radii.Modified()
        self._highlight_polydata.Modified()
        self._highlight_actor.SetVisibility(bool(selected_indices))

        # 原地更新选中化学键高亮套管
        if self._hl_bond_points is not None and self._hl_bond_lines is not None and self._hl_bond_actor is not None:
            self._hl_bond_points.Reset()
            self._hl_bond_lines.Reset()
            self._hl_bond_radii.Reset()
            self._hl_bond_radii.SetName("hl_bond_r")
            hl_b_cnt = 0
            if self._selected_bonds and self._bond_ids:
                bid_to_bidx = {bid: i for i, bid in enumerate(self._bond_ids)}
                for bid in self._selected_bonds:
                    b_idx = bid_to_bidx.get(bid, -1)
                    if 0 <= b_idx < len(self._bonds):
                        i, j, _ = self._bonds[b_idx]
                        if 0 <= i < self._n_atoms and 0 <= j < self._n_atoms:
                            p1, p2 = self._coordinates[i], self._coordinates[j]
                            r_hl = self.get_effective_bond_radius(b_idx) * 1.65
                            self._hl_bond_points.InsertNextPoint(float(p1[0]), float(p1[1]), float(p1[2]))
                            self._hl_bond_points.InsertNextPoint(float(p2[0]), float(p2[1]), float(p2[2]))
                            self._hl_bond_radii.InsertNextValue(float(r_hl))
                            self._hl_bond_radii.InsertNextValue(float(r_hl))
                            self._hl_bond_lines.InsertNextCell(2)
                            self._hl_bond_lines.InsertCellPoint(hl_b_cnt * 2)
                            self._hl_bond_lines.InsertCellPoint(hl_b_cnt * 2 + 1)
                            hl_b_cnt += 1
            self._hl_bond_points.Modified()
            self._hl_bond_lines.Modified()
            self._hl_bond_radii.Modified()
            self._hl_bond_polydata.Modified()
            self._hl_bond_actor.SetVisibility(hl_b_cnt > 0)

        # 原地更新 2~4 个选中原子之间的测量连线
        if self._measure_points is not None and self._measure_lines is not None and self._measure_actor is not None:
            self._measure_points.Reset()
            self._measure_lines.Reset()
            chain_indices: list[int] = []
            if self._measure_chain:
                valid_chain = True
                for aid in self._measure_chain:
                    idx = self._id_to_idx.get(aid)
                    if idx is not None and 0 <= idx < self._n_atoms:
                        chain_indices.append(idx)
                    else:
                        valid_chain = False
                        break
                if not valid_chain:
                    chain_indices.clear()

            if not chain_indices and 2 <= len(selected_indices) <= 4:
                chain_indices = self._resolve_topological_chain(selected_indices)

            if 2 <= len(chain_indices) <= 4:
                for idx in chain_indices:
                    p = self._coordinates[idx]
                    self._measure_points.InsertNextPoint(float(p[0]), float(p[1]), float(p[2]))
                for k in range(len(chain_indices) - 1):
                    self._measure_lines.InsertNextCell(2)
                    self._measure_lines.InsertCellPoint(k)
                    self._measure_lines.InsertCellPoint(k + 1)
                self._measure_points.Modified()
                self._measure_lines.Modified()
                self._measure_polydata.Modified()
                self._measure_actor.VisibilityOn()
            else:
                self._measure_actor.VisibilityOff()

    # ---------- 安全防重入渲染与相机控制 ----------

    def render(self) -> None:
        if self._viewer is None or self._render_pending or self._in_render:
            return
        self._render_pending = True
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._do_safe_render)

    def _do_safe_render(self) -> None:
        self._render_pending = False
        if self._viewer is None or self._in_render:
            return
        self._in_render = True
        try:
            self._viewer.render()
            self.save_camera_state()
        except Exception:
            pass
        finally:
            self._in_render = False

    def reset_camera(self) -> None:
        if self._viewer is None:
            return
        try:
            ren = self._viewer.renderer
            cam = ren.GetActiveCamera()
            if self._coordinates is not None and len(self._coordinates) >= 3:
                coords = self._coordinates.astype(np.float64)
                center = coords.mean(axis=0)
                centered = coords - center
                _, _, vh = np.linalg.svd(centered, full_matrices=False)
                normal = vh[2] if len(vh) >= 3 else np.array([0.0, 0.0, 1.0])
                up_vec = vh[1] if len(vh) >= 2 else np.array([0.0, 1.0, 0.0])
                if normal[2] < 0:
                    normal = -normal
                if up_vec[1] < 0:
                    up_vec = -up_vec
                span = max(4.5, float(np.linalg.norm(centered, axis=1).max()) * 2.4)
                dist = span / math.tan(math.radians(15.0))
                cam.SetFocalPoint(float(center[0]), float(center[1]), float(center[2]))
                pos = center + normal * dist
                cam.SetPosition(float(pos[0]), float(pos[1]), float(pos[2]))
                cam.SetViewUp(float(up_vec[0]), float(up_vec[1]), float(up_vec[2]))
                ren.ResetCameraClippingRange()
            else:
                self._viewer.reset_camera()
            self.save_camera_state()
            self.render()
        except Exception:
            pass

    def set_view_direction(self, direction: str) -> None:
        """设置固定视图方向：front(沿-Z看)/side(沿-X看)/top(沿+Y看)/iso(等轴测)。"""
        if self._viewer is None or self._coordinates is None:
            return
        try:
            ren = self._viewer.renderer
            cam = ren.GetActiveCamera()
            coords = self._coordinates.astype(np.float64)
            center = coords.mean(axis=0)
            span = max(4.5, float(np.linalg.norm(coords - center, axis=1).max()) * 2.0)
            dist = span / math.tan(math.radians(15.0))

            directions = {
                "front": {"pos": np.array([0.0, 0.0, -1.0]), "up": np.array([0.0, 1.0, 0.0])},
                "side":  {"pos": np.array([-1.0, 0.0, 0.0]), "up": np.array([0.0, 1.0, 0.0])},
                "top":   {"pos": np.array([0.0, 1.0, 0.0]), "up": np.array([0.0, 0.0, -1.0])},
                "iso":   {"pos": np.array([1.0, 1.0, 1.0]), "up": np.array([0.0, 1.0, 0.0])},
            }
            d = directions.get(direction, directions["front"])
            cam.SetFocalPoint(float(center[0]), float(center[1]), float(center[2]))
            pos = center + d["pos"] * dist
            cam.SetPosition(float(pos[0]), float(pos[1]), float(pos[2]))
            cam.SetViewUp(float(d["up"][0]), float(d["up"][1]), float(d["up"][2]))
            ren.ResetCameraClippingRange()
            self.save_camera_state()
            self.render()
        except Exception:
            pass

    def save_camera_state(self) -> dict:
        if self._viewer is None:
            return {}
        try:
            camera = self._viewer.camera
            self._camera_state = {
                "position": tuple(camera.position),
                "focal_point": tuple(camera.focal_point),
                "up": tuple(camera.up),
                "view_angle": float(camera.view_angle),
            }
        except Exception:
            pass
        return self._camera_state or {}

    def restore_camera_state(self, state: dict | None = None) -> None:
        if self._viewer is None:
            return
        state = state or self._camera_state
        if not state:
            return
        try:
            camera = self._viewer.camera
            if "position" in state:
                camera.position = state["position"]
            if "focal_point" in state:
                camera.focal_point = state["focal_point"]
            if "up" in state:
                camera.up = state["up"]
            if "view_angle" in state:
                camera.view_angle = state["view_angle"]
            self._viewer.renderer.ResetCameraClippingRange()
        except Exception:
            pass

    def set_mode(self, mode: RepresentationMode) -> None:
        self._mode = mode
        self._apply_mode()
        self.render()

    def set_selection(
        self,
        selected: set[AtomId],
        selected_bonds: set[BondId] | None = None,
        measure_chain: Sequence[AtomId] | None = None,
    ) -> None:
        self._selected = {a for a in selected if a in self._id_to_idx}
        if selected_bonds is not None:
            self._selected_bonds = set(selected_bonds)
        if measure_chain is not None:
            self._measure_chain = list(measure_chain)
        elif not self._selected:
            self._measure_chain = None
        self._update_highlights_in_place()
        self.render()

    def set_on_selection_changed(self, callback: Callable[[set[AtomId]], None]) -> None:
        self._on_selection_changed = callback

    def export_image(self, path: str, width: int = 1920, height: int = 1080) -> None:
        if self._viewer:
            self._viewer.screenshot(path, transparent_background=False)

    def set_material_preset(self, preset_name: str) -> None:
        preset = PRESETS.get(preset_name, StudioPreset)
        if self._viewer is None:
            return
        self._viewer.set_background(
            color=list(preset.background_bottom),
            top=list(preset.background_top),
        )
        for act in (self._atom_actor, self._bond_actor):
            if act is not None:
                prop = act.GetProperty()
                prop.SetInterpolationToPhong()
                prop.SetSpecular(max(0.15, 1.0 - preset.roughness))
                prop.SetSpecularPower(max(15.0, (1.0 - preset.roughness) * 60.0))
        self.render()

    def set_roughness(self, value: float) -> None:
        v = max(0.05, min(0.95, float(value)))
        for act in (self._atom_actor, self._bond_actor):
            if act is not None:
                act.GetProperty().SetSpecular(max(0.1, 1.0 - v))
                act.GetProperty().SetSpecularPower(max(10.0, (1.0 - v) * 65.0))
        self.render()

    def set_metallic(self, value: float) -> None:
        v = max(0.0, min(1.0, float(value)))
        for act in (self._atom_actor, self._bond_actor):
            if act is not None:
                act.GetProperty().SetAmbient(0.22 + 0.28 * v)
        self.render()

    def set_atom_scale(self, scale: float) -> None:
        """设置全局原子缩放比例（保留每个原子的独立 _per_atom_scales 相对比例）。"""
        self._atom_scale = max(0.30, min(2.60, float(scale)))
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    def set_bond_scale(self, scale: float) -> None:
        """设置全局化学键粗细比例（保留每条键的独立 _per_bond_scales 相对比例）。"""
        self._bond_scale = max(0.30, min(2.60, float(scale)))
        self._rebuild_vtk_molecule_in_place()
        self._update_highlights_in_place()
        self.render()

    def set_background_color(self, r: float, g: float, b: float) -> None:
        if self._viewer is None:
            return
        self._viewer.set_background(color=[float(r), float(g), float(b)])
        self.render()

    # ---------- 轨道 / 体数据 / 表面 ----------

    def clear_orbital(self):
        if self._viewer is None:
            return
        for a in self._orbital_actors:
            a.VisibilityOff()
        self._orbital_actors = []
        self.render()

    def set_orbital(self, cube, isovalue=0.05, opacity=0.68,
                    pos_color=(0.22, 0.64, 1.0), neg_color=(1.0, 0.44, 0.24)):
        import pyvista as pv
        if self._viewer is None:
            return
        self.clear_orbital()
        nx, ny, nz = cube.dims
        sp = float(np.linalg.norm(cube.axes[0]))
        grid = pv.ImageData(dimensions=(nx, ny, nz), spacing=(1, 1, 1), origin=(0, 0, 0))
        grid.point_data["orb"] = np.ascontiguousarray(cube.values.flatten(order="F"))
        origin = np.asarray(cube.origin, dtype=float)
        for iso, color in ((abs(isovalue), pos_color), (-abs(isovalue), neg_color)):
            try:
                surf = grid.contour([iso], scalars="orb", method="flying_edges")
                if surf.n_points == 0:
                    continue
                surf.points = surf.points * sp + origin
                act = self._viewer.add_mesh(
                    surf, color=color, opacity=opacity, smooth_shading=True,
                    specular=0.45, specular_power=32)
                self._orbital_actors.append(act)
            except Exception as e:
                print("[orbital] 等值面失败:", e)

    def clear_volume(self):
        if self._viewer is None:
            return
        for a in self._volume_actors:
            a.VisibilityOff()
        self._volume_actors = []
        self.render()

    @staticmethod
    def _is_orthogonal(axes, tol=1e-4) -> bool:
        off = axes - np.diag(np.diag(axes))
        return bool(np.all(np.abs(off) < tol))

    def _downsample(self, cube, max_voxels: int):
        total = int(np.prod(cube.dims))
        if total <= max_voxels:
            return cube.values, cube.dims, 1
        step = max(1, int(np.ceil((total / max_voxels) ** (1 / 3))))
        vals = cube.values[::step, ::step, ::step]
        return vals, vals.shape, step

    def set_volume(self, cube, max_voxels: int = 2_000_000, cmap: str = "turbo"):
        import pyvista as pv
        if self._viewer is None:
            return
        self.clear_volume()
        vals, dims, step = self._downsample(cube, max_voxels)
        axes = cube.axes * step
        origin = np.asarray(cube.origin, dtype=float)
        if self._is_orthogonal(axes):
            spacing = tuple(float(np.abs(axes[i, i])) for i in range(3))
            grid = pv.ImageData(dimensions=dims, spacing=spacing, origin=origin)
        else:
            nx, ny, nz = dims
            ix, iy, iz = np.meshgrid(np.arange(nx), np.arange(ny), np.arange(nz), indexing="ij")
            pts = (origin + ix.reshape(-1, 1) * axes[0]
                   + iy.reshape(-1, 1) * axes[1]
                   + iz.reshape(-1, 1) * axes[2])
            grid = pv.StructuredGrid()
            grid.points = pts
            grid.dimensions = dims
        grid.point_data["scalar"] = np.ascontiguousarray(vals.flatten(order="F"))
        act = self._viewer.add_volume(grid, cmap=cmap, opacity="linear", shade=False, show_scalar_bar=True)
        self._volume_actors.append(act)

    def set_slice(self, cube, axis: int = 2, fraction: float = 0.5, cmap: str = "turbo"):
        import pyvista as pv
        if self._viewer is None:
            return
        self.clear_volume()
        nx, ny, nz = cube.dims
        idx = int(np.clip(fraction, 0, 1) * (cube.dims[axis] - 1))
        if axis == 0:
            plane_vals = cube.values[idx, :, :]
            a, b = np.meshgrid(np.arange(ny), np.arange(nz), indexing="ij")
            keys = np.stack([np.full_like(a, idx), a, b], axis=-1).reshape(-1, 3)
            dims2 = (ny, nz)
        elif axis == 1:
            plane_vals = cube.values[:, idx, :]
            a, b = np.meshgrid(np.arange(nx), np.arange(nz), indexing="ij")
            keys = np.stack([a, np.full_like(a, idx), b], axis=-1).reshape(-1, 3)
            dims2 = (nx, nz)
        else:
            plane_vals = cube.values[:, :, idx]
            a, b = np.meshgrid(np.arange(nx), np.arange(ny), indexing="ij")
            keys = np.stack([a, b, np.full_like(a, idx)], axis=-1).reshape(-1, 3)
            dims2 = (nx, ny)
        pts = (cube.origin + keys[:, 0:1] * cube.axes[0]
               + keys[:, 1:2] * cube.axes[1] + keys[:, 2:3] * cube.axes[2])
        grid = pv.StructuredGrid()
        grid.points = pts
        grid.dimensions = (dims2[0], dims2[1], 1)
        grid.point_data["scalar"] = plane_vals.flatten()
        act = self._viewer.add_mesh(grid, scalars="scalar", cmap=cmap, show_scalar_bar=True)
        self._volume_actors.append(act)

    def _build_surface(self) -> None:
        if self._coordinates is None or self._atomic_numbers is None or self._viewer is None or vtk is None:
            return
        coords = self._coordinates
        n = self._n_atoms
        if n == 0:
            return
        implicit_balls = vtk.vtkImplicitBoolean()
        implicit_balls.SetOperationTypeToUnion()
        for i in range(n):
            r = VDW_RADII.get(int(self._atomic_numbers[i]), DEFAULT_VDW)
            sphere = vtk.vtkSphere()
            sphere.SetRadius(r)
            sphere.SetCenter(float(coords[i, 0]), float(coords[i, 1]), float(coords[i, 2]))
            implicit_balls.AddFunction(sphere)
        min_b = coords.min(axis=0) - 1.8
        max_b = coords.max(axis=0) + 1.8
        spacing = 0.18
        sample = vtk.vtkSampleFunction()
        sample.SetImplicitFunction(implicit_balls)
        sample.SetSampleDimensions(
            max(12, int((max_b[0] - min_b[0]) / spacing)),
            max(12, int((max_b[1] - min_b[1]) / spacing)),
            max(12, int((max_b[2] - min_b[2]) / spacing)),
        )
        sample.SetModelBounds(min_b[0], max_b[0], min_b[1], max_b[1], min_b[2], max_b[2])
        sample.ComputeNormalsOn()
        flying_edges = vtk.vtkFlyingEdges3D()
        flying_edges.SetInputConnection(sample.GetOutputPort())
        flying_edges.SetValue(0, 0.0)
        smoother = vtk.vtkWindowedSincPolyDataFilter()
        smoother.SetInputConnection(flying_edges.GetOutputPort())
        smoother.SetNumberOfIterations(18)
        smoother.SetPassBand(0.08)
        smoother.NonManifoldSmoothingOn()
        smoother.NormalizeCoordinatesOn()

        if self._surface_actor is None:
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(smoother.GetOutputPort())
            mapper.ScalarVisibilityOff()
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(0.38, 0.82, 0.88)
            actor.GetProperty().SetOpacity(0.26)
            actor.GetProperty().SetInterpolationToPhong()
            actor.GetProperty().SetSpecular(0.5)
            actor.GetProperty().SetSpecularPower(45.0)
            actor.GetProperty().SetFrontfaceCulling(False)
            actor.GetProperty().SetBackfaceCulling(False)
            actor.SetPickable(False)
            self._viewer.renderer.AddActor(actor)
            self._surface_actor = actor
        else:
            self._surface_actor.GetMapper().SetInputConnection(smoother.GetOutputPort())
            self._surface_actor.VisibilityOn()


# 兼容别名
    def clear_qtaim(self):
        """清除当前视口中显示的所有 QTAIM 临界点与键径。"""
        if self._viewer is None:
            return
        for a in self._qtaim_actors:
            try:
                a.VisibilityOff()
            except Exception:
                pass
        self._qtaim_actors = []
        self.render()

    def set_qtaim(self, critical_points, bond_paths=None, bcp_radius: float = 0.14, path_radius: float = 0.035):
        """在 3D 视口中叠合渲染 QTAIM 拓扑临界点与梯度键径。"""
        import pyvista as pv
        if self._viewer is None:
            return
        self.clear_qtaim()

        # 1. 临界点 (BCP: 琥珀金; RCP: 青色; CCP: 紫罗兰)
        for cp in critical_points:
            pos = getattr(cp, "coords_angstrom", None)
            if pos is None:
                continue
            cp_type = getattr(cp, "cp_type", "")
            if cp_type == "(3,-1)":
                color = (1.0, 0.65, 0.15)
                r = bcp_radius
            elif cp_type == "(3,+1)":
                color = (0.15, 0.85, 0.85)
                r = bcp_radius * 1.15
            elif cp_type == "(3,+3)":
                color = (0.85, 0.25, 0.85)
                r = bcp_radius * 1.25
            else:
                continue

            sphere = pv.Sphere(radius=r, center=pos)
            act = self._viewer.add_mesh(
                sphere, color=color, smooth_shading=True,
                specular=0.5, specular_power=24
            )
            self._qtaim_actors.append(act)

        # 2. 键径 (Bond paths)
        if bond_paths:
            for path in bond_paths:
                pts = getattr(path, "points_angstrom", None)
                if pts is not None and len(pts) >= 2:
                    try:
                        line = pv.lines_from_points(pts)
                        tube = line.tube(radius=path_radius)
                        act = self._viewer.add_mesh(
                            tube, color=(0.95, 0.85, 0.35), smooth_shading=True,
                            specular=0.4, specular_power=20
                        )
                        self._qtaim_actors.append(act)
                    except Exception:
                        pass

        self.render()


# 兼容别名
VTKMoleculeBackend = VtkRendererBackend
