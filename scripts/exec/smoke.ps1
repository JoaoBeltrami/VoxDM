# Smoke de ponta a ponta: 3 turnos reais, save, Encerrar, confere Qdrant/Neo4j/SQLite.
# Precisa da API de pe (start.bat). Gasta cota real de LLM -- nao rodar em loop.
# Limpa o que criou por padrao; -Manter deixa tudo para inspecionar a mao.
param([switch]$Manter)
Set-Location (Join-Path $PSScriptRoot "..\..")
if ($Manter) { uv run python scripts/smoke_ponta_a_ponta.py --manter } else { uv run python scripts/smoke_ponta_a_ponta.py }
