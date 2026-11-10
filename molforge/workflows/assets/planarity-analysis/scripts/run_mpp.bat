@echo off
chcp 65001 >nul
title Multiwfn MPP Planarity Calculator

::==================== 在这里修改你的输入文件名 ====================
if "%~1"=="" (
    echo Usage: run_mpp.bat ^<fchk_file^>
    exit /b 1
)
set "INP_FILE=%~1"
::=================================================================

:: 生成Multiwfn命令流临时文件
(
echo MPP
echo h
echo y
echo.
echo q
) > _mwfn_mpp_inp.txt

echo ==============================================
echo Input file: %INP_FILE%
echo Running Multiwfn MPP calculation (heavy atoms only)
echo Export pqr with d_s (plane-deviation) in charge field
echo ==============================================
"<MULTIWFN_DIR>/Multiwfn.exe" "%INP_FILE%" < _mwfn_mpp_inp.txt

:: 删除临时输入文件
del _mwfn_mpp_inp.txt

echo.
echo ==============================================
echo Finished!
echo Output pqr: %INP_FILE:.fchk=.pqr%
echo You can load this pqr into VMD for d_s coloring.
