@echo off
title Coffee Estate Management System
echo ====================================================
echo Starting Coffee Estate Web Server...
echo ====================================================
cd /d "%~dp0"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:5000"
.\venv\Scripts\python.exe wsgi.py
pause
