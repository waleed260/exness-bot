@echo off
REM ==========================================================
REM  exness-bot - start the bot
REM  Double-click to run. Stop with Ctrl+C or by closing this window.
REM ==========================================================
cd /d "%~dp0"
title exness-bot

if not exist "exness_bot\settings.py" (
    echo [ERROR] exness_bot\settings.py is missing.
    echo Run install.bat first.
    pause
    exit /b 1
)

echo Starting exness-bot...
echo (Safe DRY-RUN mode unless you changed DRY_RUN in exness_bot\config.py)
echo Press Ctrl+C to stop.
echo.
python -m exness_bot.runner

echo.
echo Bot stopped.
pause
