"""Testes do marker [COMBATE: iniciar] — engine-authority pra entrar em combate.

Por que existe: bug COMBATE-VERB-1 (26/05) — RE_COMBATE em texto do jogador não
cobre todos os casos (sparring narrado, declarações indiretas, "uso X em Y"
fora do conjunto coberto). O Mestre pode emitir [COMBATE: iniciar] quando
percebe que a ação é bélica mas a engine não detectou.

Dependências: pytest.
Armadilha: o marker tem efeito a partir do *próximo* turno (combat.md +
saves.md + initiative entram na próxima montagem de prompt). O turno em que
ele é emitido ainda foi narrado sem combat.md — comportamento aceito.
"""


from api.turn_pipeline import _RE_COMBATE_MARKER, aplicar_pos_turno
from engine.memory.quest_detector import strip_marcadores
from engine.memory.working_memory import WorkingMemory


def _wm_exploracao() -> WorkingMemory:
    """WM em estado de exploração — sem combate."""
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    assert not wm.em_combate
    return wm


# ── Regex ────────────────────────────────────────────────────────────────────


def test_marker_simples():
    assert _RE_COMBATE_MARKER.search("[COMBATE: iniciar]") is not None


def test_marker_case_insensitive():
    assert _RE_COMBATE_MARKER.search("[combate: iniciar]") is not None
    assert _RE_COMBATE_MARKER.search("[COMBATE: INICIAR]") is not None


def test_marker_com_espacos():
    assert _RE_COMBATE_MARKER.search("[COMBATE:  iniciar  ]") is not None


def test_marker_nao_casa_outras_palavras():
    # Apenas "iniciar" é aceito — palavras decorativas tipo "encerrar" ou
    # "pausar" não devem ativar o handler.
    assert _RE_COMBATE_MARKER.search("[COMBATE: encerrar]") is None
    assert _RE_COMBATE_MARKER.search("[COMBATE: pausar]") is None


def test_marker_no_meio_de_narrativa():
    texto = (
        "Tóric se posiciona, espada erguida. [COMBATE: iniciar] "
        "O ar fica denso, ambos esperam o primeiro golpe."
    )
    assert _RE_COMBATE_MARKER.search(texto) is not None


# ── Integração com aplicar_pos_turno ──────────────────────────────────────────


def test_marker_inicia_combate_quando_fora_de_combate():
    wm = _wm_exploracao()
    aplicar_pos_turno(
        wm,
        "Vou usar chama sagrada nele.",
        "Você canaliza a luz divina sobre o orc. [COMBATE: iniciar] A claridade arde no ar.",
    )
    assert wm.em_combate


def test_marker_nao_quebra_combate_ja_ativo():
    """Se já em combate, marker é noop (idempotente)."""
    wm = _wm_exploracao()
    wm.entrar_combate()
    aplicar_pos_turno(
        wm,
        "ataco o goblin",
        "O ataque conecta. [COMBATE: iniciar] O segundo orc avança.",
    )
    assert wm.em_combate  # ainda ativo


def test_marker_e_removido_do_texto_de_voz():
    """Marker não pode chegar ao TTS — strip_marcadores deve removê-lo."""
    texto = "Você usa a habilidade. [COMBATE: iniciar] O combate começa."
    limpo = strip_marcadores(texto)
    assert "[COMBATE" not in limpo
    assert "iniciar]" not in limpo
    # Texto narrativo permanece
    assert "Você usa a habilidade." in limpo
    assert "O combate começa." in limpo
