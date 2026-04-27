@echo off
echo Iniciando VoxDM MVP...

start "VoxDM API" cmd /k ".venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak >nul

start "VoxDM Frontend" cmd /k "cd frontend && npm run dev"

timeout /t 5 /nobreak >nul

start "" "http://localhost:3000"
