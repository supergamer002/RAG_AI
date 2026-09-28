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

REM Avvia Ollama direttamente tramite wsl.exe.
REM Se un server Ollama e' gia' attivo nella distro, non ne avvia un secondo.
start "RAG AI - Ollama" wsl --cd "%PROJECT_DIR%" -- bash -lc "if pgrep -x ollama >/dev/null 2>&1; then echo '[OK] Ollama server gia attivo.'; else echo '[INFO] Avvio Ollama server...'; exec ollama serve; fi"

echo Ollama command inviato a WSL.
echo.

REM ============================================================
REM 2. Controllo dipendenze frontend
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
REM 3. Avvio backend FastAPI in modalita' debug
REM ============================================================

echo [3/3] Avvio backend FastAPI in modalita' debug...

start "RAG AI Backend (FastAPI - DEBUG)" cmd /k wsl --cd "%PROJECT_DIR%" -- env RAG_DEBUG=1 python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug

echo.
echo Backend:
echo http://localhost:8000
echo.
echo Debug log:
echo %PROJECT_DIR%log_debug.log
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
