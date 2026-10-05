@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.12 from python.org and enable the launcher.
    pause
    exit /b 1
)

py -3.12 --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.12 was not found. Install Python 3.12, then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the local Python environment...
    py -3.12 -m venv .venv
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
