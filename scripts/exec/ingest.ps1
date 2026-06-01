# Ingestao do modulo no Qdrant + Neo4j (params nomeados).
# Vive em scripts\exec\ -- volta pra raiz do projeto antes de rodar (cwd-sensivel).
param(
    [string]$Input = "modulo_teste/modulo_teste_v1.2.json",
    [switch]$DryRun,
    [switch]$SkipNeo4j,
    [switch]$SkipQdrant
)

Set-Location (Join-Path $PSScriptRoot "..\..")

$args_extra = @()
if ($DryRun)    { $args_extra += "--dry-run" }
if ($SkipNeo4j) { $args_extra += "--skip-neo4j" }
if ($SkipQdrant){ $args_extra += "--skip-qdrant" }

uv run python main.py --input $Input @args_extra
