"""
MAGIA-SEM-ECONOMIA-1 (09/08) — conjurar gasta a ação e o inimigo segue agindo.

Por que existe: os passos 4 e 5 do P16 (resistência e cura) resolviam a magia
    mas NÃO gastavam a ação da rodada, e marcavam `_engine_resolveu_turno`, que
    SUPRIME o beat do inimigo. Duas consequências, ambas reintroduzindo queixas
    que tinham acabado de ser consertadas:
      1. dava pra lançar Bola de Fogo E atacar na mesma rodada;
      2. conjurar em combate fazia o inimigo não jogar a rodada — o "só o player
         age" que o TURNO-COLAPSADO-1 tinha resolvido no mesmo dia.
Dependências: nenhuma (estado puro).
Armadilha: quem gasta a ação do ataque é o orquestrador (`wm.usar_acao()`), mas
    magia de resistência e cura NÃO passam por ele — resolvem direto no
    websocket. Todo caminho novo que resolva uma ação precisa gastar a economia
    explicitamente, senão o combate volta a não ter turno.

Exemplo:
    uv run pytest tests/test_magia_economia.py -q
"""

import random
from pathlib import Path

from engine.magic.cura import resolver_cura_de_magia
from engine.magic.salvaguarda import resolver_resistencia
from engine.memory.working_memory import WorkingMemory

_WS = (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")


def _wm_conjurador() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.player_class = "mago"
    wm.player_level = 5
    wm.entrar_combate()
    wm.registrar_inimigo("g", "Goblin")
    wm.aplicar_stats_inimigo("g", ca=10, hp_max=200)
    return wm


# ── A economia existe e a magia tem que consumi-la ───────────────────────────


def test_a_economia_de_acao_funciona_no_estado():
    """Se isto falhar, o problema é anterior à magia."""
    wm = _wm_conjurador()
    assert wm.pode_agir() is True
    wm.usar_acao()
    assert wm.pode_agir() is False


def test_resistencia_gasta_a_acao_no_websocket():
    """O consumo mora no call-site, porque `resolver_resistencia` é pura — ela
    não deve ter efeito colateral de economia pra continuar testável."""
    i = _WS.index("magia_save_resolvido")
    bloco = _WS[max(0, i - 900):i]
    assert "sessao.working_mem.usar_acao()" in bloco


def test_cura_gasta_a_acao_no_websocket():
    i = _WS.index("magia_cura_resolvida")
    bloco = _WS[max(0, i - 900):i]
    assert "sessao.working_mem.usar_acao()" in bloco


# ── E o inimigo precisa AGIR ─────────────────────────────────────────────────


def test_resistencia_adia_o_turno_dos_inimigos():
    """`_engine_resolveu_turno` suprime o beat. Sem marcar o adiamento, conjurar
    fazia o inimigo pular a rodada inteira."""
    i = _WS.index("magia_save_resolvido")
    bloco = _WS[max(0, i - 900):i]
    assert "sessao.inimigos_adiados = True" in bloco


def test_cura_adia_o_turno_dos_inimigos_apenas_em_combate():
    """Curar fora de combate não pode inventar um turno de inimigo."""
    i = _WS.index("magia_cura_resolvida")
    bloco = _WS[max(0, i - 900):i]
    assert "if sessao.working_mem.em_combate:" in bloco
    assert "sessao.inimigos_adiados = True" in bloco


# ── O enforcement deixou de ser código morto ─────────────────────────────────


def test_avaliar_acao_jogador_tem_call_site_em_producao():
    """Escrito e testado desde 19/06, sem call-site até 09/08 — a classe
    'feature dormente' que o BEAT-NUNCA-RODOU-1 registrou."""
    assert "avaliar_acao_jogador(" in _WS
    assert "acao_recusada_economia" in _WS


def test_a_recusa_nao_processa_o_turno():
    i = _WS.index("acao_recusada_economia")
    bloco = _WS[i:i + 700]
    assert "continue" in bloco, "recusar e seguir processando seria pior que não recusar"


# ── As funções puras seguem sem efeito colateral ─────────────────────────────


def test_resolver_resistencia_nao_gasta_acao_sozinho():
    """Efeito colateral de economia dentro da função pura tornaria impossível
    testá-la sem simular um turno inteiro."""
    wm = _wm_conjurador()
    resolver_resistencia(
        wm, "Bola de Fogo", "g", nome_en="Fireball", nivel_slot=3, rng=random.Random(1)
    )
    assert wm.pode_agir() is True


def test_resolver_cura_nao_gasta_acao_sozinho():
    wm = _wm_conjurador()
    wm.player_hp = 5
    resolver_cura_de_magia(
        wm, "Curar Ferimentos", nome_en="Cure Wounds", rng=random.Random(1)
    )
    assert wm.pode_agir() is True
