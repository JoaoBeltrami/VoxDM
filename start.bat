@echo off
set ROOT=%~dp0

echo Iniciando VoxDM MVP...

:: ── .env: usa local ou busca no projeto principal (worktree) ─────────────────
if not exist "%ROOT%.env" (
    if exist "%ROOT%..\..\..\.env" (
        echo Copiando .env do projeto principal...
        copy "%ROOT%..\..\..\.env" "%ROOT%.env" >nul
    ) else (
        echo [ERRO] .env nao encontrado. Copie o arquivo antes de continuar.
        pause
        exit /b 1
    )
)

:: ── Frontend: instala dependencias se necessario ─────────────────────────────
if not exist "%ROOT%frontend\node_modules" (
    echo Instalando dependencias do frontend (primeira vez)...
    start "npm install" /d "%ROOT%frontend" /wait cmd /c "npm install"
)

:: ── API ──────────────────────────────────────────────────────────────────────
start "VoxDM API" /d "%ROOT%" cmd /k "uv run python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

timeout /t 3 /nobreak >nul

:: ── Frontend ─────────────────────────────────────────────────────────────────
start "VoxDM Frontend" /d "%ROOT%frontend" cmd /k "npm run dev"

timeout /t 10 /nobreak >nul

start "" "http://localhost:3000"
