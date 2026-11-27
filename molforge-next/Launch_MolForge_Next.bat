@echo off
title MolForge Next (Rust + Tauri 2 + WebGPU)
cd /d E:\YDW\Trae_Chemdraw
echo Starting MolForge Next Desktop Studio...
start "" /b cmd /c "set PYTHONPATH=E:\YDW\Trae_Chemdraw\MolForge;E:\YDW\Trae_Gaussian&& set PYTHONDONTWRITEBYTECODE=1&& D:\YDW\Trae_Gromacs\miniconda3\envs\molforge-webengine\python.exe -m molforge.server.api_bridge --port 18765"
timeout /t 1 /nobreak > nul
start "" "E:\YDW\Trae_Chemdraw\molforge-next\src-tauri\target\release\molforge-next.exe"
