@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Python environment is missing. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" --version >nul 2>nul
if errorlevel 1 (
    echo Python environment is broken. Run setup.bat to repair it.
    pause
    exit /b 1
)

if not exist "data\library\items.json" (
    echo Local sound library is missing.
    echo Drag a compatible .srz file onto import_library.bat first.
    pause
    exit /b 1
)

echo Starting live sound recognition. Press Ctrl+C in this window to stop.
".venv\Scripts\python.exe" main.py live --overlay
if errorlevel 1 echo Recognition stopped with an error.
pause
