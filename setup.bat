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

"!PYTHON_EXE!" -m pip install pyserial pycaw comtypes keyboard
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

:: --- 3. Create wake task ---
echo.
echo [3/3] Setting up wake task...

set "SCRIPT_DIR=%~dp0"
set "PYTHONW_PATH=!PYTHON_EXE:python.exe=pythonw.exe!"

if not exist "!PYTHONW_PATH!" (
    echo [ERROR] pythonw.exe not found at: !PYTHONW_PATH!
    pause
    exit /b 1
)

echo Found pythonw: !PYTHONW_PATH!
echo Working dir: %SCRIPT_DIR%

:: Remove old task if it exists
schtasks /Delete /TN "MediaControllerWake" /F >nul 2>nul

:: Create wake task with correct provider name
echo.
echo Creating wake task...
schtasks /Create ^
  /TN "MediaControllerWake" ^
  /TR "\"!PYTHONW_PATH!\" \"%SCRIPT_DIR%controller_v2.py\"" ^
  /SC ONEVENT ^
  /EC System ^
  /MO "*[System[Provider[@Name='Microsoft-Windows-Power-Troubleshooter'] and (EventID=1)]]" ^
  /F ^
  /RL HIGHEST ^
  /IT

set WAKE_RESULT=!errorlevel!

if !WAKE_RESULT! neq 0 (
    echo [ERROR] Failed to create wake task.
    echo Run this script as Administrator.
) else (
    echo Wake task created successfully.
)

:: Summary
echo.
echo ============================================
if !WAKE_RESULT! equ 0 (
    echo   ALL DONE!
    echo   - Controller will restart after sleep
) else (
    echo   FAILED
    echo   - Wake task NOT created
    echo.
    echo   Run setup.bat as Administrator.
)
echo ============================================
pause