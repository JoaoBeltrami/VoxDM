# Roda a suite de testes.
# Vive em scripts\exec\ -- volta pra raiz do projeto antes de rodar (cwd-sensivel).
Set-Location (Join-Path $PSScriptRoot "..\..")
uv run pytest tests/ -v
