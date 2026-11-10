# -*- coding: utf-8 -*-
# make_level_lines_diagram.py
# 水平线 + 轨道小图 + Gap 箭头风格
import json, os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from PIL import Image

OUT_DIR = r"<D_DRIVE_YDW>\OSC\Object_1\2610\工作三"
LMO = r"<D_DRIVE_YDW>\OSC\Object_1\Binary_Datas\B3LYP_6-311g(d,p)\LMO"
TMP = os.path.join(OUT_DIR, "_orb_png")
os.makedirs(TMP, exist_ok=True)

with open(os.path.join(OUT_DIR, "levels.json")) as f:
    lv = json.load(f)

order = ["BTP-ClFFCl", "BTP-FClClF", "BTP-FClFCl", "BTP-FFClCl", "HDO-4Cl", "p4PM6"]
submap = {
    "BTP-ClFFCl": "ClFFCl",
    "BTP-FClClF": "FClClF",
    "BTP-FClFCl": "FClFCl",
    "BTP-FFClCl": "FFClCl",
    "HDO-4Cl": "HDO4Cl",
    "p4PM6": "p4PM6",
}

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])
slide.background.fill.solid()
slide.background.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

# ---------- 绘图区 ----------
X0, X1 = 1.5, 12.5
Y_TOP, Y_BOT = 1.0, 6.2
E_TOP, E_BOT = -2.5, -6.5

def e2y(E):
    return Y_TOP + (E_TOP - E) / (E_TOP - E_BOT) * (Y_BOT - Y_TOP)

# ---------- 纵轴 ----------
axis = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                  Inches(X0), Inches(Y_TOP), Inches(X0), Inches(Y_BOT))
axis.line.color.rgb = RGBColor(0, 0, 0)
axis.line.width = Pt(1.5)

for E in [round(-2.5 - i*0.5, 1) for i in range(9)]:
    y = e2y(E)
    tick = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                      Inches(X0-0.08), Inches(y), Inches(X0), Inches(y))
    tick.line.color.rgb = RGBColor(0, 0, 0)
    tick.line.width = Pt(1)
    tb = slide.shapes.add_textbox(Inches(X0-0.85), Inches(y-0.13), Inches(0.75), Inches(0.26))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.RIGHT
    r = p.add_run(); r.text = f"{E:.1f}"
    r.font.name = "Arial"; r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(0, 0, 0)

# 纵轴标题
tb = slide.shapes.add_textbox(Inches(0.15), Inches(2.3), Inches(0.5), Inches(2.5))
tf = tb.text_frame
tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
r = p.add_run(); r.text = "Energy Level (eV)"
r.font.name = "Arial"; r.font.size = Pt(16); r.font.bold = True
r.font.color.rgb = RGBColor(0, 0, 0)
tb.rotation = 270

# ---------- 每列 ----------
IMG = 1.0          # 轨道小图边长 (从 1.3 缩到 1.0)
LINE_W = 0.8       # HOMO/LUMO 水平线长度
n = len(order)
x_centers = [X0 + 0.6 + (X1 - X0 - 1.2) * i / (n-1) for i in range(n)]

def add_text_cx(cx, y, w, h, text, size, bold=False, color=(0,0,0)):
    left = Emu(int(Inches(cx) - Inches(w)/2))
    tb = slide.shapes.add_textbox(left, Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    r.font.name = "Arial"; r.font.size = Pt(size); r.font.bold = bold
    r.font.color.rgb = RGBColor(*color)
    return tb

def bmp2png(bmp_path, png_path):
    if not os.path.exists(png_path):
        Image.open(bmp_path).convert("RGB").save(png_path, "PNG")
    return png_path

for i, name in enumerate(order):
    cx = x_centers[i]
    sub = submap[name]
    y_lumo = e2y(lv[name]["lumo"])
    y_homo = e2y(lv[name]["homo"])

    # LUMO 水平线 (红)
    lumo_line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
        Inches(cx - LINE_W/2), Inches(y_lumo),
        Inches(cx + LINE_W/2), Inches(y_lumo))
    lumo_line.line.color.rgb = RGBColor(0xE0, 0x30, 0x30)
    lumo_line.line.width = Pt(3.5)

    # HOMO 水平线 (黑)
    homo_line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
        Inches(cx - LINE_W/2), Inches(y_homo),
        Inches(cx + LINE_W/2), Inches(y_homo))
    homo_line.line.color.rgb = RGBColor(0x20, 0x20, 0x20)
    homo_line.line.width = Pt(3.5)

    # Gap 竖线 (从 LUMO 到 HOMO)
    gap_line = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
        Inches(cx), Inches(y_lumo),
        Inches(cx), Inches(y_homo))
    gap_line.line.color.rgb = RGBColor(0x40, 0x60, 0x90)
    gap_line.line.width = Pt(1.5)

    # Gap 数值 (紧贴竖线右侧)
    add_text_cx(cx + 0.35, (y_lumo+y_homo)/2 - 0.18, 1.0, 0.36,
                f"{lv[name]['gap']:.2f} eV", 14, bold=True, color=(0x40,0x60,0x90))

    # LUMO 轨道小图 (紧贴 LUMO 线上方)
    lumo_png = bmp2png(os.path.join(LMO, sub, f"{sub}_LUMO.bmp"),
                       os.path.join(TMP, f"{sub}_LUMO.png"))
    img_left = Emu(int(Inches(cx) - Inches(IMG)/2))
    slide.shapes.add_picture(lumo_png, img_left, Inches(y_lumo - IMG - 0.05),
                             width=Inches(IMG), height=Inches(IMG))

    # HOMO 轨道小图 (紧贴 HOMO 线下方)
    homo_png = bmp2png(os.path.join(LMO, sub, f"{sub}_HOMO.bmp"),
                       os.path.join(TMP, f"{sub}_HOMO.png"))
    slide.shapes.add_picture(homo_png, img_left, Inches(y_homo + 0.05),
                             width=Inches(IMG), height=Inches(IMG))

    # 底部分子名
    add_text_cx(cx, y_homo + IMG + 0.15, 2.0, 0.4, name, 16, bold=True)

# 左侧 LUMO/HOMO 标签与纵轴刻度重叠, 直接删掉; 颜色已区分红=LUMO 黑=HOMO

out = os.path.join(OUT_DIR, "能级图_水平线轨道_B3LYP.pptx")
prs.save(out)
print("saved:", out)
