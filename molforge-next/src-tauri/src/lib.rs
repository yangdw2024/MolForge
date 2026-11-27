use serde::Serialize;
use std::fs::File;
use std::io::{BufRead, BufReader};
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;

struct BridgeProcess(Mutex<Option<Child>>);

#[derive(Serialize)]
struct FastPdbScanResult {
    atoms: usize,
    cryst1: Option<[f64; 6]>,
    elapsed_ms: f64,
}

#[tauri::command]
fn inspect_pdb_fast(path: String) -> Result<FastPdbScanResult, String> {
    let t0 = Instant::now();
    let file = File::open(&path).map_err(|e| format!("Failed to open {}: {}", path, e))?;
    let mut reader = BufReader::with_capacity(256 * 1024, file);
    let mut line = String::with_capacity(128);
    let mut atoms: usize = 0;
    let mut cryst1: Option<[f64; 6]> = None;

    while reader.read_line(&mut line).map_err(|e| e.to_string())? > 0 {
        if line.starts_with("ATOM  ") || line.starts_with("HETATM") {
            atoms += 1;
        } else if cryst1.is_none() && line.starts_with("CRYST1") && line.len() >= 54 {
            let nums: Vec<f64> = line[6..54]
                .split_whitespace()
                .filter_map(|s| s.parse::<f64>().ok())
                .collect();
            if nums.len() >= 6 {
                cryst1 = Some([nums[0], nums[1], nums[2], nums[3], nums[4], nums[5]]);
            }
        }
        line.clear();
    }

    Ok(FastPdbScanResult {
        atoms,
        cryst1,
        elapsed_ms: t0.elapsed().as_secs_f64() * 1000.0,
    })
}

fn spawn_python_bridge() -> Option<Child> {
    if TcpStream::connect_timeout(&"127.0.0.1:18765".parse().ok()?, Duration::from_millis(120)).is_ok() {
        return None;
    }

    let root = PathBuf::from(r"E:\YDW\Trae_Chemdraw");
    let py = PathBuf::from(r"D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe");
    if !py.is_file() {
        return None;
    }
    let molforge_dir = root.join("MolForge");
    let py_path = format!("{};E:\\YDW\\Trae_Gaussian", molforge_dir.display());
    let mut cmd = Command::new(py);
    cmd.args(["-m", "molforge.server.api_bridge", "--port", "18765"])
        .current_dir(&root)
        .env("PYTHONPATH", py_path)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    cmd.spawn().ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let child = spawn_python_bridge();
    tauri::Builder::default()
        .manage(BridgeProcess(Mutex::new(child)))
        .invoke_handler(tauri::generate_handler![inspect_pdb_fast])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<BridgeProcess>();
                let child_opt = state.0.lock().ok().and_then(|mut g| g.take());
                if let Some(mut proc) = child_opt {
                    let _ = proc.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running MolForge Next desktop application");
}
