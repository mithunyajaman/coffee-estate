@echo off
title Coffee Estate Web Application
echo ========================================================
echo   Starting AI-Powered Smart Coffee Estate System...
echo ========================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please make sure the venv folder exists in this directory.
    pause
    exit /b 1
)

echo Starting server on http://127.0.0.1:5000 ...
echo Press Ctrl+C in this window to stop the server anytime.
echo.

start "" http://127.0.0.1:5000

.\venv\Scripts\python.exe wsgi.py
pause
