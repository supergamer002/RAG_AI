@echo off
setlocal

REM ============================================================
REM RAG AI - Avvio completo tramite WSL
REM ============================================================

echo.
echo ============================================================
echo   RAG AI - Startup
echo ============================================================
echo.

set "PROJECT_DIR=%~dp0"
set "FRONTEND_DIR=%~dp0webapp\frontend"

REM ============================================================
REM 1. Avvio Ollama
REM ============================================================

echo [1/3] Avvio Ollama in WSL...

start "RAG AI - Ollama" cmd /k "wsl --cd "%PROJECT_DIR%" -- ollama serve"

echo Ollama avviato.
echo.

REM ============================================================
REM 2. Controllo/installazione dipendenze frontend
REM ============================================================

echo [2/3] Controllo dipendenze frontend...

wsl --cd "%FRONTEND_DIR%" -- bash -lc "if [ ! -d node_modules ]; then echo 'Prima esecuzione: installo le dipendenze npm...'; npm install; else echo 'node_modules gia presente.'; fi"

if errorlevel 1 (
    echo.
    echo [ERRORE] npm install fallito.
    pause
    exit /b 1
)

echo.
echo [OK] Dipendenze frontend disponibili.
echo.

REM ============================================================
REM 3. Avvio backend + frontend
REM ============================================================

echo [3/3] Avvio backend FastAPI...

start "RAG AI Backend (FastAPI)" cmd /k "wsl --cd "%PROJECT_DIR%" -- uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo.
echo Backend:
echo http://localhost:8000
echo.

timeout /t 3 /nobreak >nul

echo Avvio dashboard frontend...
echo.
echo Dashboard:
echo http://localhost:3000
echo.

wsl --cd "%FRONTEND_DIR%" -- npm run dev

echo.
echo ============================================================
echo   Frontend terminato.
echo ============================================================
echo.

pause