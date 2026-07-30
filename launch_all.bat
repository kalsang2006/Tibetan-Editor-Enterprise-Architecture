@echo off
echo ======================================================================
echo LAUNCHING TEEA PLATFORM FOR MICROSOFT WORD ADD-IN
echo ======================================================================
echo.

echo 1. Starting Python Daemon Backend on http://127.0.0.1:50505...
start "TEEA Daemon Server" cmd /k ".venv\Scripts\python start_daemon.py"

timeout /t 2 /nobreak > NUL

echo 2. Starting Microsoft Word Add-in TaskPane Server...
cd addin
start "TEEA Word Add-in Server" cmd /k "npm start"

echo.
echo ======================================================================
echo TEEA Platform is active!
echo Opening Microsoft Word with TEEA TaskPane Add-in...
echo ======================================================================
pause
