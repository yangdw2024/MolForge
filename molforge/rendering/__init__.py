"""
rendering/ - 渲染层
=====================
负责把 domain 数据可视化。
不包含业务逻辑，只负责绘制。

目录结构：
  contracts.py      - Renderer3D Protocol（抽象接口）
  materials.py      - Scientific/Studio 材质预设
  representations.py - 表示方式定义（球棍/CPK/表面/轨道）
  vtk/              - VTK 后端实现
  render2d/         - 2D 渲染（QGraphicsView + RDKit）
"""

from .contracts import Renderer3D, RenderSnapshot, RepresentationMode
from .materials import MaterialPreset, ScientificPreset, StudioPreset

__all__ = [
    "Renderer3D", "RenderSnapshot", "RepresentationMode",
    "MaterialPreset", "ScientificPreset", "StudioPreset",
]
