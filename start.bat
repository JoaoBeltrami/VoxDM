@echo off
setlocal

:: %~dp0 termina com \  -- remove o backslash final para nao quebrar aspas
set ROOT=%~dp0
set ROOT=%ROOT:~0,-1%

echo.
echo VoxDM MVP - iniciando...
echo.

:: ── Libera as portas antes de subir (mata processos anteriores) ───────────────
echo Liberando portas 8000 e 3000...

for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":8000 " ^| findstr LISTENING') do (
    taskkill /F /PID %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano 2^>nul ^| findstr ":3000 " ^| findstr LISTENING') do (
    taskkill /F /PID %%p >nul 2>&1
)

timeout /t 1 /nobreak >nul

:: ── .env ──────────────────────────────────────────────────────────────────────
if not exist "%ROOT%\.env" (
    if exist "%ROOT%\..\..\..\env" (
        echo Copiando .env...
        copy "%ROOT%\..\..\..\env" "%ROOT%\.env" >nul
    ) else (
        echo [ERRO] .env nao encontrado em: %ROOT%
        pause
        exit /b 1
    )
)

:: ── Dependencias do frontend (primeira vez) ───────────────────────────────────
if not exist "%ROOT%\frontend\node_modules" (
    echo Instalando dependencias do frontend...
    cd /d "%ROOT%\frontend"
    call npm install
    cd /d "%ROOT%"
)

:: ── API ───────────────────────────────────────────────────────────────────────
echo Iniciando API ^(porta 8000^)...
start "VoxDM API" /d "%ROOT%" cmd /k "uv run python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"

:: ── Frontend ──────────────────────────────────────────────────────────────────
echo Iniciando Frontend ^(porta 3000^)...
start "VoxDM Frontend" /d "%ROOT%\frontend" cmd /k "npm run dev"

:: ── Aguarda compilacao e abre browser ────────────────────────────────────────
echo Aguardando frontend compilar...
timeout /t 20 /nobreak >nul

start "" "http://localhost:3000"
