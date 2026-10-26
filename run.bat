@echo off
title Coffee Estate Web Application
cd /d "%~dp0"

echo ======================================================
echo   AI-Powered Smart Coffee Estate System
echo ======================================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found in %~dp0venv
    pause
    exit /b 1
)

echo Starting web server...
echo.
echo Opening browser to http://127.0.0.1:5000 ...
echo (Keep this window open while using the website!)
echo Press Ctrl+C in this window to stop the server anytime.
echo.

REM Open browser in 1.5 seconds once server starts
start /b powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:5000'"

.\venv\Scripts\python.exe wsgi.py
pause
