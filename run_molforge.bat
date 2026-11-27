@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0MolForge"
call run_molforge.bat %*
exit /b %ERRORLEVEL%
