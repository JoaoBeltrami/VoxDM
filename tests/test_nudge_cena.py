"""
Testes do nudge de [CENA] — MESTRE-MOVER-LOCAL (23/06).

Quando o jogador declara deslocamento explícito, o prompt ganha um lembrete
pro Mestre emitir [CENA: id|Nome|hora] (que ele costuma esquecer). É só um
nudge de compliance — não muda estado, sem risco de "teleporte" falso.
"""

import pytest

from engine.llm.prompt_builder import (
    ContextoMontado,
    _RE_VIAGEM,
    invalidar_cache,
    montar_mensagens,
)
from engine.memory.working_memory import WorkingMemory


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("vila", "Vila", "sess-cena", **kw)


def _contexto(wm: WorkingMemory, transcricao: str) -> ContextoMontado:
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


# ── _RE_VIAGEM ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "vou para a mina abandonada",
    "vamos até a taverna",
    "sigo rumo ao castelo",
    "viajo para a capital",
    "me dirijo à floresta",
    "entro na caverna",
    "saio do salão",
    "atravesso a ponte",
    "vou embora daqui",
    "voltamos para a vila",
])
def test_viagem_detecta_deslocamento(texto):
    assert _RE_VIAGEM.search(texto), f"deveria casar deslocamento: {texto}"


@pytest.mark.parametrize("texto", [
    "ataco o orc líder com minha espada",
    "vou atacar o goblin",
    "vamos lutar contra os bandidos",
    "examino a porta trancada",
    "pergunto ao ferreiro sobre a espada",
    "rolo um teste de percepção",
    # Regressões de idioma (achadas no hardening adversarial) — NÃO são viagem:
    "vou ao que interessa",          # "ao que" relativo, não um lugar
    "volto a perguntar",             # "a"+infinitivo = "de novo", não destino
    "me dirijo a ele com respeito",  # falar COM alguém, não viajar
    "vou ver o que tem na mesa",
])
def test_viagem_ignora_nao_deslocamento(texto):
    assert not _RE_VIAGEM.search(texto), f"não deveria casar: {texto}"


# ── injeção no prompt ───────────────────────────────────────────────────────

def test_injeta_nudge_cena_com_deslocamento():
    invalidar_cache()
    system = montar_mensagens(_contexto(_wm(), "vou para a mina abandonada"))[0]["content"]
    assert "=== DESLOCAMENTO PEDIDO ===" in system
    assert "[CENA:" in system


def test_sem_deslocamento_nao_injeta_nudge():
    invalidar_cache()
    system = montar_mensagens(_contexto(_wm(), "pergunto ao ferreiro sobre a espada"))[0]["content"]
    assert "=== DESLOCAMENTO PEDIDO ===" not in system


def test_nudge_cena_suprimido_em_combate():
    # Mudança de cena mid-combate é rara — não injeta no turno mais pesado.
    invalidar_cache()
    wm = _wm()
    wm.entrar_combate()
    system = montar_mensagens(_contexto(wm, "vou para a outra sala"))[0]["content"]
    assert "=== DESLOCAMENTO PEDIDO ===" not in system
