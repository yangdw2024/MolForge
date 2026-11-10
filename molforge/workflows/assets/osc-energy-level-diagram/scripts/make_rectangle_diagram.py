# -*- coding: utf-8 -*-
# make_rectangle_diagram.py
# 矩形条能级图: 每个分子一个矩形, 上沿=LUMO, 下沿=HOMO, 仿论文图D风格
import json, os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

OUT_DIR = r"<D_DRIVE_YDW>\OSC\Object_1\2610\工作三"
with open(os.path.join(OUT_DIR, "levels.json")) as f:
    lv = json.load(f)

order = ["BTP-ClFFCl", "BTP-FClClF", "BTP-FClFCl", "BTP-FFClCl", "HDO-4Cl", "p4PM6"]
colors = {
    "BTP-ClFFCl": RGBColor(0xFF, 0x8C, 0x00),
    "BTP-FClClF": RGBColor(0x3C, 0xB3, 0x71),
    "BTP-FClFCl": RGBColor(0x46, 0x82, 0xB4),
    "BTP-FFClCl": RGBColor(0x93, 0x70, 0xDB),
    "HDO-4Cl":    RGBColor(0xFF, 0x14, 0x93),
    "p4PM6":      RGBColor(0x00, 0xBF, 0xBF),
}

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])

# 白底
slide.background.fill.solid()
slide.background.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

# ---------- 绘图区参数 (inch) ----------
X0, X1 = 1.6, 12.6          # 纵轴左右
Y_TOP, Y_BOT = 0.7, 6.6     # 纵轴上下
E_TOP, E_BOT = -2.5, -6.0   # 纵轴能量范围 (p4PM6 LUMO=-2.87, 上界放宽)

def e2y(E):
    """能量 eV -> y 坐标 (inch)"""
    return Y_TOP + (E_TOP - E) / (E_TOP - E_BOT) * (Y_BOT - Y_TOP)

# ---------- 纵轴 ----------
# 纵轴线
axis = slide.shapes.add_connector(1, Inches(X0), Inches(Y_TOP), Inches(X0), Inches(Y_BOT))
axis.line.color.rgb = RGBColor(0, 0, 0)
axis.line.width = Pt(1.5)

# 纵轴刻度 -2.5, -3.0, ..., -6.0
for E in [round(-2.5 - i*0.5, 1) for i in range(8)]:
    y = e2y(E)
    tick = slide.shapes.add_connector(1, Inches(X0-0.08), Inches(y), Inches(X0), Inches(y))
    tick.line.color.rgb = RGBColor(0, 0, 0)
    tick.line.width = Pt(1)
    tb = slide.shapes.add_textbox(Inches(X0-0.9), Inches(y-0.15), Inches(0.8), Inches(0.3))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = f"{E:.1f}"
    r.font.name = "Arial"
    r.font.size = Pt(14)
    r.font.color.rgb = RGBColor(0, 0, 0)

# 纵轴标题 "Energy Level (eV)" 竖排
tb = slide.shapes.add_textbox(Inches(0.2), Inches(2.5), Inches(0.5), Inches(2.5))
tf = tb.text_frame
tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
p = tf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
r = p.add_run()
r.text = "Energy Level (eV)"
r.font.name = "Arial"
r.font.size = Pt(18)
r.font.bold = True
r.font.color.rgb = RGBColor(0, 0, 0)
# 竖排
tb.rotation = 270

# ---------- 5 个矩形 ----------
RECT_W = 1.0
n = len(order)
x_gap = (X1 - X0 - n * RECT_W) / (n - 1)

for i, name in enumerate(order):
    x_left = X0 + 0.4 + i * (RECT_W + x_gap)
    y_lumo = e2y(lv[name]["lumo"])
    y_homo = e2y(lv[name]["homo"])
    h = y_homo - y_lumo

    # 矩形 (透明填充, 彩色粗边框)
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                Inches(x_left), Inches(y_lumo),
                                Inches(RECT_W), Inches(h))
    sh.fill.background()
    sh.line.color.rgb = colors[name]
    sh.line.width = Pt(3.5)
    # 去掉阴影
    sh.shadow.inherit = False

    # 矩形中间竖排分子名
    tb = slide.shapes.add_textbox(Inches(x_left), Inches(y_lumo + h/2 - 0.3),
                                  Inches(RECT_W), Inches(0.6))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = name
    r.font.name = "Arial"
    r.font.size = Pt(14)
    r.font.bold = True
    r.font.color.rgb = colors[name]
    tb.rotation = 270

    # 矩形上方 LUMO 数值
    tb = slide.shapes.add_textbox(Inches(x_left-0.3), Inches(y_lumo-0.45),
                                  Inches(RECT_W+0.6), Inches(0.35))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = f"{lv[name]['lumo']:.2f}"
    r.font.name = "Arial"
    r.font.size = Pt(16)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 0, 0)

    # 矩形下方 HOMO 数值
    tb = slide.shapes.add_textbox(Inches(x_left-0.3), Inches(y_homo+0.1),
                                  Inches(RECT_W+0.6), Inches(0.35))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = f"{lv[name]['homo']:.2f}"
    r.font.name = "Arial"
    r.font.size = Pt(16)
    r.font.bold = True
    r.font.color.rgb = RGBColor(0, 0, 0)

out = os.path.join(OUT_DIR, "能级图_矩形条_B3LYP.pptx")
prs.save(out)
print("saved:", out)
