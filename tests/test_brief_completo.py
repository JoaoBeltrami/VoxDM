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
    """Tier seco = sem peso dramático. O TEXTO do TOM varia com o ritmo
    (tell C, 24/07) — o que não pode aparecer é a instrução de momento-chave."""
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    assert _tier_do_turno(wm, "Ando até a porta") == "seco"
    s = _system(wm, "Ando até a porta")
    assert "momento-chave" not in s
    assert "TOM:" in s


def test_tier_relaxa_apos_campanha_concluida():
    """R1 (verificação 23/07): pós-conclusão o tom volta ao comum — não fica
    épico pra sempre se o jogador continua depois do fim."""
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.arc_fase = "epilogo"
    assert _tier_do_turno(wm, "Contemplo o campo") == "epico"   # epílogo tem peso
    wm.arc_fase = "concluida"
    assert _tier_do_turno(wm, "Sigo vivendo") == "seco"         # denouement relaxa


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


# ── GUARDA-REPETICAO: anti-repetição de imagem no brief ──────────────────────

def test_ambiente_recente_entra_no_brief():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.narrative.registrar_ambiente("o frio cortante da noite")
    wm.narrative.registrar_ambiente("o cheiro de fumaça de lenha")
    s = _system(wm, "Sigo em frente")
    assert "não repita" in s
    assert "frio cortante" in s and "cheiro de fumaça" in s


def test_sem_ambiente_nao_injeta_bloco():
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    s = _system(wm, "Sigo em frente")
    assert "AMBIENTAÇÃO JÁ DESCRITA" not in s


# ── TELL C: o ritmo varia por decisão da ENGINE ──────────────────────────────
#
# Medição 24/07: dizer "1-3 frases" em TODO turno É a monotonia — o modelo
# converge no mesmo tamanho e a sessão vira metrônomo. Quem alterna é a engine.

def test_pergunta_curta_pede_corte_seco():
    from engine.llm.prompt_builder import _ritmo_do_turno
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    assert _ritmo_do_turno(wm, "Quanto custa?") == "curto"
    assert _ritmo_do_turno(wm, "Olho ao redor") == "curto"


def test_local_novo_pede_ar():
    from engine.llm.prompt_builder import _ritmo_do_turno
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    assert _ritmo_do_turno(wm, "Vou para a estrada ao norte com calma") == "longo"


def test_ritmo_rotaciona_e_nao_repete_tres_vezes():
    """A alternância é o ponto: três turnos comuns seguidos não podem sair
    todos com o mesmo fôlego."""
    from engine.llm.prompt_builder import _ritmo_do_turno
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    fala = "Converso com o ferreiro sobre o preço do aço nesta temporada"
    vistos = []
    for i in range(3):
        wm.iteracoes = i
        vistos.append(_ritmo_do_turno(wm, fala))
    assert len(set(vistos)) == 3, f"ritmo não variou: {vistos}"


def test_instrucao_de_ritmo_chega_ao_prompt():
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    wm.iteracoes = 1          # → curto
    s = _system(wm, "Converso com o ferreiro sobre o preço do aço nesta temporada")
    assert "responda e PARE" in s.lower() or "responda e pare" in s.lower()
    assert "nada de gancho" in s          # o slot removido é o que encurta
    wm.iteracoes = 2          # → longo
    s2 = _system(wm, "Converso com o ferreiro sobre o preço do aço nesta temporada")
    assert "RESPIRAR" in s2


def test_orcamento_de_palavras_acompanha_o_ritmo():
    """TELL C, diagnóstico de 24/07: o modelo não obedece "UMA frase" (adesão
    0/5 em 16 turnos), mas escreve SEMPRE até encher o teto de palavras — 67 a
    94, colado nos 80 declarados. O teto é lido como ALVO, não como limite.
    Logo, a alavanca do ritmo é o ORÇAMENTO, não a contagem de frases."""
    from engine.llm.prompt_builder import _lembrete_saida

    assert "30 palavras" in _lembrete_saida("curto")
    assert "80 palavras" in _lembrete_saida("medio")
    assert "110 palavras" in _lembrete_saida("longo")
    assert "80 palavras" in _lembrete_saida("valor-invalido")   # fallback seguro


def test_prompt_do_turno_curto_pede_orcamento_menor():
    wm = WorkingMemory.nova_sessao("k", "K", "s")
    s = _system(wm, "Quem é o dono daqui?")        # pergunta curta → curto
    assert "30 palavras" in s
    assert "80 palavras" not in s
