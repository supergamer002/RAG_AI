@echo off
REM Avvia la dashboard grafica (webapp\frontend, progetto Nexus).
REM Richiede Node.js installato (npm nel PATH) - prerequisito nuovo,
REM non usato altrove nel progetto (che gira su Python/WSL).

cd /d "%~dp0webapp\frontend"

if not exist node_modules (
    echo Prima esecuzione: installo le dipendenze npm...
    call npm install
)

echo Avvio la dashboard su http://localhost:3000 ...
call npm run dev

pause
