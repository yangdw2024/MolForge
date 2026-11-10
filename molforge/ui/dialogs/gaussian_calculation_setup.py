"""
ui/dialogs/gaussian_calculation_setup.py - 对标 GaussView 的 11 页签 + 6 按钮 Gaussian 计算设置对话框
====================================================================================================
严格实现 4.3 节规范：
  - 11 个页签：Job Type / Method / Title / Link 0 / General / Guess / Pop. / PBC / Solvation / Add. Inp. / Preview
  - 6 个底部控制按钮：Submit / Quick Launch / Cancel / Edit / Retain / Defaults
  - 唯一配置事实源 GaussianJobSpec，严禁空分子伪造 C 原子提交，后台提交绑定 document.revision 防止过期覆盖。
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QFormLayout,
    QComboBox, QCheckBox, QSpinBox, QLineEdit, QPlainTextEdit, QPushButton,
    QLabel, QMessageBox, QFileDialog,
)

from ...application.calculators.gaussian_job_spec import GaussianJobSpec
from ...domain.document import MoleculeDocument


class GaussianCalculationSetupDialog(QDialog):
    """GaussView 风格 11 页签 + 6 按钮 Gaussian Calculation Setup 对话框。"""

    TAB_NAMES: tuple[str, ...] = (
        "Job Type",
        "Method",
        "Title",
        "Link 0",
        "General",
        "Guess",
        "Pop.",
        "PBC",
        "Solvation",
        "Add. Inp.",
        "Preview",
    )

    BUTTON_NAMES: tuple[str, ...] = (
        "Submit",
        "Quick Launch",
        "Cancel",
        "Edit",
        "Retain",
        "Defaults",
    )

    def __init__(self, document: MoleculeDocument, parent=None, retained_spec: GaussianJobSpec | None = None):
        super().__init__(parent)
        self.document = document
        self.spec: GaussianJobSpec = retained_spec or GaussianJobSpec.default_spec(document)
        self.retained_snapshot: dict | None = None
        self.submitted_action: str | None = None  # "submit" | "quick_launch" | "retain"

        self.setWindowTitle("Gaussian Calculation Setup — MolForge Quantum Workbench")
        self.setMinimumSize(780, 560)

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)

        self._build_all_11_tabs()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 6 个标准控制按钮
        btn_row = QHBoxLayout()
        self.btn_submit = QPushButton("Submit...")
        self.btn_quick_launch = QPushButton("Quick Launch")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_edit = QPushButton("Edit...")
        self.btn_retain = QPushButton("Retain")
        self.btn_defaults = QPushButton("Defaults")

        self.btn_submit.clicked.connect(self._on_submit)
        self.btn_quick_launch.clicked.connect(self._on_quick_launch)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_edit.clicked.connect(self._on_edit_raw)
        self.btn_retain.clicked.connect(self._on_retain)
        self.btn_defaults.clicked.connect(self._on_defaults)

        for b in (self.btn_submit, self.btn_quick_launch, self.btn_edit, self.btn_retain, self.btn_defaults, self.btn_cancel):
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._sync_ui_from_spec()

    def _build_all_11_tabs(self) -> None:
        # 1. Job Type
        p_job = QWidget(); f1 = QFormLayout(p_job)
        self.cb_job_type = QComboBox()
        self.cb_job_type.addItems(["Energy", "Optimization", "Frequency", "Opt+Freq", "TD-SCF", "IRC", "Scan"])
        self.chk_opt_ts = QCheckBox("优化至过渡态 (Optimize to a Transition State - Berny TS)")
        self.chk_raman = QCheckBox("计算拉曼光谱活性 (Compute Raman)")
        self.sp_td_nstates = QSpinBox(); self.sp_td_nstates.setRange(1, 100); self.sp_td_nstates.setValue(6)
        f1.addRow("任务类型 (Job Type):", self.cb_job_type)
        f1.addRow("", self.chk_opt_ts)
        f1.addRow("", self.chk_raman)
        f1.addRow("TD-SCF 激发态根数 (NStates):", self.sp_td_nstates)
        self.tabs.addTab(p_job, "Job Type")

        # 2. Method
        p_met = QWidget(); f2 = QFormLayout(p_met)
        self.cb_family = QComboBox(); self.cb_family.addItems(["DFT", "HF", "MP2", "CCSD(T)", "Semi-Empirical"])
        self.cb_func = QComboBox(); self.cb_func.addItems(["B3LYP", "CAM-B3LYP", "wB97XD", "PBE0", "M062X", "PBE", "HF"])
        self.cb_basis = QComboBox(); self.cb_basis.addItems(["def2SVP", "def2TZVP", "6-31G(d)", "6-311+G(d,p)", "cc-pVDZ", "cc-pVTZ", "STO-3G"])
        self.cb_disp = QComboBox(); self.cb_disp.addItems(["GD3BJ", "GD3", "None"])
        self.cb_spin = QComboBox(); self.cb_spin.addItems(["Default", "Restricted", "Unrestricted"])
        self.sp_charge = QSpinBox(); self.sp_charge.setRange(-20, 20)
        self.sp_mult = QSpinBox(); self.sp_mult.setRange(1, 15)
        f2.addRow("方法家族 (Method Family):", self.cb_family)
        f2.addRow("泛函/理论 (Functional):", self.cb_func)
        f2.addRow("基组 (Basis Set):", self.cb_basis)
        f2.addRow("经验色散 (Dispersion):", self.cb_disp)
        f2.addRow("自旋限制 (Spin):", self.cb_spin)
        f2.addRow("总电荷 (Charge):", self.sp_charge)
        f2.addRow("自旋多重度 (Spin Multiplicity):", self.sp_mult)
        self.tabs.addTab(p_met, "Method")

        # 3. Title
        p_tit = QWidget(); f3 = QFormLayout(p_tit)
        self.ed_title = QLineEdit()
        f3.addRow("任务标题 (Job Title):", self.ed_title)
        self.tabs.addTab(p_tit, "Title")

        # 4. Link 0
        p_l0 = QWidget(); f4 = QFormLayout(p_l0)
        self.sp_mem = QSpinBox(); self.sp_mem.setRange(1, 512); self.sp_mem.setSuffix(" GB")
        self.sp_nproc = QSpinBox(); self.sp_nproc.setRange(1, 128)
        self.ed_chk = QLineEdit()
        self.chk_save_chk = QCheckBox("保存 Checkpoint 文件 (%chk)")
        self.chk_save_chk.setChecked(True)
        f4.addRow("内存上限 (%mem):", self.sp_mem)
        f4.addRow("共享内存核数 (%nprocshared):", self.sp_nproc)
        f4.addRow("Chk 文件名 (%chk):", self.ed_chk)
        f4.addRow("", self.chk_save_chk)
        self.tabs.addTab(p_l0, "Link 0")

        # 5. General
        p_gen = QWidget(); f5 = QFormLayout(p_gen)
        self.cb_scf_conv = QComboBox(); self.cb_scf_conv.addItems(["Tight", "Normal", "VeryTight"])
        self.cb_grid = QComboBox(); self.cb_grid.addItems(["UltraFine", "Fine", "SuperFine"])
        self.chk_symm = QCheckBox("启用分子点群对称性 (Use Symmetry)")
        self.chk_symm.setChecked(True)
        f5.addRow("SCF 收敛标准:", self.cb_scf_conv)
        f5.addRow("DFT 积分网格 (Int=Grid):", self.cb_grid)
        f5.addRow("", self.chk_symm)
        self.tabs.addTab(p_gen, "General")

        # 6. Guess
        p_gue = QWidget(); f6 = QFormLayout(p_gue)
        self.cb_guess = QComboBox(); self.cb_guess.addItems(["Default", "Read", "Core", "Huckel", "Mix"])
        f6.addRow("初始波函数猜测 (Guess):", self.cb_guess)
        self.tabs.addTab(p_gue, "Guess")

        # 7. Pop.
        p_pop = QWidget(); f7 = QFormLayout(p_pop)
        self.cb_pop = QComboBox(); self.cb_pop.addItems(["Regular", "Full", "Minimal", "None"])
        self.chk_nbo = QCheckBox("自然键轨道分析 (NBO Population)")
        self.chk_esp = QCheckBox("Merz-Kollman 静电势拟合电荷 (ESP/MK)")
        f7.addRow("布居分析输出级别 (Pop):", self.cb_pop)
        f7.addRow("", self.chk_nbo)
        f7.addRow("", self.chk_esp)
        self.tabs.addTab(p_pop, "Pop.")

        # 8. PBC
        p_pbc = QWidget(); f8 = QFormLayout(p_pbc)
        self.chk_pbc = QCheckBox("启用周期性边界条件 (Periodic Boundary Conditions)")
        self.sp_pbc_dim = QSpinBox(); self.sp_pbc_dim.setRange(1, 3); self.sp_pbc_dim.setValue(3)
        f8.addRow("", self.chk_pbc)
        f8.addRow("周期维数 (1D/2D/3D):", self.sp_pbc_dim)
        self.tabs.addTab(p_pbc, "PBC")

        # 9. Solvation
        p_sol = QWidget(); f9 = QFormLayout(p_sol)
        self.cb_solv_model = QComboBox(); self.cb_solv_model.addItems(["None", "IEFPCM", "CPCM", "SMD"])
        self.cb_solvent = QComboBox(); self.cb_solvent.addItems(["Water", "Chloroform", "Dichloromethane", "Chlorobenzene", "Toluene", "THF", "Acetonitrile", "DMSO"])
        f9.addRow("连续介质溶剂模型 (SCRF):", self.cb_solv_model)
        f9.addRow("溶剂名称 (Solvent):", self.cb_solvent)
        self.tabs.addTab(p_sol, "Solvation")

        # 10. Add. Inp.
        p_add = QWidget(); f10 = QFormLayout(p_add)
        self.ed_add_route = QLineEdit()
        self.ed_add_tail = QPlainTextEdit()
        f10.addRow("附加 Route 关键字:", self.ed_add_route)
        f10.addRow("文件末尾附加输入块:", self.ed_add_tail)
        self.tabs.addTab(p_add, "Add. Inp.")

        # 11. Preview
        p_pre = QWidget(); l_pre = QVBoxLayout(p_pre)
        self.lbl_preview_mode = QLabel("以下内容由唯一 GaussianJobSpec 模型实时生成（点底部 [Edit...] 可切换手动高级编辑）：")
        self.ed_preview = QPlainTextEdit()
        self.ed_preview.setReadOnly(True)
        l_pre.addWidget(self.lbl_preview_mode)
        l_pre.addWidget(self.ed_preview, 1)
        self.tabs.addTab(p_pre, "Preview")

    def _sync_ui_from_spec(self) -> None:
        s = self.spec
        self.cb_job_type.setCurrentText(s.job_type)
        self.chk_opt_ts.setChecked(s.optimize_to_ts)
        self.chk_raman.setChecked(s.compute_raman)
        self.sp_td_nstates.setValue(s.td_nstates)
        self.cb_family.setCurrentText(s.theory_family)
        self.cb_func.setCurrentText(s.functional_or_method)
        self.cb_basis.setCurrentText(s.basis_set)
        self.cb_disp.setCurrentText(s.dispersion)
        self.cb_spin.setCurrentText(s.spin_restriction)
        self.sp_charge.setValue(s.charge)
        self.sp_mult.setValue(s.multiplicity)
        self.ed_title.setText(s.title)
        self.sp_mem.setValue(s.memory_gb)
        self.sp_nproc.setValue(s.nproc_shared)
        self.ed_chk.setText(s.chk_filename)
        self.chk_save_chk.setChecked(s.save_chk)
        self.cb_scf_conv.setCurrentText(s.scf_convergence)
        self.cb_grid.setCurrentText(s.integral_grid)
        self.chk_symm.setChecked(s.use_symmetry)
        self.cb_guess.setCurrentText(s.guess_type)
        self.cb_pop.setCurrentText(s.pop_level)
        self.chk_nbo.setChecked(s.compute_nbo)
        self.chk_esp.setChecked(s.compute_esp_charges)
        self.chk_pbc.setChecked(s.enable_pbc)
        self.sp_pbc_dim.setValue(max(1, s.pbc_dimensions or 3))
        self.cb_solv_model.setCurrentText(s.solvation_model)
        self.cb_solvent.setCurrentText(s.solvent)
        self.ed_add_route.setText(s.additional_route_keywords)
        self.ed_add_tail.setPlainText(s.additional_tail_input)
        self._refresh_preview()

    def sync_spec_from_ui(self) -> GaussianJobSpec:
        s = self.spec
        s.job_type = self.cb_job_type.currentText()  # type: ignore[assignment]
        s.optimize_to_ts = self.chk_opt_ts.isChecked()
        s.compute_raman = self.chk_raman.isChecked()
        s.td_nstates = int(self.sp_td_nstates.value())
        s.theory_family = self.cb_family.currentText()
        s.functional_or_method = self.cb_func.currentText()
        s.basis_set = self.cb_basis.currentText()
        s.dispersion = self.cb_disp.currentText()
        s.spin_restriction = self.cb_spin.currentText()
        s.charge = int(self.sp_charge.value())
        s.multiplicity = int(self.sp_mult.value())
        s.title = self.ed_title.text().strip()
        s.memory_gb = int(self.sp_mem.value())
        s.nproc_shared = int(self.sp_nproc.value())
        s.chk_filename = self.ed_chk.text().strip()
        s.save_chk = self.chk_save_chk.isChecked()
        s.scf_convergence = self.cb_scf_conv.currentText()
        s.integral_grid = self.cb_grid.currentText()
        s.use_symmetry = self.chk_symm.isChecked()
        s.guess_type = self.cb_guess.currentText()
        s.pop_level = self.cb_pop.currentText()
        s.compute_nbo = self.chk_nbo.isChecked()
        s.compute_esp_charges = self.chk_esp.isChecked()
        s.enable_pbc = self.chk_pbc.isChecked()
        s.pbc_dimensions = int(self.sp_pbc_dim.value()) if s.enable_pbc else 0
        s.solvation_model = self.cb_solv_model.currentText()
        s.solvent = self.cb_solvent.currentText()
        s.additional_route_keywords = self.ed_add_route.text().strip()
        s.additional_tail_input = self.ed_add_tail.toPlainText().strip()
        if not self.ed_preview.isReadOnly():
            s.custom_edited_gjf = self.ed_preview.toPlainText()
        return s

    def _refresh_preview(self) -> None:
        self.sync_spec_from_ui()
        if self.ed_preview.isReadOnly():
            self.spec.custom_edited_gjf = None
            self.ed_preview.setPlainText(self.spec.generate_gjf(self.document, allow_sample_placeholder=True))

    def _on_tab_changed(self, idx: int) -> None:
        if self.tabs.tabText(idx) == "Preview":
            self._refresh_preview()

    def _on_edit_raw(self) -> None:
        self.tabs.setCurrentIndex(10)  # Preview tab
        self.ed_preview.setReadOnly(False)
        self.lbl_preview_mode.setText("⚠️ 已进入高级原始输入编辑模式：修改文本后将直接以此文本作为最终 .gjf。")

    def _on_retain(self) -> None:
        self.sync_spec_from_ui()
        self.retained_snapshot = self.spec.to_preset_dict()
        self.submitted_action = "retain"
        self.accept()

    def _on_defaults(self) -> None:
        self.spec = GaussianJobSpec.default_spec(self.document)
        self.ed_preview.setReadOnly(True)
        self._sync_ui_from_spec()

    def _on_submit(self) -> None:
        self.sync_spec_from_ui()
        errs = self.spec.validate(self.document, for_submission=True)
        if errs:
            QMessageBox.warning(self, "Gaussian 输入校验未通过", "\n".join(errs))
            return
        self.submitted_action = "submit"
        self.accept()

    def _on_quick_launch(self) -> None:
        self.sync_spec_from_ui()
        errs = self.spec.validate(self.document, for_submission=True)
        if errs:
            QMessageBox.warning(self, "Quick Launch 校验未通过", "\n".join(errs))
            return
        self.submitted_action = "quick_launch"
        self.accept()
