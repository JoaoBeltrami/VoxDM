@echo off
set ROOT=%~dp0
echo Iniciando VoxDM MVP...

start "VoxDM API" /d "%ROOT%" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

start "VoxDM Frontend" /d "%ROOT%frontend" cmd /k "npm run dev"

timeout /t 10 /nobreak >nul

start "" "http://localhost:3000"
