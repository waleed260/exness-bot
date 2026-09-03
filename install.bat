@echo off
REM ==========================================================
REM  exness-bot - one-time installer (Windows 7 / 10 / 11)
REM  Just double-click this file.
REM ==========================================================
cd /d "%~dp0"
title exness-bot installer

echo.
echo ==========================================================
echo   exness-bot installer
echo ==========================================================
echo.

where python >nul 2>nul
if errorlevel 1 goto NOPY

python --version
echo.
echo Installing the packages the bot needs (this can take a few minutes)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto PIPFAIL

if not exist "exness_bot\settings.py" (
    copy "exness_bot\settings.example.py" "exness_bot\settings.py" >nul
    echo.
    echo ----------------------------------------------------------
    echo  A settings file was created and will now open in Notepad.
    echo  Fill in your Exness MT5 login number, password and server
    echo  (demo account details), then SAVE and close Notepad.
    echo ----------------------------------------------------------
    echo.
    pause
    notepad "exness_bot\settings.py"
)

echo.
echo ==========================================================
echo   Done. Next step: double-click  run.bat
echo ==========================================================
pause
exit /b 0

:NOPY
echo [ERROR] Python is not installed (or not on PATH).
echo.
echo   Windows 7      : install Python 3.8.10
echo                    https://www.python.org/downloads/release/python-3810/
echo   Windows 10/11  : install the latest Python 3
echo                    https://www.python.org/downloads/
echo.
echo   IMPORTANT: during setup, tick "Add Python to PATH".
echo   Then run this installer again.
pause
exit /b 1

:PIPFAIL
echo.
echo [ERROR] Package installation failed - read the messages above.
echo   Common cause on Windows 7: Python newer than 3.8 (won't work).
pause
exit /b 1
