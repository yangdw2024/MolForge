"""#54 验收：分析/结果模块直连当前画布分子，诚实区分真假输入。

offscreen 运行，结果写 qa_evidence/test_workflow_canvas_link.txt。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from molforge.io.rdkit_adapter import create_instant_caffeine_document
from molforge.ui.shells.workflow_inputs import (
    export_document_to_xyz,
    PlanarityAnalysisWorkflowDialog,
    EspSurfaceWorkflowDialog,
    ExternalWorkflowDialog,
)

LOG = open(os.path.join(ROOT, "qa_evidence", "test_workflow_canvas_link.txt"), "w", encoding="utf-8")
def log(*a):
    s = " ".join(str(x) for x in a)
    print(s); LOG.write(s + "\n"); LOG.flush()

app = QApplication(sys.argv)
doc = create_instant_caffeine_document()
n = doc.num_atoms

def check(cond, msg):
    if not cond:
        log("FAIL: " + msg); raise AssertionError(msg)
    log("PASS: " + msg)

# 1. 导出函数：xyz 内容正确
out = os.path.join(ROOT, "qa_evidence", "_canvas_test.xyz")
export_document_to_xyz(doc, out)
with open(out, encoding="utf-8") as fh:
    rows = fh.read().splitlines()
check(int(rows[0]) == n, "XYZ 首行原子数与文档一致")
check(len(rows) == n + 2, "XYZ 行数 = 原子数 + 2")
check(rows[2].split()[0] in ("C", "N", "O", "H"), "XYZ 数据行首列为元素符号")
check(len(rows[2].split()) == 4, "XYZ 数据行含元素 + 三维坐标")

# 2. 结构类工作流（PLANE）自动预填当前画布，无需手动浏览
d_plane = PlanarityAnalysisWorkflowDialog(document=doc)
check(d_plane.files.count() == 1, "平面性对话框自动预填 1 个当前画布结构文件")
check(d_plane.files.item(0).text().endswith(".xyz"), "自动预填项为 xyz 结构文件")
check(os.path.isfile(d_plane.files.item(0).text()), "自动预填文件真实存在于磁盘")

# 3. fchk 类工作流（ESP）不伪造：文件列表为空，给出诚实提示
d_esp = EspSurfaceWorkflowDialog(document=doc)
check(d_esp.files.count() == 0, "ESP 对话框不伪造 fchk（当前画布无法替代）")
check("fchk" in d_esp.log_box.placeholderText() or "无法" in d_esp.log_box.placeholderText(),
      "ESP 对话框诚实提示需要 fchk 而非伪造")

# 4. 无文档时不预填、不报错
d_none = PlanarityAnalysisWorkflowDialog()
check(d_none.files.count() == 0, "无文档时不预填且不崩溃")

# 5. INTERACTION 仅预填当前 1 个分子，运行校验仍要求第二个（不伪造双分子）
d_inter = ExternalWorkflowDialog("INTERACTION", document=doc)
check(d_inter.files.count() == 1, "相互作用对话框只预填当前 1 个分子，不伪造第二个")

log("工作流直连画布与诚实区分全部验收通过")
LOG.close()
