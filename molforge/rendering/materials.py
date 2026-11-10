"""
rendering/materials.py - 材质预设
=====================================
两套视觉预设：
  - Scientific：精确、克制、颜色可辨，适合科研和论文
  - Studio：柔和高光、真实阴影、精美材质，适合展示和封面
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MaterialPreset:
    """材质预设配置。"""
    name: str
    # 背景
    background_top: tuple[float, float, float] = (0.95, 0.96, 0.98)
    background_bottom: tuple[float, float, float] = (0.88, 0.90, 0.94)

    # 光照
    key_light_color: tuple[float, float, float] = (1.0, 0.95, 0.85)
    key_light_intensity: float = 1.0
    fill_light_color: tuple[float, float, float] = (0.80, 0.88, 1.0)
    fill_light_intensity: float = 0.6
    rim_light_color: tuple[float, float, float] = (1.0, 1.0, 1.0)
    rim_light_intensity: float = 0.4

    # 材质
    metallic: float = 0.0
    roughness: float = 0.42
    ao_enabled: bool = True
    ssao_radius: float = 0.55
    tonemap_enabled: bool = True
    fxaa_enabled: bool = True

    # 元素配色（CPK 风格）
    element_colors: dict[int, tuple[float, float, float]] = field(default_factory=dict)


# Scientific 预设：论文风格，清晰克制
ScientificPreset = MaterialPreset(
    name="Scientific",
    background_top=(0.96, 0.97, 0.99),
    background_bottom=(0.90, 0.92, 0.95),
    key_light_intensity=1.1,
    fill_light_intensity=0.5,
    rim_light_intensity=0.3,
    roughness=0.5,
    ssao_radius=0.4,
    element_colors={
        1:  (0.90, 0.90, 0.90),  # H 浅灰
        6:  (0.30, 0.35, 0.40),  # C 深石墨
        7:  (0.25, 0.40, 0.80),  # N 蓝
        8:  (0.80, 0.25, 0.25),  # O 红
        9:  (0.40, 0.70, 0.40),  # F 绿
        15: (0.90, 0.60, 0.20),  # P 橙
        16: (0.85, 0.75, 0.20),  # S 黄
        17: (0.30, 0.65, 0.35),  # Cl 绿
    },
)

# Studio 预设：展示风格，柔和精美（按设计令牌）
StudioPreset = MaterialPreset(
    name="Studio",
    # 3D 背景：蓝灰色渐变（参考设计稿）
    background_top=(0.376, 0.486, 0.573),   # #607C92
    background_bottom=(0.133, 0.224, 0.306), # #22394E
    # 光照
    key_light_color=(1.0, 0.95, 0.85),
    key_light_intensity=1.3,
    fill_light_color=(0.75, 0.85, 1.0),
    fill_light_intensity=0.7,
    rim_light_color=(1.0, 1.0, 1.0),
    rim_light_intensity=0.6,
    # 材质
    metallic=0.05,
    roughness=0.32,
    ao_enabled=True,
    ssao_radius=0.65,
    tonemap_enabled=True,
    fxaa_enabled=True,
    # 元素配色（按设计令牌 chemistry_colors_dark）
    element_colors={
        1:  (0.953, 0.961, 0.949),  # H #F3F5F2
        6:  (0.463, 0.545, 0.620),  # C #768B9E
        7:  (0.353, 0.612, 0.949),  # N #5A9CF2
        8:  (0.949, 0.467, 0.471),  # O #F27778
        9:  (0.400, 0.800, 0.550),  # F
        15: (0.933, 0.682, 0.404),  # P #EEAE67
        16: (0.957, 0.808, 0.427),  # S #F4CE6D
        17: (0.400, 0.800, 0.569),  # Cl #66CC91
    },
)

# Analysis 预设：分析风格，高性能（用于大分子）
AnalysisPreset = MaterialPreset(
    name="Analysis",
    # 深色背景，减少视觉干扰
    background_top=(0.1, 0.1, 0.12),
    background_bottom=(0.05, 0.05, 0.08),
    # 光照：简化，提高性能
    key_light_color=(1.0, 1.0, 1.0),
    key_light_intensity=1.0,
    fill_light_color=(0.8, 0.8, 0.9),
    fill_light_intensity=0.3,
    rim_light_intensity=0.0,  # 关闭轮廓光
    # 材质：关闭高级效果，提高性能
    metallic=0.0,
    roughness=0.6,  # 更粗糙，减少高光计算
    ao_enabled=False,  # 关闭 SSAO
    ssao_radius=0.0,
    tonemap_enabled=False,  # 关闭色调映射
    fxaa_enabled=False,  # 关闭抗锯齿
    # 元素配色：高对比度，便于识别
    element_colors={
        1:  (0.9, 0.9, 0.9),
        6:  (0.6, 0.6, 0.6),
        7:  (0.3, 0.5, 1.0),
        8:  (1.0, 0.3, 0.3),
        9:  (0.3, 0.8, 0.3),
        15: (1.0, 0.6, 0.2),
        16: (1.0, 0.9, 0.2),
        17: (0.2, 0.8, 0.4),
    },
)
