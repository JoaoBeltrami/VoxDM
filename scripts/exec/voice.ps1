# Loop de voz local (STT -> LLM mock -> TTS) com relatorio de latencia.
# Vive em scripts\exec\ -- volta pra raiz do projeto antes de rodar (cwd-sensivel).
Set-Location (Join-Path $PSScriptRoot "..\..")
uv run python demo/voice_loop.py
