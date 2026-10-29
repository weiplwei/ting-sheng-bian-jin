@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.12 from python.org and enable the launcher.
    pause
    exit /b 1
)

set "PYTHON_LAUNCHER=py -3.12"
%PYTHON_LAUNCHER% --version >nul 2>nul
if errorlevel 1 (
    set "PYTHON_LAUNCHER=py -3.13"
    !PYTHON_LAUNCHER! --version >nul 2>nul
    if errorlevel 1 (
        echo Python 3.12 or 3.13 was not found. Install either version, then run this file again.
        pause
        exit /b 1
    )
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>nul
    if errorlevel 1 (
        echo Repairing the existing Python environment...
        !PYTHON_LAUNCHER! -m venv --clear .venv
        if errorlevel 1 goto failed
    )
) else (
    echo Creating the local Python environment...
    !PYTHON_LAUNCHER! -m venv .venv
    if errorlevel 1 goto failed
)

echo Installing required packages...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed

echo.
echo Setup is complete. The bundled default sound library is ready.
echo Double-click start_live.bat to begin.
pause
exit /b 0

:failed
echo Setup failed. Check your internet connection and Python installation, then try again.
pause
exit /b 1
