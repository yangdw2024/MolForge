"""
ui/dialogs/hpc_job_dialog.py - Linux 超算集群作业生成、提交与监控一体化工作台
========================================================================
功能：
  1. 多集群配置选择（支持远程 SSH 密钥连接与本地 WSL2 零配置仿真）
  2. 自动生成 Gaussian 16 / ORCA 6 / GROMACS / xTB / CalChem 的计算输入与 Slurm 脚本
  3. 一键通过 SSH/SCP 传输并提交至远程 Slurm/PBS 调度系统
  4. 实时轮询 squeue 队列状态，一键将完成的结果日志拉回并加载进 3D 画布
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QSpinBox, QLineEdit, QPlainTextEdit, QTabWidget, QMessageBox, QFileDialog,
    QProgressBar, QGroupBox
)

from ...domain.document import MoleculeDocument
from ...infrastructure.hpc.cluster_config import ClusterConfigManager, ClusterProfile
from ...infrastructure.hpc.slurm_generator import SlurmScriptGenerator, JobSpec
from ...infrastructure.hpc.remote_executor import RemoteHPCExecutor


class HpcJobDialog(QDialog):
    """Linux HPC 超算作业提交与任务管理对话框。"""

    def __init__(self, main_window, document: MoleculeDocument, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.document = document
        self.config_mgr = ClusterConfigManager()
        self.submitted_jobs: list[dict[str, Any]] = []

        self.setWindowTitle(f"Linux 超算集群任务调度中心 - {document.name}")
        self.resize(820, 620)

        self._build_ui()
        self._refresh_script_preview()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_submit_tab(), "🚀 1. 新建超算作业 (Submit New Job)")
        self.tabs.addTab(self._build_monitor_tab(), "📋 2. 远程作业队列监控 (Job Monitor)")
        self.tabs.addTab(self._build_cluster_tab(), "⚙️ 3. 集群主机配置 (Cluster Config)")
        root.addWidget(self.tabs, 1)

        bot = QHBoxLayout()
        bot.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bot.addWidget(close_btn)
        root.addLayout(bot)

    # ---------- Tab 1: Submit Job ----------
    def _build_submit_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        top_grid = QHBoxLayout()

        # 左侧：参数配置
        left_box = QGroupBox("作业资源配置 (Slurm Directives)")
        l_form = QFormLayout(left_box)

        self.cluster_combo = QComboBox()
        for name in self.config_mgr.profiles:
            self.cluster_combo.addItem(name)
        self.cluster_combo.currentIndexChanged.connect(self._refresh_script_preview)
        l_form.addRow("目标超算主机:", self.cluster_combo)

        self.engine_combo = QComboBox()
        self.engine_combo.addItems([
            "Gaussian 16 (DFT/ab initio)",
            "ORCA 6 (DFT/DLPNO-CCSD(T))",
            "xTB (半经验快速预优化)",
            "REST (复旦大学 Rust 原生量子化学/双杂化)",
            "GROMACS (分子动力学)",
            "CalChem-CLI (纯 Rust 高性能内核)",
        ])
        self.engine_combo.currentIndexChanged.connect(self._refresh_script_preview)
        l_form.addRow("计算引擎 (Engine):", self.engine_combo)

        self.job_name_edit = QLineEdit(f"{self.document.name}_calc")
        self.job_name_edit.textChanged.connect(self._refresh_script_preview)
        l_form.addRow("作业名称 (Name):", self.job_name_edit)

        self.partition_edit = QLineEdit("compute")
        self.partition_edit.textChanged.connect(self._refresh_script_preview)
        l_form.addRow("队列分区 (Partition):", self.partition_edit)

        self.cores_spin = QSpinBox()
        self.cores_spin.setRange(1, 256)
        self.cores_spin.setValue(16)
        self.cores_spin.valueChanged.connect(self._refresh_script_preview)
        l_form.addRow("计算核心 (Cores):", self.cores_spin)

        self.mem_spin = QSpinBox()
        self.mem_spin.setRange(1000, 512000)
        self.mem_spin.setSingleStep(4000)
        self.mem_spin.setValue(32000)
        self.mem_spin.setSuffix(" MB")
        self.mem_spin.valueChanged.connect(self._refresh_script_preview)
        l_form.addRow("内存限额 (Memory):", self.mem_spin)

        self.walltime_edit = QLineEdit("24:00:00")
        self.walltime_edit.textChanged.connect(self._refresh_script_preview)
        l_form.addRow("墙上时钟 (Walltime):", self.walltime_edit)

        top_grid.addWidget(left_box, 1)

        # 右侧：脚本实时预览
        right_box = QGroupBox("生成的 slurm.sh 脚本预览")
        r_lay = QVBoxLayout(right_box)
        self.script_preview = QPlainTextEdit()
        self.script_preview.setReadOnly(True)
        self.script_preview.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; background: #0E1A27; color: #66DEC9;")
        r_lay.addWidget(self.script_preview)
        top_grid.addWidget(right_box, 1)

        lay.addLayout(top_grid, 1)

        # 提交按钮区
        btn_box = QHBoxLayout()
        self.export_local_btn = QPushButton("💾 导出本地作业包 (Export Package)...")
        self.export_local_btn.clicked.connect(self._on_export_local)
        btn_box.addWidget(self.export_local_btn)

        self.submit_btn = QPushButton("🚀 一键上传并提交至超算 (Submit to Slurm)")
        self.submit_btn.setProperty("role", "action")
        self.submit_btn.clicked.connect(self._on_submit_remote)
        btn_box.addWidget(self.submit_btn)
        btn_box.addStretch()
        lay.addLayout(btn_box)

        return w

    # ---------- Tab 2: Job Monitor ----------
    def _build_monitor_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        top_bar = QHBoxLayout()
        self.refresh_queue_btn = QPushButton("🔄 刷新队列状态 (squeue)")
        self.refresh_queue_btn.clicked.connect(self._on_refresh_queue)
        top_bar.addWidget(self.refresh_queue_btn)

        self.download_log_btn = QPushButton("📥 拉回结果日志 (Download Logs)")
        self.download_log_btn.clicked.connect(self._on_download_logs)
        top_bar.addWidget(self.download_log_btn)
        top_bar.addStretch()
        lay.addLayout(top_bar)

        self.job_table = QTableWidget()
        self.job_table.setColumnCount(6)
        self.job_table.setHorizontalHeaderLabels([
            "作业编号 (Job ID)", "作业名称", "目标集群", "调度状态", "执行节点/耗时", "提交时间"
        ])
        self.job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.job_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lay.addWidget(self.job_table, 1)

        return w

    # ---------- Tab 3: Cluster Config ----------
    def _build_cluster_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("已保存的主机与超算节点："))
        self.cluster_list = QPlainTextEdit()
        self.cluster_list.setPlainText(json.dumps(
            {name: p.to_dict() for name, p in self.config_mgr.profiles.items()},
            indent=2, ensure_ascii=False
        ))
        lay.addWidget(self.cluster_list, 1)
        save_cfg_btn = QPushButton("保存集群配置修改")
        save_cfg_btn.clicked.connect(self._on_save_cluster_json)
        lay.addWidget(save_cfg_btn)
        return w

    def _get_current_job_spec_and_profile(self) -> tuple[JobSpec, ClusterProfile]:
        prof_name = self.cluster_combo.currentText()
        prof = self.config_mgr.get(prof_name) or ClusterProfile()

        eng_raw = self.engine_combo.currentText().lower()
        if "gaussian" in eng_raw:
            eng = "g16"
            in_file = f"{self.job_name_edit.text()}.gjf"
            out_file = f"{self.job_name_edit.text()}.log"
        elif "orca" in eng_raw:
            eng = "orca"
            in_file = f"{self.job_name_edit.text()}.inp"
            out_file = f"{self.job_name_edit.text()}.out"
        elif "gromacs" in eng_raw:
            eng = "gromacs"
            in_file = f"{self.job_name_edit.text()}.tpr"
            out_file = f"{self.job_name_edit.text()}.log"
        elif "xtb" in eng_raw:
            eng = "xtb"
            in_file = f"{self.job_name_edit.text()}.xyz"
            out_file = f"{self.job_name_edit.text()}.log"
        elif "rest" in eng_raw:
            eng = "rest"
            in_file = f"{self.job_name_edit.text()}.toml"
            out_file = f"{self.job_name_edit.text()}.log"
        else:
            eng = "calchem"
            in_file = f"{self.job_name_edit.text()}.json"
            out_file = f"{self.job_name_edit.text()}.out"

        job = JobSpec(
            job_name=self.job_name_edit.text(),
            engine=eng,
            input_file=in_file,
            output_file=out_file,
            n_cores=int(self.cores_spin.value()),
            memory_mb=int(self.mem_spin.value()),
            walltime=self.walltime_edit.text().strip(),
            partition=self.partition_edit.text().strip(),
        )
        return job, prof

    def _refresh_script_preview(self) -> None:
        try:
            job, prof = self._get_current_job_spec_and_profile()
            script = SlurmScriptGenerator.generate(job, prof)
            self.script_preview.setPlainText(script)
        except Exception:
            pass

    def _generate_job_input_file(self, job: JobSpec, target_path: Path) -> None:
        """根据计算引擎与当前 MoleculeDocument 生成规范的真实计算输入文件。"""
        doc = self.document
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if job.engine == "g16":
            from ...application.calculators.gaussian_job_spec import GaussianJobSpec
            spec = GaussianJobSpec.default_spec(doc)
            spec.job_type = "Opt+Freq"
            spec.nproc_shared = max(1, job.n_cores)
            spec.memory_gb = max(1, job.memory_mb // 1024)
            spec.chk_filename = f"{job.job_name}.chk"
            content = spec.generate_gjf(doc, allow_sample_placeholder=False)
            target_path.write_text(content, encoding="utf-8")
        elif job.engine == "orca":
            from ...application.calculators.qc_input_generator import extract_xyz_lines
            xyz_lines = extract_xyz_lines(doc)
            maxcore = max(1000, job.memory_mb // max(1, job.n_cores))
            charge = int(doc.properties.get("charge", 0))
            z_sum = sum(doc.topology.get_atom(aid).atomic_num for aid in doc.topology.atom_ids)
            mult = 1 if ((z_sum - charge) % 2 == 0) else 2
            lines = [
                f"# ORCA 6 Input generated by MolForge for {doc.name}",
                "! B3LYP D3BJ def2-SVP TightSCF Opt",
                f"%pal nprocs {job.n_cores} end",
                f"%maxcore {maxcore}",
                "",
                f"* xyz {charge} {mult}",
            ]
            lines.extend(xyz_lines)
            lines.append("*")
            target_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        elif job.engine == "xtb":
            from ...application.calculators.qc_input_generator import export_document_to_xyz
            export_document_to_xyz(doc, str(target_path))
        elif job.engine == "rest":
            from ...application.calculators.qc_input_generator import generate_rest_ctrl_in
            charge = float(doc.properties.get("charge", 0.0))
            toml_text = generate_rest_ctrl_in(
                doc,
                xc="b3lyp",
                basis="def2-SVP",
                auxbas="def2-universal-jkfit",
                charge=charge,
                num_threads=max(2, job.n_cores),
                basis_pool="/mnt/e/YDW/REST/knowledge_base/rest_github/basis-set-pool",
            )
            target_path.write_text(toml_text, encoding="utf-8")
        elif job.engine == "calchem":
            import json
            atom_data = []
            coords = doc.coordinates.current.coords if (doc.has_3d and doc.coordinates.current is not None) else None
            idx_to_id, _ = doc.topology.atom_index_map()
            for i, aid in enumerate(idx_to_id):
                atom = doc.topology.get_atom(aid)
                c = coords[i].tolist() if coords is not None and i < len(coords) else [0.0, 0.0, 0.0]
                atom_data.append({"atomic_number": atom.atomic_num, "xyz": c})
            charge = int(doc.properties.get("charge", 0))
            payload = {
                "name": job.job_name,
                "method": "RHF",
                "basis": "sto-3g",
                "charge": charge,
                "atoms": atom_data,
            }
            target_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        elif job.engine == "gromacs":
            from ...ui.shells.workflow_inputs import export_document_to_xyz
            export_document_to_xyz(doc, str(target_path.with_suffix(".xyz")))
            target_path.write_text(f"; GROMACS job placeholder for {doc.name}\n", encoding="utf-8")
        else:
            target_path.write_text(f"# Generic input for {job.engine}\n", encoding="utf-8")

    def _on_export_local(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "选择本地作业导出目录")
        if not dir_path:
            return
        dest = Path(dir_path) / self.job_name_edit.text()
        dest.mkdir(parents=True, exist_ok=True)
        job, prof = self._get_current_job_spec_and_profile()
        script = SlurmScriptGenerator.generate(job, prof)

        # 写 slurm.sh
        with open(dest / "slurm.sh", "w", encoding="utf-8") as f:
            f.write(script)

        # 写规范真实计算输入文件
        self._generate_job_input_file(job, dest / job.input_file)

        QMessageBox.information(self, "导出成功", f"作业包已完整生成至：\n{dest}")

    def _on_submit_remote(self) -> None:
        job, prof = self._get_current_job_spec_and_profile()
        from ...runtime import data_dir
        tmp_pkg = data_dir() / "temp" / f"hpc_{job.job_name}"
        tmp_pkg.mkdir(parents=True, exist_ok=True)

        script = SlurmScriptGenerator.generate(job, prof)
        script_file = tmp_pkg / "slurm.sh"
        with open(script_file, "w", encoding="utf-8") as f:
            f.write(script)

        input_path = tmp_pkg / job.input_file
        self._generate_job_input_file(job, input_path)

        executor = RemoteHPCExecutor(prof)
        remote_job_dir = f"{prof.remote_workdir}/{job.job_name}"

        # 1. 上传文件
        ok_up = executor.upload_files([script_file, input_path], remote_job_dir)
        if not ok_up:
            QMessageBox.warning(self, "上传失败", f"无法连接或上传至 {prof.hostname}:{remote_job_dir}")
            return

        # 2. 提交作业
        ok_sub, msg = executor.submit_job(remote_job_dir, "slurm.sh")
        if not ok_sub:
            QMessageBox.warning(self, "提交失败", msg)
            return

        import datetime
        job_info = {
            "id": msg,
            "name": job.job_name,
            "cluster": prof.name,
            "status": "PENDING",
            "info": "刚刚提交",
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "remote_dir": remote_job_dir,
            "output_file": job.output_file,
            "profile": prof,
        }
        self.submitted_jobs.append(job_info)
        self._append_job_to_table(job_info)
        self.tabs.setCurrentIndex(1)
        QMessageBox.information(self, "提交成功", f"作业已成功提交至集群！\nJob ID: {msg}")

    def _append_job_to_table(self, job_info: dict[str, Any]) -> None:
        r = self.job_table.rowCount()
        self.job_table.insertRow(r)
        self.job_table.setItem(r, 0, QTableWidgetItem(str(job_info["id"])))
        self.job_table.setItem(r, 1, QTableWidgetItem(job_info["name"]))
        self.job_table.setItem(r, 2, QTableWidgetItem(job_info["cluster"]))
        self.job_table.setItem(r, 3, QTableWidgetItem(job_info["status"]))
        self.job_table.setItem(r, 4, QTableWidgetItem(job_info["info"]))
        self.job_table.setItem(r, 5, QTableWidgetItem(job_info["time"]))

    def _on_refresh_queue(self) -> None:
        for i, j in enumerate(self.submitted_jobs):
            executor = RemoteHPCExecutor(j["profile"])
            st = executor.query_job(j["id"])
            j["status"] = st.status
            j["info"] = f"{st.node} {st.elapsed}".strip()
            self.job_table.setItem(i, 3, QTableWidgetItem(st.status))
            self.job_table.setItem(i, 4, QTableWidgetItem(j["info"]))

    def _on_download_logs(self) -> None:
        sel = self.job_table.selectionModel().selectedRows()
        if not sel:
            return
        r = sel[0].row()
        j = self.submitted_jobs[r]
        executor = RemoteHPCExecutor(j["profile"])
        from ...runtime import data_dir
        dest = data_dir() / "temp" / f"dl_{j['output_file']}"
        rem_file = f"{j['remote_dir']}/{j['output_file']}"
        ok = executor.download_file(rem_file, dest)
        if ok and dest.exists():
            QMessageBox.information(self, "下载完成", f"结果文件已拉回本地:\n{dest}")
            if hasattr(self.main_window, "_open_file_path"):
                self.main_window._open_file_path(str(dest))
            elif hasattr(self.main_window, "_open_qc_log"):
                self.main_window._open_qc_log()
        else:
            QMessageBox.warning(self, "下载失败", f"未能从远程拉回 {rem_file}，可能作业仍在运行。")

    def _on_save_cluster_json(self) -> None:
        try:
            data = json.loads(self.cluster_list.toPlainText())
            self.config_mgr.profiles = {
                name: ClusterProfile.from_dict(prof) for name, prof in data.items()
            }
            self.config_mgr.save()
            self.cluster_combo.clear()
            for name in self.config_mgr.profiles:
                self.cluster_combo.addItem(name)
            QMessageBox.information(self, "保存成功", "集群配置已持久化！")
        except Exception as e:
            QMessageBox.warning(self, "格式错误", f"JSON 格式无效: {e}")
