"""
MolForge v7.4.2 官方工业级交付与发布自动化构建器 (build_delivery_v7_4.py)
========================================================================
功能：
  1. 全量自动化运行科学算法、核心不变量及数据映射测试门禁 (Gate 1 - Gate 4)
  2. 收集 MolForge 完整源码、静态资源、技能包与测试套件（排除一切缓存与临时数据）
  3. 计算每一个文件的 SHA-256 哈希指纹并构建 release_manifest.json
  4. 生成带数字校验的标准化交付压缩包 (MolForge_v7.4.0_delivery_20261106.zip)
  5. 严密执行 zip 完整性检验与回读 hash 匹配断言
  6. 输出结构化交付报告 delivery_report.json
"""
from __future__ import annotations

import os
import sys
import json
import time
import zipfile
import hashlib
import platform
import subprocess
import re
from pathlib import Path

# 保护 Windows Python 3.13 下 platform / numpy.testing 的 WMI COM 崩溃
if sys.platform == "win32":
    try:
        _wv = sys.getwindowsversion()
        def _safe_wmi(table=None, *fields, **kw):
            if table == 'CPU':
                return (os.environ.get('PROCESSOR_ARCHITECTURE', ''), os.environ.get('PROCESSOR_IDENTIFIER', 'Unknown CPU'))
            return (f"{_wv.major}.{_wv.minor}.{_wv.build}", 1, 'Multiprocessor Free', 0, 0)
        platform._wmi_query = _safe_wmi
    except Exception:
        pass

# 强制 UTF-8 标准输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 路径常量定义
WORKSPACE = Path(r"E:\YDW\Trae_Chemdraw")
MOLFORGE_DIR = WORKSPACE / "MolForge"
SKILL_DIR = WORKSPACE / ".agents" / "skills" / "molforge-maintenance"

TEMP_DIR = WORKSPACE / "_build_tmp" / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DELIVERY_ZIP_PATH = WORKSPACE / "MolForge_v7.4.2_delivery.zip"
REPORT_PATH = WORKSPACE / "delivery_report_v7_4.json"
MANIFEST_PATH = WORKSPACE / "delivery_manifest_v7_4.json"

PYTHON_EXE = sys.executable


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run_gate_checks() -> dict[str, any]:
    """运行回归门禁，并要求每项提供真实的执行数量或完成标记。"""
    print("=" * 70)
    print(">>> 正在执行 MolForge v7.4.2 回归验收门禁...")
    print("=" * 70)

    env = os.environ.copy()
    env["TEMP"] = str(TEMP_DIR)
    env["TMP"] = str(TEMP_DIR)
    env["MOLFORGE_DATA_DIR"] = str(WORKSPACE / "_build_tmp" / "user_data")
    env["PYTHONPATH"] = f"{MOLFORGE_DIR};E:\\YDW\\Trae_Gaussian"
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"

    tests = [
        ("Invariant & CommandBus Integrity", ["scripts/check_invariants.py"], "marker", r"结果：([1-9]\d*) 通过, 0 失败"),
        ("Trajectory Kabsch & Welford RMSF", ["tests/test_trajectory_analysis.py"], "unittest", None),
        ("Multiwfn QTAIM & Mayer Driver (sample parsing)", ["tests/test_multiwfn_driver.py"], "unittest", None),
        ("Document Session Multi-View", ["tests/test_document_session_multi_view.py"], "unittest", None),
        ("Fragment Transactions", ["tests/test_fragment_transactions.py"], "unittest", None),
        ("Gaussian Job Spec Generator", ["tests/test_gaussian_job_spec.py"], "unittest", None),
        ("Internal Coordinate Commands", ["tests/test_internal_coordinate_commands.py"], "unittest", None),
        ("Measurement Target Resolution", ["tests/test_measurement_target_resolution.py"], "unittest", None),
        ("Gaussian 16 Geometry & Dihedral Benchmark", ["tests/test_gaussian_geometry_benchmark.py"], "unittest", None),
        ("2D-3D Bidirectional Sync & Projection", ["tests/test_bidirectional_2d3d_sync.py"], "unittest", None),
        ("Linux HPC Remote Execution & Squeue (mock runner)", ["tests/test_hpc_remote_execution.py"], "unittest", None),
        ("Model Context Protocol (MCP) Server & Bridge", ["tests/test_mcp_server_protocol.py"], "unittest", None),
        ("LLM Unified Config & In-Place Chat Sync", ["tests/test_llm_config_sync.py"], "unittest", None),
        ("UI Typography, Custom Fragments & Timeline", ["tests/test_ui_enhancements_v7_4.py"], "marker", r"All UI enhancements tests passed successfully!"),
        ("Massive System Data Structures (not main-GUI certification)", ["tests/test_massive_system_architecture.py"], "marker", r"All massive system architecture tests passed successfully!"),
        ("Scientific Summary Counterexamples", ["tests/test_scientific_summary.py"], "unittest", None),
        ("Periodic Cell & CRYST1 Roundtrip", ["tests/test_periodic.py"], "unittest", None),
        ("Repair Regressions", ["tests/test_repair_regressions.py"], "unittest", None),
        ("Responsive Layout Geometry (offscreen)", ["tests/test_typography_responsive.py"], "unittest", None),
        ("Native Qt Logic (offscreen, not mouse acceptance)", ["tests/test_win10_native_gui.py"], "unittest", None),
        ("Desktop MCP Current Document (real stdio subprocess)", ["tests/test_desktop_mcp.py"], "unittest", None),
        ("Workflow Bundle & Resource Defaults", ["tests/test_v4_true_style_and_storage.py"], "unittest", None),
        ("v7.5 Regression Candidates", ["tests/test_bugfixes_v7_5.py"], "unittest", None),
    ]

    results = []
    for name, args, kind, marker in tests:
        start = time.time()
        command_args = [*args, "-v"] if kind == "unittest" else args
        res = subprocess.run(
            [PYTHON_EXE] + command_args,
            cwd=str(MOLFORGE_DIR), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
        elapsed = round(time.time() - start, 3)
        output = (res.stdout or "") + "\n" + (res.stderr or "")
        test_count = None
        evidence_error = ""
        if res.returncode == 0 and kind == "unittest":
            match = re.search(r"Ran (\d+) tests?", output)
            if not match or int(match.group(1)) < 1:
                evidence_error = "no positive unittest execution count"
            else:
                test_count = int(match.group(1))
        elif res.returncode == 0 and kind == "marker":
            match = re.search(marker, output)
            if not match:
                evidence_error = f"completion marker missing: {marker}"
            elif match.groups():
                test_count = int(match.group(1))
        passed = res.returncode == 0 and not evidence_error
        print(f"[{'PASS [OK]' if passed else 'FAIL [X]'}] {name} ({elapsed}s; tests={test_count if test_count is not None else 'completion-marker'})")
        results.append({
            "name": name,
            "command": " ".join(command_args),
            "passed": passed,
            "exit_code": res.returncode,
            "test_count": test_count,
            "evidence_kind": kind,
            "evidence_error": evidence_error,
            "elapsed_seconds": elapsed,
            "stdout_tail": res.stdout.strip().splitlines()[-3:] if res.stdout else [],
            "stderr_tail": res.stderr.strip().splitlines()[-3:] if res.stderr else [],
        })
        if not passed:
            print(f"       ERROR: {evidence_error or res.stderr.strip()[:500]}")
            raise RuntimeError(f"Gate check '{name}' failed; delivery aborted: {evidence_error or res.returncode}")

    return {"all_passed": True, "test_results": results}


def collect_package_files() -> dict[str, Path]:
    """收集所有需要纳入交付包的源码、配置与资源文件。"""
    files: dict[str, Path] = {}

    exclude_dirs = {
        "__pycache__",
        "user_data",
        ".pytest_cache",
        ".git",
        ".idea",
        ".vscode",
        "build",
        "dist",
        "_build_tmp",
        "release_assets",
        "qa_evidence",
        ".system_generated",
    }
    exclude_exts = {".pyc", ".pyo", ".pyd_old", ".tmp", ".log", ".zip", ".whl", ".tar", ".gz"}

    # 1. 收集 MolForge 目录
    for root, dirs, filenames in os.walk(MOLFORGE_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith("backup_") and not d.startswith("_audit")]
        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext in exclude_exts or f.endswith("~"):
                continue
            full_p = Path(root) / f
            rel_p = full_p.relative_to(MOLFORGE_DIR)
            arc_name = f"MolForge/{rel_p.as_posix()}"
            files[arc_name] = full_p

    # 2. 收集 .agents 技能目录
    if SKILL_DIR.exists():
        for root, dirs, filenames in os.walk(SKILL_DIR):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in filenames:
                ext = Path(f).suffix.lower()
                if ext in exclude_exts:
                    continue
                full_p = Path(root) / f
                rel_p = full_p.relative_to(WORKSPACE)
                arc_name = rel_p.as_posix()
                files[arc_name] = full_p

    return files


def build_delivery():
    # 第一步：运行门禁测试
    gate_summary = run_gate_checks()
    if not gate_summary["all_passed"]:
        failed_tests = [r["name"] for r in gate_summary["test_results"] if not r["passed"]]
        raise RuntimeError(f"门禁自动化测试未全部通过，构建已终止！失败项目: {failed_tests}")

    # 第二步：收集文件清单与哈希
    print("\n" + "=" * 70)
    print(">>> 正在扫描并计算文件 SHA-256 哈希指纹...")
    files = collect_package_files()
    print(f"    共收集到 {len(files)} 个交付文件。")

    manifest = {}
    total_bytes = 0
    for arc_name, file_path in sorted(files.items()):
        f_hash = compute_sha256(file_path)
        manifest[arc_name] = f_hash
        total_bytes += file_path.stat().st_size

    # 保存 release_manifest.json
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"    哈希清单已写入: {MANIFEST_PATH}")

    # 第三步：打包 Zip
    print("\n" + "=" * 70)
    print(f">>> 正在打包压缩交付件: {DELIVERY_ZIP_PATH} ...")
    with zipfile.ZipFile(DELIVERY_ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for arc_name, file_path in sorted(files.items()):
            z.write(file_path, arc_name)
        # 将清单文件也打入根目录
        z.write(MANIFEST_PATH, "release_manifest.json")

    # 第四步：严格完整性与 SHA-256 回读校验
    print("\n" + "=" * 70)
    print(">>> 正在执行交付压缩包完整性与 SHA-256 回读校验...")
    with zipfile.ZipFile(DELIVERY_ZIP_PATH, "r") as z:
        crc_error = z.testzip()
        if crc_error is not None:
            raise RuntimeError(f"Zip 文件 CRC 校验失败: {crc_error}")
        print("    [OK] Zip 结构 CRC 校验 100% 通过 (CRC Error: None)")

        # 校验每个文件的哈希
        for arc_name, expected_hash in manifest.items():
            actual_hash = hashlib.sha256(z.read(arc_name)).hexdigest()
            if actual_hash != expected_hash:
                raise RuntimeError(f"文件哈希不匹配: {arc_name}")
        print(f"    [OK] 全量 {len(manifest)} 个文件 SHA-256 哈希指纹 100% 匹配断言通过！")

    zip_size_mb = round(DELIVERY_ZIP_PATH.stat().st_size / (1024 * 1024), 2)
    zip_sha256 = compute_sha256(DELIVERY_ZIP_PATH)

    acceptance_path = MOLFORGE_DIR / "docs" / "repair_20261116" / "acceptance_summary.json"
    acceptance = {}
    if acceptance_path.is_file():
        acceptance = json.loads(acceptance_path.read_text(encoding="utf-8"))
    external_gates = {
        "native_gui_acceptance": "NOT_TESTED",
        "real_external_engines": "NOT_TESTED",
        "clean_environment_install": "NOT_TESTED",
    }
    external_gates.update(acceptance.get("gates", {}))

    # 第五步：生成最终交付报告
    report = {
        "product": "MolForge",
        "version": "7.4.2",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "platform": platform.platform(),
        "python_executable": str(PYTHON_EXE),
        "delivery_zip": {
            "path": str(DELIVERY_ZIP_PATH),
            "size_mb": zip_size_mb,
            "bytes": DELIVERY_ZIP_PATH.stat().st_size,
            "sha256": zip_sha256,
            "file_count": len(files) + 1,
        },
        "gates": {
            "regression_suite": "PASS",
            **external_gates,
            "delivery_packaging_integrity": "PASS",
        },
        "evidence_scope": {
            "mock_or_sample_tests": ["Linux HPC remote runner", "Multiwfn sample-output parsing"],
            "external_acceptance_not_rerun_by_builder": True,
            "not_certified": acceptance.get("not_certified", [
                "native mouse/screen interaction",
                "real Gaussian/Multiwfn/GROMACS/HPC/LLM execution",
                "100M-atom main-GUI rendering or 60 FPS",
            ]),
        },
        "acceptance_evidence": acceptance,
        "gate_tests": gate_summary,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n交付总结报告已落盘: {REPORT_PATH}")
    print("=" * 70)
    print(f"🎉 MolForge v7.4.2 交付构建成功！")
    print(f"   交付文件: {DELIVERY_ZIP_PATH}")
    print(f"   大小: {zip_size_mb} MB")
    print(f"   SHA-256: {zip_sha256}")
    print("=" * 70)


if __name__ == "__main__":
    build_delivery()
