"""
Testes da Frente B — gating condicional de fragmentos do prompt.

Garante:
- voz_dupla.md só injeta quando wm.npc_vozes nao vazio
- markers_lista.md so injeta quando cena dramatica (em_combate / pacing alto /
  cliffhanger / fios / agendas)
- Em cena calma de exploracao, ambos sao omitidos
- chars_breakdown reflete o que foi injetado
"""



from engine.llm.prompt_builder import (
    _carregar_markers_lista,
    _carregar_voz_dupla,
    _cena_dramatica,
    montar_mensagens,
)
from engine.llm.types import ContextoMontado
from engine.memory.working_memory import WorkingMemory


def _wm_calmo() -> WorkingMemory:
    """WorkingMemory em cena de exploracao calma — sem voz NPC, pacing baixo."""
    wm = WorkingMemory.nova_sessao("loc", "Local", "sess-calmo")
    wm.pacing_nivel = 3.0
    return wm


def _ctx(wm: WorkingMemory) -> ContextoMontado:
    """ContextoMontado minimo com wm dado."""
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        spells_conhecidas=[],
        transcricao_atual="o que vejo aqui?",
    )


# ── _cena_dramatica heuristica ────────────────────────────────────────────────

def test_cena_dramatica_calma_retorna_false():
    wm = _wm_calmo()
    assert _cena_dramatica(wm) is False


def test_cena_dramatica_combate_retorna_true():
    wm = _wm_calmo()
    wm.em_combate = True
    assert _cena_dramatica(wm) is True


def test_cena_dramatica_pacing_alto_retorna_true():
    wm = _wm_calmo()
    wm.pacing_nivel = 4.5
    assert _cena_dramatica(wm) is True


def test_cena_dramatica_cliffhanger_retorna_true():
    wm = _wm_calmo()
    wm.cliffhanger_pendente = "Aldric ergue a faca, encara voce"
    assert _cena_dramatica(wm) is True


def test_cena_dramatica_fios_soltos_retorna_true():
    wm = _wm_calmo()
    wm.fios_soltos = ["jogador prometeu voltar pra Maren"]
    assert _cena_dramatica(wm) is True


def test_cena_dramatica_agenda_npcs_retorna_true():
    wm = _wm_calmo()
    wm.agenda_npcs = {"aldric": "esconde o pacto"}
    assert _cena_dramatica(wm) is True


# ── Carregamento dos fragmentos ────────────────────────────────────────────────

def test_fragmento_voz_dupla_carregavel():
    """voz_dupla.md deve estar presente e conter regras de aspas + atribuicao."""
    texto = _carregar_voz_dupla()
    assert texto is not None
    assert "aspas" in texto.lower()
    assert "atribui" in texto.lower()
    assert "voz dupla" in texto.lower()


def test_fragmento_markers_lista_carregavel():
    """markers_lista.md deve conter os marcadores principais."""
    texto = _carregar_markers_lista()
    assert texto is not None
    # Marcadores essenciais documentados
    for marker in ("[FIO:", "[CONSEQUÊNCIA:", "[XP:", "[COMBATE:", "[LAMPEJO:"):
        assert marker in texto, f"marker {marker} ausente em markers_lista.md"


# ── Integracao com montar_mensagens ────────────────────────────────────────────

# Strings UNICAS dos fragmentos — nao aparecem nos stubs deixados no master_system.md.
# Garantem que o teste checa o FRAGMENTO completo injetado, nao o stub resumido.
_MARKER_UNICO_VOZ_DUPLA = "passa de raspão"   # exemplo dentro do fragmento
# [CICATRIZ: só existe na lista completa — o master_system menciona apenas
# FIO/CONSEQUÊNCIA/XP/CENA/NPC.
#
# Histórico deste sentinela, que já trocou duas vezes pelo MESMO motivo — o
# marcador escolhido saiu do prompt:
#   - era "CR≤¼=25", removida na dieta de 01/07 (a tabela de XP por CR saiu do
#     prompt porque a engine paga abate/quest sozinha);
#   - virou "[RELOGIO_AVANCA:", que ficou OBSOLETO em 07/08 (P7 — quem avança
#     relógio é a engine; ver engine/markers.NOMES_OBSOLETOS).
# Se cair de novo, o conserto é o mesmo: escolher um marcador que esteja no
# fragmento e NÃO no master_system.md.
_MARKER_UNICO_MARKERS = "[CICATRIZ:"


def test_cena_calma_omite_ambos_fragmentos():
    """Exploracao pura — fragmentos completos nao entram (stubs no master_system ok)."""
    wm = _wm_calmo()
    mensagens = montar_mensagens(_ctx(wm))
    system = mensagens[0]["content"]
    assert _MARKER_UNICO_VOZ_DUPLA not in system, "voz_dupla.md vazou em cena calma"
    assert _MARKER_UNICO_MARKERS not in system, "markers_lista.md vazou em cena calma"


def test_cena_com_voz_npc_inclui_voz_dupla():
    """Quando wm.npc_vozes nao vazio, voz_dupla.md eh injetado por completo."""
    wm = _wm_calmo()
    wm.npc_vozes = {"lyssa": {"pitch": "+5Hz", "rate": "-10%"}}
    mensagens = montar_mensagens(_ctx(wm))
    system = mensagens[0]["content"]
    assert _MARKER_UNICO_VOZ_DUPLA in system


def test_combate_inclui_markers_lista():
    """Em combate, lista completa de markers entra (tabela XP visivel)."""
    wm = _wm_calmo()
    wm.em_combate = True
    mensagens = montar_mensagens(_ctx(wm))
    system = mensagens[0]["content"]
    assert _MARKER_UNICO_MARKERS in system
    assert "[COMBATE: iniciar]" in system


def test_pacing_alto_inclui_markers_lista():
    """Pacing >= 4 sinaliza ritmo dramatico, markers entram."""
    wm = _wm_calmo()
    wm.pacing_nivel = 5.0
    mensagens = montar_mensagens(_ctx(wm))
    system = mensagens[0]["content"]
    assert _MARKER_UNICO_MARKERS in system


def test_cena_dramatica_inclui_ambos_se_tem_npc_voz():
    """Cena dramatica + NPC com voz: ambos fragmentos entram."""
    wm = _wm_calmo()
    wm.em_combate = True
    wm.npc_vozes = {"toric": {"pitch": "-5Hz", "rate": "+0%"}}
    mensagens = montar_mensagens(_ctx(wm))
    system = mensagens[0]["content"]
    assert _MARKER_UNICO_VOZ_DUPLA in system
    assert _MARKER_UNICO_MARKERS in system


# ── Economia mensuravel ────────────────────────────────────────────────────────

def test_cena_calma_system_menor_que_dramatica():
    """Sistema prompt em exploracao calma deve ser menor que em combate.

    Diferenca esperada: ~2000 chars (voz_dupla 600 + markers 1500).
    Margem de teste: 1500 chars pra absorver variacao de outros blocos.
    """
    wm_calmo = _wm_calmo()
    wm_drama = _wm_calmo()
    wm_drama.em_combate = True
    wm_drama.npc_vozes = {"x": {"pitch": "+0Hz", "rate": "+0%"}}

    sys_calmo = montar_mensagens(_ctx(wm_calmo))[0]["content"]
    sys_drama = montar_mensagens(_ctx(wm_drama))[0]["content"]

    # Combate injeta tambem combat.md e saves.md — diferenca total esperada
    # bem maior que so os fragmentos. Garante apenas que calmo < drama.
    assert len(sys_calmo) < len(sys_drama)
    # Voz dupla + markers sozinhos somam pelo menos 1500 chars
    delta_minimo_esperado = 1500
    assert len(sys_drama) - len(sys_calmo) >= delta_minimo_esperado


# ── TOKENS-21K: decomposicao do bucket "outros" ────────────────────────────────

# Chaves novas que decompoem o antigo "outros" invisivel (~10k chars no teste #6).
_CHAVES_BREAKDOWN_NOVAS = (
    "social_md", "saves_md", "dice_md", "quests_md",
    "canon", "relacoes_grafo", "rolling_summary", "lembrete_saida",
)


def _capturar_breakdown(wm: WorkingMemory) -> dict:
    """Roda montar_mensagens e extrai o chars_breakdown do log prompt_montado."""
    import structlog

    with structlog.testing.capture_logs() as logs:
        montar_mensagens(_ctx(wm))
    eventos = [e for e in logs if e.get("event") == "prompt_montado"]
    assert eventos, "log prompt_montado nao capturado"
    return eventos[-1]["chars_breakdown"]


def test_breakdown_tem_chaves_decompostas():
    """As novas chaves existem no breakdown mesmo quando o bloco nao foi injetado."""
    bd = _capturar_breakdown(_wm_calmo())
    for chave in _CHAVES_BREAKDOWN_NOVAS:
        assert chave in bd, f"chave {chave} ausente no breakdown"
    assert bd["lembrete_saida"] > 0  # _LEMBRETE_SAIDA e constante, sempre presente


def test_breakdown_mede_social_md_quando_injetado():
    """social.md (maior culpado oculto do 'outros') vira bucket proprio mensuravel."""
    wm = _wm_calmo()
    wm.npcs_presentes = ["mira"]  # NPC presente fora de combate -> social.md injeta
    bd = _capturar_breakdown(wm)
    assert bd["social_md"] > 0


def test_breakdown_soma_fecha_o_total_sem_dupla_contagem():
    """Invariante: a soma dos buckets == tamanho do system prompt (outros e residuo)."""
    import structlog

    wm = _wm_calmo()
    wm.npcs_presentes = ["mira"]
    with structlog.testing.capture_logs() as logs:
        system = montar_mensagens(_ctx(wm))[0]["content"]
    bd = [e for e in logs if e.get("event") == "prompt_montado"][-1]["chars_breakdown"]
    assert bd["outros"] >= 0
    assert sum(bd.values()) == len(system)
