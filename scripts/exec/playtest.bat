@echo off
setlocal

:: ── playtest.bat ──────────────────────────────────────────────────────────────
:: Igual ao start.bat, MAS sobe a API gravando TODO o log em .internal\playtest.log
:: (fresco a cada execucao). E desse arquivo que o Claude le o blow-by-blow ao vivo
:: durante o /playtest (combate_engine_*, prompt_excede_budget, cascata, etc.).
::
:: Este .bat vive em scripts\exec\ -- ROOT = 2 niveis acima (raiz do projeto).
for %%i in ("%~dp0..\..") do set "ROOT=%%~fi"

echo.
echo VoxDM - PLAYTEST (API com log em arquivo)
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

:: ── Garante a pasta .internal (onde o log vai) ────────────────────────────────
if not exist "%ROOT%\.internal" mkdir "%ROOT%\.internal"

:: ── Dependencias do frontend (primeira vez) ───────────────────────────────────
if not exist "%ROOT%\frontend\node_modules" (
    echo Instalando dependencias do frontend...
    cd /d "%ROOT%\frontend"
    call npm install
    cd /d "%ROOT%"
)

:: ── API (com log em arquivo) ──────────────────────────────────────────────────
:: O ">" trunca o log a cada run (sempre fresco). "2>&1" junta stdout+stderr.
:: ATENCAO: a janela da API fica EM BRANCO de proposito -- tudo vai pro arquivo.
:: O ROOT nao tem espacos, entao o caminho do log dispensa aspas (evita conflito
:: com as aspas do cmd /k).
echo Iniciando API ^(porta 8000^) -- log em .internal\playtest.log ^(janela fica em branco^)...
start "VoxDM API [PLAYTEST LOG]" /d "%ROOT%" cmd /k "%ROOT%\.venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload > %ROOT%\.internal\playtest.log 2>&1"

:: ── Limpa cache do Next.js (evita 404 por cache corrompido apos hot-reload) ───
if exist "%ROOT%\frontend\.next" (
    echo Limpando cache do Next.js...
    rmdir /s /q "%ROOT%\frontend\.next"
)

:: ── Frontend ──────────────────────────────────────────────────────────────────
echo Iniciando Frontend ^(porta 3000^)...
start "VoxDM Frontend" /d "%ROOT%\frontend" cmd /k "npm run dev"

:: ── Aguarda compilacao e abre browser ────────────────────────────────────────
echo Aguardando frontend compilar...
timeout /t 20 /nobreak >nul

start "" "http://localhost:3000"

echo.
echo ============================================================
echo  PLAYTEST PRONTO. Diga "to no ar" pro Claude no chat.
echo  A API esta logando em: .internal\playtest.log
echo  Kill-switch do combate novo: COMBATE_ENGINE_ATIVO=false no .env
echo ============================================================
echo.
