"""
Testes do nudge de [CENA] — MESTRE-MOVER-LOCAL (23/06).

Quando o jogador declara deslocamento explícito, o prompt ganha um lembrete
pro Mestre emitir [CENA: id|Nome|hora] (que ele costuma esquecer). É só um
nudge de compliance — não muda estado, sem risco de "teleporte" falso.
"""

import pytest

from engine.llm.prompt_builder import (
    _RE_VIAGEM,
    ContextoMontado,
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


def test_nudge_cena_injetado_tambem_em_combate():
    """Fix playtest 01/07 (sess-7893f3bdbd28): 'Eu entro na casa' com
    em_combate=True (combate-conversa que não encerrava) → o gate antigo
    suprimia o nudge → [CENA] nunca veio → a engine achou que o jogador nunca
    saiu do local inicial ('voltou pro local do nada, todos me atacaram').
    Mudança de cena mid-combate NÃO é rara na prática — o nudge entra sempre."""
    invalidar_cache()
    wm = _wm()
    wm.entrar_combate()
    system = montar_mensagens(_contexto(wm, "eu entro na casa com toda minha imponência"))[0]["content"]
    assert "=== DESLOCAMENTO PEDIDO ===" in system


# ── nudge de [INIMIGO] — combate sem combatente registrado (05/07) ───────────
# Playtest sess-95a7c47468c5: sparring abriu em_combate mas nenhum [INIMIGO]
# foi emitido a luta inteira → sem turno de inimigo da engine, sem [DANO]
# aplicado, combate-zumbi de 6+ turnos. O nudge cobra o marcador no único
# estado em que faz falta (combate ativo + zero registrados).


def test_injeta_nudge_inimigo_em_combate_vazio():
    invalidar_cache()
    wm = _wm()
    wm.entrar_combate()
    assert wm.inimigos_combate == {}
    system = montar_mensagens(_contexto(wm, "dou mais um soco nele"))[0]["content"]
    assert "=== COMBATE SEM COMBATENTE REGISTRADO ===" in system
    assert "[INIMIGO:" in system


def test_nao_injeta_nudge_inimigo_com_inimigo_registrado():
    invalidar_cache()
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("tharn-1", "Tharnvik", "intacto")
    system = montar_mensagens(_contexto(wm, "ataco o Tharnvik"))[0]["content"]
    assert "=== COMBATE SEM COMBATENTE REGISTRADO ===" not in system


def test_nao_injeta_nudge_inimigo_fora_de_combate():
    invalidar_cache()
    system = montar_mensagens(_contexto(_wm(), "converso com o taverneiro"))[0]["content"]
    assert "=== COMBATE SEM COMBATENTE REGISTRADO ===" not in system
