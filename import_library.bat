@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo Drag a compatible SoundRadar .srz library file onto this batch file.
    echo Importing replaces the current item index. Back up data\library first.
    echo Or run: import_library.bat "C:\path\to\library.srz"
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Python environment is missing. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" import_library.py --src "%~1"
if errorlevel 1 (
    echo Import failed. Confirm the file is a compatible .srz library.
    pause
    exit /b 1
)

echo Sound library imported successfully.
pause
