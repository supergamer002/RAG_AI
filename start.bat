@echo off
setlocal
cd /d "%~dp0"
echo.
echo  RAG AI - avvio
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] Python non trovato. Installa Python 3.10+ da https://www.python.org/downloads/
    echo          e spunta "Add Python to PATH" durante l'installazione.
    pause
    exit /b 1
)

where ollama >nul 2>nul
if errorlevel 1 (
    echo [ATTENZIONE] Ollama non trovato. Installalo da https://ollama.com/download
    echo              Poi riavvia questo script: i modelli si scaricano da soli.
    echo.
)

if not exist .venv (
    echo Prima esecuzione: creo l'ambiente Python...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo [ERRORE] Installazione dipendenze fallita.
    pause
    exit /b 1
)

echo Avvio su http://localhost:8000  (Ctrl+C per chiudere)
python run.py
pause
