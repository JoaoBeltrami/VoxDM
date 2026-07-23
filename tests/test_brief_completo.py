"""
O caminho do brief (produção, BRIEF_ATIVO=True) tem o que o resumo não codifica.

Por que existe (auditoria 22/07): 5 achados ALTO de lentes independentes
    convergiram na mesma raiz — `_montar_mensagens_brief` nasceu enxuto demais e
    perdeu blocos que o caminho legado sempre teve. O rolling summary carrega "o
    que aconteceu", mas NÃO carrega contra quem o jogador luta (ficha/PV do
    inimigo), o protocolo de combate, a voz distinta de cada NPC, nem os nudges
    de marcador. Resultado na mesa: combate cego, todo NPC igual, tom sempre
    chapado, mundo que não muda quando o jogador viaja.
Dependências: nenhuma externa — monta o prompt com WM offline.
Armadilha: estes testes miram o caminho do BRIEF especificamente. O legado tem
    cobertura própria em test_master_prompt; não os confunda.
"""

from engine.llm.prompt_builder import (
    ContextoMontado,
    _montar_mensagens_brief,
    _tier_do_turno,
)
from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import registrar_npc


def _ctx(wm, transcricao: str) -> ContextoMontado:
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


def _system(wm, transcricao: str) -> str:
    return _montar_mensagens_brief(_ctx(wm, transcricao))[0]["content"]


# ── COMBATE-CEGO-BRIEF-1: o Mestre precisa saber contra quem luta ─────────────

def test_combate_injeta_estado_do_inimigo_no_brief():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.entrar_combate()
    wm.registrar_inimigo("bandido-1", "Bandido", "ferido")
    s = _system(wm, "Ataco o bandido")
    assert "Bandido" in s
    assert "COMBATE ATIVO" in s          # rodada + inimigos


def test_combate_injeta_ficha_srd_quando_existe():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.entrar_combate()
    wm.registrar_inimigo("ogro-1", "Ogro", "intacto")
    wm.inimigos_combate["ogro-1"]["ficha"] = "Ogro — CR 2, CA 11, PV 59, clava 2d8+4"
    s = _system(wm, "Ataco o ogro")
    assert "CA 11" in s and "2d8+4" in s


def test_combate_injeta_protocolo_combat_md():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.entrar_combate()
    wm.registrar_inimigo("bandido-1", "Bandido", "intacto")
    s = _system(wm, "Ataco")
    assert "combat" in s.lower()          # combat.md carregado


# ── MESMICE-NPC / VOZ-DUPLA-SUMIU: NPC tem voz distinta ───────────────────────

def test_cena_social_injeta_social_e_voz_dupla():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.npcs_presentes = ["ferreiro"]
    registrar_npc(wm, "ferreiro", "Halvard")
    s = _system(wm, "Pergunto ao ferreiro sobre a guerra")
    # social.md fala de voz por NPC; voz_dupla.md fala de interpretar entre aspas
    assert "voz" in s.lower()
    assert "interpreta" in s.lower() or "aspas" in s.lower()


def test_combate_nao_carrega_camada_social():
    """Mutuamente exclusivos — combate não paga social.md por cima."""
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.entrar_combate()
    wm.npcs_presentes = ["bandido-1"]
    wm.registrar_inimigo("bandido-1", "Bandido", "intacto")
    s = _system(wm, "Ataco o bandido")
    # combat.md presente, mas o guia de camada social NÃO
    from engine.llm.prompt_builder import _carregar_social
    social = _carregar_social() or ""
    assert social[:40] not in s


# ── TOM-CHAPADO: o momento épico soa épico ────────────────────────────────────

def test_tier_epico_no_climax_da_campanha():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.arc_fase = "climax"
    assert _tier_do_turno(wm, "Ergo o estandarte") == "epico"
    s = _system(wm, "Ergo o estandarte")
    assert "momento-chave" in s
    assert "turno comum" not in s


def test_tier_epico_com_pacing_alto():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.pacing_nivel = 8.0
    assert _tier_do_turno(wm, "Avanço") == "epico"


def test_tier_seco_no_turno_comum():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    assert _tier_do_turno(wm, "Ando até a porta") == "seco"
    s = _system(wm, "Ando até a porta")
    assert "turno comum" in s


def test_tier_epico_em_linha_engine_de_critico():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    assert _tier_do_turno(wm, "ENGINE: teste de Ataque — 20 NATURAL no dado") == "epico"


# ── NUDGES-MORTOS: os empurrões de marcador voltam ao brief ───────────────────

def test_nudge_cena_no_deslocamento():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    s = _system(wm, "Vou para a estrada ao norte")
    assert "DESLOCAMENTO PEDIDO" in s


def test_nudge_inimigo_em_combate_sem_registro():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.entrar_combate()                    # em combate, zero inimigos
    s = _system(wm, "Continuo lutando")
    assert "COMBATE SEM COMBATENTE REGISTRADO" in s


def test_sem_nudge_inimigo_quando_ha_inimigo():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.entrar_combate()
    wm.registrar_inimigo("bandido-1", "Bandido", "intacto")
    s = _system(wm, "Ataco")
    assert "COMBATE SEM COMBATENTE REGISTRADO" not in s


def test_cena_calma_de_exploracao_fica_enxuta():
    """A dieta do brief se mantém quando não há combate nem NPC nem viagem."""
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    s = _system(wm, "Observo o horizonte em silêncio")
    assert "COMBATE ATIVO" not in s
    assert "DESLOCAMENTO PEDIDO" not in s
    # sem NPC não carrega social.md
    from engine.llm.prompt_builder import _carregar_social
    social = _carregar_social() or ""
    assert social[:40] not in s
