@echo off
setlocal

:: VoxDM - Ingestão do módulo de teste no Qdrant + Neo4j
:: Wrapper de `make ingest` (equivalente a: uv run python main.py)

:: Este .bat vive em scripts\exec\ -- ROOT = 2 niveis acima (raiz do projeto).
for %%i in ("%~dp0..\..") do set "ROOT=%%~fi"

echo.
echo === VoxDM - Ingestao ===
echo.
echo Diretorio: %ROOT%
echo Comando:   uv run python main.py %*
echo.

cd /d "%ROOT%"

:: Argumentos comuns documentados pra referencia:
::   ingest.bat                 - ingestao completa
::   ingest.bat --dry-run       - so valida sem subir
::   ingest.bat --skip-neo4j    - so Qdrant
::   ingest.bat --skip-qdrant   - so Neo4j

uv run python main.py %*

set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% EQU 0 (
    echo === Ingestao concluida com sucesso ===
) else (
    echo === FALHA na ingestao [codigo %EXITCODE%] ===
)
echo.
pause
exit /b %EXITCODE%
