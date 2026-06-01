# Testa conectividade com Groq, Qdrant e Neo4j.
# Vive em scripts\exec\ -- volta pra raiz do projeto antes de rodar (cwd-sensivel).
Set-Location (Join-Path $PSScriptRoot "..\..")
uv run python connection_test.py
