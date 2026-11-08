@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   Media Controller - Setup
echo ============================================
echo.

:: --- 1. Locate Python ---
echo [1/3] Locating Python...

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python313\python.exe"

if not exist "!PYTHON_EXE!" (
    echo [ERROR] Python not found at: !PYTHON_EXE!
    echo Install Python 3.13 from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Found Python: !PYTHON_EXE!

:: --- 2. Install libraries ---
echo.
echo [2/3] Installing dependencies...

"!PYTHON_EXE!" -m pip install -r "%~dp0requirements.txt"
if !errorlevel! neq 0 (
    echo.
    echo [ERROR] Failed to install libraries.
    pause
    exit /b 1
)
echo Libraries installed successfully.

"!PYTHON_EXE!" -c "import serial, pycaw, keyboard" >nul 2>nul
if !errorlevel! neq 0 (
    echo [ERROR] Libraries not visible for this Python.
    pause
    exit /b 1
)
echo Libraries verified.

:: --- 3. Install sign-in and wake task ---
echo.
echo [3/3] Setting up automatic startup and wake recovery...

"!PYTHON_EXE!" "%~dp0install_autostart.py"
if !errorlevel! neq 0 (
    echo [ERROR] Failed to install the scheduled task.
    echo Run setup.bat as Administrator under your normal Windows account.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ALL DONE!
echo   - Controller starts automatically after Windows sign-in
echo   - Controller restarts automatically after sleep
echo   - Keep the installed files in this directory
echo ============================================
pause
