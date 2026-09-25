@echo off
setlocal

REM ------------------------------------------------------------
REM Directory del progetto
REM ------------------------------------------------------------
cd /d "%~dp0"

REM ------------------------------------------------------------
REM BACKEND
REM ------------------------------------------------------------
start "Nexus Backend" wsl -d Ubuntu -e bash -lc "./run_backend.sh"

REM ------------------------------------------------------------
REM FRONTEND
REM ------------------------------------------------------------
start "Nexus Frontend" wsl -d Ubuntu -e bash -lc "./run_frontend.sh"

REM ------------------------------------------------------------
REM Attendi l'avvio dei server
REM ------------------------------------------------------------
timeout /t 5 /nobreak >nul

REM ------------------------------------------------------------
REM Apri Edge
REM ------------------------------------------------------------
start "" msedge.exe "http://localhost:3000"

echo.
echo ==========================================
echo       Nexus Dashboard avviata
echo ==========================================
echo.
echo Premi un tasto per terminare backend e frontend...
pause >nul

REM ------------------------------------------------------------
REM TERMINA I SERVER
REM ------------------------------------------------------------
wsl -d Ubuntu -e bash -lc "pkill -f run_backend.sh"
wsl -d Ubuntu -e bash -lc "pkill -f run_frontend.sh"

echo.
echo Dashboard terminata.
pause
