@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not defined MOLFORGE_PYTHON (
    for /d %%A in (D:\*) do (
        for /d %%B in ("%%A\*") do (
            if exist "%%B\miniconda3\envs\molforge-webengine\python.exe" (
                set "MOLFORGE_PYTHON=%%B\miniconda3\envs\molforge-webengine\python.exe"
            )
        )
    )
)

if defined MOLFORGE_PYTHON (
    if exist "%MOLFORGE_PYTHON%" (
        "%MOLFORGE_PYTHON%" scripts\launch.py %*
        exit /b %ERRORLEVEL%
    )
)

python scripts\launch.py %*
exit /b %ERRORLEVEL%
