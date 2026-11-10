# -*- coding: utf-8 -*-
# make_energy_table.py
# 生成可编辑 Excel 能级表
import json, os
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

OUT_DIR = r"<D_DRIVE_YDW>\OSC\Object_1\2610\工作三"
with open(os.path.join(OUT_DIR, "levels.json")) as f:
    lv = json.load(f)

order = ["BTP-ClFFCl", "BTP-FClClF", "BTP-FClFCl", "BTP-FFClCl", "HDO-4Cl"]

wb = Workbook()
ws = wb.active
ws.title = "HOMO_LUMO"

thin = Side(border_style="thin", color="000000")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
center = Alignment(horizontal="center", vertical="center")
header_fill = PatternFill("solid", fgColor="D9E1F2")

# 表头
headers = ["Molecule", "HOMO (eV)", "LUMO (eV)", "Gap (eV)"]
for j, h in enumerate(headers, 1):
    c = ws.cell(row=1, column=j, value=h)
    c.font = Font(bold=True, size=12)
    c.alignment = center
    c.fill = header_fill
    c.border = border

# 数据
for i, name in enumerate(order, 2):
    ws.cell(row=i, column=1, value=name).alignment = center
    ws.cell(row=i, column=2, value=round(lv[name]["homo"], 2)).alignment = center
    ws.cell(row=i, column=3, value=round(lv[name]["lumo"], 2)).alignment = center
    ws.cell(row=i, column=4, value=round(lv[name]["gap"], 2)).alignment = center
    for j in range(1, 5):
        ws.cell(row=i, column=j).border = border
        ws.cell(row=i, column=j).font = Font(size=12)

# 列宽
ws.column_dimensions["A"].width = 18
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 14
ws.column_dimensions["D"].width = 12

# 第二张 sheet: 换算说明
ws2 = wb.create_sheet("说明")
ws2["A1"] = "数据来源"
ws2["A1"].font = Font(bold=True, size=12)
notes = [
    "计算级别: B3LYP/6-311g(d,p), 真空, 几何优化最终结构",
    "fchk 路径: D:\\YDW\\OSC\\Object_1\\Binary_Datas\\B3LYP_6-311g(d,p)\\",
    "HOMO 轨道号: BTP 系列 = 407, HDO-4Cl = 463",
    "LUMO 轨道号: BTP 系列 = 408, HDO-4Cl = 464",
    "换算系数: 1 Hartree = 27.211386245988 eV",
    "Gap = LUMO - HOMO",
]
for i, t in enumerate(notes, 2):
    ws2.cell(row=i, column=1, value=t)
ws2.column_dimensions["A"].width = 80

out = os.path.join(OUT_DIR, "HOMO_LUMO_能级表.xlsx")
wb.save(out)
print("saved:", out)
