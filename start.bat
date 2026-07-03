@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0scripts\start_lab.py" %*
) else (
    py -3 "%~dp0scripts\start_lab.py" %*
)
endlocal
