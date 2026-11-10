# MolForge v7.2 quick start

1. Unzip `MolForge` to the workstation's project drive.
2. Launch `run_molforge.bat`. The launcher uses the configured `D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe` first.
3. Configure Multiwfn and VMD in **结果 → 外部科学引擎与依赖状态管理** before running ESP/HOMO orbitals. The executable path should point to the `.exe`, not just the folder.
4. Select **结果 → ESP 表面分析** and a Gaussian `.fchk`, or select the OSC/HOMO workflow and its `.fchk` plus matching `.log` files. Results are written to a new `MolForge_Results` folder beside the selected input; existing files are not overwritten.
5. Install optional XLSX/PPTX and MD support into the existing MolForge Python environment, not a system Python:

```bat
D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe -m pip install -r requirements-workflows.txt
```

The MD workflow needs a topology and trajectory with matching atom order. Unwrap periodic boundaries first where needed. It reports RMSD/Rg, attempts hydrogen-bond occupancy when topology permits, and clusters on the RMSD/Rg features.

Gaussian calculations are not launched by these workflows. Each external Multiwfn call runs serially. Check `*_last.log`, `multiwfn_esp.log`, and the result status files when an external tool is unavailable or exits early.
