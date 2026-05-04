@echo off
setlocal

:: %~dp0 termina com \  -- remove o backslash final para nao quebrar aspas
set ROOT=%~dp0
set ROOT=%ROOT:~0,-1%

echo.
echo VoxDM MVP - iniciando...
echo.

:: .env: usa local ou copia do projeto raiz (estrutura de worktree)
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

:: Frontend: instala dependencias se necessario (bloqueante, so na primeira vez)
if not exist "%ROOT%\frontend\node_modules" (
    echo Instalando dependencias do frontend...
    cd /d "%ROOT%\frontend"
    call npm install
    cd /d "%ROOT%"
)

:: API - abre janela separada, /d define o diretorio de trabalho
echo Iniciando API ^(porta 8000^)...
start "VoxDM API" /d "%ROOT%" cmd /k "uv run python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"

:: Frontend - abre janela separada
echo Iniciando Frontend ^(porta 3000^)...
start "VoxDM Frontend" /d "%ROOT%\frontend" cmd /k "npm run dev"

:: Aguarda Next.js compilar (primeira vez leva ~30s, subsequentes ~5s)
echo Aguardando frontend compilar...
timeout /t 20 /nobreak >nul

start "" "http://localhost:3000"
