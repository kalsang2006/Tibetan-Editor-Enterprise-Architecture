@echo off
setlocal enabledelayedexpansion

echo ======================================================================
echo           LAUNCHING TEEA PLATFORM FOR MICROSOFT WORD
echo ======================================================================
echo.

:: 1. Determine Python Executable & Set PYTHONPATH
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [INFO] Using virtual environment Python: !PYTHON_EXE!
) else (
    set "PYTHON_EXE=python"
    echo [INFO] Using system Python: !PYTHON_EXE!
)

set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"

:: 2. Install npm dependencies (if needed)
echo.
echo [1/5] Checking npm dependencies in addin/...
cd addin
if not exist "node_modules" (
    echo [INFO] node_modules not found — running npm install...
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed. Please check for errors above.
        cd ..
        pause
        exit /b 1
    )
) else (
    echo [INFO] node_modules already present — skipping install.
)
cd ..

:: 3. Production build (validates TypeScript + generates dist/)
echo.
echo [2/5] Building production bundle (addin)...
cd addin
call npm run build
if errorlevel 1 (
    echo.
    echo [ERROR] Production build failed! Fix TypeScript/Webpack errors before launching.
    cd ..
    pause
    exit /b 1
)
echo [OK] Production build succeeded.
cd ..

:: 4. Start TEEA Python Daemon Backend
echo.
echo [3/5] Starting TEEA Daemon Backend on http://127.0.0.1:50505...
start "TEEA Daemon Server" cmd /k "set PYTHONPATH=%CD%\src&& set PYTHONIOENCODING=utf-8&& set TEEA_TOKENIZATION__MODEL_LOCAL_PATH=%CD%\TiBERT&& !PYTHON_EXE! start_daemon.py"

:: 5. Wait for Daemon Readiness
echo.
echo [WAIT] Checking daemon health endpoint...
!PYTHON_EXE! scripts\wait_for_daemon.py
if errorlevel 1 (
    echo.
    echo [ERROR] TEEA Daemon failed to start or health check timed out.
    echo Please check the "TEEA Daemon Server" terminal window for error logs.
    pause
    exit /b 1
)

:: 6. Start Word Add-in Webpack Dev Server & Sideload
echo.
echo [4/5] Starting Webpack TaskPane Dev Server...
cd addin
start "TEEA Word Add-in Server" cmd /k "npm start"

echo.
echo [5/5] Sideloading TEEA Add-in manifest into Microsoft Word Desktop...
start "TEEA Word Sideload" cmd /k "npx office-addin-debugging start manifest.xml desktop"

cd ..

echo.
echo ======================================================================
echo               TEEA PLATFORM IS ACTIVE AND RUNNING!
echo ======================================================================
echo  - Local Daemon API:    http://127.0.0.1:50505
echo  - Health Check:        http://127.0.0.1:50505/health
echo  - Add-in TaskPane UI:  https://localhost:3000/taskpane.html
echo  - Host Application:    Microsoft Word Desktop
echo  - Monlam AI Key:       Set in addin/.env
echo ======================================================================
echo.
echo Leave the background server windows open while editing.
pause
