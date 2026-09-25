@echo off
REM Avvia la dashboard grafica (webapp\frontend, progetto Nexus).
REM Richiede Node.js installato (npm nel PATH) - prerequisito nuovo,
REM non usato altrove nel progetto (che gira su Python/WSL).

echo Verifico e installo le dipendenze Python del backend...
python -m pip install --upgrade pip
python -m pip install -r "%~dp0webapp\backend\requirements.txt"

cd /d "%~dp0webapp\frontend"

if not exist node_modules (
    echo Prima esecuzione: installo le dipendenze npm...
    call npm install
)

echo Avvio del backend FastAPI in una nuova finestra...
start "RAG AI Backend (FastAPI)" cmd /k "cd /d "%~dp0" && uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo Avvio della dashboard frontend su http://localhost:3000 ...
call npm run dev

pause
