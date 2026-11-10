"""2D 编辑器性能基准：加载真实几百原子蛋白，测量各操作单次耗时（优化前基线）。"""
import os, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv)

from molforge.io.rdkit_adapter import load_molecule_document
from molforge.ui.editor2d_widget import Editor2DWidget

LOG = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "qa_evidence", "perf_2d.txt"), "a", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.write(s + "\n"); LOG.flush()

path = sys.argv[1] if len(sys.argv) > 1 else "samples/bio/1CRN.pdb"
doc = load_molecule_document(path)
doc = doc[0] if isinstance(doc, tuple) else doc
log(f"分子: {doc.name}  原子数: {doc.num_atoms}  键数: {doc.topology.num_bonds}")

w = Editor2DWidget()
w.resize(1600, 1000)
w.set_document(doc)
w.show()
app.processEvents()

def bench(name, fn, repeat=None):
    if repeat is None:
        repeat = 3 if doc.num_atoms > 2000 else 20
    # 预热
    for _ in range(2):
        fn()
    t0 = time.perf_counter()
    for _ in range(repeat):
        fn()
    dt = (time.perf_counter() - t0) / repeat * 1000
    log(f"{name:32s} {dt:8.3f} ms")
    return dt

# 各组件单独耗时
bench("ensure_world_coords_2d", w._ensure_world_coords_2d)
bench("get_screen_coords", w._get_screen_coords)
bench("find_ring_centroids", lambda: w._find_ring_centroids(w._get_screen_coords()))
bench("sync_2d_coords_from_3d", doc.sync_2d_coords_from_3d)

# 完整重绘（这是鼠标移动每帧实际触发的）
bench("full paintEvent (repaint)", w.repaint)

# 模拟框选全选的计算
from PyQt6.QtCore import QRectF
big = QRectF(0, 0, 1600, 1000)
bench("apply_marquee(全选)", lambda: w._apply_marquee(big, False))

log("基线测量完成")
