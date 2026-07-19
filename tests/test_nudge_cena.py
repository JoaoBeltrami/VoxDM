"""
Testes do nudge de [CENA] — MESTRE-MOVER-LOCAL (23/06).

Quando o jogador declara deslocamento explícito, o prompt ganha um lembrete
pro Mestre emitir [CENA: id|Nome|hora] (que ele costuma esquecer). É só um
nudge de compliance — não muda estado, sem risco de "teleporte" falso.
"""

import pytest

from engine.llm.prompt_builder import (
    _RE_RECRUTAMENTO,
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


def test_nudge_cena_cobre_local_de_transito():
    """CENA-TRANSITO-1 (validações 16-18/07, 3/3 corridas): o nudge disparava
    mas o Mestre não emitia [CENA] quando o destino era local de PASSAGEM
    ("saio da taverna e sigo pela estrada ao norte") — a estrada não é location
    do módulo e o texto antigo sugeria local 'de verdade'. Guarda de doc: a
    instrução precisa dizer que trânsito CONTA e mostrar um id improvisado."""
    invalidar_cache()
    # Frase EXATA das corridas de validação — o regex tem que casar…
    frase = "Termino minha bebida, saio da taverna e sigo pela estrada ao norte."
    assert _RE_VIAGEM.search(frase)
    # …e a instrução tem que cobrir passagem/improviso de id.
    system = montar_mensagens(_contexto(_wm(), frase))[0]["content"]
    assert "=== DESLOCAMENTO PEDIDO ===" in system
    assert "passagem" in system
    assert "estrada-norte" in system  # exemplo concreto de id improvisado


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


# ── nudge de [COMPANION_ADD] — recrutamento fechado (playtest 10/07) ──────────
# Playtest sess-cc69c30f7c4f: contratação inequívoca de mercenário (aperto de
# mão, "selando o acordo", LLM até emitiu [XP: +100]) e [COMPANION_ADD] nunca
# veio — a instrução já estava no prompt (social.md + markers_lista.md) e o
# modelo ignorou. Reforço pontual quando o jogador fecha o acordo na fala.

@pytest.mark.parametrize("texto", [
    "bem-vindo ao bando, Moreno",
    "bem-vinda ao grupo",
    "a partir de agora você anda comigo",
    "vem comigo, Moreno",
    "venha comigo, viajante",
    "você está contratado",
    "está contratada, parceira",
    "eu te contrato",
    "junte-se a mim nessa jornada",
    "fechado, sessenta moedas de ouro",
    "combinado, cinquenta moedas pra te contratar",
])
def test_recrutamento_detecta_fechamento_de_acordo(texto):
    assert _RE_RECRUTAMENTO.search(texto), f"deveria casar recrutamento: {texto}"


@pytest.mark.parametrize("texto", [
    "quanto você cobra pra me acompanhar?",
    "você aluga a espada?",
    "preciso de um parceiro de estrada",
    "qual é o seu nome e o seu preço?",
    "ataco o goblin com minha espada",
])
def test_recrutamento_ignora_negociacao_em_curso(texto):
    assert not _RE_RECRUTAMENTO.search(texto), f"não deveria casar ainda: {texto}"


def test_injeta_nudge_companion_ao_fechar_recrutamento():
    invalidar_cache()
    texto = "Aperto a mão dele: fechado, sessenta moedas. Bem-vindo ao bando, Moreno."
    system = montar_mensagens(_contexto(_wm(), texto))[0]["content"]
    assert "=== RECRUTAMENTO SENDO FECHADO ===" in system
    assert "[COMPANION_ADD:" in system


def test_sem_recrutamento_nao_injeta_nudge_companion():
    invalidar_cache()
    system = montar_mensagens(_contexto(_wm(), "pergunto ao ferreiro sobre a espada"))[0]["content"]
    assert "=== RECRUTAMENTO SENDO FECHADO ===" not in system
