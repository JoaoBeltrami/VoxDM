@echo off
set ROOT=%~dp0
echo Iniciando VoxDM MVP em %ROOT%

start "VoxDM API" cmd /k "cd /d "%ROOT%" && .venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak >nul

start "VoxDM Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

timeout /t 8 /nobreak >nul

start "" "http://localhost:3000"
