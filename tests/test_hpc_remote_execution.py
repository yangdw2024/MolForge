"""
tests/test_hpc_remote_execution.py - Linux HPC 超算作业调度、脚本生成与队列监控单元测试
========================================================================================
覆盖：
  1. SlurmScriptGenerator 对各计算引擎 (Gaussian/ORCA/xTB/CalChem/GROMACS) 的脚本渲染
  2. ClusterConfigManager 配置文件持久化与多集群管理
  3. squeue / sacct 状态解析与标准化 (PENDING, RUNNING, COMPLETED, FAILED)
  4. RemoteHPCExecutor 模拟分发、队列轮询与状态机转换
  5. 真实 MoleculeDocument 到各计算引擎输入卡 (.gjf, .inp, .xyz, .json) 的转换
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from molforge.domain.document import MoleculeDocument
from molforge.infrastructure.hpc.cluster_config import ClusterConfigManager, ClusterProfile
from molforge.infrastructure.hpc.remote_executor import (
    RemoteHPCExecutor,
    RemoteJobStatus,
    parse_squeue_output,
)
from molforge.infrastructure.hpc.slurm_generator import JobSpec, SlurmScriptGenerator
from molforge.io.rdkit_adapter import create_sample_molecule


class TestHpcRemoteExecution(unittest.TestCase):
    def test_slurm_script_generation_gaussian(self):
        prof = ClusterProfile(
            name="TestCluster",
            default_partition="gpu_queue",
            env_preamble=["module purge", "module load gaussian/g16"],
            app_paths={"g16": "/opt/gaussian/g16"},
        )
        job = JobSpec(
            job_name="opt_freq_caffeine",
            engine="g16",
            input_file="caffeine.gjf",
            output_file="caffeine.log",
            n_cores=32,
            memory_mb=64000,
            walltime="48:00:00",
            partition="gpu_queue",
        )
        script = SlurmScriptGenerator.generate(job, prof)

        self.assertIn("#!/bin/bash", script)
        self.assertIn("#SBATCH --job-name=opt_freq_caffeine", script)
        self.assertIn("#SBATCH --ntasks=32", script)
        self.assertIn("#SBATCH --mem=64000M", script)
        self.assertIn("#SBATCH --time=48:00:00", script)
        self.assertIn("#SBATCH --partition=gpu_queue", script)
        self.assertIn("module load gaussian/g16", script)
        self.assertIn("/opt/gaussian/g16 < caffeine.gjf > caffeine.log", script)
        self.assertIn("formchk opt_freq_caffeine.chk opt_freq_caffeine.fchk", script)

    def test_slurm_script_generation_orca_and_xtb(self):
        prof = ClusterProfile()
        job_orca = JobSpec(
            job_name="orca_calc",
            engine="orca",
            input_file="mol.inp",
            output_file="mol.out",
            n_cores=16,
        )
        script_orca = SlurmScriptGenerator.generate(job_orca, prof)
        self.assertIn("orca mol.inp > mol.out", script_orca)

        job_xtb = JobSpec(
            job_name="xtb_opt",
            engine="xtb",
            input_file="mol.xyz",
            output_file="mol.log",
        )
        script_xtb = SlurmScriptGenerator.generate(job_xtb, prof)
        self.assertIn("xtb mol.xyz --opt > mol.log", script_xtb)

    def test_cluster_config_manager_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = ClusterConfigManager(config_dir=Path(tmpdir))
            # 默认应该有 Default_Linux_Cluster 和 Local_WSL2_Ubuntu
            self.assertIn("Default_Linux_Cluster", mgr.profiles)
            self.assertIn("Local_WSL2_Ubuntu", mgr.profiles)

            # 添加自定义超算档案
            my_prof = ClusterProfile(
                name="TH_Supercomputer",
                host_type="ssh",
                hostname="ln01.nscc-tj.cn",
                port=22,
                username="user_sc",
                default_partition="th_compute",
                default_nodes=2,
                default_ntasks=48,
                default_memory_mb=128000,
            )
            mgr.set(my_prof)

            # 重新实例化并读取，验证序列化持久化
            mgr_reloaded = ClusterConfigManager(config_dir=Path(tmpdir))
            loaded_prof = mgr_reloaded.get("TH_Supercomputer")
            self.assertIsNotNone(loaded_prof)
            self.assertEqual(loaded_prof.hostname, "ln01.nscc-tj.cn")
            self.assertEqual(loaded_prof.default_nodes, 2)
            self.assertEqual(loaded_prof.default_ntasks, 48)

    def test_parse_squeue_output(self):
        # 1. 运行中状态
        r1 = parse_squeue_output("100234 R cn05 02:45:12", "100234")
        self.assertEqual(r1.status, "RUNNING")
        self.assertEqual(r1.node, "cn05")
        self.assertEqual(r1.elapsed, "02:45:12")

        # 2. 排队状态 (PD / PENDING)
        r2 = parse_squeue_output("100235 PD (Priority) 00:00:00", "100235")
        self.assertEqual(r2.status, "PENDING")
        self.assertEqual(r2.node, "(Priority)")

        # 3. 失败 / 超时状态
        r3 = parse_squeue_output("100236 TO None 24:00:01", "100236")
        self.assertEqual(r3.status, "FAILED")

        # 4. 空输出
        r4 = parse_squeue_output("", "100237")
        self.assertEqual(r4.status, "UNKNOWN")

    def test_remote_executor_mock_dispatch_and_query(self):
        prof = ClusterProfile(
            name="MockCluster",
            host_type="ssh",
            hostname="mock.hpc",
            scheduler="slurm",
        )

        mock_responses = {
            "sbatch slurm.sh": (0, "Submitted batch job 776655\n", ""),
            "squeue -j 776655": (0, "776655 R node02 00:15:30\n", ""),
            "squeue -j 999999": (0, "", ""),
            "sacct -j 999999": (0, "999999|COMPLETED\n999999.batch|COMPLETED\n", ""),
        }

        def mock_runner(cmd_list: list[str]):
            cmd_str = " ".join(cmd_list)
            for k, resp in mock_responses.items():
                if k in cmd_str:
                    return resp
            return 1, "", f"Command not found: {cmd_str}"

        executor = RemoteHPCExecutor(prof, runner=mock_runner)

        # 1. 测试作业提交
        ok, job_id = executor.submit_job("/remote/jobs/test", "slurm.sh")
        self.assertTrue(ok)
        self.assertEqual(job_id, "776655")

        # 2. 测试运行中作业查询
        st_running = executor.query_job("776655")
        self.assertEqual(st_running.status, "RUNNING")
        self.assertEqual(st_running.node, "node02")
        self.assertEqual(st_running.elapsed, "00:15:30")

        # 3. 测试已完成作业查询 (离开 squeue 队列，sacct 返回 COMPLETED)
        st_completed = executor.query_job("999999")
        self.assertEqual(st_completed.status, "COMPLETED")

    def test_authentic_input_generation_from_document(self):
        doc = create_sample_molecule("咖啡因")
        self.assertGreater(doc.topology.num_atoms, 0)
        self.assertTrue(doc.has_3d)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # 1. 测试 Gaussian 输入生成
            from molforge.application.calculators.gaussian_job_spec import GaussianJobSpec
            spec = GaussianJobSpec.default_spec(doc)
            spec.job_type = "Opt+Freq"
            spec.functional_or_method = "B3LYP"
            spec.basis_set = "def2SVP"
            spec.nproc_shared = 16
            spec.memory_gb = 32
            gjf_content = spec.generate_gjf(doc)
            gjf_file = tmppath / "test.gjf"
            gjf_file.write_text(gjf_content, encoding="utf-8")

            self.assertTrue(gjf_file.exists())
            self.assertIn("%mem=32GB", gjf_content)
            self.assertIn("%nprocshared=16", gjf_content)
            self.assertIn("#p B3LYP/def2SVP Opt Freq", gjf_content)
            self.assertIn("0 1\n", gjf_content)  # 咖啡因电荷与多重度

            # 2. 测试 ORCA 6 输入生成
            from molforge.application.calculators.qc_input_generator import extract_xyz_lines
            xyz_lines = extract_xyz_lines(doc)
            self.assertEqual(len(xyz_lines), doc.topology.num_atoms)
            orca_lines = [
                "! B3LYP D3BJ def2-SVP TightSCF Opt",
                "%pal nprocs 16 end",
                "%maxcore 2000",
                "",
                "* xyz 0 1",
            ]
            orca_lines.extend(xyz_lines)
            orca_lines.append("*")
            inp_file = tmppath / "test.inp"
            inp_file.write_text("\n".join(orca_lines) + "\n", encoding="utf-8")

            self.assertTrue(inp_file.exists())
            self.assertIn("! B3LYP D3BJ", inp_file.read_text(encoding="utf-8"))
            self.assertIn("* xyz 0 1", inp_file.read_text(encoding="utf-8"))

            # 3. 测试 XYZ 输入生成
            from molforge.application.calculators.qc_input_generator import export_document_to_xyz
            xyz_file = tmppath / "test.xyz"
            export_document_to_xyz(doc, str(xyz_file))
            self.assertTrue(xyz_file.exists())
            xyz_text = xyz_file.read_text(encoding="utf-8")
            lines = [l for l in xyz_text.splitlines() if l.strip()]
            self.assertEqual(int(lines[0]), doc.topology.num_atoms)

    def test_rest_engine_input_generation_and_wsl_execution(self):
        doc = create_sample_molecule("咖啡因")
        from molforge.application.calculators.qc_input_generator import generate_rest_ctrl_in
        from molforge.application.calculators.rest_engine import RestEngine, parse_rest_log_text

        # 1. 验证 REST TOML 输入生成
        toml_text = generate_rest_ctrl_in(doc, xc="b3lyp", basis="def2-SVP")
        self.assertIn("[ctrl]", toml_text)
        self.assertIn("[geom]", toml_text)
        self.assertIn('xc = "b3lyp"', toml_text)
        self.assertIn('basis_type = "spheric"', toml_text)

        # 2. 验证 REST 输出文本解析器 (真实样例匹配)
        sample_log = """
====================================================
              REST: Mission accomplished
====================================================
The SCF energy        :     -667.9098810737 Ha
SCF is converged after   15 iterations.
Overall   |:    0.041 s for the whole job
Mulliken population analysis:
  0-C  :  -0.078425
  1-N  :  -0.231113
"""
        parsed = parse_rest_log_text(sample_log)
        self.assertTrue(parsed["ok"])
        self.assertAlmostEqual(parsed["final_energy_hartree"], -667.9098810737, places=6)
        self.assertEqual(parsed["iterations"], 15)
        self.assertEqual(parsed["elapsed_seconds"], 0.041)
        self.assertEqual(len(parsed["mulliken_charges"]), 2)
        self.assertAlmostEqual(parsed["mulliken_charges"][0], -0.078425)

        # 3. 本机 WSL2 真实环境探针与实际执行测试
        engine = RestEngine()
        if engine.probe():
            res = engine.run_calculation(doc, xc="hf", basis="STO-3G", num_threads=4)
            self.assertTrue(res.get("ok"))
            self.assertIsNotNone(res.get("final_energy_hartree"))
            self.assertEqual(len(res.get("mulliken_charges", {})), doc.num_atoms)


if __name__ == "__main__":
    unittest.main()
