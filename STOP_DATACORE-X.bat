@echo off
title DATACORE-X stop
echo Stopping the DATACORE-X backend and OPC UA server...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /PID %%p /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq DATACORE-X backend*" /T /F >nul 2>&1
echo Done. The Ignition gateway keeps running as a Windows service (it is harmless to leave on).
timeout /t 5
