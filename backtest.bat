@echo off
REM ==========================================================
REM  exness-bot - test the strategy on past data
REM ==========================================================
cd /d "%~dp0"
title exness-bot backtest

echo Backtest the strategy on historical candles.
echo You need a CSV file with columns: time,open,high,low,close
echo (export one from MetaTrader 5:  View - Symbols - Bars - Export)
echo.
set /p CSV="Drag your CSV file here and press Enter: "

REM strip surrounding quotes if the path was dragged in
set CSV=%CSV:"=%

python -m exness_bot.backtest --csv "%CSV%"
echo.
pause
