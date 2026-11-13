@echo off
setlocal EnableDelayedExpansion
title DATACORE-X launcher
REM ===================================================================
REM  DATACORE-X one-click start
REM   1. checks the Ignition gateway service
REM   2. starts the digital-twin backend + OPC UA server (port 8000 / 4840)
REM   3. waits until both are ready
REM   4. opens the Ignition dashboard (and the 3D twin)
REM  Stop everything with STOP_DATACORE-X.bat
REM ===================================================================

set "ROOT=%~dp0"
set "APP=%ROOT%app\datacore-x"
set "PY=%ROOT%app\venv\Scripts\python.exe"
set "DASH=http://localhost:8088/data/perspective/client/DATACORE_X"
set "TWIN=http://localhost:8000/"
REM simulation speed: simulated seconds per real second (10 = good for a demo)
if "%DCX_SPEED%"=="" set "DCX_SPEED=10"

echo.
echo   ============================================
echo     DATACORE-X  Data-Centre Digital Twin
echo   ============================================
echo.

if not exist "%PY%" (
    echo [X] Python environment not found: %PY%
    echo     Recreate it:  python -m venv app\venv  then  app\venv\Scripts\pip install -r app\datacore-x\requirements.txt
    goto :fail
)

REM ---------- 1. Ignition gateway ----------
echo [1/4] Checking Ignition gateway service...
sc query Ignition | find "RUNNING" >nul
if errorlevel 1 (
    echo       Ignition is not running - starting it ^(may ask for admin permission^)...
    powershell -NoProfile -Command "Start-Process sc.exe -ArgumentList 'start Ignition' -Verb RunAs -WindowStyle Hidden" >nul 2>&1
) else (
    echo       Ignition service is running.
)

REM ---------- 2. Backend ----------
echo [2/4] Starting the digital-twin backend and OPC UA server...
REM free port 8000 if an old backend is still running
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
    echo       Stopping old backend ^(PID %%p^)...
    taskkill /PID %%p /T /F >nul 2>&1
)
set "DCX_OPCUA=1"
start "DATACORE-X backend" /min cmd /k "cd /d "%APP%\backend" && "%PY%" -m uvicorn datacorex.api:app --host 127.0.0.1 --port 8000"

REM ---------- 3. Wait for readiness ----------
echo [3/4] Waiting for the twin to come up...
set /a n=0
:waitbackend
timeout /t 2 /nobreak >nul
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:8000/api/snapshot 2>nul | find "200" >nul
if not errorlevel 1 goto backendok
set /a n+=1
if !n! geq 45 (
    echo [X] Backend did not start within 90 s. Open the "DATACORE-X backend" window to see the error.
    goto :fail
)
goto waitbackend
:backendok
echo       Twin backend ready  ^(http://localhost:8000^), OPC UA on opc.tcp://localhost:4840

echo       Waiting for the Ignition gateway...
set /a n=0
:waitign
curl -s http://localhost:8088/StatusPing 2>nul | find "RUNNING" >nul
if not errorlevel 1 goto ignok
set /a n+=1
if !n! geq 60 (
    echo [!] Ignition is not answering on port 8088 after 2 min.
    echo     Opening only the 3D twin. Start Ignition and open: %DASH%
    start "" "%TWIN%"
    goto :done
)
timeout /t 2 /nobreak >nul
goto waitign
:ignok
echo       Ignition gateway ready. Giving the OPC UA connection a few seconds to reconnect...
timeout /t 6 /nobreak >nul

REM ---------- 4. Open the screens ----------
echo [4/4] Opening the dashboard...
start "" "%DASH%"
if /i "%1"=="twin" start "" "%TWIN%"

:done
echo.
echo   DATACORE-X is running.
echo     Dashboard : %DASH%
echo     3D twin   : %TWIN%
echo     Speed     : %DCX_SPEED%x real time
echo.
echo   Leave the minimised "DATACORE-X backend" window open.
echo   To stop: double-click STOP_DATACORE-X.bat
echo.
timeout /t 15
exit /b 0

:fail
echo.
pause
exit /b 1
