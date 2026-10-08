# Mantem o Neo4j AuraDB Free e o Qdrant Free acordados (uma escrita + uma leitura).
# Roda todo dia pela tarefa agendada "VoxDM - manter bancos vivos" (o Aura pausa com 72h sem escrita).
# Vive em scripts\exec\ -- volta pra raiz do projeto antes de rodar (cwd-sensivel).
# Exit 1 = algum banco nao respondeu: abra o console dele (pausado = Resume manual).
# Log: .internal\manter_vivo.log
Set-Location (Join-Path $PSScriptRoot "..\..")
$env:PYTHONIOENCODING = "utf-8"
$saida = uv run python -m scripts.manter_vivo 2>&1
$codigo = $LASTEXITCODE
"$(Get-Date -Format s) exit=$codigo $($saida | Select-Object -Last 1)" | Out-File -Append -Encoding utf8 ".internal\manter_vivo.log"
exit $codigo
