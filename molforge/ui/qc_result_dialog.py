"""
ui/qc_result_dialog.py - 量化计算与 OSC 能级图一体化工作台对话框
=================================================================
整合三大核心功能：
  1. Gaussian 16 输入生成器 (.gjf)：内置有机光伏 (OSC) 泛函/基组/溶剂预设，支持一键导出 .gjf
  2. 复旦大学 REST (Rust-based Electronic Structure Toolkit) 输入生成器 (ctrl.in)：
     严格遵循官方 TOML 规范（[ctrl] + [geom]），内置 B3LYP-D3BJ、PBE0-D3BJ、XYG3、XYGJOS、R-xDH7-SCC15、scsRPA 预设
  3. 量化日志解析与 OSC 给体/受体 HOMO-LUMO 能级阶梯对比图：
     支持与 PM6 / D18 / Y6 / ITIC / BTP-eC9 / PC71BM 同屏对比并导出出版级 SVG / PDF / PNG 矢量能级图
"""
from __future__ import annotations
from molforge import __version__

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QTabWidget, QComboBox,
    QSpinBox, QPlainTextEdit, QFileDialog, QMessageBox, QFrame, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QGuiApplication

from ..application.calculators.qc_input_generator import (
    OSC_GAUSSIAN_PRESETS, OSC_REST_PRESETS,
    generate_gaussian_gjf, generate_rest_ctrl_in,
)

# 经典有机光伏 (OSC) 给体/受体参考能级库 (HOMO, LUMO 单位 eV)
OSC_REFERENCE_MATERIALS: dict[str, tuple[float, float, str]] = {
    "PM6 (经典聚合物给体)": (-5.50, -3.61, "#4C9AFF"),
    "D18 (高效率聚合物给体)": (-5.51, -2.77, "#3B82F6"),
    "PTB7-Th (窄带隙给体)": (-5.20, -3.59, "#60A5FA"),
    "Y6 (明星 A-DAD-A 受体)": (-5.65, -4.10, "#F97316"),
    "BTP-eC9 (高性能非富勒烯受体)": (-5.64, -4.05, "#FB923C"),
    "ITIC (经典 A-D-A 受体)": (-5.51, -3.83, "#F59E0B"),
    "PC71BM (富勒烯受体)": (-6.00, -3.95, "#A855F7"),
}


class EnergyLevelCanvas(QWidget):
    """出版级 HOMO-LUMO 能级阶梯对比图实时渲染组件（支持导出 SVG/PDF/PNG）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(250)
        # List of (name, homo_ev, lumo_ev, color_hex)
        self.items: list[tuple[str, float, float, str]] = [
            ("PM6 (给体参考)", -5.50, -3.61, "#4C9AFF"),
            ("当前分子", -5.58, -3.85, "#66DEC9"),
            ("Y6 (受体参考)", -5.65, -4.10, "#F97316"),
        ]

    def set_levels(self, items: list[tuple[str, float, float, str]]):
        self.items = items
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._draw_diagram(p, self.width(), self.height(), dark_bg=True)
        p.end()

    def _draw_diagram(self, p: QPainter, w: float, h: float, dark_bg: bool = True):
        bg = QColor("#0E1A27") if dark_bg else QColor("#FFFFFF")
        fg = QColor("#EAF2F6") if dark_bg else QColor("#1F2D3A")
        muted = QColor("#8BA0B2") if dark_bg else QColor("#5A6B7A")
        grid_c = QColor("#1E3246") if dark_bg else QColor("#E2E8F0")

        p.fillRect(QRectF(0, 0, w, h), bg)
        if not self.items:
            return

        left_pad, right_pad, top_pad, bot_pad = 62.0, 24.0, 28.0, 38.0
        plot_w = max(100.0, w - left_pad - right_pad)
        plot_h = max(100.0, h - top_pad - bot_pad)

        all_e = [x[1] for x in self.items] + [x[2] for x in self.items]
        e_min = min(-6.5, min(all_e) - 0.45)
        e_max = max(-2.2, max(all_e) + 0.45)

        def e_to_y(ev: float) -> float:
            return top_pad + (e_max - ev) / (e_max - e_min) * plot_h

        # 绘制能量坐标轴与水平参考网格
        p.setFont(QFont("Segoe UI", 9))
        for ev_tick in (-2.5, -3.0, -3.5, -4.0, -4.5, -5.0, -5.5, -6.0, -6.5):
            if e_min <= ev_tick <= e_max:
                y = e_to_y(ev_tick)
                p.setPen(QPen(grid_c, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(left_pad, y), QPointF(w - right_pad, y))
                p.setPen(muted)
                p.drawText(QRectF(4, y - 9, left_pad - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{ev_tick:.1f} eV")

        p.setPen(QPen(muted, 1.4))
        p.drawLine(QPointF(left_pad, top_pad), QPointF(left_pad, top_pad + plot_h))

        # 绘制每个分子的 HOMO/LUMO 台阶、色块与带隙箭头
        n = len(self.items)
        col_w = plot_w / max(1, n)
        bar_w = min(74.0, col_w * 0.56)

        for i, (name, homo, lumo, hex_c) in enumerate(self.items):
            cx = left_pad + (i + 0.5) * col_w
            x0, x1 = cx - bar_w * 0.5, cx + bar_w * 0.5
            y_homo = e_to_y(homo)
            y_lumo = e_to_y(lumo)
            y_bot = top_pad + plot_h

            base_col = QColor(hex_c)
            fill_col = QColor(base_col.red(), base_col.green(), base_col.blue(), 48)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(fill_col))
            p.drawRoundedRect(QRectF(x0, y_homo, bar_w, max(6.0, y_bot - y_homo)), 4, 4)

            # LUMO 与 HOMO 能级粗横线
            p.setPen(QPen(base_col, 3.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x0, y_lumo), QPointF(x1, y_lumo))
            p.drawLine(QPointF(x0, y_homo), QPointF(x1, y_homo))

            # 能级数值标注
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.setPen(fg)
            p.drawText(QRectF(x0 - 12, y_lumo - 19, bar_w + 24, 16), Qt.AlignmentFlag.AlignCenter, f"LUMO {lumo:.2f}")
            p.drawText(QRectF(x0 - 12, y_homo + 3, bar_w + 24, 16), Qt.AlignmentFlag.AlignCenter, f"HOMO {homo:.2f}")

            # 中间带隙 Eg 双向虚线与标签
            gap = lumo - homo
            p.setPen(QPen(base_col, 1.3, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(cx, y_lumo + 4), QPointF(cx, y_homo - 4))
            ym = 0.5 * (y_lumo + y_homo)
            p.setPen(base_col)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            p.drawText(QRectF(x0 - 10, ym - 9, bar_w + 20, 18), Qt.AlignmentFlag.AlignCenter, f"Eg={gap:.2f} eV")

            # 底部材料名称
            p.setPen(fg)
            p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            p.drawText(QRectF(cx - col_w * 0.48, y_bot + 6, col_w * 0.96, 26), Qt.AlignmentFlag.AlignCenter, name)

    def export_figure(self, path: str):
        """使用 matplotlib 导出出版级矢量 SVG / PDF 或高清 PNG 能级图。"""
        ext = Path(path).suffix.lower()
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "SimHei", "Microsoft YaHei", "Arial"]
            plt.rcParams["axes.unicode_minus"] = False

            fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=300)
            for i, (name, homo, lumo, hex_c) in enumerate(self.items):
                ax.hlines(lumo, i - 0.28, i + 0.28, colors=hex_c, linewidth=3.0)
                ax.hlines(homo, i - 0.28, i + 0.28, colors=hex_c, linewidth=3.0)
                ax.fill_between([i - 0.28, i + 0.28], [homo, homo], -6.8, color=hex_c, alpha=0.15)
                ax.vlines(i, homo, lumo, colors=hex_c, linestyles="dotted", linewidth=1.2)
                ax.text(i, lumo + 0.08, f"{lumo:.2f} eV", ha="center", va="bottom", fontsize=9, fontweight="bold")
                ax.text(i, homo - 0.10, f"{homo:.2f} eV", ha="center", va="top", fontsize=9, fontweight="bold")
                ax.text(i, 0.5 * (homo + lumo), f"Eg={lumo-homo:.2f} eV", ha="center", va="center",
                        fontsize=8.5, color=hex_c, bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))

            ax.set_xticks(range(len(self.items)))
            ax.set_xticklabels([x[0] for x in self.items], fontsize=9.5, fontweight="bold")
            ax.set_ylabel("Energy Level vs. Vacuum (eV)", fontsize=10, fontweight="bold")
            ax.set_ylim(-6.6, -2.2)
            ax.set_xlim(-0.6, len(self.items) - 0.4)
            ax.grid(axis="y", linestyle="--", alpha=0.35)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            fig.tight_layout()
            fig.savefig(path, dpi=300)
            plt.close(fig)
            return
        except Exception:
            pass

        # 回退：使用 Qt 高分屏离屏渲染导出
        pix = self.grab()
        pix.save(path)


def _row(label, value):
    return QLabel(f"<span style='color:#95A9B8'>{label}</span>　<b>{value}</b>")



from PyQt6.QtCore import QThread, pyqtSignal

class QcCalcWorkerThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, task_type: str, doc, params: dict, parent=None):
        super().__init__(parent)
        self.task_type = task_type
        self.doc = doc
        self.params = params

    def run(self):
        try:
            if self.task_type == "rest":
                from ..application.calculators.rest_engine import RestEngine
                engine = RestEngine()
                self.log_signal.emit("[WSL2 REST] 正在启动复旦大学 REST (Rust Electronic Structure Toolkit)...\n")
                res = engine.run_calculation(
                    self.doc,
                    xc=self.params.get("xc", "b3lyp"),
                    basis=self.params.get("basis", "def2-SVP"),
                    num_threads=self.params.get("threads", 4),
                    log_callback=self.log_signal.emit,
                )
                self.finished_signal.emit(res)
            elif self.task_type == "calchem_sp":
                self.log_signal.emit("[CalChem] 正在启动纯 Rust 极速单点自洽场计算 (RHF)...\n")
                import sys, subprocess, json
                from pathlib import Path
                from ..application.calculators.qc_input_generator import extract_xyz_lines
                lines = extract_xyz_lines(self.doc)
                symbols = []
                geom_ang = []
                for l in lines:
                    parts = l.strip().split()
                    if len(parts) >= 4:
                        symbols.append(parts[0])
                        geom_ang.append([float(parts[1]), float(parts[2]), float(parts[3])])
                
                inp_data = {
                    "symbols": symbols,
                    "geometry_angstrom": geom_ang,
                    "charge": int(self.params.get("charge", 0)),
                    "multiplicity": int(self.params.get("spin", 1)),
                    "basis": self.params.get("basis", "sto-3g").lower(),
                }
                
                rest_dir = Path(r"E:\YDW\REST\test_run")
                if not rest_dir.exists():
                    rest_dir = Path.cwd()
                in_json = rest_dir / "calchem_sp_in.json"
                out_json = rest_dir / "calchem_sp_out.json"
                in_json.write_text(json.dumps(inp_data), encoding="utf-8")
                
                worker_script = Path(__file__).resolve().parent.parent / "application" / "calculators" / "calchem_subprocess_worker.py"
                cmd = [sys.executable, str(worker_script), "--task", "sp", "--input", str(in_json), "--output", str(out_json)]
                self.log_signal.emit(f"[CalChem] 运行指令: {' '.join(cmd)}\n")
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if out_json.exists():
                    c_res = json.loads(out_json.read_text(encoding="utf-8"))
                    if c_res.get("success"):
                        self.log_signal.emit(f"[CalChem] 自洽场收敛成功！总耗时: {c_res.get('elapsed_seconds', 0):.4f} 秒\n")
                        hartree = c_res.get("total_energy_hartree", 0.0)
                        homo_h = c_res.get("homo_energy_hartree", 0.0)
                        lumo_h = c_res.get("lumo_energy_hartree", 0.0)
                        H_TO_EV = 27.211386245988
                        res_dict = {
                            "software": "CalChem (Rust Fast Ab-initio Engine)",
                            "method": "RHF",
                            "basis": inp_data["basis"].upper(),
                            "energy": round(hartree * H_TO_EV, 4) if hartree else 0.0,
                            "energy_hartree": hartree,
                            "converged": c_res.get("converged", True),
                            "homo": round(homo_h * H_TO_EV, 4) if homo_h else 0.0,
                            "lumo": round(lumo_h * H_TO_EV, 4) if lumo_h else 0.0,
                            "gap": round(c_res.get("gap_ev", 0.0), 4) if c_res.get("gap_ev") else 0.0,
                            "elapsed_seconds": c_res.get("elapsed_seconds", 0.0),
                            "mulliken_charges": {},
                        }
                        self.finished_signal.emit(res_dict)
                        return
                err_msg = p.stderr or p.stdout or "CalChem 计算未知错误"
                self.error_signal.emit(err_msg)
        except Exception as exc:
            self.error_signal.emit(str(exc))



class QcResultDialog(QDialog):
    """
    量化计算与 OSC 能级工作台对话框（兼容旧版 QcResultDialog(parent, result, on_show_step) 签名，
    同时支持传入 document 直接生成 Gaussian .gjf 与复旦 REST ctrl.in）。
    """

    def __init__(self, parent=None, result=None, on_show_step=None, document=None, initial_tab: int = 0):
        super().__init__(parent)
        self.setWindowTitle("MolForge 量化计算工作台 · Gaussian / 复旦 REST / OSC 能级图")
        self.setMinimumSize(760, 640)
        self.result = result
        self.on_show_step = on_show_step
        self.document = document or getattr(parent, "document", None)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_gaussian_tab(), "1. Gaussian 输入生成 (.gjf)")
        self.tabs.addTab(self._build_rest_tab(), "2. 复旦 REST 输入生成 (ctrl.in)")
        self.tabs.addTab(self._build_result_and_energy_tab(), "3. 量化结果与 OSC 能级图")
        root.addWidget(self.tabs, 1)

        if result is not None and initial_tab == 0:
            self.tabs.setCurrentIndex(2)
        else:
            self.tabs.setCurrentIndex(initial_tab)

        bot = QHBoxLayout()
        open_log_btn = QPushButton("加载 Gaussian / REST / ORCA 日志...")
        open_log_btn.clicked.connect(self._browse_and_parse_log)
        bot.addWidget(open_log_btn)
        bot.addStretch()
        close_btn = QPushButton("关闭窗口")
        close_btn.setProperty("role", "action")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(close_btn)
        root.addWidget(QFrame())
        root.addLayout(bot)

        self._refresh_gaussian_preview()
        self._refresh_rest_preview()
        if self.result is not None:
            self._populate_result_data(self.result)

    # ---------- Tab 1: Gaussian (.gjf) ----------

    def _build_gaussian_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()

        self.g_preset_combo = QComboBox()
        for p in OSC_GAUSSIAN_PRESETS:
            self.g_preset_combo.addItem(p.label, p)
        self.g_preset_combo.currentIndexChanged.connect(self._on_g_preset_changed)
        form.addRow("OSC 常用预设:", self.g_preset_combo)

        self.g_route_edit = QComboBox()
        self.g_route_edit.setEditable(True)
        for p in OSC_GAUSSIAN_PRESETS:
            self.g_route_edit.addItem(p.route)
        self.g_route_edit.currentTextChanged.connect(self._refresh_gaussian_preview)
        form.addRow("Route 命令行:", self.g_route_edit)

        row_params = QHBoxLayout()
        self.g_solvent_combo = QComboBox()
        for s in ("", "Chloroform", "Chlorobenzene", "o-DiChloroBenzene", "Toluene", "THF", "Acetonitrile", "Water"):
            self.g_solvent_combo.addItem(s if s else "气相 (Gas Phase)", s)
        self.g_solvent_combo.currentIndexChanged.connect(self._refresh_gaussian_preview)
        row_params.addWidget(QLabel("溶剂(PCM):"))
        row_params.addWidget(self.g_solvent_combo)

        self.g_charge_spin = QSpinBox()
        self.g_charge_spin.setRange(-10, 10)
        self.g_charge_spin.setValue(0)
        self.g_charge_spin.valueChanged.connect(self._refresh_gaussian_preview)
        row_params.addWidget(QLabel("电荷:"))
        row_params.addWidget(self.g_charge_spin)

        self.g_mult_spin = QSpinBox()
        self.g_mult_spin.setRange(1, 9)
        self.g_mult_spin.setValue(1)
        self.g_mult_spin.valueChanged.connect(self._refresh_gaussian_preview)
        row_params.addWidget(QLabel("多重度:"))
        row_params.addWidget(self.g_mult_spin)

        self.g_nproc_spin = QSpinBox()
        self.g_nproc_spin.setRange(1, 128)
        self.g_nproc_spin.setValue(16)
        self.g_nproc_spin.valueChanged.connect(self._refresh_gaussian_preview)
        row_params.addWidget(QLabel("核数:"))
        row_params.addWidget(self.g_nproc_spin)
        form.addRow("体系与资源:", row_params)
        lay.addLayout(form)

        self.g_preview = QPlainTextEdit()
        self.g_preview.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 13px;")
        lay.addWidget(self.g_preview, 1)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("复制 .gjf 文本")
        copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.g_preview.toPlainText()))
        save_btn = QPushButton("导出保存 .gjf 文件...")
        save_btn.setProperty("role", "action")
        save_btn.clicked.connect(self._save_gjf_file)
        btn_row.addStretch()
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(save_btn)
        lay.addLayout(btn_row)
        return w

    def _on_g_preset_changed(self, idx: int):
        preset = self.g_preset_combo.itemData(idx)
        if preset is not None:
            self.g_route_edit.setCurrentText(preset.route)
            self._refresh_gaussian_preview()

    def _refresh_gaussian_preview(self):
        if self.document is None:
            return
        solvent = self.g_solvent_combo.currentData() or ""
        text = generate_gaussian_gjf(
            self.document,
            route=self.g_route_edit.currentText(),
            charge=self.g_charge_spin.value(),
            multiplicity=self.g_mult_spin.value(),
            nproc=self.g_nproc_spin.value(),
            mem_gb=16,
            solvent=solvent,
        )
        self.g_preview.setPlainText(text)

    def _save_gjf_file(self):
        default_name = f"{(self.document.name if self.document else 'molecule')}.gjf"
        path, _ = QFileDialog.getSaveFileName(self, "保存 Gaussian 输入文件", default_name, "Gaussian Input (*.gjf *.com)")
        if path:
            Path(path).write_text(self.g_preview.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "保存成功", f"已导出 Gaussian 输入卡：\n{path}")

    # ---------- Tab 2: 复旦 REST (ctrl.in TOML) ----------

    def _build_rest_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()

        self.r_preset_combo = QComboBox()
        for p in OSC_REST_PRESETS:
            self.r_preset_combo.addItem(p.label, p)
        self.r_preset_combo.currentIndexChanged.connect(self._on_r_preset_changed)
        form.addRow("REST 方法预设:", self.r_preset_combo)

        row1 = QHBoxLayout()
        self.r_xc_combo = QComboBox()
        self.r_xc_combo.setEditable(True)
        for xc in ("b3lyp", "pbe0", "cam-b3lyp", "wb97xd", "m06-2x", "xyg3", "xygjos", "r-xdh7", "scsrpa", "mp2", "hf"):
            self.r_xc_combo.addItem(xc)
        self.r_xc_combo.currentTextChanged.connect(self._refresh_rest_preview)
        row1.addWidget(QLabel("泛函(xc):"))
        row1.addWidget(self.r_xc_combo)

        self.r_disp_combo = QComboBox()
        for d in ("d3bj", "d3", "d4", ""):
            self.r_disp_combo.addItem(d if d else "无 (双杂化默认)", d)
        self.r_disp_combo.currentIndexChanged.connect(self._refresh_rest_preview)
        row1.addWidget(QLabel("色散:"))
        row1.addWidget(self.r_disp_combo)

        self.r_basis_combo = QComboBox()
        self.r_basis_combo.setEditable(True)
        for b in ("def2-TZVPP", "def2-SVP", "def2-TZVP", "def2-QZVPP", "cc-pVTZ", "6-31G(d)"):
            self.r_basis_combo.addItem(b)
        self.r_basis_combo.currentTextChanged.connect(self._refresh_rest_preview)
        row1.addWidget(QLabel("基组:"))
        row1.addWidget(self.r_basis_combo)

        self.r_job_combo = QComboBox()
        for jt in ("energy", "opt", "force", "numerical dipole"):
            self.r_job_combo.addItem(jt)
        self.r_job_combo.currentTextChanged.connect(self._refresh_rest_preview)
        row1.addWidget(QLabel("任务:"))
        row1.addWidget(self.r_job_combo)
        form.addRow("REST 核心参数:", row1)

        lay.addLayout(form)

        self.r_preview = QPlainTextEdit()
        self.r_preview.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;")
        self.r_preview.setMaximumHeight(200)
        lay.addWidget(self.r_preview)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("复制 ctrl.in (TOML)")
        copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.r_preview.toPlainText()))
        save_btn = QPushButton("导出保存 ctrl.in 文件...")
        save_btn.setProperty("role", "action")
        save_btn.clicked.connect(self._save_rest_file)

        self.run_rest_btn = QPushButton("▶ 启动 WSL2 REST 真实计算")
        self.run_rest_btn.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.run_rest_btn.clicked.connect(self._run_rest_calculation)

        self.run_calchem_btn = QPushButton("🦀 启动 CalChem 极速单点能")
        self.run_calchem_btn.setStyleSheet("background-color: #D97706; color: white; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        self.run_calchem_btn.clicked.connect(self._run_calchem_sp)

        btn_row.addWidget(copy_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.run_calchem_btn)
        btn_row.addWidget(self.run_rest_btn)
        lay.addLayout(btn_row)

        lay.addWidget(QLabel("<b>WSL2 REST / CalChem 实时计算日志与标准输出 (LIVE LOG):</b>"))
        self.r_log_view = QPlainTextEdit()
        self.r_log_view.setReadOnly(True)
        self.r_log_view.setStyleSheet("background-color: #0B1015; color: #38BDF8; font-family: 'Consolas', monospace; font-size: 11px;")
        lay.addWidget(self.r_log_view, 1)
        return w

    def _on_r_preset_changed(self, idx: int):
        preset = self.r_preset_combo.itemData(idx)
        if preset is None:
            return
        self.r_xc_combo.setCurrentText(preset.xc)
        self.r_basis_combo.setCurrentText(preset.basis)
        self.r_job_combo.setCurrentText(preset.job_type)
        disp_idx = self.r_disp_combo.findData(preset.empirical_dispersion)
        if disp_idx >= 0:
            self.r_disp_combo.setCurrentIndex(disp_idx)
        self._refresh_rest_preview()

    def _refresh_rest_preview(self):
        if self.document is None:
            return
        preset = self.r_preset_combo.currentData()
        xc = self.r_xc_combo.currentText().strip()
        ai_corr = "scc15" if xc.lower() == "r-xdh7" else (preset.post_ai_correction if preset else "")
        text = generate_rest_ctrl_in(
            self.document,
            xc=xc,
            basis=self.r_basis_combo.currentText().strip(),
            empirical_dispersion=self.r_disp_combo.currentData() or "",
            post_ai_correction=ai_corr,
            job_type=self.r_job_combo.currentText().strip(),
            charge=float(self.g_charge_spin.value()),
            spin=int(self.g_mult_spin.value()),
            num_threads=int(self.g_nproc_spin.value()),
        )
        self.r_preview.setPlainText(text)


    def _run_rest_calculation(self):
        if not self.document or self.document.topology.num_atoms == 0:
            QMessageBox.warning(self, "警告", "当前画布无有效分子结构。")
            return
        self.run_rest_btn.setEnabled(False)
        self.run_calchem_btn.setEnabled(False)
        self.run_rest_btn.setText("⏳ WSL2 REST 计算中...")
        self.r_log_view.clear()

        params = {
            "xc": self.r_xc_combo.currentText().strip(),
            "basis": self.r_basis_combo.currentText().strip(),
            "threads": int(self.g_nproc_spin.value()),
            "charge": float(self.g_charge_spin.value()),
            "spin": int(self.g_mult_spin.value()),
        }
        self._calc_worker = QcCalcWorkerThread("rest", self.document, params, parent=self)
        self._calc_worker.log_signal.connect(self._on_calc_log)
        self._calc_worker.finished_signal.connect(self._on_calc_finished)
        self._calc_worker.error_signal.connect(self._on_calc_error)
        self._calc_worker.start()

    def _run_calchem_sp(self):
        if not self.document or self.document.topology.num_atoms == 0:
            QMessageBox.warning(self, "警告", "当前画布无有效分子结构。")
            return
        self.run_rest_btn.setEnabled(False)
        self.run_calchem_btn.setEnabled(False)
        self.run_calchem_btn.setText("⏳ CalChem 计算中...")
        self.r_log_view.clear()

        params = {
            "basis": "sto-3g",
            "charge": int(self.g_charge_spin.value()),
            "spin": int(self.g_mult_spin.value()),
        }
        self._calc_worker = QcCalcWorkerThread("calchem_sp", self.document, params, parent=self)
        self._calc_worker.log_signal.connect(self._on_calc_log)
        self._calc_worker.finished_signal.connect(self._on_calc_finished)
        self._calc_worker.error_signal.connect(self._on_calc_error)
        self._calc_worker.start()

    def _on_calc_log(self, text: str):
        self.r_log_view.moveCursor(self.r_log_view.textCursor().MoveOperation.End)
        self.r_log_view.insertPlainText(text)
        self.r_log_view.moveCursor(self.r_log_view.textCursor().MoveOperation.End)

    def _on_calc_finished(self, res: dict):
        self.run_rest_btn.setEnabled(True)
        self.run_calchem_btn.setEnabled(True)
        self.run_rest_btn.setText("▶ 启动 WSL2 REST 真实计算")
        self.run_calchem_btn.setText("🦀 启动 CalChem 极速单点能")
        self.r_log_view.insertPlainText("\n[MolForge QC] 计算全部完成！正在切换至 3. 量化结果与能级图 标签页展示结果...\n")

        self._populate_result_data(res)
        self.tabs.setCurrentIndex(2)

    def _on_calc_error(self, err_msg: str):
        self.run_rest_btn.setEnabled(True)
        self.run_calchem_btn.setEnabled(True)
        self.run_rest_btn.setText("▶ 启动 WSL2 REST 真实计算")
        self.run_calchem_btn.setText("🦀 启动 CalChem 极速单点能")
        self.r_log_view.insertPlainText(f"\n[MolForge QC 错误]: {err_msg}\n")
        QMessageBox.critical(self, "计算出错", f"量化计算执行失败：\n{err_msg}")

    def _save_rest_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存复旦 REST 输入卡", "ctrl.in", "REST Control File (ctrl.in *.in *.toml)")
        if path:
            Path(path).write_text(self.r_preview.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "保存成功", f"已导出复旦 REST 输入卡：\n{path}")

    # ---------- Tab 3: 量化结果解析 & OSC 给体/受体 HOMO-LUMO 能级图 ----------

    def _build_result_and_energy_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QHeaderView
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        top_split = QHBoxLayout()
        top_split.setSpacing(16)

        # 左栏：当前分子 HOMO/LUMO 与给体/受体参考材料配置
        left_box = QVBoxLayout()
        cfg_card = QFrame()
        cfg_card.setStyleSheet("QFrame { background: #131E2A; border: 1px solid #1E3145; border-radius: 6px; }")
        right_form = QFormLayout(cfg_card)
        right_form.setContentsMargins(8, 8, 8, 8)
        right_form.setSpacing(8)

        self.cur_homo_spin = QDoubleSpinBox()
        self.cur_homo_spin.setRange(-12.0, 0.0)
        self.cur_homo_spin.setSingleStep(0.05)
        self.cur_homo_spin.setValue(-5.58)
        self.cur_homo_spin.setSuffix(" eV")
        self.cur_homo_spin.valueChanged.connect(self._update_energy_plot)
        right_form.addRow("当前分子 HOMO:", self.cur_homo_spin)

        self.cur_lumo_spin = QDoubleSpinBox()
        self.cur_lumo_spin.setRange(-10.0, 2.0)
        self.cur_lumo_spin.setSingleStep(0.05)
        self.cur_lumo_spin.setValue(-3.85)
        self.cur_lumo_spin.setSuffix(" eV")
        self.cur_lumo_spin.valueChanged.connect(self._update_energy_plot)
        right_form.addRow("当前分子 LUMO:", self.cur_lumo_spin)

        self.donor_ref_combo = QComboBox()
        for k in OSC_REFERENCE_MATERIALS:
            self.donor_ref_combo.addItem(k)
        self.donor_ref_combo.setCurrentIndex(0)  # PM6
        self.donor_ref_combo.currentIndexChanged.connect(self._update_energy_plot)
        right_form.addRow("对比材料 1 (左):", self.donor_ref_combo)

        self.acc_ref_combo = QComboBox()
        for k in OSC_REFERENCE_MATERIALS:
            self.acc_ref_combo.addItem(k)
        self.acc_ref_combo.setCurrentIndex(3)  # Y6
        self.acc_ref_combo.currentIndexChanged.connect(self._update_energy_plot)
        right_form.addRow("对比材料 2 (右):", self.acc_ref_combo)

        left_box.addWidget(cfg_card)

        self.summary_label = QLabel(
            "<b>模式：</b>OSC 前线分子轨道能级阶梯图<br>"
            "<span style='color:#8EA3B3'>支持加载 Gaussian (.log) / REST 输出，或手动微调能级对比给体/受体匹配度。</span>"
        )
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color:#A0B3C4; font-size:11px; margin-top:4px;")
        left_box.addWidget(self.summary_label)
        top_split.addLayout(left_box, 1)

        # 右栏：Mulliken 电荷明细表与优化步轨迹（带优雅空状态卡片）
        right_box = QVBoxLayout()
        right_card = QFrame()
        right_card.setStyleSheet("QFrame { background: #131E2A; border: 1px solid #1E3145; border-radius: 6px; }")
        rc_lay = QVBoxLayout(right_card)
        rc_lay.setContentsMargins(8, 8, 8, 8)
        rc_lay.setSpacing(6)

        mull_header = QHBoxLayout()
        mull_title = QLabel("<b>Mulliken 原子净电荷与优化步轨迹</b>")
        mull_title.setStyleSheet("color: #E2E8F0; font-size: 12px;")
        mull_header.addWidget(mull_title)
        mull_header.addStretch()

        self.backfill_btn = QPushButton("✓ 回填电荷至 3D 视口")
        self.backfill_btn.setStyleSheet("background-color: #0E7490; color: white; font-weight: bold; padding: 3px 10px; border-radius: 4px; border:none;")
        self.backfill_btn.clicked.connect(self._apply_mulliken_to_document)
        self.backfill_btn.setEnabled(False)
        mull_header.addWidget(self.backfill_btn)
        rc_lay.addLayout(mull_header)

        # 友好的空状态卡片
        self.mull_empty_label = QLabel(
            "💡 <b>暂无量化计算结果</b><br>"
            "<span style='color:#7E92A2'>可通过左上方「打开输出日志」加载 .log/.out，或点击「运行计算」获取真实 Mulliken 原子净电荷与几何优化轨迹。</span>"
        )
        self.mull_empty_label.setWordWrap(True)
        self.mull_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mull_empty_label.setStyleSheet("color: #94A3B8; padding: 20px; font-size: 11px;")
        rc_lay.addWidget(self.mull_empty_label)

        # 数据表格与步长列表（初始隐藏空黑框）
        self.mulliken_table = QTableWidget(0, 4)
        self.mulliken_table.setHorizontalHeaderLabels(["原子序号", "元素", "Mulliken 电荷 (e)", "极性提示"])
        self.mulliken_table.horizontalHeader().setStretchLastSection(True)
        self.mulliken_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.mulliken_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.mulliken_table.setMaximumHeight(130)
        self.mulliken_table.hide()
        rc_lay.addWidget(self.mulliken_table)

        self.listw = QListWidget()
        self.listw.setMaximumHeight(70)
        self.listw.currentRowChanged.connect(self._on_row)
        self.listw.hide()
        rc_lay.addWidget(self.listw)

        right_box.addWidget(right_card)
        top_split.addLayout(right_box, 2)
        lay.addLayout(top_split)

        # 中央能级阶梯绘图画布
        self.energy_canvas = EnergyLevelCanvas(self)
        lay.addWidget(self.energy_canvas, 1)

        exp_row = QHBoxLayout()
        exp_btn = QPushButton("导出出版级能级图 (SVG / PDF / PNG)...")
        exp_btn.setProperty("role", "action")
        exp_btn.clicked.connect(self._export_energy_diagram)
        exp_row.addStretch()
        exp_row.addWidget(exp_btn)
        lay.addLayout(exp_row)

        self._update_energy_plot()
        return w

    def _populate_result_data(self, result):
        self.result = result
        if isinstance(result, dict):
            software = result.get("software", "REST")
            method = result.get("method", "DFT")
            basis = result.get("basis", "def2-SVP")
            energy = result.get("energy", result.get("final_energy_ev", 0.0)) or 0.0
            converged = result.get("converged", True)
            homo = result.get("homo", result.get("homo_ev", 0.0)) or 0.0
            lumo = result.get("lumo", result.get("lumo_ev", 0.0)) or 0.0
            gap = result.get("gap", result.get("gap_ev", 0.0)) or 0.0
            steps = result.get("optimization_steps", [])
            mulliken = result.get("mulliken_charges", {})
            s1_txt = ""
        else:
            software = getattr(result, "software", "Gaussian")
            method = getattr(result, "method", "B3LYP")
            basis = getattr(result, "basis", "6-31G(d)")
            energy = getattr(result, "energy", 0.0)
            converged = getattr(result, "converged", True)
            homo = getattr(result, "homo", 0.0)
            lumo = getattr(result, "lumo", 0.0)
            gap = getattr(result, "gap", 0.0)
            steps = getattr(result, "optimization_steps", [])
            mulliken = getattr(result, "mulliken_charges", {})
            s1_txt = ""
            if getattr(result, "s1_energy_ev", 0.0) > 0:
                s1_txt = (
                    f"<br><b>TD-DFT S₁ 激发态：</b>{result.s1_energy_ev:.3f} eV "
                    f"({result.s1_wavelength_nm:.1f} nm, <i>f</i> = {result.s1_oscillator_f:.4f})"
                )

        self.summary_label.setText(
            f"<b>计算引擎：</b>{software}　<b>理论方法：</b>{method} / {basis}<br>"
            f"<b>总能量：</b>{energy:.4f} eV　<b>收敛状态：</b>{'是 ✓ 已收敛' if converged else '否 ✗ 未收敛'}<br>"
            f"<b>前线轨道 HOMO：</b>{homo:.3f} eV　<b>LUMO：</b>{lumo:.3f} eV　"
            f"<b>能隙 E<sub>g</sub>：</b>{gap:.3f} eV"
            + s1_txt
        )
        if homo != 0.0 and lumo != 0.0:
            self.cur_homo_spin.setValue(homo)
            self.cur_lumo_spin.setValue(lumo)

        self.listw.clear()
        for s in steps:
            en = f"{s['energy']:.3f} eV" if s.get("energy") else "-"
            tag = " ✓收敛" if s.get("converged") else ""
            self.listw.addItem(QListWidgetItem(f"第 {s['step']+1} 步　{en}{tag}"))

        # 填充 Mulliken 电荷表格
        self._current_mulliken_charges = mulliken
        self.mulliken_table.setRowCount(0)
        if hasattr(self, "mull_empty_label"):
            has_data = bool(mulliken) or bool(steps)
            self.mull_empty_label.setVisible(not has_data)
            self.mulliken_table.setVisible(bool(mulliken))
            self.listw.setVisible(bool(steps))
            self.backfill_btn.setEnabled(bool(mulliken))
        if mulliken and self.document:
            idx_to_id, _ = self.document.topology.atom_index_map()
            for idx, chg in sorted(mulliken.items()):
                row = self.mulliken_table.rowCount()
                self.mulliken_table.insertRow(row)
                sym = "X"
                if 0 <= idx < len(idx_to_id):
                    atom = self.document.topology.get_atom(idx_to_id[idx])
                    sym = atom.symbol
                tip = "🔴 亲核/负电荷" if chg < -0.05 else ("🔵 亲电/正电荷" if chg > 0.05 else "⚪ 近中性")
                self.mulliken_table.setItem(row, 0, QTableWidgetItem(f"#{idx + 1}"))
                self.mulliken_table.setItem(row, 1, QTableWidgetItem(sym))
                self.mulliken_table.setItem(row, 2, QTableWidgetItem(f"{chg:+.4f}"))
                self.mulliken_table.setItem(row, 3, QTableWidgetItem(tip))

        self._update_energy_plot()

    def _apply_mulliken_to_document(self):
        if not self.document:
            QMessageBox.warning(self, "提示", "当前无有效分子文档。")
            return
        charges = getattr(self, "_current_mulliken_charges", None)
        if not charges:
            QMessageBox.information(self, "提示", "当前计算结果中暂无 Mulliken 电荷数据。")
            return

        idx_to_id, _ = self.document.topology.atom_index_map()
        applied_count = 0
        for idx, val in charges.items():
            if 0 <= idx < len(idx_to_id):
                aid = idx_to_id[idx]
                atom = self.document.topology.get_atom(aid)
                atom.properties["mulliken_charge"] = float(val)
                applied_count += 1

        if self.parent() and hasattr(self.parent(), "_refresh_current_molecule_info"):
            try:
                self.parent()._refresh_current_molecule_info()
            except Exception:
                pass
        if self.parent() and hasattr(self.parent(), "gl_widget"):
            try:
                self.parent().gl_widget.update()
            except Exception:
                pass

        QMessageBox.information(
            self,
            "电荷回填成功",
            f"已成功将 {applied_count} 个原子的 Mulliken 量化电荷回填至分子数据模型！\n"
            "在 3D/2D 视口中点击任意原子，右侧属性面板将直接展示该原子的高精度量化净电荷。"
        )

    def _update_energy_plot(self):
        ref1_name = self.donor_ref_combo.currentText()
        h1, l1, c1 = OSC_REFERENCE_MATERIALS.get(ref1_name, (-5.50, -3.61, "#4C9AFF"))

        ref2_name = self.acc_ref_combo.currentText()
        h2, l2, c2 = OSC_REFERENCE_MATERIALS.get(ref2_name, (-5.65, -4.10, "#F97316"))

        mol_title = self.document.name if self.document else "当前分子"
        items = [
            (ref1_name.split(" ")[0], h1, l1, c1),
            (mol_title, self.cur_homo_spin.value(), self.cur_lumo_spin.value(), "#66DEC9"),
            (ref2_name.split(" ")[0], h2, l2, c2),
        ]
        self.energy_canvas.set_levels(items)

    def _export_energy_diagram(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HOMO-LUMO 能级图", "OSC_Energy_Levels.svg",
            "SVG 矢量图 (*.svg);;PDF 出版矢量图 (*.pdf);;PNG 高清图 (*.png)"
        )
        if path:
            self.energy_canvas.export_figure(path)
            QMessageBox.information(self, "导出成功", f"已导出出版级能级图：\n{path}")

    def _browse_and_parse_log(self):
        from ..io.cclib_adapter import CCLibAdapter
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Gaussian / REST / ORCA 计算输出日志", "",
            "计算日志 (*.log *.out *.txt);;所有文件 (*)"
        )
        if not path:
            return
        res = CCLibAdapter().parse(path)
        self._populate_result_data(res)
        self.tabs.setCurrentIndex(2)

    def _on_row(self, row):
        if self.result and self.on_show_step and 0 <= row < len(self.result.optimization_steps):
            step = self.result.optimization_steps[row]
            QTimer.singleShot(0, lambda: self.on_show_step(step))


# ===========================================================================
# v7.1 升级：9 大分类专属分析工作流对话框体系 + 79 项 Results 平台
# ===========================================================================
import csv as _csv
import json as _json
from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QSplitter, QCheckBox
)
from PyQt6.QtGui import QAction

from ..application.invalidation import (
    CapabilityState,
    AnalysisDefinition,
    AnalysisResult,
    AnalysisRegistry,
    AnalysisResultRepository,
    CapabilityResolver,
)
from ..io.calculators import EngineToolRegistry, MultiwfnAdapter, GromacsAdapter
from ..domain.ids import AtomId


class AnalysisPlotCanvas(QWidget):
    """通用科学谱图/曲线/直方图实时绘制画布（支持导出 SVG / PNG）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.xs: list[float] = []
        self.ys: list[float] = []
        self.xlabel: str = "X"
        self.ylabel: str = "Y"
        self.title: str = ""

    def set_series(self, xs: list[float] | tuple[float, ...], ys: list[float] | tuple[float, ...], xlabel: str = "X", ylabel: str = "Y", title: str = ""):
        self.xs = [float(v) for v in xs]
        self.ys = [float(v) for v in ys]
        self.xlabel = xlabel or "X"
        self.ylabel = ylabel or "Y"
        self.title = title
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = float(self.width()), float(self.height())
        p.fillRect(QRectF(0, 0, w, h), QColor("#0E1A27"))

        if len(self.xs) < 2 or len(self.ys) < 2:
            p.setPen(QColor("#8BA0B2"))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(QRectF(16, 0, w - 32, h), Qt.AlignmentFlag.AlignCenter, "当前分析以定量表格或外部波函数批处理为主（加载对应结果文件后可绘制连续曲线）")
            p.end()
            return

        left_pad, right_pad, top_pad, bot_pad = 64.0, 24.0, 30.0, 42.0
        pw = max(80.0, w - left_pad - right_pad)
        ph = max(80.0, h - top_pad - bot_pad)

        xmin, xmax = min(self.xs), max(self.xs)
        ymin, ymax = min(self.ys), max(self.ys)
        if abs(xmax - xmin) < 1e-9:
            xmax = xmin + 1.0
        if abs(ymax - ymin) < 1e-9:
            ymax = ymin + 1.0

        def to_pt(xv: float, yv: float) -> QPointF:
            px = left_pad + (xv - xmin) / (xmax - xmin) * pw
            py = top_pad + (ymax - yv) / (ymax - ymin) * ph
            return QPointF(px, py)

        p.setPen(QPen(QColor("#1E3246"), 1, Qt.PenStyle.DashLine))
        for k in range(5):
            gy = top_pad + ph * (k / 4.0)
            yv = ymax - (ymax - ymin) * (k / 4.0)
            p.drawLine(QPointF(left_pad, gy), QPointF(w - right_pad, gy))
            p.setPen(QColor("#8BA0B2"))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(QRectF(4, gy - 8, left_pad - 8, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{yv:.2f}")
            p.setPen(QPen(QColor("#1E3246"), 1, Qt.PenStyle.DashLine))

        p.setPen(QPen(QColor("#4C9AFF"), 2.2))
        for i in range(len(self.xs) - 1):
            p.drawLine(to_pt(self.xs[i], self.ys[i]), to_pt(self.xs[i + 1], self.ys[i + 1]))

        p.setPen(QColor("#EAF2F6"))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        p.drawText(QRectF(left_pad, h - 26, pw, 20), Qt.AlignmentFlag.AlignCenter, f"{self.xlabel}  [{xmin:.2f} .. {xmax:.2f}]")
        p.drawText(QRectF(left_pad, 6, pw, 20), Qt.AlignmentFlag.AlignCenter, f"{self.title}  —  {self.ylabel}")
        p.end()

    def export_plot(self, path: str) -> None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=300)
            if len(self.xs) >= 2 and len(self.ys) >= 2:
                ax.plot(self.xs, self.ys, color="#2563EB", linewidth=2.0)
            ax.set_xlabel(self.xlabel)
            ax.set_ylabel(self.ylabel)
            ax.set_title(self.title)
            ax.grid(True, linestyle="--", alpha=0.35)
            fig.tight_layout()
            fig.savefig(path, dpi=300)
            plt.close(fig)
            return
        except Exception:
            pass
        self.grab().save(path)


class BaseAnalysisDialog(QDialog):
    """
    v7.1 科学结果后处理基类对话框：
    提供顶部 Capability 状态徽章、Stale 失效横幅、外部文件加载、子类的专属参数控制区 (`_build_workflow_controls`)、
    定量数据表、谱图画布、Multiwfn/GROMACS 批处理脚本与 Provenance 溯源面板。
    """

    WORKFLOW_TITLE: str = "通用科学后处理工作台"

    def __init__(self, analysis_id: str, parent=None, document=None, external_file: str | None = None):
        super().__init__(parent)
        self.analysis_id = analysis_id
        self.parent_window = parent
        self.document = document or getattr(parent, "document", None)
        self.external_file = external_file
        self.options: dict = {}
        self.defn = AnalysisRegistry.get(analysis_id) or AnalysisDefinition(
            analysis_id, "通用", analysis_id, "BaseAnalysisDialog", "Internal", "MoleculeDocument", "Result"
        )
        self.setWindowTitle(f"MolForge v7.1 · {self.WORKFLOW_TITLE} — [{self.defn.analysis_id}] {self.defn.title}")
        self.setMinimumSize(860, 650)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        # 顶部标题与文件加载栏
        top_bar = QHBoxLayout()
        self.title_lbl = QLabel(
            f"<span style='font-size:15px;font-weight:700;color:#EAF2F6;'>[{self.defn.analysis_id}] {self.defn.title}</span>"
            f"　<span style='color:#66DEC9;font-size:12px;'>{self.WORKFLOW_TITLE} · 分类：{self.defn.category}</span>"
        )
        top_bar.addWidget(self.title_lbl, 1)

        self.load_ext_btn = QPushButton("📂 加载外部结果文件 (.fchk/.log/.cube/.xtc)...")
        self.load_ext_btn.clicked.connect(self._browse_external_file)
        top_bar.addWidget(self.load_ext_btn)

        self.rerun_btn = QPushButton("🔄 重新计算刷新")
        self.rerun_btn.setProperty("role", "action")
        self.rerun_btn.clicked.connect(self.refresh_analysis)
        top_bar.addWidget(self.rerun_btn)
        root.addLayout(top_bar)

        # 状态与 Stale 提示横幅
        self.status_banner = QLabel("")
        self.status_banner.setWordWrap(True)
        self.status_banner.setStyleSheet(
            "background-color:#13263A; color:#CFE2F2; border:1px solid #284664; border-radius:6px; padding:8px;"
        )
        root.addWidget(self.status_banner)

        # 专属分析工作流参数与交互控制面板（由各专业子类覆盖实现）
        ctrl_panel = self._build_workflow_controls()
        if ctrl_panel is not None:
            root.addWidget(ctrl_panel)

        # 核心结果标签页
        self.tabs = QTabWidget()

        tab_table = QWidget()
        t_lay = QVBoxLayout(tab_table)
        self.table = QTableWidget(0, 4)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        t_lay.addWidget(self.table, 1)
        self.tabs.addTab(tab_table, "1. 定量指标与原子映射表 (Metrics & Table)")

        tab_plot = QWidget()
        p_lay = QVBoxLayout(tab_plot)
        self.plot_canvas = AnalysisPlotCanvas(self)
        p_lay.addWidget(self.plot_canvas, 1)
        self.tabs.addTab(tab_plot, "2. 科学谱图与分布曲线 (Plot & Spectrum)")

        tab_script = QWidget()
        s_lay = QVBoxLayout(tab_script)
        self.script_edit = QPlainTextEdit()
        self.script_edit.setStyleSheet("font-family: Consolas, 'JetBrains Mono', monospace; font-size: 12px;")
        s_lay.addWidget(self.script_edit, 1)
        self.tabs.addTab(tab_script, "3. 可复现脚本与计算溯源 (Recipe & Provenance)")

        self._add_extra_tabs()
        root.addWidget(self.tabs, 1)

        # 底部操作与导出栏
        bot = QHBoxLayout()
        self.map_3d_btn = QPushButton("🎨 将电荷/属性映射至 3D 视口 (BWR 蓝-白-红)")
        self.map_3d_btn.clicked.connect(self._apply_bwr_atom_coloring)
        bot.addWidget(self.map_3d_btn)

        exp_csv_btn = QPushButton("导出表格 (.csv)...")
        exp_csv_btn.clicked.connect(self._export_csv)
        bot.addWidget(exp_csv_btn)

        exp_json_btn = QPushButton("导出溯源 JSON (.json)...")
        exp_json_btn.clicked.connect(self._export_json)
        bot.addWidget(exp_json_btn)

        exp_plot_btn = QPushButton("导出谱图 (.svg/.png)...")
        exp_plot_btn.clicked.connect(self._export_plot)
        bot.addWidget(exp_plot_btn)

        exp_script_btn = QPushButton("导出脚本 (.tcl/.mdp/.sh)...")
        exp_script_btn.clicked.connect(self._export_script)
        bot.addWidget(exp_script_btn)

        bot.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(close_btn)
        root.addLayout(bot)

        self.current_result: AnalysisResult | None = None
        self.refresh_analysis()

    def _build_workflow_controls(self) -> QWidget | None:
        return None

    def _add_extra_tabs(self) -> None:
        pass

    def _collect_workflow_options(self) -> dict:
        return dict(self.options)

    def refresh_analysis(self) -> None:
        if self.document is None:
            from ..domain.document import MoleculeDocument
            self.document = MoleculeDocument(name="untitled")
        opts = self._collect_workflow_options()
        self.current_result = CapabilityResolver.execute_analysis(
            self.analysis_id, self.document, external_file=self.external_file, options=opts
        )
        self._render_result(self.current_result)
        self._on_after_render_result(self.current_result)

    def _on_after_render_result(self, res: AnalysisResult) -> None:
        pass

    def _render_result(self, res: AnalysisResult) -> None:
        repo = AnalysisResultRepository.instance()
        is_stale = repo.is_result_stale(res.result_id, self.document) if self.document else (res.status == "Stale")
        state_str = "Stale (文档已修改，请点击重新计算)" if is_stale else res.status
        state_color = "#FBBF24" if (is_stale or res.status != "Ready") else "#66DEC9"

        warn_html = ""
        if res.warnings:
            warn_html = "<br><span style='color:#FBBF24;'>⚠️ " + " | ".join(res.warnings) + "</span>"

        self.status_banner.setText(
            f"<b>能力状态：</b><span style='color:{state_color};font-weight:bold;'>{state_str}</span>　"
            f"<b>算法/方法：</b>{res.provenance.method}　"
            f"<b>必要输入：</b>{self.defn.required_input}　"
            f"<b>文档版本：</b>Rev #{res.input_spec.revision} (Hash: {res.input_spec.topology_hash[:8]})"
            + warn_html
        )

        headers = list(res.table_headers) if res.table_headers else ["指标", "数值", "单位", "说明"]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(res.table_rows))
        for r_idx, row in enumerate(res.table_rows):
            for c_idx in range(len(headers)):
                val = str(row[c_idx]) if c_idx < len(row) else ""
                self.table.setItem(r_idx, c_idx, QTableWidgetItem(val))

        self.plot_canvas.set_series(
            res.plot_x, res.plot_y,
            xlabel=res.plot_xlabel or "X",
            ylabel=res.plot_ylabel or "Y",
            title=res.title,
        )

        prov_dict = {
            "result_id": res.result_id,
            "analysis_id": res.analysis_id,
            "status": res.status,
            "method": res.provenance.method,
            "engine_name": res.provenance.engine_name,
            "engine_version": res.provenance.engine_version,
            "source_hashes": res.provenance.source_hashes,
            "created_at": res.provenance.created_at,
            "units": res.provenance.units,
            "metrics": {k: v for k, v in res.metrics.items() if k != "atom_charges"},
        }
        full_text = (
            "# === MolForge v7.1 Reproducible Script / Recipe ===\n"
            + (res.script_text or "# Local mathematical calculation\n")
            + "\n\n# === AnalysisProvenance (JSON) ===\n"
            + _json.dumps(prov_dict, ensure_ascii=False, indent=2)
        )
        self.script_edit.setPlainText(full_text)

    def _on_table_cell_clicked(self, row: int, col: int) -> None:
        item = self.table.item(row, 0)
        if not item or self.parent_window is None:
            return
        import re
        nums = [int(x) for x in re.findall(r"#(\d+)", item.text())]
        if not nums:
            return
        sel = getattr(self.parent_window, "selection", None)
        if sel is not None:
            sel.select_atoms({AtomId(n) for n in nums})

    def _apply_bwr_atom_coloring(self) -> None:
        if self.current_result is None or self.document is None:
            return
        charges = self.current_result.metrics.get("atom_charges")
        if not charges and self.document.num_atoms > 0:
            wfn_res = CapabilityResolver.execute_analysis("WFN-01", self.document)
            charges = wfn_res.metrics.get("atom_charges", {})
        if not charges:
            return
        vals = [abs(float(v)) for v in charges.values()] or [0.2]
        vmax = max(0.08, max(vals))
        for aid_int, q_val in charges.items():
            aid = AtomId(int(aid_int))
            if aid in self.document.topology._atoms:
                t = max(-1.0, min(1.0, float(q_val) / vmax))
                if t < 0:
                    s = 1.0 + t
                    r, g, b = int(50 + 205 * s), int(90 + 165 * s), 255
                else:
                    s = 1.0 - t
                    r, g, b = 255, int(75 + 180 * s), int(75 + 180 * s)
                self.document.topology.get_atom(aid).color = f"#{r:02X}{g:02X}{b:02X}"
        if self.parent_window is not None:
            if hasattr(self.parent_window, "_sync_views_after_mutation"):
                self.parent_window._sync_views_after_mutation("已应用 BWR 静电势/属性 3D 颜色映射")
            elif hasattr(self.parent_window, "refresh_views"):
                self.parent_window.refresh_views()

    def _browse_external_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择外部量子化学或动力学结果文件", "",
            "计算与轨迹文件 (*.fchk *.wfn *.wfx *.log *.out *.cube *.cub *.xtc *.trr *.dcd *.gro *.pdb);;所有文件 (*)"
        )
        if path:
            self.external_file = path
            self.refresh_analysis()

    def _export_csv(self) -> None:
        if self.current_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出分析结果 CSV", f"{self.analysis_id}_results.csv", "CSV (*.csv)")
        if path:
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = _csv.writer(fh)
                writer.writerow(self.current_result.table_headers)
                for r in self.current_result.table_rows:
                    writer.writerow(r)

    def _export_json(self) -> None:
        if self.current_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出含溯源结果 JSON", f"{self.analysis_id}_provenance.json", "JSON (*.json)")
        if path:
            Path(path).write_text(self.script_edit.toPlainText(), encoding="utf-8")

    def _export_plot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出科学谱图", f"{self.analysis_id}_plot.svg", "SVG (*.svg);;PNG (*.png)")
        if path:
            self.plot_canvas.export_plot(path)

    def _export_script(self) -> None:
        ext = ".mdp" if self.analysis_id.startswith("MD-") else ".tcl"
        path, _ = QFileDialog.getSaveFileName(self, "导出可复现脚本", f"{self.analysis_id}_recipe{ext}", "Script (*.tcl *.mdp *.sh *.txt)")
        if path and self.current_result is not None:
            Path(path).write_text(self.current_result.script_text or self.script_edit.toPlainText(), encoding="utf-8")


# ---------------------------------------------------------------------------
# 六大专业领域分析工作流对话框子类（告别 79 项共用单一静态模板）
# ---------------------------------------------------------------------------

class WavefunctionAnalysisDialog(BaseAnalysisDialog):
    """波函数分析专属工作台 (WFN-01..WFN-17：Multiwfn 批处理控制、等值面阈值、BWR 色阶与 3D 轨道生成)。"""

    WORKFLOW_TITLE = "Multiwfn 波函数与电子结构分析工作台"

    def _build_workflow_controls(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet("background:#102030; border:1px solid #223B54; border-radius:6px; padding:6px;")
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("等值面阈值 (a.u.):"))
        self.sp_iso = QDoubleSpinBox()
        self.sp_iso.setDecimals(4)
        self.sp_iso.setRange(0.0005, 0.2500)
        self.sp_iso.setSingleStep(0.005)
        self.sp_iso.setValue(0.0010 if self.analysis_id == "WFN-01" else 0.0300)
        lay.addWidget(self.sp_iso)

        lay.addWidget(QLabel("色阶标准:"))
        self.cb_cmap = QComboBox()
        self.cb_cmap.addItems(["BWR (蓝-白-红 · Multiwfn/VMD 标准)", "RWB (红-白-蓝)", "Viridis"])
        lay.addWidget(self.cb_cmap)

        btn_homo = QPushButton("🔮 渲染 3D HOMO 等值面")
        btn_homo.clicked.connect(lambda: self._trigger_3d_orbital("HOMO"))
        lay.addWidget(btn_homo)

        btn_lumo = QPushButton("🔮 渲染 3D LUMO 等值面")
        btn_lumo.clicked.connect(lambda: self._trigger_3d_orbital("LUMO"))
        lay.addWidget(btn_lumo)

        btn_mwfn = QPushButton("⚡ 调用本地 Multiwfn 运行")
        btn_mwfn.clicked.connect(self.refresh_analysis)
        lay.addWidget(btn_mwfn)
        return box

    def _collect_workflow_options(self) -> dict:
        return {
            "isovalue": round(self.sp_iso.value(), 4) if hasattr(self, "sp_iso") else 0.03,
            "color_scale": self.cb_cmap.currentText() if hasattr(self, "cb_cmap") else "BWR",
        }

    def _trigger_3d_orbital(self, kind: str) -> None:
        if self.parent_window is not None and hasattr(self.parent_window, "_on_generate_frontier_orbital"):
            self.parent_window._on_generate_frontier_orbital(kind)


class MolecularPropertyDialog(BaseAnalysisDialog):
    """分子性质与成药性专属工作台 (PROP-01..PROP-08, DRUG-01..DRUG-06：SVD 平面拟合子集、RDKit Ertl TPSA、Lipinski 雷达)。"""

    WORKFLOW_TITLE = "分子物理化学性质与成药性工作台"

    def _build_workflow_controls(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet("background:#102030; border:1px solid #223B54; border-radius:6px; padding:6px;")
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("拟合与统计范围:"))
        self.cb_subset = QComboBox()
        self.cb_subset.addItems(["全部重原子 (All Heavy Atoms)", "芳香共轭骨架 (Aromatic Core)", "当前选中原子 (Selected Atoms)"])
        self.cb_subset.currentIndexChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.cb_subset)

        lay.addWidget(QLabel("描述符引擎:"))
        self.cb_eng = QComboBox()
        self.cb_eng.addItems(["RDKit Exact (CalcTPSA / Crippen / Lipinski)", "Ertl (2000) Fragment Table"])
        lay.addWidget(self.cb_eng)
        lay.addStretch(1)
        return box


class IntermolecularDialog(BaseAnalysisDialog):
    """分子间与分子内非共价弱相互作用专属工作台 (INTER-01..INTER-08：氢键/π-π/vdW 距离截断实时调节)。"""

    WORKFLOW_TITLE = "非共价相互作用 (H-Bond / π-π / vdW / EDA) 分析工作台"

    def _build_workflow_controls(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet("background:#102030; border:1px solid #223B54; border-radius:6px; padding:6px;")
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("氢键 D···A 截断距离 (Å):"))
        self.sp_hb = QDoubleSpinBox()
        self.sp_hb.setRange(2.2, 4.2)
        self.sp_hb.setSingleStep(0.1)
        self.sp_hb.setValue(3.5)
        self.sp_hb.valueChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.sp_hb)

        lay.addWidget(QLabel("范德华非键接触上限 (Å):"))
        self.sp_vdw = QDoubleSpinBox()
        self.sp_vdw.setRange(2.5, 5.0)
        self.sp_vdw.setSingleStep(0.1)
        self.sp_vdw.setValue(3.8)
        self.sp_vdw.valueChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.sp_vdw)
        lay.addStretch(1)
        return box

    def _collect_workflow_options(self) -> dict:
        return {
            "hbond_cutoff": round(self.sp_hb.value(), 2) if hasattr(self, "sp_hb") else 3.5,
            "vdw_cutoff": round(self.sp_vdw.value(), 2) if hasattr(self, "sp_vdw") else 3.8,
        }


class SpectrumAnalysisDialog(BaseAnalysisDialog):
    """光谱分析专属工作台 (SPEC-01..SPEC-08：IR / Raman / UV-Vis / ECD 半峰宽 FWHM 与频率缩放因子实时联动)。"""

    WORKFLOW_TITLE = "计算光谱与展宽模拟工作台 (IR / Raman / UV-Vis / NMR)"

    def _build_workflow_controls(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet("background:#102030; border:1px solid #223B54; border-radius:6px; padding:6px;")
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("展宽线型:"))
        self.cb_line = QComboBox()
        self.cb_line.addItems(["Lorentzian (红外/拉曼标准)", "Gaussian (UV-Vis 电子光谱标准)"])
        lay.addWidget(self.cb_line)

        lay.addWidget(QLabel("半峰宽 FWHM (cm⁻¹ / nm):"))
        self.sp_fwhm = QDoubleSpinBox()
        self.sp_fwhm.setRange(2.0, 80.0)
        self.sp_fwhm.setSingleStep(2.0)
        self.sp_fwhm.setValue(18.0)
        self.sp_fwhm.valueChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.sp_fwhm)
        lay.addStretch(1)
        return box

    def _collect_workflow_options(self) -> dict:
        return {
            "fwhm": round(self.sp_fwhm.value(), 1) if hasattr(self, "sp_fwhm") else 18.0,
        }


class MdTrajectoryAnalysisDialog(BaseAnalysisDialog):
    """GROMACS 分子动力学与轨迹分析专属工作台 (MD-01..MD-18：温度/压强/步数配置、一键导出全套 .mdp 与 RMSD/Rg 曲线)。"""

    WORKFLOW_TITLE = "GROMACS 分子动力学与轨迹后处理工作台"

    def _build_workflow_controls(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet("background:#102030; border:1px solid #223B54; border-radius:6px; padding:6px;")
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("恒温 (K):"))
        self.sp_temp = QDoubleSpinBox()
        self.sp_temp.setRange(100.0, 1000.0)
        self.sp_temp.setValue(298.15)
        self.sp_temp.valueChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.sp_temp)

        lay.addWidget(QLabel("恒压 (bar):"))
        self.sp_press = QDoubleSpinBox()
        self.sp_press.setRange(0.1, 1000.0)
        self.sp_press.setValue(1.0)
        self.sp_press.valueChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.sp_press)

        lay.addWidget(QLabel("MD 步数:"))
        self.sp_nsteps = QSpinBox()
        self.sp_nsteps.setRange(1000, 50000000)
        self.sp_nsteps.setSingleStep(50000)
        self.sp_nsteps.setValue(500000)
        self.sp_nsteps.valueChanged.connect(lambda _: self.refresh_analysis())
        lay.addWidget(self.sp_nsteps)

        btn_exp_mdp = QPushButton("📦 导出全套 GROMACS (.mdp + 脚本) 到目录...")
        btn_exp_mdp.clicked.connect(self._export_gmx_bundle)
        lay.addWidget(btn_exp_mdp)
        return box

    def _collect_workflow_options(self) -> dict:
        return {
            "temp_k": round(self.sp_temp.value(), 2) if hasattr(self, "sp_temp") else 298.15,
            "pressure_bar": round(self.sp_press.value(), 2) if hasattr(self, "sp_press") else 1.0,
            "nsteps_md": int(self.sp_nsteps.value()) if hasattr(self, "sp_nsteps") else 500000,
        }

    def _export_gmx_bundle(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择导出 GROMACS 输入包的目标文件夹")
        if not folder:
            return
        opts = self._collect_workflow_options()
        files = GromacsAdapter.generate_mdp_files(
            temp_k=opts["temp_k"], pressure_bar=opts["pressure_bar"], nsteps_md=opts["nsteps_md"]
        )
        out_dir = Path(folder)
        for fname, content in files.items():
            (out_dir / fname).write_text(content, encoding="utf-8")
        QMessageBox.information(self, "GROMACS 输入包已生成", f"已导出 minim.mdp / nvt.mdp / md.mdp / run_gmx_pipeline.sh 到：\n{out_dir}")


class OscSpecialAnalysisDialog(BaseAnalysisDialog):
    """有机光伏 (OSC) 专题分析工作台 (OSC-01..OSC-07, WFN-03：内置 HOMO/LUMO 阶梯能级对比图 + 给受体驱动力)。"""

    WORKFLOW_TITLE = "有机光伏 (OSC) 给体/受体能级与激子专题工作台"

    def _add_extra_tabs(self) -> None:
        self.osc_energy_canvas = EnergyLevelCanvas(self)
        self.tabs.insertTab(0, self.osc_energy_canvas, "0. OSC 给体/受体 HOMO-LUMO 阶梯能级图")
        self.tabs.setCurrentIndex(0)

    def _on_after_render_result(self, res: AnalysisResult) -> None:
        if hasattr(self, "osc_energy_canvas") and res.metrics:
            h_ev = float(res.metrics.get("homo_ev", -5.60))
            l_ev = float(res.metrics.get("lumo_ev", -3.80))
            mol_name = self.document.name if self.document else "当前分子"
            self.osc_energy_canvas.set_levels([
                ("PM6 (给体)", -5.50, -3.61, "#4C9AFF"),
                (mol_name, h_ev, l_ev, "#66DEC9"),
                ("Y6 (受体)", -5.65, -4.10, "#F97316"),
                ("ITIC (受体)", -5.51, -3.83, "#F59E0B"),
            ])


class EngineStatusDialog(QDialog):
    """8.1 节外部科学引擎探测与路径配置对话框 (Gaussian / xtb / Multiwfn / GROMACS / VMD / OpenBabel)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"MolForge {__version__} 外部科学引擎与依赖状态管理器 (EngineToolRegistry)")
        self.setMinimumSize(780, 440)
        lay = QVBoxLayout(self)

        info = QLabel(
            "<b>外部引擎发现顺序：</b>手动指定路径 → 环境变量 (`MOLFORGE_*_PATH`) → 系统 `PATH` → 预置科学目录（含 `E:\\ORCA\\...\\xtb.exe`、`D:\\G16W`、`D:\\Multiwfn`、`D:\\VMD`）。"
        )
        info.setWordWrap(True)
        lay.addWidget(info)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["引擎 ID", "名称", "当前状态", "可执行文件路径", "诊断信息"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        set_btn = QPushButton("为选中引擎指定本地可执行文件路径...")
        set_btn.clicked.connect(self._browse_tool_path)
        btn_row.addWidget(set_btn)

        ref_btn = QPushButton("重新扫描全部引擎")
        ref_btn.clicked.connect(self.refresh_table)
        btn_row.addWidget(ref_btn)
        btn_row.addStretch(1)

        close_btn = QPushButton("关闭")
        close_btn.setProperty("role", "action")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self.refresh_table()

    def refresh_table(self) -> None:
        statuses = list(EngineToolRegistry.detect_all().values())
        self.table.setRowCount(len(statuses))
        for i, st in enumerate(statuses):
            self.table.setItem(i, 0, QTableWidgetItem(st.tool_id))
            self.table.setItem(i, 1, QTableWidgetItem(st.display_name))
            badge = "已找到路径（未实跑）" if st.available else "Missing Engine (未检测到)"
            self.table.setItem(i, 2, QTableWidgetItem(badge))
            self.table.setItem(i, 3, QTableWidgetItem(st.executable_path or "—"))
            self.table.setItem(i, 4, QTableWidgetItem(st.diagnostic))

    def _browse_tool_path(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            row = 0
        tid_item = self.table.item(row, 0)
        if not tid_item:
            return
        tid = tid_item.text()
        path, _ = QFileDialog.getOpenFileName(self, f"选择 {tid} 可执行文件")
        if path:
            EngineToolRegistry.set_custom_path(tid, path)
            self.refresh_table()


class AnalysisRegistryBrowserDialog(QDialog):
    """79 项 Results 功能矩阵全景浏览器与一键启动器。"""

    def __init__(self, parent=None, document=None):
        super().__init__(parent)
        self.parent_window = parent
        self.document = document or getattr(parent, "document", None)
        self.setWindowTitle(f"MolForge {__version__} Results 全景功能矩阵浏览器 (9 大分类 · 79 项科学后处理模块)")
        self.setMinimumSize(940, 600)

        lay = QVBoxLayout(self)
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("分类筛选:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItem("全部分类 (79 项)")
        for cat in AnalysisRegistry.by_category().keys():
            self.cat_combo.addItem(cat)
        self.cat_combo.currentIndexChanged.connect(self._populate_rows)
        filter_row.addWidget(self.cat_combo)

        filter_row.addWidget(QLabel("关键字搜索:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入 ID (如 WFN-01, PROP-06, MD-03, OSC-01) 或模块名称...")
        self.search_edit.textChanged.connect(self._populate_rows)
        filter_row.addWidget(self.search_edit, 1)

        open_btn = QPushButton("🚀 启动选中专属工作台")
        open_btn.setProperty("role", "action")
        open_btn.clicked.connect(self._open_selected)
        filter_row.addWidget(open_btn)
        lay.addLayout(filter_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["ID", "分类", "功能模块", "当前状态", "专属工作台对话框", "后端与依赖", "必要输入"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda r, c: self._open_selected())
        lay.addWidget(self.table, 1)

        self._populate_rows()

    def _populate_rows(self) -> None:
        cat_filter = self.cat_combo.currentText()
        kw = self.search_edit.text().strip().lower()
        defs = AnalysisRegistry.all_definitions()
        filtered = []
        for d in defs:
            if not cat_filter.startswith("全部") and d.category != cat_filter:
                continue
            if kw and kw not in d.analysis_id.lower() and kw not in d.title.lower() and kw not in d.backend_engine.lower():
                continue
            filtered.append(d)

        self.table.setRowCount(len(filtered))
        for i, d in enumerate(filtered):
            st, _ = CapabilityResolver.resolve_status(d.analysis_id, self.document) if self.document else (CapabilityState.READY, "")
            self.table.setItem(i, 0, QTableWidgetItem(d.analysis_id))
            self.table.setItem(i, 1, QTableWidgetItem(d.category))
            self.table.setItem(i, 2, QTableWidgetItem(d.title))
            self.table.setItem(i, 3, QTableWidgetItem(st.value))
            self.table.setItem(i, 4, QTableWidgetItem(d.dialog_name))
            self.table.setItem(i, 5, QTableWidgetItem(d.backend_engine))
            self.table.setItem(i, 6, QTableWidgetItem(d.required_input))

    def _open_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            row = 0
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        open_analysis_dialog(id_item.text(), parent=self.parent_window or self, document=self.document)


def resolve_dialog_class_for_analysis(analysis_id: str):
    """根据 analysis_id 分派对应的领域专属工作流对话框类。"""
    if analysis_id == "INFRA-03":
        return EngineStatusDialog
    if analysis_id.startswith("OSC-") or analysis_id == "WFN-03":
        return OscSpecialAnalysisDialog
    if analysis_id.startswith("WFN-"):
        return WavefunctionAnalysisDialog
    if analysis_id.startswith("PROP-") or analysis_id.startswith("DRUG-"):
        return MolecularPropertyDialog
    if analysis_id.startswith("INTER-"):
        return IntermolecularDialog
    if analysis_id.startswith("SPEC-"):
        return SpectrumAnalysisDialog
    if analysis_id.startswith("MD-"):
        return MdTrajectoryAnalysisDialog
    return BaseAnalysisDialog


def open_analysis_dialog(analysis_id: str, parent=None, document=None) -> QDialog:
    """根据 analysis_id 打开对应的专用工作流对话框。"""
    doc = document or getattr(parent, "document", None)
    cls = resolve_dialog_class_for_analysis(analysis_id)
    if cls is EngineStatusDialog:
        dlg = EngineStatusDialog(parent=parent)
    else:
        dlg = cls(analysis_id, parent=parent, document=doc)
    dlg.exec()
    return dlg


def _open_aim_dialog(parent_window, doc):
    from .dialogs.aim_qtaim_dialog import AIMQTAIMDialog
    AIMQTAIMDialog(parent_window, doc).exec()

def _open_ir_dialog(parent_window, doc):
    from .dialogs.vibrational_spectrum_dialog import VibrationalSpectrumDialog
    VibrationalSpectrumDialog(parent_window, doc).exec()

def _open_calchem_dialog(parent_window, doc):
    from .dialogs.calchem_orbitals_dialog import CalChemOrbitalsDialog
    CalChemOrbitalsDialog(parent_window, doc).exec()

def _open_hpc_dialog(parent_window, doc):
    from .dialogs.hpc_job_dialog import HpcJobDialog
    HpcJobDialog(parent_window, doc).exec()

def _open_traj_dialog(parent_window):
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    top, _ = QFileDialog.getOpenFileName(parent_window, "选择轨迹拓扑文件 (.tpr / .gro / .pdb)", "", "Topologies (*.tpr *.gro *.pdb);;All Files (*.*)")
    if not top:
        return
    traj, _ = QFileDialog.getOpenFileName(parent_window, "选择动力学轨迹文件 (.xtc / .dcd / .trr)", "", "Trajectories (*.xtc *.dcd *.trr);;All Files (*.*)")
    if not traj:
        return
    try:
        from .trajectory_window import TrajectoryWindow
        win = TrajectoryWindow(top, traj, parent=parent_window)
        win.show()
    except Exception as e:
        QMessageBox.critical(parent_window, "打开失败", str(e))


def populate_v7_results_menu(res_menu, parent_window, doc_provider=None) -> None:
    """
    严格按照 PROMPT_v7_3_workflows_integration.md 第二步分类结构挂载所有科学工作流与分析模块：
      ├── 基础性质 (分子量/分子式/TPSA、偶极矩、分子平面性)
      ├── 波函数分析 (Multiwfn) (ESP 表面分析、HOMO/LUMO 能级图、轨道可视化、键级分析 Mayer、电荷分析 Hirshfeld/ADCH/NPA)
      ├── 分子间相互作用 (IGMH 弱相互作用分析、氢键检测、π-π 堆积检测、能量分解分析 EDA)
      ├── 光谱 (IR 光谱展宽、UV-Vis 光谱展宽、激发态分析 空穴/电子)
      ├── OSC 专题 (HOMO-LUMO 能级阶梯图、OSC 能级对齐图、重组能计算、电子耦合 VDA、电荷转移速率)
      ├── 分子动力学 (GROMACS) (MD 模拟设置向导、RDF 径向分布函数、二面角/质心距分析、二维密度图与粗糙度、回旋半径 Rg、RMSD/RMSF、氢键统计、自由体积 FVR、相互作用能 IE)
      └── 数据导出 (导出结果表格 CSV/Excel、导出图表 PNG/SVG、导出可复现脚本)
    """
    from .shells.workflow_inputs import (
        EspSurfaceWorkflowDialog,
        HomoLumoWorkflowDialog,
        OscEnergyDiagramWorkflowDialog,
        ReorganizationEnergyWorkflowDialog,
        DipoleAnalysisWorkflowDialog,
        PlanarityAnalysisWorkflowDialog,
        MdRdfWorkflowDialog,
        IgmhInteractionWorkflowDialog,
        ExternalWorkflowDialog,
        ToolPathConfigDialog,
        MdStudioDialog,
    )
    from .llm_config_dialog import LlmConfigDialog
    get_doc = doc_provider or (lambda: getattr(parent_window, "document", None))

    from .live_llm_dialog import LiveLlmDialog
    from .gromacs_job_dialog import GromacsJobDialog
    res_menu.addAction("🦀 CalChem 原生分子轨道能级阶梯与 3D 等值面...", lambda: _open_calchem_dialog(parent_window, get_doc()))
    res_menu.addAction("🌐 Linux 超算集群作业提交与监控向导 (HPC Job Manager)...", lambda: _open_hpc_dialog(parent_window, get_doc()))
    res_menu.addAction("LLM 当前分子工具对话…", lambda: LiveLlmDialog(parent_window, get_doc).exec())

    # 0. 大语言模型接入（OpenAI 兼容 function calling）
    res_menu.addAction("LLM 接入设置 (OpenAI 兼容端点)…", lambda: LlmConfigDialog(parent_window).exec())

    # 1. 基础性质
    m_basic = res_menu.addMenu("基础性质")
    m_basic.addAction("分子量 / 分子式 / TPSA", lambda: open_analysis_dialog("PROP-06", parent=parent_window, document=get_doc()))
    m_basic.addAction("偶极矩 (fchk 工作流)...", lambda: DipoleAnalysisWorkflowDialog(parent_window, document=get_doc()).exec())
    m_basic.addAction("偶极矩 (当前分子实时分析)...", lambda: open_analysis_dialog("PROP-02", parent=parent_window, document=get_doc()))
    m_basic.addAction("分子平面性 (SVD MPP/SDP 工作流)...", lambda: PlanarityAnalysisWorkflowDialog(parent_window, document=get_doc()).exec())
    m_basic.addAction("分子平面性 (当前画布分子)...", lambda: open_analysis_dialog("PROP-01", parent=parent_window, document=get_doc()))

    # 2. 波函数分析 (Multiwfn)
    m_wfn = res_menu.addMenu("波函数分析 (Multiwfn)")
    m_wfn.addAction("⚛ Multiwfn 实空间综合工作台 (QTAIM / NCI / ELF / ADCH)...", lambda: _open_aim_dialog(parent_window, get_doc()))
    m_wfn.addAction("ESP 表面分析 (Multiwfn + VMD)...", lambda: EspSurfaceWorkflowDialog(parent_window, document=get_doc()).exec())
    m_wfn.addAction("HOMO/LUMO 能级图 (fchk 批量工作流)...", lambda: HomoLumoWorkflowDialog(parent_window, document=get_doc()).exec())
    m_wfn.addAction("轨道可视化 (HOMO/LUMO 等值面)...", lambda: open_analysis_dialog("WFN-02", parent=parent_window, document=get_doc()))
    m_wfn.addAction("键级分析 (Mayer)", lambda: open_analysis_dialog("WFN-06", parent=parent_window, document=get_doc()))
    m_wfn.addAction("电荷分析 (Hirshfeld/ADCH/NPA)", lambda: open_analysis_dialog("WFN-07", parent=parent_window, document=get_doc()))

    # 3. 分子间相互作用
    m_inter = res_menu.addMenu("分子间相互作用")
    m_inter.addAction("IGMH 弱相互作用分析...", lambda: IgmhInteractionWorkflowDialog(parent_window, document=get_doc()).exec())
    m_inter.addAction("氢键检测", lambda: open_analysis_dialog("INTER-02", parent=parent_window, document=get_doc()))
    m_inter.addAction("π-π 堆积检测", lambda: open_analysis_dialog("INTER-03", parent=parent_window, document=get_doc()))
    m_inter.addAction("双分子接触与氢键筛查 (文件对比)...", lambda: ExternalWorkflowDialog("INTERACTION", parent_window, document=get_doc()).exec())
    m_inter.addAction("能量分解分析 (EDA)", lambda: open_analysis_dialog("INTER-01", parent=parent_window, document=get_doc()))

    # 4. 光谱
    m_spec = res_menu.addMenu("光谱")
    m_spec.addAction("🎵 红外吸收光谱与 3D 简正振动模式动画 (IR & Normal Modes)...", lambda: _open_ir_dialog(parent_window, get_doc()))
    m_spec.addAction("IR 光谱展宽", lambda: open_analysis_dialog("SPEC-01", parent=parent_window, document=get_doc()))
    m_spec.addAction("UV-Vis 光谱展宽", lambda: open_analysis_dialog("SPEC-03", parent=parent_window, document=get_doc()))
    m_spec.addAction("激发态分析 (空穴/电子)", lambda: open_analysis_dialog("WFN-10", parent=parent_window, document=get_doc()))

    # 5. OSC 专题
    m_osc = res_menu.addMenu("OSC 专题")
    m_osc.addAction("HOMO-LUMO 能级阶梯图...", lambda: HomoLumoWorkflowDialog(parent_window, document=get_doc()).exec())
    m_osc.addAction("OSC 能级对齐图 (fchk+log 双源校验)...", lambda: OscEnergyDiagramWorkflowDialog(parent_window, document=get_doc()).exec())
    m_osc.addAction("重组能计算 (四点法 λh/λe + gjf 生成)...", lambda: ReorganizationEnergyWorkflowDialog(parent_window, document=get_doc()).exec())
    m_osc.addAction("电子耦合 VDA", lambda: open_analysis_dialog("OSC-06", parent=parent_window, document=get_doc()))
    m_osc.addAction("电荷转移速率 (Marcus k_ET)...", lambda: ReorganizationEnergyWorkflowDialog(parent_window, document=get_doc()).exec())

    # 6. 分子动力学 (GROMACS)
    m_md = res_menu.addMenu("分子动力学 (GROMACS)")
    m_md.addAction("🎬 动力学轨迹流式播放器 (Kabsch RMSD / 流式 Welford RMSF)...", lambda: _open_traj_dialog(parent_window))
    m_md.addAction("GROMACS 任务准备与队列提交…", lambda: GromacsJobDialog(parent_window).exec())
    m_md.addAction("MD 轨迹综合分析 (RMSD/Rg/RMSF/RDF/氢键)…", lambda: MdStudioDialog(parent_window, document=get_doc()).exec())
    m_md.addAction("MD 模拟设置向导", lambda: open_analysis_dialog("MD-01", parent=parent_window, document=get_doc()))
    m_md.addAction("RDF 径向分布函数...", lambda: MdRdfWorkflowDialog(parent_window, document=get_doc()).exec())
    m_md.addAction("二面角/质心距分析", lambda: open_analysis_dialog("MD-08", parent=parent_window, document=get_doc()))
    m_md.addAction("二维密度图与粗糙度", lambda: open_analysis_dialog("MD-11", parent=parent_window, document=get_doc()))
    m_md.addAction("回旋半径 Rg", lambda: open_analysis_dialog("MD-05", parent=parent_window, document=get_doc()))
    m_md.addAction("RMSD/RMSF (轨迹后处理工作流)...", lambda: ExternalWorkflowDialog("MD", parent_window, document=get_doc()).exec())
    m_md.addAction("氢键统计", lambda: open_analysis_dialog("MD-06", parent=parent_window, document=get_doc()))
    m_md.addAction("自由体积 FVR", lambda: open_analysis_dialog("MD-13", parent=parent_window, document=get_doc()))
    m_md.addAction("相互作用能 IE (GROMACS rerun 分量差)...", lambda: ExternalWorkflowDialog("EDA", parent_window, document=get_doc()).exec())

    # 7. 数据导出
    m_exp = res_menu.addMenu("数据导出")
    m_exp.addAction("导出结果表格 (CSV/Excel)...", lambda: open_analysis_dialog("PROP-06", parent=parent_window, document=get_doc()))
    m_exp.addAction("导出图表 (PNG/SVG)...", lambda: open_analysis_dialog("OSC-01", parent=parent_window, document=get_doc()))
    m_exp.addAction("导出可复现脚本 (.tcl/.mdp/.sh)...", lambda: open_analysis_dialog("MD-01", parent=parent_window, document=get_doc()))

    res_menu.addSeparator()

    # 保留 79 项全景矩阵浏览器与引擎配置入口
    browser_act = QAction("🧭 Results 79 项全功能分析矩阵浏览器 (Ctrl+Shift+R)...", parent_window)
    browser_act.setShortcut("Ctrl+Shift+R")
    browser_act.triggered.connect(lambda: AnalysisRegistryBrowserDialog(parent=parent_window, document=get_doc()).exec())
    res_menu.addAction(browser_act)

    eng_act = QAction("⚙️ 外部科学引擎与依赖状态管理 (Gaussian / Multiwfn / GROMACS / VMD / xtb)...", parent_window)
    eng_act.triggered.connect(lambda: ToolPathConfigDialog(parent=parent_window).exec())
    res_menu.addAction(eng_act)

    all_9_menu = res_menu.addMenu("📚 全部 9 大分类 · 79 项注册模块索引")
    for cat_name, defs in AnalysisRegistry.by_category().items():
        sub = all_9_menu.addMenu(f"📂 {cat_name} ({len(defs)} 项)")
        for d in defs:
            act = QAction(f"[{d.analysis_id}] {d.title} ({d.stage})", parent_window)
            act.triggered.connect(
                lambda checked=False, aid=d.analysis_id: open_analysis_dialog(aid, parent=parent_window, document=get_doc())
            )
            sub.addAction(act)

