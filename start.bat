@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if not errorlevel 1 (
    python "%~dp0start.py" %*
) else (
    py -3 "%~dp0start.py" %*
)
endlocal
