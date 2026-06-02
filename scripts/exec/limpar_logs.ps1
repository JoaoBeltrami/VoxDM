# limpar_logs.ps1 — zera os logs ANTES de uma sessao de teste, pra que o que
# sobrar no disco seja 100% da sessao atual (sem ruido de sessoes antigas).
#
# Rodar logo ANTES do start.bat:
#   scripts\exec\limpar_logs.ps1
#
# Apaga: .internal/voxdm.log (+ rotacoes .log.1/.2/.3) e .internal/telemetry.jsonl.
# Nao toca em mais nada. Os arquivos sao recriados automaticamente ao subir a API.

# Vive em scripts\exec\ -- volta pra raiz do projeto.
Set-Location (Join-Path $PSScriptRoot "..\..")

$alvos = @(
    ".internal\voxdm.log",
    ".internal\voxdm.log.1",
    ".internal\voxdm.log.2",
    ".internal\voxdm.log.3",
    ".internal\telemetry.jsonl"
)

$apagados = 0
foreach ($f in $alvos) {
    if (Test-Path $f) {
        Remove-Item $f -Force
        Write-Host "  apagado: $f"
        $apagados++
    }
}

Write-Host ""
Write-Host "Logs zerados ($apagados arquivos). Pode rodar scripts\exec\start.bat agora."
Write-Host "Ao terminar a sessao, e so me dizer 'terminei' que eu leio os logs daqui."
