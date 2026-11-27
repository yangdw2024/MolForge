//! Native external computational chemistry & MD engine probing and execution.
//! All external binaries (ORCA, Gaussian, xTB, Multiwfn, GROMACS, VMD, OpenBabel)
//! are invoked directly from Rust without requiring Python.

use crate::io;
use crate::model::Molecule;
use crate::{CoreError, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineStatus {
    pub id: String,
    pub name: String,
    pub available: bool,
    pub executable_path: Option<String>,
    pub version_hint: String,
    pub sha256: Option<String>,
    pub diagnostic: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EnginePaths {
    pub overrides: HashMap<String, String>,
}

fn find_executable(
    candidates: &[&str],
    env_keys: &[&str],
    fallbacks: &[&str],
    override_path: Option<&str>,
) -> Option<PathBuf> {
    if let Some(ov) = override_path {
        let p = Path::new(ov);
        if p.is_file() {
            return Some(p.to_path_buf());
        }
    }
    for ek in env_keys {
        if let Ok(val) = std::env::var(ek) {
            let p = Path::new(val.trim());
            if p.is_file() {
                return Some(p.to_path_buf());
            }
        }
    }
    let path_var = std::env::var_os("PATH").unwrap_or_default();
    for dir in std::env::split_paths(&path_var) {
        for name in candidates {
            let candidate = dir.join(name);
            if candidate.is_file() {
                return Some(candidate);
            }
            #[cfg(windows)]
            {
                let exe = dir.join(format!("{name}.exe"));
                if exe.is_file() {
                    return Some(exe);
                }
            }
        }
    }
    for fb in fallbacks {
        let p = Path::new(fb);
        if p.is_file() {
            return Some(p.to_path_buf());
        }
    }
    None
}

pub fn probe_all(paths: &EnginePaths, python_exe: Option<&Path>) -> Vec<EngineStatus> {
    let calchem_built = cfg!(feature = "calchem");
    let mut out = vec![
        EngineStatus {
            id: "molforge_core".into(),
            name: "MolForge Rust Core".into(),
            available: true,
            executable_path: std::env::current_exe().ok().map(|p| p.display().to_string()),
            version_hint: env!("CARGO_PKG_VERSION").into(),
            sha256: None,
            diagnostic: "已就绪 · 零 Python 原生分子引擎与 MOLF 二进制流".into(),
        },
        EngineStatus {
            id: "calchem".into(),
            name: "CalChem (纯 Rust 量子化学)".into(),
            available: calchem_built,
            executable_path: None,
            version_hint: "0.3.0".into(),
            sha256: None,
            diagnostic: if calchem_built {
                "已就绪 · CalChem v0.3.0 纯 Rust HF/DFT/Direct-SCF/优化与偶极计算".into()
            } else {
                "未启用 calchem 特性".into()
            },
        },
    ];

    let externals: &[(&str, &str, &[&str], &[&str], &[&str], &str)] = &[
        (
            "orca",
            "ORCA",
            &["orca"],
            &["MOLFORGE_ORCA_PATH"],
            &[r"E:\ORCA\software\ORCA6.1.1\orca.exe", r"D:\ORCA\orca.exe"],
            "从头算 / DFT 量子化学引擎",
        ),
        (
            "gaussian",
            "Gaussian 16 (g16)",
            &["g16", "g09"],
            &["MOLFORGE_GAUSSIAN_PATH", "GAUSS_EXEDIR"],
            &[r"D:\G16W\g16.exe", r"E:\G16W\g16.exe"],
            "Gaussian 电子结构引擎",
        ),
        (
            "xtb",
            "GFN2-xTB (xtb)",
            &["xtb"],
            &["MOLFORGE_XTB_PATH"],
            &[
                r"E:\ORCA\software\ORCA6.1.1\xtb-6.7.1pre\xtb.exe",
                r"D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\Library\bin\xtb.exe",
                r"E:\xtb\bin\xtb.exe",
            ],
            "半经验紧束缚与结构优化",
        ),
        (
            "multiwfn",
            "Multiwfn 3.8",
            &["Multiwfn", "multiwfn"],
            &["MOLFORGE_MULTIWFN_PATH", "Multiwfnpath"],
            &[
                r"D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe",
                r"E:\Multiwfn\Multiwfn.exe",
            ],
            "波函数与实空间电子密度分析",
        ),
        (
            "gromacs",
            "GROMACS (gmx)",
            &["gmx", "gmx_mpi"],
            &["MOLFORGE_GROMACS_PATH", "GMXBIN"],
            &[
                r"D:\YDW\Trae_Gromacs\release_package\GROMACS_GUI_v4.3.0_AVX2_CPU\gromacs\gromacs-2026.1-AVX2-CPU\bin\gmx.exe",
                r"D:\YDW\Trae_Gromacs\gromacs\gromacs-2026.3-AVX512-CUDA-sm120-final2\bin\gmx.exe",
                r"D:\GROMACS\bin\gmx.exe",
                r"E:\GROMACS\bin\gmx.exe",
            ],
            "分子动力学模拟引擎",
        ),
        (
            "vmd",
            "VMD 1.9.4",
            &["vmd"],
            &["MOLFORGE_VMD_PATH"],
            &[r"D:\VMD\vmd.exe", r"E:\VMD\vmd.exe"],
            "轨迹与生物大分子可视化",
        ),
        (
            "openbabel",
            "OpenBabel (obabel)",
            &["obabel"],
            &["MOLFORGE_OBABEL_PATH"],
            &[r"E:\openbabel-install-msvc\bin\obabel.exe", r"D:\openbabel\bin\obabel.exe"],
            "化学格式与构象转换工具",
        ),
    ];

    for &(id, name, bins, env_keys, fallbacks, desc) in externals {
        let ov = paths.overrides.get(id).map(|s| s.as_str());
        let found = find_executable(bins, env_keys, fallbacks, ov);
        let available = found.is_some();
        out.push(EngineStatus {
            id: id.into(),
            name: name.into(),
            available,
            executable_path: found.map(|p| p.display().to_string()),
            version_hint: if available { "detected".into() } else { "missing".into() },
            sha256: None,
            diagnostic: if available {
                format!("已就绪 · {desc}")
            } else {
                format!("未检测到可执行文件 · {desc}")
            },
        });
    }

    out.push(EngineStatus {
        id: "python_worker".into(),
        name: "可选 Python 科学扩展 (RDKit/cclib)".into(),
        available: python_exe.is_some(),
        executable_path: python_exe.map(|p| p.display().to_string()),
        version_hint: if python_exe.is_some() { "optional".into() } else { "disabled".into() },
        sha256: None,
        diagnostic: if python_exe.is_some() {
            "已就绪 · 仅按需用于 SMILES/ETKDG/cclib，核心启动不依赖 Python".into()
        } else {
            "未启用 · MolForge Rust 核心独立运行中".into()
        },
    });

    out
}

pub fn find_engine_path(id: &str, paths: &EnginePaths) -> Option<PathBuf> {
    let lower = id.trim().to_ascii_lowercase();
    let externals: &[(&str, &[&str], &[&str], &[&str])] = &[
        (
            "orca",
            &["orca"],
            &["MOLFORGE_ORCA_PATH"],
            &[r"E:\ORCA\software\ORCA6.1.1\orca.exe", r"D:\ORCA\orca.exe"],
        ),
        (
            "gaussian",
            &["g16", "g09"],
            &["MOLFORGE_GAUSSIAN_PATH", "GAUSS_EXEDIR"],
            &[r"D:\G16W\g16.exe", r"E:\G16W\g16.exe"],
        ),
        (
            "xtb",
            &["xtb"],
            &["MOLFORGE_XTB_PATH"],
            &[
                r"E:\ORCA\software\ORCA6.1.1\xtb-6.7.1pre\xtb.exe",
                r"D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\Library\bin\xtb.exe",
                r"E:\xtb\bin\xtb.exe",
            ],
        ),
        (
            "multiwfn",
            &["Multiwfn", "multiwfn"],
            &["MOLFORGE_MULTIWFN_PATH", "Multiwfnpath"],
            &[
                r"D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe",
                r"E:\Multiwfn\Multiwfn.exe",
            ],
        ),
        (
            "gromacs",
            &["gmx", "gmx_mpi"],
            &["MOLFORGE_GROMACS_PATH", "GMXBIN"],
            &[
                r"D:\YDW\Trae_Gromacs\release_package\GROMACS_GUI_v4.3.0_AVX2_CPU\gromacs\gromacs-2026.1-AVX2-CPU\bin\gmx.exe",
                r"D:\YDW\Trae_Gromacs\gromacs\gromacs-2026.3-AVX512-CUDA-sm120-final2\bin\gmx.exe",
                r"D:\GROMACS\bin\gmx.exe",
                r"E:\GROMACS\bin\gmx.exe",
            ],
        ),
    ];

    for &(eid, cands, envs, fallbacks) in externals {
        if eid == lower {
            let ov = paths.overrides.get(eid).map(|s| s.as_str());
            return find_executable(cands, envs, fallbacks, ov);
        }
    }
    None
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExternalRunOutput {
    pub engine: String,
    pub exit_code: i32,
    pub workdir: String,
    pub stdout: String,
    pub stderr: String,
    pub optimized_xyz: Option<String>,
    /// 从引擎真实 stdout 解析的总能量（Hartree）；解析不到为 None，绝不填 0 冒充。
    pub energy_hartree: Option<f64>,
    /// 几何优化是否收敛（以引擎产物文件为准，如 xtb 的 .xtboptok）。
    pub converged: Option<bool>,
    /// 是否因超时被护栏终止。
    pub timed_out: bool,
}

/// 计算临时工作目录：默认 D 盘（NVMe SSD），可用 MOLFORGE_SCRATCH_DIR 覆盖；
/// 遵守本机磁盘约束——活跃计算/临时文件不落 C 盘。
fn scratch_workdir(tag: &str, doc_id: &str) -> PathBuf {
    let base = std::env::var("MOLFORGE_SCRATCH_DIR")
        .unwrap_or_else(|_| r"D:\YDW\MolForge_Scratch".to_string());
    PathBuf::from(base).join(format!("molforge_{tag}_{doc_id}"))
}

/// 带超时护栏的外部进程执行：超过 secs 秒 kill 并标记 timed_out，绝不假完成。
fn run_with_timeout(mut cmd: Command, secs: u64) -> Result<(std::process::Output, bool)> {
    let mut child = cmd.spawn()?;
    let start = std::time::Instant::now();
    loop {
        match child.try_wait()? {
            Some(_) => return Ok((child.wait_with_output()?, false)),
            None => {
                if start.elapsed().as_secs() > secs {
                    let _ = child.kill();
                    let out = child.wait_with_output()?;
                    return Ok((out, true));
                }
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
        }
    }
}

/// 从 stdout 中按标记行提取最后一个浮点能量值（xtb/ORCA/Gaussian 通用）。
fn parse_last_energy(stdout: &str, markers: &[&str]) -> Option<f64> {
    let mut last = None;
    for line in stdout.lines() {
        let ll = line.to_ascii_lowercase();
        // 标记命中即整行扫数：ORCA property.txt 的数值在标记注释之前，g16/xtb 在之后，整行兼容两者。
        if !markers.iter().any(|m| ll.contains(m)) {
            continue;
        }
        for tok in line.split(|c: char| c.is_whitespace() || c == ':' || c == '|') {
            if let Ok(v) = tok.parse::<f64>() {
                last = Some(v);
                break;
            }
        }
    }
    last
}

pub fn run_xtb_native(
    mol: &Molecule,
    method: &str,
    optimize: bool,
    charge: i32,
    uhf_electrons: u32,
    paths: &EnginePaths,
) -> Result<ExternalRunOutput> {
    let exe = find_executable(
        &["xtb"],
        &["MOLFORGE_XTB_PATH"],
        &[
            r"E:\ORCA\software\ORCA6.1.1\xtb-6.7.1pre\xtb.exe",
            r"D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\Library\bin\xtb.exe",
            r"E:\xtb\bin\xtb.exe",
        ],
        paths.overrides.get("xtb").map(|s| s.as_str()),
    )
    .ok_or_else(|| CoreError::External("xtb executable not found".into()))?;

    let workdir = scratch_workdir("xtb", &mol.document_id);
    std::fs::create_dir_all(&workdir)?;
    let xyz_path = workdir.join("input.xyz");
    std::fs::write(&xyz_path, io::write_xyz(mol))?;

    let mut cmd = Command::new(&exe);
    cmd.current_dir(&workdir)
        .arg("input.xyz")
        .arg("--chrg")
        .arg(charge.to_string())
        .arg("--uhf")
        .arg(uhf_electrons.to_string());
    if method.eq_ignore_ascii_case("gfn1") {
        cmd.arg("--gfn").arg("1");
    } else if method.eq_ignore_ascii_case("gfnff") {
        cmd.arg("--gfnff");
    } else {
        cmd.arg("--gfn").arg("2");
    }
    if optimize {
        cmd.arg("--opt");
    }

    let out = cmd.output()?;
    let opt_path = workdir.join("xtbopt.xyz");
    let optimized_xyz = if opt_path.is_file() {
        std::fs::read_to_string(&opt_path).ok()
    } else {
        None
    };
    let stdout_text = String::from_utf8_lossy(&out.stdout).to_string();
    let energy_hartree = parse_last_energy(&stdout_text, &["total energy"]);
    let converged = if optimize {
        Some(workdir.join(".xtboptok").is_file())
    } else {
        None
    };

    Ok(ExternalRunOutput {
        engine: "xtb".into(),
        exit_code: out.status.code().unwrap_or(-1),
        workdir: workdir.display().to_string(),
        stdout: stdout_text,
        stderr: String::from_utf8_lossy(&out.stderr).to_string(),
        optimized_xyz,
        energy_hartree,
        converged,
        timed_out: false,
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultiwfnRunResult {
    pub ok: bool,
    pub analysis_id: String,
    pub input_file: String,
    pub metrics: serde_json::Value,
    pub plot_x: Vec<f64>,
    pub plot_y: Vec<f64>,
    pub x_label: String,
    pub y_label: String,
    pub message: String,
    pub stdout_tail: String,
}

fn extract_first_f64(s: &str) -> Option<f64> {
    for tok in s.split(|c: char| c.is_whitespace() || c == ':' || c == '(' || c == ')' || c == ',') {
        if let Ok(v) = tok.parse::<f64>() {
            return Some(v);
        }
    }
    None
}

fn extract_after_marker(text: &str, marker: &str) -> Option<f64> {
    let idx = text.find(marker)?;
    extract_first_f64(&text[idx + marker.len()..])
}

fn extract_in_paren_after(text: &str, marker: &str) -> Option<f64> {
    let idx = text.find(marker)?;
    let line = text[idx..].lines().next().unwrap_or("");
    let p_start = line.find('(')?;
    let p_end = line[p_start + 1..].find(')').map(|e| p_start + 1 + e).unwrap_or(line.len());
    // Skip "(sigma^2_tot):" etc. and find the last "(  number unit)" paren pair
    if line[p_start..].contains("a.u.") || line[p_start..].contains("Bohr") || line[p_start..].contains("eV") {
        // Scan from last '(' on the line
        if let Some(last_open) = line.rfind('(') {
            if let Some(v) = extract_first_f64(&line[last_open + 1..]) {
                return Some(v);
            }
        }
    }
    extract_first_f64(&line[p_start + 1..p_end])
}

pub fn run_multiwfn_native(
    mol: &Molecule,
    analysis_id: &str,
    input_file: Option<&str>,
    paths: &EnginePaths,
) -> Result<MultiwfnRunResult> {
    let aid = analysis_id.trim().to_ascii_uppercase();
    let kind = if aid == "WFN-12" || aid == "WFN-NCI" || aid == "NCI" {
        "nci"
    } else if aid == "WFN-01" || aid == "WFN-ESP" || aid == "ESP" {
        "esp"
    } else if aid == "WFN-06" || aid == "WFN-MAYER" || aid == "MAYER" {
        "mayer"
    } else if aid == "WFN-08" || aid == "WFN-ADCH" || aid == "ADCH" {
        "adch"
    } else {
        return Ok(MultiwfnRunResult {
            ok: false,
            analysis_id: analysis_id.to_string(),
            input_file: input_file.unwrap_or("").to_string(),
            metrics: serde_json::json!({ "status": "unavailable" }),
            plot_x: Vec::new(),
            plot_y: Vec::new(),
            x_label: String::new(),
            y_label: String::new(),
            message: format!(
                "Multiwfn 分析项 {analysis_id} 尚未接入真实菜单序列（当前支持 WFN-01 ESP、WFN-06 Mayer、WFN-08 ADCH、WFN-12 NCI/RDG），拒绝返回模拟数据。"
            ),
            stdout_tail: String::new(),
        });
    };

    let exe = find_executable(
        &["Multiwfn", "multiwfn"],
        &["MOLFORGE_MULTIWFN_PATH", "Multiwfnpath"],
        &[
            r"D:\Multiwfn\Multiwfn_3.8_bin_Win64\Multiwfn.exe",
            r"E:\Multiwfn\Multiwfn.exe",
        ],
        paths.overrides.get("multiwfn").map(|s| s.as_str()),
    )
    .ok_or_else(|| CoreError::External("Multiwfn executable not found".into()))?;

    let workdir = scratch_workdir("mwfn", &mol.document_id);
    std::fs::create_dir_all(&workdir)?;

    let raw_input = if let Some(p) = input_file.filter(|s| !s.trim().is_empty()) {
        PathBuf::from(p)
    } else {
        let p = workdir.join("input.xyz");
        std::fs::write(&p, io::write_xyz(mol))?;
        p
    };

    let ext = raw_input
        .extension()
        .map(|e| e.to_string_lossy().to_ascii_lowercase())
        .unwrap_or_default();
    let has_wfn = matches!(
        ext.as_str(),
        "fch" | "fchk" | "wfn" | "wfx" | "molden" | "31f" | "47"
    );

    if kind != "nci" && !has_wfn {
        return Ok(MultiwfnRunResult {
            ok: false,
            analysis_id: analysis_id.to_string(),
            input_file: raw_input.display().to_string(),
            metrics: serde_json::json!({ "status": "wavefunction_required" }),
            plot_x: Vec::new(),
            plot_y: Vec::new(),
            x_label: String::new(),
            y_label: String::new(),
            message: format!(
                "Multiwfn {analysis_id} 需要 .fchk / .wfn / .wfx / .molden 波函数文件（当前仅坐标，拒绝使用模拟数据）。"
            ),
            stdout_tail: String::new(),
        });
    }

    // Windows Fortran Multiwfn fails on non-ASCII paths; copy to ASCII scratch path when needed.
    let target_input = if !raw_input.to_string_lossy().is_ascii() {
        let safe_ext = if ext.is_empty() { "dat" } else { ext.as_str() };
        let dst = workdir.join(format!("mwfn_input.{safe_ext}"));
        std::fs::copy(&raw_input, &dst)?;
        dst
    } else {
        raw_input.clone()
    };

    let commands: String = match kind {
        "nci" => {
            let mode = if has_wfn { "1" } else { "2" };
            format!("20\n{mode}\n1\n2\n0\nq\n")
        }
        "esp" => "12\n0\n-1\n-1\nq\n".into(),
        "mayer" => "9\n1\nn\n0\nq\n".into(),
        "adch" => "7\n11\n1\nn\n0\nq\n".into(),
        _ => unreachable!(),
    };

    if kind == "nci" {
        let _ = std::fs::remove_file(workdir.join("output.txt"));
    }

    let mut cmd = Command::new(&exe);
    cmd.current_dir(&workdir)
        .arg(&target_input)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let mut child = cmd.spawn()?;
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(commands.as_bytes());
    }
    let out = child.wait_with_output()?;
    let stdout_all = String::from_utf8_lossy(&out.stdout).to_string();
    let tail: String = stdout_all
        .lines()
        .rev()
        .take(25)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect::<Vec<_>>()
        .join("\n");

    match kind {
        "nci" => {
            let mode_label = if has_wfn {
                "波函数 NCI/RDG"
            } else {
                "Promolecular NCI/RDG"
            };
            let scatter_path = workdir.join("output.txt");
            let mut xs = Vec::new();
            let mut ys = Vec::new();
            if let Ok(text) = std::fs::read_to_string(&scatter_path) {
                for line in text.lines() {
                    let cols: Vec<&str> = line.split_whitespace().collect();
                    if cols.len() >= 5 {
                        if let (Ok(x), Ok(y)) = (cols[3].parse::<f64>(), cols[4].parse::<f64>()) {
                            xs.push(x);
                            ys.push(y);
                        }
                    }
                }
            }
            let total_points = xs.len();
            let grid_ok = stdout_all.contains("Calculation of grid data");
            let ok = grid_ok && total_points > 0;
            let stride = if total_points > 20000 {
                (total_points as f64 / 20000.0).ceil() as usize
            } else {
                1
            };
            let plot_x: Vec<f64> = xs.iter().step_by(stride).copied().collect();
            let plot_y: Vec<f64> = ys.iter().step_by(stride).copied().collect();
            let wall_s = stdout_all
                .lines()
                .find(|l| l.contains("Calculation of grid data took up wall clock time"))
                .and_then(|l| {
                    l.split_whitespace()
                        .rev()
                        .nth(1)
                        .and_then(|t| t.parse::<f64>().ok())
                })
                .unwrap_or(0.0);

            Ok(MultiwfnRunResult {
                ok,
                analysis_id: analysis_id.to_string(),
                input_file: raw_input.display().to_string(),
                metrics: serde_json::json!({
                    "exit_code": out.status.code().unwrap_or(0),
                    "num_atoms": mol.atoms.len(),
                    "engine": exe.display().to_string(),
                    "mode": mode_label,
                    "total_scatter_points": total_points,
                    "sampled_points": plot_x.len(),
                    "grid_wall_s": wall_s,
                }),
                plot_x,
                plot_y,
                x_label: "sign(λ2)·ρ (a.u.)".into(),
                y_label: "RDG (a.u.)".into(),
                message: if ok {
                    format!(
                        "Multiwfn 实算完成（{mode_label}）：{total_points} 个真实散点，网格耗时 {wall_s:.0} s"
                    )
                } else {
                    "Multiwfn 未产出真实散点数据（output.txt 缺失或为空），拒绝返回模拟数据；详见 stdout_tail".into()
                },
                stdout_tail: tail,
            })
        }
        "esp" => {
            let v_min = extract_after_marker(&stdout_all, "Minimal value:");
            let v_max = extract_after_marker(&stdout_all, "Maximal value:");
            let area_tot = extract_in_paren_after(&stdout_all, "Overall surface area:");
            let area_pos = extract_in_paren_after(&stdout_all, "Positive surface area:");
            let area_neg = extract_in_paren_after(&stdout_all, "Negative surface area:");
            let vol_a3 = extract_in_paren_after(&stdout_all, "Volume:");
            let nu = extract_after_marker(&stdout_all, "Balance of charges (nu):");
            let pi_kcal = extract_in_paren_after(&stdout_all, "Internal charge separation (Pi):");
            let mpi_kcal = extract_in_paren_after(&stdout_all, "Molecular polarity index (MPI):");
            let sigma2_tot_kcal = stdout_all
                .lines()
                .find(|l| l.contains("Overall variance (sigma^2_tot):"))
                .and_then(|l| l.rfind("a.u.^2").and_then(|i| extract_first_f64(&l[i + 6..])));

            let mut extrema_vals = Vec::new();
            let mut in_ext = false;
            for line in stdout_all.lines() {
                let t = line.trim();
                if t.starts_with("The number of surface minima:") || t.starts_with("The number of surface maxima:") {
                    in_ext = true;
                    continue;
                }
                if t.starts_with("=================") {
                    in_ext = false;
                    continue;
                }
                if in_ext {
                    let clean = t.trim_start_matches('*').trim();
                    let cols: Vec<&str> = clean.split_whitespace().collect();
                    if cols.len() >= 7 && cols[0].parse::<usize>().is_ok() {
                        if let Ok(kcal) = cols[3].parse::<f64>() {
                            extrema_vals.push(kcal);
                        }
                    }
                }
            }
            let plot_x: Vec<f64> = (1..=extrema_vals.len()).map(|i| i as f64).collect();
            let ok = v_min.is_some() && v_max.is_some();
            Ok(MultiwfnRunResult {
                ok,
                analysis_id: analysis_id.to_string(),
                input_file: raw_input.display().to_string(),
                metrics: serde_json::json!({
                    "exit_code": out.status.code().unwrap_or(0),
                    "mode": "定量分子表面静电势 (ESP)",
                    "vs_min_kcal": v_min,
                    "vs_max_kcal": v_max,
                    "volume_a3": vol_a3,
                    "overall_area_a2": area_tot,
                    "positive_area_a2": area_pos,
                    "negative_area_a2": area_neg,
                    "sigma2_tot_kcal2": sigma2_tot_kcal,
                    "nu_balance": nu,
                    "pi_kcal": pi_kcal,
                    "mpi_kcal": mpi_kcal,
                    "extrema_count": extrema_vals.len(),
                }),
                plot_x,
                plot_y: extrema_vals,
                x_label: "Surface Extrema Index".into(),
                y_label: "ESP (kcal/mol)".into(),
                message: if ok {
                    format!(
                        "Multiwfn 实算完成（定量 ESP 表面）：Vs,min={:.2} kcal/mol，Vs,max={:.2} kcal/mol，MPI={:.2} kcal/mol",
                        v_min.unwrap_or(0.0),
                        v_max.unwrap_or(0.0),
                        mpi_kcal.unwrap_or(0.0)
                    )
                } else {
                    "Multiwfn ESP 表面未产出完整定量指标，拒绝返回模拟数据；详见 stdout_tail".into()
                },
                stdout_tail: tail,
            })
        }
        "mayer" => {
            let mut orders = Vec::new();
            let mut bonds_desc = Vec::new();
            let mut in_section = false;
            for line in stdout_all.lines() {
                let t = line.trim();
                if t.starts_with("Bond orders with absolute value >=") {
                    in_section = true;
                    continue;
                }
                if in_section {
                    if t.is_empty() || t.starts_with("Total valences") {
                        break;
                    }
                    if t.starts_with('#') {
                        if let Some(val) = t.split_whitespace().last().and_then(|s| s.parse::<f64>().ok()) {
                            orders.push(val);
                            bonds_desc.push(serde_json::json!({ "entry": t, "bond_order": val }));
                        }
                    }
                }
            }
            let ok = !orders.is_empty();
            let max_bo = orders.iter().copied().fold(0.0_f64, f64::max);
            let mean_bo = if ok { orders.iter().sum::<f64>() / orders.len() as f64 } else { 0.0 };
            let plot_x: Vec<f64> = (1..=orders.len()).map(|i| i as f64).collect();
            let n_bonds = plot_x.len();
            Ok(MultiwfnRunResult {
                ok,
                analysis_id: analysis_id.to_string(),
                input_file: raw_input.display().to_string(),
                metrics: serde_json::json!({
                    "exit_code": out.status.code().unwrap_or(0),
                    "mode": "Mayer 键级实算 (9->1)",
                    "bond_count": orders.len(),
                    "max_bond_order": (max_bo * 10000.0).round() / 10000.0,
                    "mean_bond_order": (mean_bo * 10000.0).round() / 10000.0,
                    "top_bonds": bonds_desc.into_iter().take(12).collect::<Vec<_>>(),
                }),
                plot_x,
                plot_y: orders,
                x_label: "Bond Pair Index".into(),
                y_label: "Mayer Bond Order".into(),
                message: if ok {
                    format!(
                        "Multiwfn 实算完成（Mayer 键级）：共 {} 条键，最大键级 {:.4}",
                        n_bonds,
                        max_bo
                    )
                } else {
                    "Multiwfn Mayer 键级未解析到有效数值，拒绝返回模拟数据".into()
                },
                stdout_tail: tail,
            })
        }
        "adch" => {
            let mut charges = Vec::new();
            let mut atom_list = Vec::new();
            let mut in_section = false;
            for line in stdout_all.lines() {
                let t = line.trim();
                if t.starts_with("Final atomic charges:") {
                    in_section = true;
                    continue;
                }
                if in_section {
                    if t.is_empty() || t.starts_with("Calculation took") || t.starts_with("If outputting") {
                        break;
                    }
                    if t.starts_with("Atom") {
                        if let Some(val) = t.split_whitespace().last().and_then(|s| s.parse::<f64>().ok()) {
                            charges.push(val);
                            atom_list.push(serde_json::json!({ "entry": t, "charge": val }));
                        }
                    }
                }
            }
            let ok = !charges.is_empty();
            let min_q = charges.iter().copied().fold(f64::INFINITY, f64::min);
            let max_q = charges.iter().copied().fold(f64::NEG_INFINITY, f64::max);
            let sum_q: f64 = charges.iter().sum();
            let plot_x: Vec<f64> = (1..=charges.len()).map(|i| i as f64).collect();
            let n_atoms_adch = plot_x.len();
            Ok(MultiwfnRunResult {
                ok,
                analysis_id: analysis_id.to_string(),
                input_file: raw_input.display().to_string(),
                metrics: serde_json::json!({
                    "exit_code": out.status.code().unwrap_or(0),
                    "mode": "ADCH 原子偶极校正 Hirshfeld 电荷 (7->11)",
                    "atom_count": charges.len(),
                    "min_charge_e": if ok { Some((min_q * 10000.0).round() / 10000.0) } else { None },
                    "max_charge_e": if ok { Some((max_q * 10000.0).round() / 10000.0) } else { None },
                    "sum_charge_e": (sum_q * 100000.0).round() / 100000.0,
                    "atom_charges": atom_list.into_iter().take(24).collect::<Vec<_>>(),
                }),
                plot_x,
                plot_y: charges,
                x_label: "Atom Index".into(),
                y_label: "ADCH Charge (e)".into(),
                message: if ok {
                    format!(
                        "Multiwfn 实算完成（ADCH 电荷）：{} 原子，区间 [{:.4}, {:.4}] e",
                        n_atoms_adch,
                        min_q,
                        max_q
                    )
                } else {
                    "Multiwfn ADCH 电荷未解析到有效数值，拒绝返回模拟数据".into()
                },
                stdout_tail: tail,
            })
        }
        _ => unreachable!(),
    }
}

/// 真实外部量化引擎执行（ORCA / Gaussian / xTB），带超时护栏与能量解析。
/// 绝不返回假 completed：引擎缺失返回 Err，超时标记 timed_out，失败保留真实 exit_code。
pub fn run_external_native(
    mol: &Molecule,
    engine: &str,
    keywords: &str,
    method: &str,
    basis: &str,
    optimize: bool,
    workdir_override: Option<&str>,
    paths: &EnginePaths,
) -> Result<ExternalRunOutput> {
    let engine = engine.trim().to_ascii_lowercase();
    if engine == "xtb" {
        let (charge, mult, _) = crate::summary::resolve_spin_state(mol);
        return run_xtb_native(mol, method, optimize, charge, mult.saturating_sub(1), paths);
    }
    let exe = find_engine_path(&engine, paths).ok_or_else(|| {
        CoreError::External(format!(
            "未在系统路径中检测到可执行的 {engine} 引擎。请在“偏好设置”中指定引擎路径，或改用内置引擎。"
        ))
    })?;
    let (charge, mult, _) = crate::summary::resolve_spin_state(mol);
    let workdir = match workdir_override.filter(|s| !s.trim().is_empty()) {
        Some(w) => PathBuf::from(w),
        None => scratch_workdir(&engine, &mol.document_id),
    };
    std::fs::create_dir_all(&workdir)?;

    let (input_name, content, energy_markers): (&str, String, &[&str]) = match engine.as_str() {
        "orca" => {
            let body = if keywords.trim().is_empty() {
                io::write_orca_inp(mol, method, basis, charge, mult, optimize)
            } else {
                let mut s = format!("{}\n", keywords.trim());
                s.push_str(&format!("* xyz {charge} {mult}\n"));
                for a in &mol.atoms {
                    s.push_str(&format!(
                        "{} {:.6} {:.6} {:.6}\n",
                        crate::elements::symbol_of(a.z),
                        a.pos[0],
                        a.pos[1],
                        a.pos[2]
                    ));
                }
                s.push_str("*\n");
                s
            };
            ("input.inp", body, &["final single point energy"])
        }
        "gaussian" => {
            let body = if keywords.trim().is_empty() {
                io::write_gjf(mol, method, basis, charge, mult, optimize)
            } else {
                let mut s = format!("%nprocshared=4\n%mem=2GB\n{}\n\n{}\n\n{charge} {mult}\n", keywords.trim(), mol.name);
                for a in &mol.atoms {
                    s.push_str(&format!(
                        "{} {:.6} {:.6} {:.6}\n",
                        crate::elements::symbol_of(a.z),
                        a.pos[0],
                        a.pos[1],
                        a.pos[2]
                    ));
                }
                s.push('\n');
                s
            };
            ("input.gjf", body, &["scf done:"])
        }
        other => {
            return Err(CoreError::External(format!(
                "engine '{other}' 不支持外部实算（支持 orca / gaussian / xtb）"
            )))
        }
    };
    std::fs::write(workdir.join(input_name), &content)?;
    let mut cmd = Command::new(&exe);
    cmd.current_dir(&workdir).arg(input_name);
    let (out, timed_out) = run_with_timeout(cmd, 600)?;
    let stdout_text = String::from_utf8_lossy(&out.stdout).to_string();
    // ORCA/g16 在 Windows 下把主输出写进工作目录文件（input.out / input.log），stdout 可能为空；
    // 能量与日志尾必须从 stdout + 产物文件合并解析，绝不因 stdout 空而报"无能量"。
    let mut combined = stdout_text.clone();
    if let Ok(rd) = std::fs::read_dir(&workdir) {
        let mut logs: Vec<PathBuf> = rd
            .filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| {
                p.extension()
                    .map(|e| matches!(e.to_string_lossy().to_ascii_lowercase().as_str(), "out" | "log" | "txt"))
                    .unwrap_or(false)
            })
            .collect();
        logs.sort();
        for p in logs.iter().take(4) {
            if let Ok(t) = std::fs::read_to_string(p) {
                combined.push('\n');
                combined.push_str(&t);
                if combined.len() > 8_000_000 {
                    break;
                }
            }
        }
    }
    let energy_hartree = parse_last_energy(&combined, energy_markers);
    // ORCA 优化成功会写 input.xyz（优化后几何）；回收为真产物，不伪造。
    let optimized_xyz = if optimize {
        std::fs::read_to_string(workdir.join("input.xyz")).ok()
    } else {
        None
    };
    let converged = if optimize {
        let lc = combined.to_ascii_lowercase();
        Some(
            optimized_xyz.is_some()
                || lc.contains("the optimization has converged")
                || lc.contains("optimization completed")
                || lc.contains("stationary point found"),
        )
    } else {
        None
    };
    Ok(ExternalRunOutput {
        engine: engine.clone(),
        exit_code: out.status.code().unwrap_or(-1),
        workdir: workdir.display().to_string(),
        stdout: combined,
        stderr: String::from_utf8_lossy(&out.stderr).to_string(),
        optimized_xyz,
        energy_hartree,
        converged,
        timed_out,
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RdfResult {
    pub r_angstrom: Vec<f64>,
    pub g_r: Vec<f64>,
    pub n_r: Vec<f64>,
    pub first_peak_r_angstrom: f64,
    pub first_peak_g_r: f64,
    pub num_atoms: usize,
    pub num_pairs: usize,
    pub volume_a3: f64,
    pub mode: String,
}

/// Pure-Rust pairwise Radial Distribution Function g(r) and running coordination integral N(r).
/// Mirrors `MolForge/molforge/workflows/md_rdf_analysis.py` without requiring Python.
pub fn compute_pairwise_rdf(mol: &Molecule, r_max: f64, n_bins: usize) -> Result<RdfResult> {
    let n = mol.atoms.len();
    if n < 2 {
        return Err(CoreError::InvalidOp(
            "RDF 径向分布函数至少需要 2 个原子".into(),
        ));
    }
    let bins = n_bins.clamp(10, 500);
    let r_min = 0.5_f64;
    let r_hi = r_max.max(2.0);
    let dr = (r_hi - r_min) / bins as f64;
    let mut counts = vec![0usize; bins];

    let mut min_c = [f64::INFINITY; 3];
    let mut max_c = [f64::NEG_INFINITY; 3];
    for a in &mol.atoms {
        for q in 0..3 {
            min_c[q] = min_c[q].min(a.pos[q]);
            max_c[q] = max_c[q].max(a.pos[q]);
        }
    }

    let mut num_pairs = 0usize;
    for i in 0..n {
        let pi = mol.atoms[i].pos;
        for j in (i + 1)..n {
            let pj = mol.atoms[j].pos;
            let dx = pi[0] - pj[0];
            let dy = pi[1] - pj[1];
            let dz = pi[2] - pj[2];
            let d = (dx * dx + dy * dy + dz * dz).sqrt();
            num_pairs += 1;
            if d >= r_min && d < r_hi {
                let b = (((d - r_min) / dr).floor() as usize).min(bins - 1);
                counts[b] += 1;
            }
        }
    }

    let (vol, mode) = if let Some(m) = mol.cell.as_ref().and_then(|c| c.matrix()) {
        let a = m[0];
        let b = m[1];
        let c = m[2];
        let cross = [
            b[1] * c[2] - b[2] * c[1],
            b[2] * c[0] - b[0] * c[2],
            b[0] * c[1] - b[1] * c[0],
        ];
        let v = (a[0] * cross[0] + a[1] * cross[1] + a[2] * cross[2]).abs();
        (v.max(50.0), "periodic_cell".to_string())
    } else {
        let dx = (max_c[0] - min_c[0]) + 4.0;
        let dy = (max_c[1] - min_c[1]) + 4.0;
        let dz = (max_c[2] - min_c[2]) + 4.0;
        ((dx * dy * dz).max(50.0), "molecular_envelope".to_string())
    };

    let rho_pair = ((num_pairs as f64) / vol).max(1e-6);
    let mut r_angstrom = Vec::with_capacity(bins);
    let mut g_r = Vec::with_capacity(bins);
    let mut n_r = Vec::with_capacity(bins);
    let mut cum_pairs = 0usize;
    let mut peak_idx = 0usize;
    let mut peak_val = -1.0_f64;

    for i in 0..bins {
        let r0 = r_min + (i as f64) * dr;
        let r1 = r0 + dr;
        let r_mid = 0.5 * (r0 + r1);
        let shell_vol = (4.0 / 3.0) * std::f64::consts::PI * (r1.powi(3) - r0.powi(3));
        let g = (counts[i] as f64) / (shell_vol * rho_pair + 1e-12);
        cum_pairs += counts[i];
        let coord = (2.0 * cum_pairs as f64) / (n as f64);
        if g > peak_val {
            peak_val = g;
            peak_idx = i;
        }
        r_angstrom.push((r_mid * 10000.0).round() / 10000.0);
        g_r.push((g * 100000.0).round() / 100000.0);
        n_r.push((coord * 10000.0).round() / 10000.0);
    }

    Ok(RdfResult {
        first_peak_r_angstrom: r_angstrom.get(peak_idx).copied().unwrap_or(0.0),
        first_peak_g_r: g_r.get(peak_idx).copied().unwrap_or(0.0),
        r_angstrom,
        g_r,
        n_r,
        num_atoms: n,
        num_pairs,
        volume_a3: (vol * 100.0).round() / 100.0,
        mode,
    })
}

pub fn generate_gromacs_mdp(ensemble: &str, nsteps: u64, dt: f64, temp_k: f64) -> String {
    let tcoupl = if ensemble.eq_ignore_ascii_case("nve") {
        "no"
    } else {
        "V-rescale"
    };
    let pcoupl = if ensemble.eq_ignore_ascii_case("npt") {
        "C-rescale"
    } else {
        "no"
    };
    format!(
        "; MolForge Studio GROMACS .mdp ({ensemble})\n\
         integrator  = md\n\
         dt          = {dt}\n\
         nsteps      = {nsteps}\n\
         nstxout-compressed = 500\n\
         nstenergy   = 500\n\
         nstlog      = 500\n\
         cutoff-scheme = Verlet\n\
         coulombtype = PME\n\
         rcoulomb    = 1.0\n\
         rvdw        = 1.0\n\
         tcoupl      = {tcoupl}\n\
         tc-grps     = System\n\
         tau_t       = 0.1\n\
         ref_t       = {temp_k}\n\
         pcoupl      = {pcoupl}\n\
         tau_p       = 2.0\n\
         ref_p       = 1.0\n\
         compressibility = 4.5e-5\n"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn caffeine_rdf_has_bond_length_first_peak() {
        let mol = crate::presets::build_preset("caffeine").unwrap();
        let res = compute_pairwise_rdf(&mol, 12.0, 80).unwrap();
        assert_eq!(res.r_angstrom.len(), 80);
        assert!(res.first_peak_r_angstrom >= 0.9 && res.first_peak_r_angstrom <= 1.7);
        assert!(res.first_peak_g_r > 0.0);
    }
}
