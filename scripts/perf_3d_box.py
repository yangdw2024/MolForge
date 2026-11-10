"""3D 框选性能基准：对比"逐原子循环选择(旧/O(N^2))"与"批量选择(新/单次通知)"。

offscreen 运行，结果写 qa_evidence/perf_3d.txt。
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout

from molforge.io.rdkit_adapter import load_molecule_document
from molforge.application.selection import SelectionService
from molforge.ui.render3d_widget import Render3DWidget

LOG = open(os.path.join(ROOT, "qa_evidence", "perf_3d.txt"), "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LOG.write(s + "\n"); LOG.flush()

app = QApplication(sys.argv)
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "samples", "bio", "1CRN.pdb")
doc = load_molecule_document(path)
doc = doc[0] if isinstance(doc, tuple) else doc
log(f"分子: {doc.name}  原子数: {doc.num_atoms}  键数: {doc.topology.num_bonds}")

host = QWidget()
host.resize(900, 700)
w = Render3DWidget(host)
sel = SelectionService()
w.set_selection_service(sel)
lay = QVBoxLayout(host); lay.addWidget(w)
host.show()
w.set_document(doc)
app.processEvents()
app.processEvents()

# 一个覆盖整个视口的框（屏幕坐标），保证所有原子都落在里面
W, H = 900, 700
bs = QPointF(0, 0)
be = QPointF(W, H)

def drain():
    # 让所有 QTimer.singleShot(0) 的选择回调真正执行
    for _ in range(6):
        app.processEvents()

def old_loop():
    sel.clear(origin="3d")
    # 直接复用 _finish_box_select 的投影结果，单独模拟旧的逐原子写法
    coords = w.renderer._coordinates
    atom_ids = w.renderer._atom_ids
    sx, sy, _, _ = w.renderer._project_points_to_qt_numpy(coords, W, H)
    inside = (sx >= 0) & (sx <= W) & (sy >= 0) & (sy <= H)
    picked = [atom_ids[i] for i in range(len(atom_ids)) if inside[i]]
    for aid in picked:
        sel.select_atom(aid, add=True, origin="3d")
    drain()

def new_batch():
    w._finish_box_select(bs, be, W, H, None)
    drain()

def timeit(name, fn, repeat=5):
    fn()  # 预热
    t0 = time.perf_counter()
    for _ in range(repeat):
        fn()
    dt = (time.perf_counter() - t0) / repeat * 1000
    log(f"{name:32s} {dt:8.3f} ms")
    return dt

t_old = timeit("旧: 逐原子循环选择(含N次高亮)", old_loop)
n_picked = len(sel.selected_atoms)
t_new = timeit("新: 批量选择(单次高亮)", new_batch)
log(f"实际选中原子数: {n_picked}")
log(f"加速比: {t_old / max(t_new, 1e-6):.2f}x")

# 真实渲染耗时（强制同步渲染，测量 GPU/软件光栅单帧）
def one_render():
    w.renderer._do_safe_render()
t0 = time.perf_counter()
for _ in range(5):
    one_render()
tr = (time.perf_counter() - t0) / 5 * 1000
log(f"单帧同步渲染: {tr:8.3f} ms  ({1000/max(tr,1e-6):.1f} FPS)")

log("3D 框选基准完成")
LOG.close()
