# -*- coding: utf-8 -*-
# make_editable_pptx.py
# 把 HOMO/LUMO 轨道图 + 能级文本框 + 分子名文本框组装成可编辑 PPT
import os, json
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from PIL import Image

LMO = r"<D_DRIVE_YDW>\OSC\Object_1\Binary_Datas\B3LYP_6-311g(d,p)\LMO"
OUT_DIR = r"<D_DRIVE_YDW>\OSC\Object_1\2610\工作三"
TMP_PNG = os.path.join(OUT_DIR, "_tmp_png")
os.makedirs(TMP_PNG, exist_ok=True)

with open(os.path.join(OUT_DIR, "levels.json")) as f:
    lv = json.load(f)

# 列: (显示名, LMO 子目录名)
cols = [
    ("BTP-ClFFCl", "ClFFCl"),
    ("BTP-FClClF", "FClClF"),
    ("BTP-FClFCl", "FClFCl"),
    ("BTP-FFClCl", "FFClCl"),
    ("HDO-4Cl",    "HDO4Cl"),
]

# ---------- 幻灯片 16:9 ----------
prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

# 白底
from pptx.oxml.ns import qn
bg = slide.background
fill = bg.fill
fill.solid()
fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

# ---------- 版式参数 (inch) ----------
MARGIN_X = 0.4
IMG_W = 2.2                       # 每张轨道图边长
GAP_X = (13.333 - 2*MARGIN_X - 5*IMG_W) / 4   # 列间距
TOP_Y = 0.3                       # 标题 y
ENERGY_H = 0.38
IMG_H = IMG_W
NAME_H = 0.4
ROW_GAP = 0.45                    # 上下排之间的额外间距

# 上排 LUMO 起点
row1_img_y = 1.4
row1_energy_y = row1_img_y - ENERGY_H - 0.05
row1_name_y = row1_img_y + IMG_H + 0.05
# 下排 HOMO 起点
row2_img_y = row1_name_y + NAME_H + ROW_GAP
row2_energy_y = row2_img_y - ENERGY_H - 0.05
row2_name_y = row2_img_y + IMG_H + 0.05

def add_text(cx_center, y, w, h, text, size, bold=False):
    """在以 cx_center(Emu) 为中心的文本框里写文字, 水平居中"""
    left = Emu(int(cx_center - Inches(w)/2))
    tb = slide.shapes.add_textbox(left, Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.word_wrap = False
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.name = "Arial"
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = RGBColor(0, 0, 0)
    return tb

def add_png_cell(sub, orb_kind, cx_center, img_y):
    """放一张轨道图 (BMP->PNG), 居中于 cx_center"""
    bmp = os.path.join(LMO, sub, f"{sub}_{orb_kind}.bmp")
    png = os.path.join(TMP_PNG, f"{sub}_{orb_kind}.png")
    if not os.path.exists(png):
        Image.open(bmp).convert("RGB").save(png, "PNG")
    left = Emu(int(cx_center - Inches(IMG_W)/2))
    slide.shapes.add_picture(png, left, Inches(img_y),
                             width=Inches(IMG_W), height=Inches(IMG_H))

# ---------- 大标题 (左上角, 仿参考图) ----------
title_tb = slide.shapes.add_textbox(Inches(MARGIN_X), Inches(TOP_Y), Inches(6), Inches(0.6))
ttf = title_tb.text_frame
ttf.margin_left = ttf.margin_right = ttf.margin_top = ttf.margin_bottom = 0
tp = ttf.paragraphs[0]
tr = tp.add_run()
tr.text = "B3LYP/6-311g(d,p)"
tr.font.name = "Arial"
tr.font.size = Pt(32)
tr.font.bold = True
tr.font.color.rgb = RGBColor(0, 0, 0)

# ---------- 逐列填充 ----------
for i, (disp, sub) in enumerate(cols):
    x_left = MARGIN_X + i * (IMG_W + GAP_X)
    cx = Emu(int(Inches(x_left + IMG_W/2)))

    # 上排: LUMO
    add_png_cell(sub, "LUMO", cx, row1_img_y)
    add_text(cx, row1_energy_y, 2.2, ENERGY_H,
             f"{lv[disp]['lumo']:.2f} eV", 18, bold=False)
    add_text(cx, row1_name_y, 2.4, NAME_H, disp, 20, bold=True)

    # 下排: HOMO
    add_png_cell(sub, "HOMO", cx, row2_img_y)
    add_text(cx, row2_energy_y, 2.2, ENERGY_H,
             f"{lv[disp]['homo']:.2f} eV", 18, bold=False)
    add_text(cx, row2_name_y, 2.4, NAME_H, disp, 20, bold=True)

# 行侧标 (LUMO / HOMO) 参考图没有, 不画

out = os.path.join(OUT_DIR, "HOMO_LUMO_B3LYP_6-311gdp.pptx")
prs.save(out)
print("saved:", out)
print(f"row1: energy_y={row1_energy_y:.2f} img_y={row1_img_y:.2f} name_y={row1_name_y:.2f}")
print(f"row2: energy_y={row2_energy_y:.2f} img_y={row2_img_y:.2f} name_y={row2_name_y:.2f}")
