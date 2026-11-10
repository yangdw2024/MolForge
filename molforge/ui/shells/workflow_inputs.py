"""
ui/shells/workflow_inputs.py - MolForge v7.3 标准化科研工作流对话框集与工具路径配置中心
=======================================================================================
严格实现 PROMPT_v7_3_workflows_integration.md 全部要求：
  1. 8 个核心科研工作流中文独立对话框（使用 QThread 后台执行 subprocess，绝不阻塞 GUI 线程）：
     - (1) EspSurfaceWorkflowDialog         : ESP 表面分析 (fchk -> Multiwfn + VMD -> 描述符表 + BWR 表面图)
     - (2) HomoLumoWorkflowDialog           : HOMO-LUMO 能级图 (多个 fchk -> 提取能级 -> 阶梯图 + 轨道图)
     - (3) OscEnergyDiagramWorkflowDialog   : OSC 能级对齐图 (给体+受体 fchk+log -> 3种SVG + Excel + PPTX)
     - (4) ReorganizationEnergyWorkflowDialog: 重组能计算 λh/λe (四点法 4 个 log 计算 λ 与 Marcus 速率 / 一键生成 4 个 gjf)
     - (5) DipoleAnalysisWorkflowDialog     : 偶极矩分析 (读取 fchk -> 总偶极矩向量 Debye + VMD 3D 箭头)
     - (6) PlanarityAnalysisWorkflowDialog  : 分子平面性分析 (SVD 最佳拟合平面 -> RMSD/MPP + SDP + PQR)
     - (7) MdRdfWorkflowDialog              : MD 后处理 RDF (选择拓扑/轨迹 -> 计算 g(r) 曲线 + 导出 gmx rdf 脚本)
     - (8) IgmhInteractionWorkflowDialog    : IGMH 弱相互作用 (生成二聚体 igmh.gjf / 调用 Multiwfn 20->10 IGMH)
  2. 统一外部工具路径配置对话框 ToolPathConfigDialog：
     - 自动探测 Gaussian 16、Multiwfn、GROMACS、VMD、OpenBabel、xtb
     - 支持手动指定可执行文件路径并持久化保存在 QSettings("MolForge", "ExternalEngines") 中
     - 挂载在「计算 -> 引擎状态...」与「结果 -> 外部科学引擎与依赖状态管理...」菜单下
"""
from __future__ import annotations

import json
from pathlib import Path
from PyQt6.QtCore import Qt, QThread, QSettings, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QFileDialog, QListWidget, QMessageBox, QLineEdit, QDoubleSpinBox,
    QComboBox, QPlainTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QSpinBox, QCheckBox
)

from ...io.calculators import EngineToolRegistry
from ...domain.elements import get_element


# 可直接用当前画布结构（xyz）作为输入的工作流；其余需要 fchk/轨迹，不自动预填
_STRUCTURE_CAPABLE_KINDS = {"PLANE", "REORG", "IGMH", "INTERACTION"}


from ...application.calculators.qc_input_generator import export_document_to_xyz


class ToolPathConfigDialog(QDialog):
    """
    第四步：统一外部科学工具探测与路径配置对话框（配置持久化保存在 QSettings 中）。
    支持自动探测与手动指定：Gaussian 16、Multiwfn、GROMACS、VMD、OpenBabel、xtb。
    """

    TOOLS = (
        ("gaussian", "Gaussian 16 (g16.exe)"),
        ("multiwfn", "Multiwfn 3.8 (Multiwfn.exe)"),
        ("gromacs", "GROMACS (gmx.exe / gmx_mpi)"),
        ("vmd", "VMD 1.9.4 (vmd.exe)"),
        ("openbabel", "OpenBabel (obabel.exe)"),
        ("xtb", "GFN2-xTB (xtb.exe)"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("外部科学计算工具路径配置与引擎状态")
        self.resize(820, 460)
        self.settings = QSettings("MolForge", "ExternalEngines")
        EngineToolRegistry.load_from_qsettings()

        lay = QVBoxLayout(self)
        tip = QLabel(
            "<b>工具探测与配置说明：</b>系统自动探测本机安装的量子化学与分子动力学程序。若安装在自定义目录，"
            "请选中对应行并点击「手动指定可执行文件 (.exe)...」，路径将自动保存在本地配置 (`QSettings`) 中。"
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.table = QTableWidget(len(self.TOOLS), 4, self)
        self.table.setHorizontalHeaderLabels(["工具名称", "检测状态", "当前可执行文件路径", "诊断说明"])
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for i, width in enumerate((210,190,340,340)):
            self.table.setColumnWidth(i,width)
        lay.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_browse = QPushButton("指定可执行文件…")
        btn_browse.clicked.connect(self._browse_selected_tool)
        btn_row.addWidget(btn_browse)

        btn_probe = QPushButton("重新扫描")
        btn_probe.clicked.connect(self.refresh_status)
        btn_row.addWidget(btn_probe)

        btn_row.addStretch(1)
        btn_close = QPushButton("保存并关闭")
        btn_close.setProperty("role", "action")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        self.refresh_status()

    def refresh_status(self):
        statuses = EngineToolRegistry.detect_all()
        for row, (tid, label) in enumerate(self.TOOLS):
            st = statuses.get(tid) or EngineToolRegistry.detect_tool(tid)
            self.table.setItem(row, 0, QTableWidgetItem(label))
            badge = "已找到路径 · 未实跑验证" if st.available else "⚠️ 未配置 / 未找到"
            self.table.setItem(row, 1, QTableWidgetItem(badge))
            self.table.setItem(row, 2, QTableWidgetItem(st.executable_path or "未检测到"))
            self.table.setItem(row, 3, QTableWidgetItem(st.diagnostic))
            for column in range(4):
                self.table.item(row,column).setToolTip(self.table.item(row,column).text())

    def _browse_selected_tool(self):
        row = self.table.currentRow()
        if row < 0:
            row = 0
        tid, label = self.TOOLS[row]
        path, _ = QFileDialog.getOpenFileName(self, f"选择 {label} 可执行文件", "", "Executable (*.exe *);;All Files (*)")
        if path:
            EngineToolRegistry.set_custom_path(tid, path, persist=True)
            self.refresh_status()


class _WorkflowWorker(QThread):
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, kind: str, files: list[str], output_dir: str, params: dict | None = None):
        super().__init__()
        self.kind = kind
        self.files = list(files)
        self.output_dir = output_dir
        self.params = dict(params or {})

    def run(self):
        try:
            from ...workflows.esp_surface import run_esp_surface_workflow
            from ...workflows.homo_lumo_plot import run_homo_lumo_workflow
            from ...workflows.osc_energy_diagram import run_osc_energy_workflow
            from ...workflows.reorganization_energy import (
                run_reorganization_energy_workflow,
                generate_four_point_gjf_bundle,
            )
            from ...workflows.dipole_analysis import run_dipole_workflow
            from ...workflows.planarity_analysis import run_planarity_workflow
            from ...workflows.md_rdf_analysis import run_md_rdf_workflow
            from ...workflows.igmh_interaction import run_igmh_workflow
            from ...workflows.scientific_workflows import (
                detect_pair_interactions,
                run_md_postprocess,
                calculate_pair_energy_components,
            )

            if self.kind == "ESP":
                iso = float(self.params.get("isovalue", 0.001))
                out = run_esp_surface_workflow(self.files[0], self.output_dir, isovalue=iso)
            elif self.kind == "HOMO":
                logs = {Path(p).stem: p for p in self.files if Path(p).suffix.lower() in (".log", ".out")}
                fchks = [p for p in self.files if Path(p).suffix.lower() == ".fchk"]
                out = run_homo_lumo_workflow(fchks, self.output_dir, log_by_stem=logs)
            elif self.kind == "OSC":
                fchks = [Path(p) for p in self.files if Path(p).suffix.lower() == ".fchk"]
                pairs = []
                for f in fchks:
                    log = next((x for x in self.files if Path(x).stem == f.stem and Path(x).suffix.lower() in (".log", ".out")), None)
                    if log is None:
                        log = next((str(f.with_suffix(s)) for s in (".log", ".out") if f.with_suffix(s).is_file()), None)
                    if log is None:
                        raise ValueError(f"{f.name} 缺少同名 Gaussian .log/.out；OSC 能级要求双源校验。")
                    pairs.append((f, log))
                out = run_osc_energy_workflow(pairs, self.output_dir)
            elif self.kind == "REORG":
                mode = self.params.get("mode", "calc_from_logs")
                if mode == "generate_gjf" or (len(self.files) == 1 and Path(self.files[0]).suffix.lower() not in (".log", ".out")):
                    out = generate_four_point_gjf_bundle(
                        self.files[0],
                        self.output_dir,
                        carrier_type=self.params.get("carrier_type", "electron"),
                        solvent=self.params.get("solvent", "chloroform"),
                    )
                else:
                    out = run_reorganization_energy_workflow(
                        self.files,
                        self.output_dir,
                        v_da_ev=float(self.params.get("v_da_ev", 0.025)),
                        dg_ev=float(self.params.get("dg_ev", 0.0)),
                    )
            elif self.kind == "PLANE":
                out = run_planarity_workflow(self.files[0], self.output_dir)
            elif self.kind == "DIPOLE":
                out = run_dipole_workflow(self.files[0], self.output_dir)
            elif self.kind == "RDF":
                out = run_md_rdf_workflow(
                    self.files,
                    self.output_dir,
                    r_max=float(self.params.get("r_max", 12.0)),
                )
            elif self.kind == "IGMH":
                out = run_igmh_workflow(
                    self.files[0],
                    self.output_dir,
                    frag1_range=self.params.get("frag1_range", "1-30"),
                    frag2_range=self.params.get("frag2_range", "31-60"),
                )
            elif self.kind == "INTERACTION":
                from ...io.rdkit_adapter import load_molecule_document
                a = load_molecule_document(self.files[0])[0]
                b = load_molecule_document(self.files[1])[0]
                out = detect_pair_interactions(a, b, self.output_dir)
            elif self.kind == "MD":
                topology = next(
                    (x for x in self.files if Path(x).suffix.lower() in (".pdb", ".gro", ".tpr", ".psf", ".prmtop")),
                    self.files[0],
                )
                trajectory = next((x for x in self.files if x != topology), None)
                if trajectory is None:
                    raise ValueError("需要一个拓扑文件和一个轨迹文件。")
                out = run_md_postprocess(topology, trajectory, self.output_dir)
            elif self.kind == "EDA":
                out = calculate_pair_energy_components(self.files[0], self.output_dir)
            else:
                raise ValueError(f"未知工作流类型: {self.kind}")
            self.succeeded.emit(str(out))
        except Exception as exc:
            self.failed.emit(str(exc))


class ExternalWorkflowDialog(QDialog):
    """通用与专项科研工作流对话框基类（全中文界面、支持参数面板扩展、工具状态自检、后台 QThread 执行与结果预览）。"""

    CONFIG = {
        "ESP": ("ESP 表面定量分析 (Multiwfn + VMD)", 1, "Gaussian fchk (*.fchk)", ("multiwfn", "vmd")),
        "HOMO": ("HOMO-LUMO 能级图与轨道渲染", 1, "Gaussian fchk / log (*.fchk *.log *.out)", ()),
        "OSC": ("OSC 给体/受体能级对齐图", 2, "Gaussian 文件 (*.fchk *.log *.out)", ()),
        "REORG": ("重组能计算 λh/λe (四点法 / 输入生成)", 1, "Gaussian log 或结构文件 (*.log *.out *.xyz *.mol *.sdf *.pdb *.gjf)", ()),
        "PLANE": ("分子平面性分析 (SVD 拟合平面 MPP/SDP)", 1, "结构或 fchk 文件 (*.fchk *.xyz *.mol *.sdf *.pdb)", ()),
        "DIPOLE": ("分子偶极矩分析", 1, "Gaussian fchk (*.fchk)", ()),
        "RDF": ("MD 后处理：RDF 径向分布函数", 1, "GROMACS 结构与轨迹 (*.gro *.pdb *.tpr *.xtc *.trr *.dcd *.xyz)", ()),
        "IGMH": ("IGMH 弱相互作用分析 (Gaussian + Multiwfn)", 1, "二聚体结构或 fchk (*.fchk *.wfn *.xyz *.mol *.sdf *.pdb *.mol2)", ()),
        "INTERACTION": ("分子间氢键与范德华接触筛查", 2, "分子结构 (*.mol *.sdf *.pdb *.xyz *.mol2)", ()),
        "MD": ("MD 轨迹 RMSD / Rg / 聚类后处理", 2, "拓扑与轨迹文件 (*.pdb *.gro *.tpr *.psf *.prmtop *.xtc *.trr *.dcd)", ()),
        "EDA": ("GROMACS 组分间相互作用能 IE 分量分析", 1, "GROMACS 能量分量 CSV (*.csv)", ()),
    }

    NOTES = {
        "ESP": "【输入】Gaussian .fchk 文件  |  【调用工具】Multiwfn 3.8 + VMD 1.9.4  |  【输出】σ²+、σ²-、ν、Π、MPI 定量表 + BWR 静电势等值面图",
        "HOMO": "【输入】1 个或多个 .fchk（可选同名 .log 校验）  |  【调用工具】fchk 流式读取器 (+ 可选 Multiwfn/VMD)  |  【输出】能级阶梯图 SVG/CSV/JSON + 轨道 BMP",
        "OSC": "【输入】至少 2 个分子的 .fchk 与同名 .log（强制双源误差 ≤0.05 eV 校验）  |  【输出】3 种论文级 SVG 能级图 + Excel 表 (.xlsx) + 可编辑 PPTX",
        "REORG": "【输入】4 个 Gaussian .log（中性优化/带电优化/中性单点/带电单点）计算 λh/λe 与 Marcus 速率；或输入 1 个结构文件一键生成全套 4 个 .gjf 输入卡",
        "PLANE": "【输入】.fchk 或 3D 结构文件  |  【算法】SVD 重原子最佳拟合平面  |  【输出】平面度 RMSD (MPP)、最大离面距离 (SDP)、法向量与逐原子离面距离 .pqr",
        "DIPOLE": "【输入】Gaussian .fchk 文件  |  【输出】总偶极矩三维分量 (a.u.)、总偶极矩大小 (Debye) 与 VMD 3D 偶极箭头渲染脚本 (.tcl)",
        "RDF": "【输入】拓扑/结构文件 (.gro/.pdb/.tpr) 与可选轨迹 (.xtc/.trr)  |  【输出】径向分布函数 g(r) 曲线 CSV/SVG、第一配位峰位置与 GROMACS run_rdf.sh 脚本",
        "IGMH": "【输入】D-A 二聚体结构（生成带 IOp(7/33=1) 的 igmh.gjf）或二聚体 .fchk（调用 Multiwfn 20->10 IGMH）  |  【输出】dg_inter.cub / sl2r.cub 与 VMD 渲染脚本",
        "INTERACTION": "【输入】2 个分子结构文件  |  【输出】跨分子氢键 (D-H···A)、范德华紧密接触与芳香环 π-π 堆积筛查表",
        "MD": "【输入】1 个拓扑文件 (.pdb/.gro/.tpr) + 1 个轨迹文件 (.xtc/.trr/.dcd)  |  【输出】逐帧 Kabsch 对齐 RMSD、回旋半径 Rg、构象聚类与氢键占有率",
        "EDA": "【输入】包含 system(AB/A/B), component, mean_kj_mol 三列的 CSV  |  【输出】经典力场 rerun 组分间相互作用能差 ΔE = E(AB) - E(A) - E(B)",
    }

    def __init__(self, kind: str, parent=None, document=None):
        super().__init__(parent)
        title, minimum, pattern, req_tools = self.CONFIG[kind]
        self.kind = kind
        self.minimum = minimum
        self.pattern = pattern
        self.req_tools = req_tools
        self.canvas_document = document
        self.output_dir = str(Path.cwd() / "MolForge_Results")
        self._output_chosen = False
        self._canvas_input_path: str | None = None
        self.worker: _WorkflowWorker | None = None

        self.setWindowTitle(f"MolForge 科学工作流 — {title}")
        self.resize(700, 520)

        layout = QVBoxLayout(self)
        note_lbl = QLabel(self.NOTES.get(kind, title))
        note_lbl.setWordWrap(True)
        note_lbl.setStyleSheet("background:#122436; color:#CFE2F2; border:1px solid #284664; border-radius:6px; padding:8px;")
        layout.addWidget(note_lbl)

        # 工具依赖诚实检查栏
        self.engine_banner = QLabel()
        self.engine_banner.setWordWrap(True)
        layout.addWidget(self.engine_banner)
        self._update_engine_banner()

        # 子类专属参数区
        param_w = self._build_custom_params()
        if param_w is not None:
            layout.addWidget(param_w)

        layout.addWidget(QLabel("已选择的输入文件列表："))
        self.files = QListWidget(self)
        layout.addWidget(self.files, 1)

        row = QHBoxLayout()
        add_btn = QPushButton("➕ 添加输入文件…", self)
        add_btn.clicked.connect(self._add_files)
        row.addWidget(add_btn)

        clr_btn = QPushButton("清空列表", self)
        clr_btn.clicked.connect(self.files.clear)
        row.addWidget(clr_btn)

        out_btn = QPushButton("📁 选择结果输出目录…", self)
        out_btn.clicked.connect(self._choose_output)
        row.addWidget(out_btn)

        cfg_btn = QPushButton("⚙️ 配置外部工具路径…", self)
        cfg_btn.clicked.connect(self._open_tool_config)
        row.addWidget(cfg_btn)
        layout.addLayout(row)

        self.log_box = QPlainTextEdit(self)
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(110)
        self.log_box.setPlaceholderText("工作流执行进度与输出文件摘要将在此处显示...")
        layout.addWidget(self.log_box)

        self.run_button = QPushButton("🚀 运行工作流分析", self)
        self.run_button.setProperty("role", "action")
        self.run_button.setMinimumHeight(36)
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.run_button)

        # 默认接收当前画布分子：自动导出结构并预填，不再强制手动浏览磁盘
        self._prefill_canvas_document()

    def _prefill_canvas_document(self):
        if self.canvas_document is None:
            return
        if self.kind not in _STRUCTURE_CAPABLE_KINDS:
            # 需要 fchk/轨迹的工作流：当前画布无法替代，诚实提示而不伪造输入
            self.log_box.setPlaceholderText(
                "当前画布分子无法直接作为此分析输入（需要 .fchk 或轨迹文件），请点击「添加输入文件」选择已计算结果。"
            )
            return
        tmp_dir = Path(self.output_dir) / "_canvas_input"
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in self.canvas_document.name)
        xyz_path = str(tmp_dir / f"{safe}_canvas.xyz")
        export_document_to_xyz(self.canvas_document, xyz_path)
        self._canvas_input_path = xyz_path
        self.files.addItem(xyz_path)
        self.log_box.setPlainText(
            f"已自动载入当前画布分子（临时结构文件）：\n{xyz_path}\n可直接运行，或点击「添加输入文件」手动替换。"
        )

    def _build_custom_params(self):
        return None

    def _collect_params(self) -> dict:
        return {}

    def _update_engine_banner(self):
        if not self.req_tools:
            self.engine_banner.setText("<span style='color:#66DEC9;'>✅ 当前工作流核心计算可直接在本地运行（可选调用 Multiwfn / VMD / GROMACS）。</span>")
            return
        missing = []
        for tid in self.req_tools:
            st = EngineToolRegistry.detect_tool(tid)
            if not st.available:
                missing.append(st.display_name)
        if missing:
            self.engine_banner.setText(
                f"<span style='color:#FBBF24;'>⚠️ 诚实状态提示：当前未检测到 <b>{', '.join(missing)}</b>。"
                f"请先点击下方「⚙️ 配置外部工具路径…」指定可执行文件后再运行。</span>"
            )
        else:
            self.engine_banner.setText("<span style='color:#66DEC9;'>✅ 所需外部程序 (Multiwfn / VMD) 均已就绪。</span>")

    def _open_tool_config(self):
        ToolPathConfigDialog(self).exec()
        self._update_engine_banner()

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择输入文件", "", self.pattern)
        known = {self.files.item(i).text() for i in range(self.files.count())}
        for p in paths:
            if p not in known and Path(p).is_file():
                self.files.addItem(p)
        if paths and not self._output_chosen:
            self.output_dir = str(Path(paths[0]).resolve().parent / "MolForge_Results")

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择结果目录", self.output_dir)
        if path:
            self.output_dir = path
            self._output_chosen = True

    def _run(self):
        files = [self.files.item(i).text() for i in range(self.files.count())]
        if len(files) < self.minimum:
            QMessageBox.warning(self, "输入不足", f"至少需要 {self.minimum} 个输入文件。")
            return
        if self.kind in ("ESP", "DIPOLE") and Path(files[0]).suffix.lower() != ".fchk":
            QMessageBox.warning(self, "输入格式不匹配", "此分析需要 Gaussian .fchk 文件。")
            return
        if self.kind == "MD" and sum(Path(p).suffix.lower() in (".xtc", ".trr", ".dcd") for p in files) != 1:
            QMessageBox.warning(self, "输入不匹配", "MD 分析需要一个拓扑文件和一个 xtc/trr/dcd 轨迹文件。")
            return
        if self.kind == "INTERACTION" and len(files) != 2:
            QMessageBox.warning(self, "输入不足", "相互作用分析需要两个分子结构文件。")
            return
        if self.kind in ("OSC", "HOMO") and not any(Path(p).suffix.lower() == ".fchk" for p in files):
            QMessageBox.warning(self, "输入格式不匹配", "请选择至少一个 .fchk 文件。")
            return

        self.run_button.setEnabled(False)
        self.run_button.setText("⏳ 正在后台串行执行工作流…")
        self.log_box.setPlainText(f"开始执行 [{self.kind}] 工作流...\n目标输出根目录: {self.output_dir}")
        self.worker = _WorkflowWorker(self.kind, files, self.output_dir, params=self._collect_params())
        self.worker.succeeded.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _done(self, path: str):
        self.run_button.setEnabled(True)
        self.run_button.setText("🚀 运行工作流分析")
        out_p = Path(path)
        generated = [f.name for f in sorted(out_p.glob("*")) if f.is_file()] if out_p.is_dir() else []
        self.log_box.appendPlainText(f"✅ 分析完成！输出目录：{path}\n生成文件：{', '.join(generated)}")
        QMessageBox.information(self, "分析完成", f"结果已保存至：\n{path}\n\n包含文件：\n" + "\n".join(generated[:12]))

    def _failed(self, message: str):
        self.run_button.setEnabled(True)
        self.run_button.setText("🚀 运行工作流分析")
        self.log_box.appendPlainText(f"❌ 分析未完成：{message}")
        QMessageBox.critical(self, "分析未完成", message)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "正在运行", "外部分析正在后台串行执行；请等待当前任务结束后关闭窗口。")
            event.ignore()
            return
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# 第三步要求的 8 个核心工作流独立对话框子类
# ---------------------------------------------------------------------------

class EspSurfaceWorkflowDialog(ExternalWorkflowDialog):
    """1. ESP 表面分析对话框（选择 fchk -> 调用 Multiwfn + VMD -> 输出描述符表格 + BWR 表面图）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("ESP", parent=parent, document=document)

    def _build_custom_params(self):
        box = QFrame(self)
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("电子密度等值面 (a.u.):"))
        self.sp_iso = QDoubleSpinBox(self)
        self.sp_iso.setDecimals(4)
        self.sp_iso.setRange(0.0002, 0.0500)
        self.sp_iso.setSingleStep(0.0005)
        self.sp_iso.setValue(0.0010)
        lay.addWidget(self.sp_iso)
        lay.addStretch(1)
        return box

    def _collect_params(self) -> dict:
        return {"isovalue": round(self.sp_iso.value(), 4) if hasattr(self, "sp_iso") else 0.001}


class HomoLumoWorkflowDialog(ExternalWorkflowDialog):
    """2. HOMO-LUMO 能级图对话框（选择多个 fchk -> 提取能级 -> 画阶梯图 + 轨道图）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("HOMO", parent=parent, document=document)


class OscEnergyDiagramWorkflowDialog(ExternalWorkflowDialog):
    """3. OSC 能级对齐图对话框（给体+受体 fchk+log -> 画能级对齐图 + Excel + PPTX）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("OSC", parent=parent, document=document)


class ReorganizationEnergyWorkflowDialog(ExternalWorkflowDialog):
    """4. 重组能计算对话框（输入中性/阴离子 4 个 log 计算 λh/λe 与 Marcus 速率，或从结构生成 4 个 gjf）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("REORG", parent=parent, document=document)

    def _build_custom_params(self):
        box = QFrame(self)
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("工作模式:"))
        self.cb_mode = QComboBox(self)
        self.cb_mode.addItem("从 4 个 Gaussian .log 计算四点法 λ 与 Marcus 速率", "calc_from_logs")
        self.cb_mode.addItem("从 1 个分子结构文件生成全套 4 个重组能 .gjf 输入卡", "generate_gjf")
        lay.addWidget(self.cb_mode)

        lay.addWidget(QLabel("载流子类型:"))
        self.cb_carrier = QComboBox(self)
        self.cb_carrier.addItem("电子重组能 λ_e (阴离子 -1 2)", "electron")
        self.cb_carrier.addItem("空穴重组能 λ_h (阳离子 +1 2)", "hole")
        lay.addWidget(self.cb_carrier)

        lay.addWidget(QLabel("电子耦合 V_DA (eV):"))
        self.sp_vda = QDoubleSpinBox(self)
        self.sp_vda.setDecimals(4)
        self.sp_vda.setRange(0.0001, 1.0000)
        self.sp_vda.setValue(0.0250)
        lay.addWidget(self.sp_vda)
        return box

    def _collect_params(self) -> dict:
        return {
            "mode": self.cb_mode.currentData() if hasattr(self, "cb_mode") else "calc_from_logs",
            "carrier_type": self.cb_carrier.currentData() if hasattr(self, "cb_carrier") else "electron",
            "v_da_ev": round(self.sp_vda.value(), 4) if hasattr(self, "sp_vda") else 0.025,
        }


class DipoleAnalysisWorkflowDialog(ExternalWorkflowDialog):
    """5. 偶极矩分析对话框（读取 fchk -> 显示总偶极矩矢量与 Debye 数值 + VMD 箭头）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("DIPOLE", parent=parent, document=document)


class PlanarityAnalysisWorkflowDialog(ExternalWorkflowDialog):
    """6. 分子平面性分析对话框（SVD 最佳拟合平面 -> RMSD/MPP + 最大离面距离 SDP + PQR）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("PLANE", parent=parent, document=document)


class MdRdfWorkflowDialog(ExternalWorkflowDialog):
    """7. MD 后处理：RDF 径向分布函数对话框（选择结构/轨迹 -> 计算 g(r) 曲线 + 导出 gmx rdf 脚本）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("RDF", parent=parent, document=document)

    def _build_custom_params(self):
        box = QFrame(self)
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("RDF 最大截断半径 r_max (Å):"))
        self.sp_rmax = QDoubleSpinBox(self)
        self.sp_rmax.setRange(4.0, 30.0)
        self.sp_rmax.setValue(12.0)
        lay.addWidget(self.sp_rmax)
        lay.addStretch(1)
        return box

    def _collect_params(self) -> dict:
        return {"r_max": round(self.sp_rmax.value(), 1) if hasattr(self, "sp_rmax") else 12.0}


class IgmhInteractionWorkflowDialog(ExternalWorkflowDialog):
    """8. IGMH 弱相互作用对话框（生成二聚体 igmh.gjf 或调用 Multiwfn 20->10 计算 IGMH 等值面）。"""

    def __init__(self, parent=None, document=None):
        super().__init__("IGMH", parent=parent, document=document)

    def _build_custom_params(self):
        box = QFrame(self)
        lay = QHBoxLayout(box)
        lay.addWidget(QLabel("片段 1 原子序号范围:"))
        self.ed_frag1 = QLineEdit("1-30", self)
        lay.addWidget(self.ed_frag1)
        lay.addWidget(QLabel("片段 2 原子序号范围:"))
        self.ed_frag2 = QLineEdit("31-60", self)
        lay.addWidget(self.ed_frag2)
        return box

    def _collect_params(self) -> dict:
        return {
            "frag1_range": self.ed_frag1.text().strip() if hasattr(self, "ed_frag1") else "1-30",
            "frag2_range": self.ed_frag2.text().strip() if hasattr(self, "ed_frag2") else "31-60",
        }


class _MdStudioWorker(QThread):
    """后台线程执行 MD Studio 真实轨迹分析，避免阻塞 GUI。"""
    progress = pyqtSignal(str)
    succeeded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, topology, trajectory, output_dir, selection, frame_step, r_max, preprocess_pbc=False):
        super().__init__()
        self.topology, self.trajectory = topology, trajectory
        self.output_dir, self.selection = output_dir, selection
        self.frame_step, self.r_max = frame_step, r_max
        self.preprocess_pbc = preprocess_pbc

    def run(self):
        try:
            from ...workflows.md_studio import run_md_studio
            out = run_md_studio(
                self.topology, self.trajectory, self.output_dir,
                selection=self.selection, frame_step=self.frame_step, r_max=self.r_max,
                progress_callback=self.progress.emit, preprocess_pbc=self.preprocess_pbc,
            )
            self.succeeded.emit(str(out))
        except Exception as exc:  # 真实异常回传，不伪造
            self.failed.emit(str(exc))


class MdStudioDialog(QDialog):
    """统一外接分子动力学工作台：选择真实 GROMACS 轨迹，做 RMSD/Rg/RMSF/RDF/氢键分析。"""

    def __init__(self, parent=None, document=None):
        super().__init__(parent)
        self.setWindowTitle("MolForge 分子动力学工作台（GROMACS / MDAnalysis）")
        self.resize(640, 460)
        self.worker: _MdStudioWorker | None = None

        lay = QVBoxLayout(self)
        tip = QLabel(
            "对真实 GROMACS 轨迹做内存安全分析：RMSD（Kabsch 对齐）、回旋半径 Rg、"
            "逐原子 RMSF、径向分布函数 RDF 与氢键占有率。需要拓扑（gro/tpr）与轨迹（xtc/trr）。"
        )
        tip.setWordWrap(True)
        lay.addWidget(tip)

        form = QFormLayout()
        self.ed_top = QLineEdit()
        self.ed_traj = QLineEdit()
        row_t = QHBoxLayout(); row_t.addWidget(self.ed_top)
        bt_t = QPushButton("浏览…"); bt_t.clicked.connect(lambda: self._pick(self.ed_top, "拓扑文件 (*.gro *.tpr *.pdb)"))
        row_t.addWidget(bt_t)
        box_t = QFrame(); box_t.setLayout(row_t); form.addRow("拓扑文件：", box_t)

        row_j = QHBoxLayout(); row_j.addWidget(self.ed_traj)
        bt_j = QPushButton("浏览…"); bt_j.clicked.connect(lambda: self._pick(self.ed_traj, "轨迹文件 (*.xtc *.trr *.dcd)"))
        row_j.addWidget(bt_j)
        box_j = QFrame(); box_j.setLayout(row_j); form.addRow("轨迹文件：", box_j)

        self.ed_sel = QLineEdit("not name H*")
        form.addRow("原子选择：", self.ed_sel)
        self.sp_step = QSpinBox(); self.sp_step.setRange(1, 100); self.sp_step.setValue(2)
        form.addRow("帧采样步长：", self.sp_step)
        self.sp_rmax = QDoubleSpinBox(); self.sp_rmax.setRange(4.0, 50.0); self.sp_rmax.setValue(12.0)
        form.addRow("RDF 最大半径 (Å)：", self.sp_rmax)
        self.pbc_check = QCheckBox("先用GROMACS nojump消除周期跳跃（要求初始构型完整）")
        self.pbc_check.setChecked(True)
        self.pbc_check.setToolTip("先处理完整轨迹再采样。若轨迹已正确展开可取消；nojump不能修复起始帧中已断开的分子。")
        form.addRow(self.pbc_check)
        note = QLabel("默认RDF包含分子内/成键对；RMSF需正确处理周期边界后解释。")
        note.setWordWrap(True)
        form.addRow(note)
        lay.addLayout(form)

        self.log_box = QPlainTextEdit(); self.log_box.setReadOnly(True); self.log_box.setMaximumHeight(110)
        self.log_box.setPlaceholderText("分析进度与输出目录将在此显示…")
        lay.addWidget(self.log_box)

        self.run_btn = QPushButton("运行轨迹分析")
        self.run_btn.setProperty("role", "action"); self.run_btn.setMinimumHeight(36)
        self.run_btn.clicked.connect(self._run)
        lay.addWidget(self.run_btn)

    def _pick(self, edit, flt):
        p, _ = QFileDialog.getOpenFileName(self, "选择文件", "", flt)
        if p:
            edit.setText(p)
            if not self.ed_top.text():
                return
            if not self.log_box.toPlainText():
                self.output_dir = str(Path(p).resolve().parent / "MolForge_Results")

    def _run(self):
        top, traj = self.ed_top.text().strip(), self.ed_traj.text().strip()
        if not top or not traj:
            QMessageBox.warning(self, "输入不足", "请指定拓扑与轨迹文件。")
            return
        if not Path(top).is_file() or not Path(traj).is_file():
            QMessageBox.warning(self, "文件不存在", "拓扑或轨迹文件不存在。")
            return
        out_dir = str(Path(traj).resolve().parent / "MolForge_Results")
        self.run_btn.setEnabled(False); self.run_btn.setText("正在后台分析…")
        self.log_box.setPlainText("开始对真实轨迹执行 MD Studio 分析…")
        self.worker = _MdStudioWorker(
            top, traj, out_dir, self.ed_sel.text().strip() or "all",
            int(self.sp_step.value()), float(self.sp_rmax.value()), self.pbc_check.isChecked(),
        )
        self.worker.progress.connect(self.log_box.appendPlainText)
        self.worker.succeeded.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.start()

    def _done(self, path):
        self.run_btn.setEnabled(True); self.run_btn.setText("运行轨迹分析")
        self.log_box.appendPlainText(f"分析完成，输出目录：{path}")
        QMessageBox.information(self, "分析完成", f"结果已保存至：{path}")

    def _failed(self, msg):
        self.run_btn.setEnabled(True); self.run_btn.setText("运行轨迹分析")
        self.log_box.appendPlainText(f"分析失败：{msg}")
        QMessageBox.critical(self, "分析失败", msg)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "分析进行中", "轨迹仍在后台分析，请等待完成后关闭，避免中断结果。")
            event.ignore()
            return
        super().closeEvent(event)
