@echo off
setlocal enableextensions
title Meditech Lab launcher

REM This launcher lives in dashboard\ (the git repo) but the lab's
REM docker-compose.yml sits one level up in meditech-lab\, so we run the
REM compose commands from the parent and launch Flask from this folder.
set "APPDIR=%~dp0"
cd /d "%~dp0.."

echo ==================================================
echo    Meditech Lab - one-click launcher
echo ==================================================
echo.

REM ---------- 1. Make sure the Docker engine is running ----------
echo [1/3] Checking Docker...
docker info >nul 2>&1
if %errorlevel%==0 (
    echo        Docker is already running.
    goto dockerready
)

echo        Docker is not running - starting Docker Desktop...
if not exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    echo        ERROR: Docker Desktop was not found at the default location.
    echo        Start Docker Desktop manually, then run this again.
    pause
    exit /b 1
)
start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
echo        Waiting for the Docker engine to come up ^(can take a minute^)...
set /a dtries=0
:waitdocker
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if %errorlevel%==0 goto dockerready
set /a dtries+=1
if %dtries% geq 36 (
    echo.
    echo        ERROR: Docker did not start within 3 minutes.
    echo        Open Docker Desktop manually, then run this again.
    pause
    exit /b 1
)
goto waitdocker

:dockerready
echo        Docker engine is up.
echo.

REM ---------- 2. Start Postgres ----------
echo [2/3] Starting Postgres...
docker compose up -d postgres
if %errorlevel% neq 0 (
    echo.
    echo        ERROR: failed to start the postgres container.
    pause
    exit /b 1
)
echo        Postgres container is up.
echo.

REM ---------- 3. Start the Flask dashboard (in its own window) ----------
echo [3/3] Starting the dashboard ^(Flask^)...
REM Set encoding here so the child window inherits it; use start /d for the
REM working dir so the spaces in the path don't break nested quoting.
set PYTHONIOENCODING=utf-8
start "Meditech Lab - Flask" /d "%APPDIR%" cmd /k python app.py
echo        Flask is starting in a separate window.
echo.

REM ---------- Wait until the whole stack actually answers ----------
echo Waiting for the app + database to be ready...
set /a atries=0
:waitapp
timeout /t 3 /nobreak >nul
curl -s http://localhost:5000/api/health 2>nul | findstr /r "postgres.*true" >nul
if %errorlevel%==0 goto live
set /a atries+=1
if %atries% geq 40 (
    echo.
    echo        The app started but Postgres is not answering yet.
    echo        Check the Flask window - the dashboard still opens below.
    goto live
)
goto waitapp

:live
echo.
echo ==================================================
echo               App is Live!
echo               http://localhost:5000
echo ==================================================
echo.
start "" http://localhost:5000
echo This window can be closed.
echo The Flask window keeps the app running - close it to stop the app.
echo.
pause
endlocal
