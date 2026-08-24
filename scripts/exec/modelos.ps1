# Confere se os modelos configurados ainda existem na conta Groq.
# Vive em scripts\exec\ -- volta pra raiz do projeto antes de rodar (cwd-sensivel).
# Exit 1 = tem modelo configurado que sumiu (foi o que aconteceu em 16/08/26).
Set-Location (Join-Path $PSScriptRoot "..\..")
uv run python scripts/checar_modelos.py
