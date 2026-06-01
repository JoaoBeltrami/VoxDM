@echo off
setlocal

:: monitor.bat - sobe as ferramentas de observacao da sessao de teste:
::   - Dashboard Streamlit (aba "Decisoes LLM") em http://localhost:8501
::   - watch_teste.py (tail inteligente do telemetry.jsonl) numa janela cmd
::
:: Pre-requisito: o jogo ja deve estar rodando (start.bat). Estes sao apenas
:: os monitores; nao sobem API nem frontend.

:: Este .bat vive em scripts\exec\ -- ROOT = 2 niveis acima (raiz do projeto).
:: "%%~fi" resolve para caminho absoluto sem barra final.
for %%i in ("%~dp0..\..") do set "ROOT=%%~fi"

echo.
echo VoxDM - monitores de teste...
echo.

:: ── .env (dashboard precisa de DEBUG=true) ───────────────────────────────────
if not exist "%ROOT%\.env" (
    echo [ERRO] .env nao encontrado em: %ROOT%
    echo Rode start.bat primeiro ^(ele copia/valida o .env^).
    pause
    exit /b 1
)

:: ── Dashboard Streamlit ───────────────────────────────────────────────────────
echo Iniciando Dashboard ^(porta 8501^)...
start "VoxDM Dashboard" /d "%ROOT%" cmd /k "%ROOT%\.venv\Scripts\streamlit.exe run dashboard.py"

:: ── Watch (tail inteligente do telemetry.jsonl) ──────────────────────────────
echo Iniciando watch_teste...
start "VoxDM Watch" /d "%ROOT%" cmd /k "%ROOT%\.venv\Scripts\python.exe scripts\watch_teste.py"

:: ── Aguarda o Streamlit subir e abre o browser na aba certa ──────────────────
echo Aguardando o dashboard subir...
timeout /t 6 /nobreak >nul

start "" "http://localhost:8501"

echo.
echo Pronto. Dashboard: http://localhost:8501  ^|  Watch: janela "VoxDM Watch".
echo (Feche as janelas para encerrar os monitores.)
endlocal
