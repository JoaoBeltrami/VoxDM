"""
Confere se os modelos configurados ainda EXISTEM na conta Groq.

Por que existe (MODELO-DESLIGADO-1, 17/08/2026): o Groq desligou a família Llama
    de chat em 16/08 e levou junto o primário do projeto. O projeto rastreava a
    deprecation de UM modelo (`llama-3.1-8b-instant`), migrou o fallback e deu o
    assunto por encerrado — ninguém olhou o topo da cascata. Toda chamada virou
    404 e o turno morria. O hábito de "conferir deprecations a cada /estado"
    estava escrito no CLAUDE.md e não impediu nada, porque hábito escrito não
    roda. Este script roda.
Dependências: groq (SDK já na stack), config, engine.llm.tasks.
Armadilha: a lista de slots vem de `modelo_do_slot()`, NUNCA de literais aqui —
    senão este arquivo vira a quarta cópia da configuração de modelo e mente
    junto com as outras na próxima troca.
Armadilha (14/10): rodado como ARQUIVO, o `sys.path[0]` é `scripts/` e o
    `from config import settings` morria com ModuleNotFoundError. O comando do
    `/estado` e do `modelos.ps1` é exatamente esse — a vigia nunca conferiu nada
    desde que nasceu. A raiz entra no path antes dos imports do projeto, e
    `tests/test_checar_modelos.py` roda o arquivo de verdade para provar.

Exemplo:
    uv run python scripts/checar_modelos.py
    # → [OK] groq-principal  openai/gpt-oss-120b
    # → exit 1 se algum modelo configurado sumiu da conta
"""

import asyncio
import sys
from collections.abc import Iterable
from pathlib import Path

# Raiz do repo no path: o script é chamado como arquivo pelo /estado.
_RAIZ = str(Path(__file__).resolve().parent.parent)
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)

from config import settings  # noqa: E402
from engine.llm.tasks import (  # noqa: E402
    PROV_GROQ_120B,
    PROV_GROQ_LEVE,
    PROV_GROQ_PRINCIPAL,
    modelo_do_slot,
)

# Os slots Groq, na ordem em que a cascata os encontra. Só Groq: a lista de
# modelos que consultamos é da conta Groq, e Gemini/Ollama têm outro dono.
_SLOTS_GROQ = (PROV_GROQ_PRINCIPAL, PROV_GROQ_120B, PROV_GROQ_LEVE)


def modelos_configurados() -> dict[str, str]:
    """Slot -> modelo real, lido da MESMA fonte que o router usa."""
    return {slot: modelo_do_slot(slot) for slot in _SLOTS_GROQ}


def comparar(
    configurados: dict[str, str], disponiveis: Iterable[str]
) -> list[tuple[str, str]]:
    """Os (slot, modelo) que NÃO existem mais na conta. Lista vazia = tudo certo.

    Função PURA de propósito: é ela que o teste exercita. O caminho de rede fica
    no `main`, porque teste que depende de rede não roda quando mais importa.
    """
    vivos = {str(m).strip() for m in disponiveis}
    return [
        (slot, modelo)
        for slot, modelo in configurados.items()
        if modelo and modelo not in vivos
    ]


async def _listar_da_conta() -> list[str]:
    from groq import AsyncGroq

    cliente = AsyncGroq(api_key=settings.GROQ_API_KEY)
    resposta = await cliente.models.list()
    return [str(m.id) for m in (resposta.data or [])]


async def main() -> int:
    if not settings.GROQ_API_KEY:
        print("GROQ_API_KEY vazia — nada a conferir.")
        return 0

    try:
        disponiveis = await _listar_da_conta()
    except Exception as e:  # noqa: BLE001 — o script existe pra avisar, não pra explodir
        print(f"nao consegui listar os modelos da conta: {str(e)[:160]}")
        return 2

    configurados = modelos_configurados()
    ausentes = comparar(configurados, disponiveis)

    print(f"modelos que a conta enxerga: {len(disponiveis)}")
    for slot, modelo in configurados.items():
        marca = "AUSENTE" if any(slot == s for s, _ in ausentes) else "OK"
        print(f"  [{marca:7s}] {slot:16s} {modelo}")

    if ausentes:
        print()
        print("MODELO CONFIGURADO QUE NAO EXISTE MAIS NA CONTA:")
        for slot, modelo in ausentes:
            print(f"  {slot} -> {modelo}")
        print()
        print("A cascata sobrevive (404 de modelo cascateia desde 17/08), mas cada")
        print("turno paga uma chamada morta. Troque em config.py e confira o nome")
        print("do slot: nome que cita tamanho de modelo mente na primeira troca.")
        print()
        nao_usados = sorted(set(disponiveis) - set(configurados.values()))
        if nao_usados:
            print("candidatos disponiveis na conta:")
            for m in nao_usados:
                print(f"  - {m}")
        return 1

    print()
    print("todos os modelos configurados existem na conta.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
