@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ======================================================================
echo  MolForge v7.4.0 绿色便携独立版打包构建程序
echo ======================================================================

set "BUILD_TMP=E:\temp\pyinstaller_build"
if not exist "%BUILD_TMP%" mkdir "%BUILD_TMP%"
set "TEMP=%BUILD_TMP%"
set "TMP=%BUILD_TMP%"

REM 优先选择安装了 PyInstaller 的 Python 解释器
if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PY_EXE=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
) else (
    set "PY_EXE=python"
)

echo [*] 正在使用 %PY_EXE% 启动 PyInstaller 构建...
"%PY_EXE%" -m PyInstaller --noconfirm --clean --workpath "E:\temp\pyinstaller_work" --distpath "%~dp0dist" "%~dp0molforge_standalone.spec"

if %ERRORLEVEL% equ 0 (
    echo ======================================================================
    echo [OK] 打包完成！便携可执行文件位于:
    echo      %~dp0dist\MolForge\MolForge.exe
    echo ======================================================================
) else (
    echo [ERROR] PyInstaller 构建失败，退出码: %ERRORLEVEL%
)

pause
