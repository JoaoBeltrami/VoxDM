"""Testes do Pacote 1 dos Pilares do Mestre Virtual (10/06).

Pilar Perigo: [DANO]/[CURA] (HP autoritativo na engine), death_policy
    (narrativo|mortal) com protocolo de 0 PV no prompt, [CICATRIZ] permanente,
    e o beat de turno inimigo (engine conduz a resposta dos inimigos).
Pilar Mundo Vivo: Relógios de Ameaça — criação via [RELOGIO], avanço dramático
    via [RELOGIO_AVANCA], ticks da engine (descanso longo, viagem), irrupção
    one-shot no prompt quando enchem.
Ritual de mesa: modo episódio — momento_de_fecho() pós-clímax, one-shot.

Offline — sem Qdrant/Neo4j/Groq/Edge TTS reais.
"""

from types import SimpleNamespace

import pytest

from api.turn_pipeline import (
    _RE_CICATRIZ,
    _RE_CURA,
    _RE_DANO,
    _RE_RELOGIO,
    _RE_RELOGIO_AVANCA,
    aplicar_pos_turno,
)
from engine.llm.prompt_builder import montar_mensagens
from engine.llm.types import ContextoMontado
from engine.memory.working_memory import WorkingMemory


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("vila", "Vila", "sess-test", **kw)


def _ctx(wm, transcricao="o que eu vejo?") -> ContextoMontado:
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


# ══ Pilar Perigo — [DANO] / [CURA] ════════════════════════════════════════════


def test_regex_dano_e_cura():
    m = _RE_DANO.search("A lâmina abre seu ombro. [DANO: -7 lança do goblin]")
    assert m is not None and m.group(1) == "7"
    m2 = _RE_CURA.search("O calor se espalha. [CURA: +5 poção]")
    assert m2 is not None and m2.group(1) == "5"


def test_dano_reduz_hp_do_jogador():
    wm = _wm(player_hp=20, player_hp_max=20)
    aplicar_pos_turno(wm, "Avanço!", "O golpe acerta em cheio. [DANO: -7 maça]")
    assert wm.player_hp == 13


def test_dano_alucinado_clampa_em_hp_max_por_aplicacao():
    """[DANO: -999] não pode tirar mais que hp_max num golpe só."""
    wm = _wm(player_hp=20, player_hp_max=20)
    aplicar_pos_turno(wm, "Avanço!", "Tudo escurece. [DANO: -999 meteoro]")
    assert wm.player_hp == 0  # floor em 0, nunca negativo


def test_cura_clampa_em_hp_max_e_reseta_death_saves():
    wm = _wm(player_hp=20, player_hp_max=20)
    wm.character.hp_current = 0
    wm.character.death_saves_failures = 2
    aplicar_pos_turno(wm, "", "Você volta a si. [CURA: +50 milagre]")
    assert wm.player_hp == 20
    assert wm.death_saves_failures == 0


def test_dano_e_cura_no_mesmo_turno_em_ordem():
    wm = _wm(player_hp=20, player_hp_max=20)
    aplicar_pos_turno(wm, "", "Dói, mas a poção age. [DANO: -8 flecha] [CURA: +3 poção]")
    assert wm.player_hp == 15


# ══ Pilar Perigo — [CICATRIZ] ═════════════════════════════════════════════════


def test_regex_cicatriz():
    m = _RE_CICATRIZ.search("[CICATRIZ: queimadura ácida no antebraço esquerdo]")
    assert m is not None and "queimadura" in m.group(1)


def test_cicatriz_registrada_com_dedup_e_cap():
    wm = _wm()
    for _ in range(2):
        aplicar_pos_turno(wm, "", "Sobrou marca. [CICATRIZ: corte no rosto]")
    assert wm.cicatrizes == ["corte no rosto"]
    for i in range(6):
        wm.character.registrar_cicatriz(f"marca {i}")
    assert len(wm.cicatrizes) == 5  # cap


def test_cicatriz_persiste_no_dm_state_roundtrip():
    from api.routes.session import _wm_para_dm_state

    wm = _wm()
    wm.character.registrar_cicatriz("olho leitoso pós-ritual")
    wm.narrative.criar_relogio("ritual", "O ritual de Valdrek", 6)
    dm_state = _wm_para_dm_state(wm)
    assert "olho leitoso pós-ritual" in dm_state["cicatrizes"]
    assert "ritual" in dm_state["relogios"]

    wm2 = _wm()
    wm2.aplicar_character_state(SimpleNamespace(dm_state=dm_state))
    assert "olho leitoso pós-ritual" in wm2.cicatrizes
    assert wm2.narrative.relogios["ritual"]["nome"] == "O ritual de Valdrek"


def test_cicatrizes_aparecem_no_prompt():
    wm = _wm()
    wm.character.registrar_cicatriz("três garras no peito")
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "CICATRIZES" in system and "três garras no peito" in system


# ══ Pilar Perigo — death_policy + protocolo 0 PV ══════════════════════════════


def test_death_policy_invalida_cai_no_default():
    wm = _wm(death_policy="hardcore-inventado")
    assert wm.death_policy == "narrativo"


def test_protocolo_zero_pv_narrativo():
    wm = _wm(death_policy="narrativo")
    wm.character.hp_current = 0
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "DERROTA COM CUSTO" in system
    assert "NÃO o mate" in system


def test_protocolo_zero_pv_mortal():
    wm = _wm(death_policy="mortal")
    wm.character.hp_current = 0
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "PROTOCOLO MORTAL" in system
    assert "MORTE REAL" in system


def test_protocolo_zero_pv_ausente_com_hp_positivo():
    wm = _wm(death_policy="mortal")
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "PROTOCOLO MORTAL" not in system
    assert "DERROTA COM CUSTO" not in system


# ══ Mundo Vivo — Relógios de Ameaça ═══════════════════════════════════════════


def test_regex_relogio_e_avanca():
    m = _RE_RELOGIO.search("[RELOGIO: ritual-valdrek|O ritual dos Filhos|6]")
    assert m is not None and m.group(1) == "ritual-valdrek" and m.group(3) == "6"
    m2 = _RE_RELOGIO.search("[RELOGIO: cacada|A caçada começa]")
    assert m2 is not None and m2.group(1) == "cacada" and m2.group(3) is None
    m3 = _RE_RELOGIO_AVANCA.search("[RELOGIO_AVANCA: ritual-valdrek]")
    assert m3 is not None and m3.group(1) == "ritual-valdrek"


def test_criar_relogio_idempotente_com_cap_e_clamp():
    wm = _wm()
    assert wm.narrative.criar_relogio("a", "Ameaça A", 2) is True
    assert wm.narrative.relogios["a"]["max"] == 3  # clamp mínimo
    assert wm.narrative.criar_relogio("a", "Duplicado", 6) is False  # idempotente
    for rid in ("b", "c", "d"):
        wm.narrative.criar_relogio(rid, rid.upper(), 6)
    assert wm.narrative.criar_relogio("e", "Quinto", 6) is False  # cap 4


def test_relogio_enche_e_gera_irrupcao_one_shot():
    wm = _wm()
    wm.narrative.criar_relogio("ritual", "O ritual", 3)
    assert wm.narrative.avancar_relogio("ritual") is False
    assert wm.narrative.avancar_relogio("ritual") is False
    assert wm.narrative.avancar_relogio("ritual") is True  # encheu
    assert "ritual" not in wm.narrative.relogios  # removido
    assert wm.narrative.consumir_relogio_irrompido() == "O ritual"
    assert wm.narrative.consumir_relogio_irrompido() == ""  # one-shot


def test_pipeline_cria_e_avanca_relogio():
    wm = _wm()
    aplicar_pos_turno(wm, "Aceito a missão.", "Que assim seja. [RELOGIO: cacada|A caçada|4]")
    assert wm.narrative.relogios["cacada"]["atual"] == 0
    aplicar_pos_turno(wm, "Continuo bebendo na taverna.", "Você ignora os uivos lá fora. [RELOGIO_AVANCA: cacada]")
    assert wm.narrative.relogios["cacada"]["atual"] == 1


def test_descanso_longo_tica_todos_os_relogios():
    wm = _wm()
    wm.narrative.criar_relogio("ritual", "O ritual", 6)
    aplicar_pos_turno(wm, "Vamos descansar.", "A noite passa. [DESCANSO: longo]")
    assert wm.narrative.relogios["ritual"]["atual"] == 1


def test_viagem_tica_todos_os_relogios():
    wm = _wm()
    wm.narrative.criar_relogio("ritual", "O ritual", 6)
    aplicar_pos_turno(wm, "Sigo pra estrada.", "Vocês partem. [CENA: estrada|Estrada|dia]")
    assert wm.narrative.relogios["ritual"]["atual"] == 1


def test_relogios_aparecem_no_prompt_com_segmentos():
    wm = _wm()
    wm.narrative.criar_relogio("ritual", "O ritual", 4)
    wm.narrative.avancar_relogio("ritual")
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "RELÓGIOS DE AMEAÇA" in system
    assert "▓░░░ 1/4" in system


def test_irrupcao_injetada_uma_vez_no_prompt():
    wm = _wm()
    wm.narrative.criar_relogio("ritual", "O ritual sombrio", 3)
    wm.narrative.avancar_relogio("ritual", passos=3)
    system1 = montar_mensagens(_ctx(wm))[0]["content"]
    assert "RELÓGIO ESTOUROU: O ritual sombrio" in system1
    system2 = montar_mensagens(_ctx(wm))[0]["content"]
    assert "RELÓGIO ESTOUROU" not in system2  # one-shot consumido


# ══ Pilar Perigo — beat do turno inimigo ══════════════════════════════════════


class _GroqNuncaChamado:
    async def completar(self, *a, **kw):  # pragma: no cover - falha se chamado
        raise AssertionError("beat não devia ter chamado o LLM")


class _GroqSoMarkers:
    """Retorna resposta só-markers: pipeline aplica, mas nada vai pro frontend."""

    def __init__(self) -> None:
        self.chamadas = 0

    async def completar(self, *a, **kw) -> str:
        self.chamadas += 1
        return "[DANO: -5 lança do guarda]"


class _WsNuncaUsado:
    async def send_text(self, *a, **kw):  # pragma: no cover - falha se chamado
        raise AssertionError("beat só-markers não devia enviar nada ao frontend")


def _sessao_fake(wm, groq) -> SimpleNamespace:
    return SimpleNamespace(working_mem=wm, groq=groq)


@pytest.mark.asyncio
async def test_beat_nao_roda_fora_de_combate():
    from api.websocket import _beat_turno_inimigo

    wm = _wm()
    await _beat_turno_inimigo(_WsNuncaUsado(), _sessao_fake(wm, _GroqNuncaChamado()), "Ataco o goblin!")


@pytest.mark.asyncio
async def test_beat_nao_roda_sem_inimigos_vivos():
    from api.websocket import _beat_turno_inimigo

    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "morto")
    await _beat_turno_inimigo(_WsNuncaUsado(), _sessao_fake(wm, _GroqNuncaChamado()), "Ataco!")


@pytest.mark.asyncio
async def test_beat_nao_roda_sem_acao_de_combate():
    """Fala social em combate não cede o turno aos inimigos."""
    from api.websocket import _beat_turno_inimigo

    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    await _beat_turno_inimigo(
        _WsNuncaUsado(), _sessao_fake(wm, _GroqNuncaChamado()), "Esperem! Podemos conversar!"
    )


@pytest.mark.asyncio
async def test_beat_nao_roda_com_jogador_a_zero():
    from api.websocket import _beat_turno_inimigo

    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.character.hp_current = 0
    await _beat_turno_inimigo(_WsNuncaUsado(), _sessao_fake(wm, _GroqNuncaChamado()), "Ataco!")


@pytest.mark.asyncio
async def test_beat_aplica_dano_do_turno_inimigo():
    """Ataque do jogador → beat roda → [DANO] do LLM reduz HP de verdade."""
    from api.websocket import _beat_turno_inimigo

    wm = _wm(player_hp=20, player_hp_max=20)
    wm.entrar_combate()
    wm.registrar_inimigo("guarda", "Guarda", "intacto")
    groq = _GroqSoMarkers()
    await _beat_turno_inimigo(_WsNuncaUsado(), _sessao_fake(wm, groq), "Ataco o guarda!")
    assert groq.chamadas == 1
    assert wm.player_hp == 15


@pytest.mark.asyncio
async def test_beat_roda_apos_rolagem_resolvida():
    from api.websocket import _beat_turno_inimigo

    wm = _wm(player_hp=20, player_hp_max=20)
    wm.entrar_combate()
    wm.registrar_inimigo("guarda", "Guarda", "intacto")
    groq = _GroqSoMarkers()
    await _beat_turno_inimigo(_WsNuncaUsado(), _sessao_fake(wm, groq), "[Rolagem: d20+5 = 18]")
    assert groq.chamadas == 1


# ══ Ritual de mesa — modo episódio ════════════════════════════════════════════


def _narrative_pronto_pra_fecho(wm):
    wm.narrative.turnos_total = 25
    wm.narrative.pico_pacing = 8.0
    wm.narrative.pacing_nivel = 2.0
    return wm.narrative


def test_momento_de_fecho_exige_todas_as_condicoes():
    wm = _wm()
    n = wm.narrative
    n.turnos_total, n.pico_pacing, n.pacing_nivel = 25, 8.0, 2.0
    n.turnos_total = 10
    assert n.momento_de_fecho() is False  # poucos turnos
    n.turnos_total, n.pico_pacing = 25, 5.0
    assert n.momento_de_fecho() is False  # sem clímax real
    n.pico_pacing, n.pacing_nivel = 8.0, 6.0
    assert n.momento_de_fecho() is False  # ritmo ainda alto


def test_momento_de_fecho_e_one_shot():
    wm = _wm()
    n = _narrative_pronto_pra_fecho(wm)
    assert n.momento_de_fecho() is True
    assert n.momento_de_fecho() is False  # já sugerido


def test_fecho_injetado_no_prompt_so_em_modo_episodio():
    wm = _wm(modo_episodio=True)
    _narrative_pronto_pra_fecho(wm)
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "MOMENTO DE FECHO" in system

    wm2 = _wm(modo_episodio=False)
    _narrative_pronto_pra_fecho(wm2)
    system2 = montar_mensagens(_ctx(wm2))[0]["content"]
    assert "MOMENTO DE FECHO" not in system2


def test_pico_pacing_acompanha_ajustes():
    wm = _wm()
    for _ in range(4):
        wm.narrative.ajustar_pacing(em_combate=True, saiu_combate_recentemente=False, trust_mudou=False)
    assert wm.narrative.pico_pacing >= 8.0
    assert wm.narrative.turnos_total == 4


# ══ PACOTE 2 — Mundo Vivo restante + Ritual ══════════════════════════════════


def test_tracking_de_arco_roda_no_pipeline():
    """Regressão do bug do pacote 1: o pipeline calcula pacing inline e não
    chama ajustar_pacing() — turnos_total/pico_pacing nunca subiam em produção
    e momento_de_fecho() jamais disparava."""
    wm = _wm()
    wm.entrar_combate()
    aplicar_pos_turno(wm, "Ataco o goblin!", "O aço encontra carne.")
    assert wm.narrative.turnos_total == 1
    assert wm.narrative.pico_pacing >= 4.0  # combate subiu o pacing e o pico seguiu


# ── NPC toma a iniciativa ────────────────────────────────────────────────────


def _wm_com_agenda(presente: bool) -> WorkingMemory:
    wm = _wm()
    wm.narrative.agenda_npcs["mira"] = "descobrir o que o jogador sabe do ritual"
    wm.npcs_presentes = ["mira"] if presente else ["taverneiro"]
    return wm


def test_iniciativa_npc_dispara_apos_calmaria_com_cooldown():
    wm = _wm_com_agenda(presente=True)
    for _ in range(5):
        aplicar_pos_turno(wm, "Olho ao redor da praça.", "A tarde segue mansa.")
    pendente = wm.narrative.iniciativa_npc_pendente
    assert pendente is not None
    npc_id, plano, presente = pendente
    assert npc_id == "mira" and presente is True
    assert "ritual" in plano


def test_iniciativa_npc_ausente_vira_sinal():
    wm = _wm_com_agenda(presente=False)
    for _ in range(5):
        aplicar_pos_turno(wm, "Sigo observando o movimento.", "Nada muda.")
    pendente = wm.narrative.iniciativa_npc_pendente
    assert pendente is not None and pendente[2] is False  # não está na cena


def test_iniciativa_npc_nao_dispara_em_combate():
    wm = _wm_com_agenda(presente=True)
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin", "intacto")
    for _ in range(6):
        aplicar_pos_turno(wm, "Ataco o goblin!", "Vocês trocam golpes.")
    assert wm.narrative.iniciativa_npc_pendente is None


def test_iniciativa_npc_sem_agenda_nao_dispara():
    wm = _wm()
    wm.npcs_presentes = ["mira"]
    for _ in range(8):
        aplicar_pos_turno(wm, "Olho ao redor.", "Tudo calmo.")
    assert wm.narrative.iniciativa_npc_pendente is None


def test_iniciativa_npc_one_shot_e_cooldown():
    wm = _wm_com_agenda(presente=True)
    for _ in range(5):
        aplicar_pos_turno(wm, "Espero na praça.", "O tempo passa.")
    assert wm.narrative.consumir_iniciativa_npc() is not None
    assert wm.narrative.consumir_iniciativa_npc() is None  # one-shot
    # Cooldown zerado no disparo: o turno seguinte NÃO re-arma de imediato
    aplicar_pos_turno(wm, "Continuo esperando.", "Nada ainda.")
    assert wm.narrative.iniciativa_npc_pendente is None


def test_iniciativa_npc_injetada_no_prompt():
    wm = _wm_com_agenda(presente=True)
    wm.narrative.iniciativa_npc_pendente = ("mira", "cobrar a dívida", True)
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "INICIATIVA DE NPC" in system and "Mira" in system and "cobrar a dívida" in system
    # Consumido — não repete no próximo prompt
    system2 = montar_mensagens(_ctx(wm))[0]["content"]
    assert "INICIATIVA DE NPC" not in system2


def test_sinal_de_npc_ausente_injetado_no_prompt():
    wm = _wm()
    wm.narrative.iniciativa_npc_pendente = ("velho-sabio", "alertar sobre a mina", False)
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "SINAL DE NPC" in system and "não o NPC em pessoa" in system


# ── Ecos de consequência (retorno a local conhecido) ─────────────────────────


def test_retorno_a_local_conhecido_seta_flag_one_shot():
    wm = _wm()  # começa em "vila"
    aplicar_pos_turno(wm, "Sigo pra estrada.", "Vocês partem. [CENA: estrada|Estrada]")
    assert "vila" in wm.scene.locais_visitados
    assert wm.scene.retorno_local_conhecido is False  # estrada é nova
    aplicar_pos_turno(wm, "Volto pra vila.", "O caminho de volta. [CENA: vila|Vila]")
    assert wm.scene.consumir_retorno_local() is True
    assert wm.scene.consumir_retorno_local() is False  # one-shot


def test_eco_injetado_no_prompt_no_retorno():
    wm = _wm()
    wm.registrar_consequencia("A guarda de Drevamor desconfia do jogador")
    aplicar_pos_turno(wm, "Pra estrada.", "[CENA: estrada|Estrada]")
    aplicar_pos_turno(wm, "De volta.", "[CENA: vila|Vila]")
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "RETORNO A LOCAL CONHECIDO" in system
    assert "guarda de Drevamor" in system
    system2 = montar_mensagens(_ctx(wm))[0]["content"]
    assert "RETORNO A LOCAL CONHECIDO" not in system2  # one-shot


# ── Perfil do jogador ────────────────────────────────────────────────────────


def test_perfil_classifica_estilos_no_pipeline():
    wm = _wm()
    aplicar_pos_turno(wm, "Ataco o goblin com tudo!", "Aço no ar.")
    aplicar_pos_turno(wm, "Pergunto ao taverneiro sobre a mina.", "Ele coça a barba.")
    aplicar_pos_turno(wm, "Examino as marcas no chão.", "Pegadas recentes.")
    e = wm.narrative.estilo_jogador
    assert e["combate"] == 1 and e["social"] == 1 and e["exploracao"] == 1


def test_estilo_dominante_exige_amostra_e_dominancia():
    wm = _wm()
    n = wm.narrative
    n.estilo_jogador = {"social": 5, "combate": 2}
    assert n.estilo_dominante() is None  # amostra < 10
    n.estilo_jogador = {"social": 4, "combate": 4, "exploracao": 4}
    assert n.estilo_dominante() is None  # equilibrado (33% < 45%)
    n.estilo_jogador = {"social": 9, "combate": 3, "exploracao": 2}
    dom = n.estilo_dominante()
    assert dom is not None and dom[0] == "social" and dom[1] == 9 and dom[2] == 14


def test_perfil_no_prompt_gated_por_combate():
    wm = _wm()
    wm.narrative.estilo_jogador = {"social": 9, "combate": 3, "exploracao": 2}
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "PERFIL DO JOGADOR" in system and "resolver na conversa" in system

    wm.entrar_combate()
    system2 = montar_mensagens(_ctx(wm, "ataco o orc"))[0]["content"]
    assert "PERFIL DO JOGADOR" not in system2  # budget de combate protegido


def test_perfil_e_locais_persistem_no_dm_state():
    from api.routes.session import _wm_para_dm_state

    wm = _wm()
    wm.narrative.estilo_jogador = {"social": 7}
    wm.scene.locais_visitados.add("mina-abandonada")
    dm_state = _wm_para_dm_state(wm)
    assert dm_state["estilo_jogador"] == {"social": 7}
    assert "mina-abandonada" in dm_state["locais_visitados"]

    wm2 = _wm()
    wm2.aplicar_character_state(SimpleNamespace(dm_state=dm_state))
    assert wm2.narrative.estilo_jogador == {"social": 7}
    assert "mina-abandonada" in wm2.scene.locais_visitados


# ══ PACOTE 3 — Session Zero por voz ══════════════════════════════════════════


def test_chargen_atributos_por_classe():
    from engine.chargen import gerar_atributos

    mago = gerar_atributos("Mago")
    assert mago["int_score"] == 15 and mago["con_score"] == 14 and mago["str_score"] == 8
    barbaro = gerar_atributos("Bárbaro")
    assert barbaro["str_score"] == 15 and barbaro["int_score"] == 8
    desconhecida = gerar_atributos("Cavaleiro do Caos")
    assert desconhecida["str_score"] == 15  # ordem genérica


def test_chargen_normalizar_classe():
    from engine.chargen import normalizar_classe

    assert normalizar_classe("guerreira") == "Guerreiro"
    assert normalizar_classe("LADRÃO") == "Ladino"
    assert normalizar_classe("patrulheiro") == "Ranger"
    assert normalizar_classe("clerigo") == "Clérigo"
    assert normalizar_classe("necromante") == ""


def test_chargen_hp_nivel():
    from engine.chargen import hp_nivel

    # Guerreiro (d10) nv3, CON +2: 10+2 + 2×(6+2) = 28
    assert hp_nivel("Guerreiro", 3, 2) == 28
    # Mago (d6) nv1, CON 0: 6
    assert hp_nivel("Mago", 1, 0) == 6
    # CON muito negativa nunca zera
    assert hp_nivel("Mago", 3, -5) >= 3


def test_regex_ficha_com_e_sem_traco():
    from api.turn_pipeline import _RE_FICHA

    m = _RE_FICHA.search("[FICHA: Kael|Meio-orc|Guerreiro|soldado desertor|procura o irmão]")
    assert m is not None
    assert m.group(1) == "Kael" and m.group(3) == "Guerreiro"
    assert m.group(5) == "procura o irmão"
    m2 = _RE_FICHA.search("[FICHA: Mira|Humana|maga|aprendiz expulsa]")
    assert m2 is not None and m2.group(5) is None


def test_ficha_aplica_personagem_completo_e_desliga_modo():
    wm = _wm(session_zero=True)
    assert wm.session_zero_ativa is True
    aplicar_pos_turno(
        wm, "Sou a Mira, uma maga.",
        "Então é assim que Mira entra na história. [FICHA: Mira|Humana|maga|aprendiz expulsa|provar seu valor]",
    )
    assert wm.session_zero_ativa is False
    ch = wm.character
    assert ch.player_name == "Mira"
    assert ch.player_class == "Mago"          # alias normalizado
    assert ch.int_score == 15                  # standard array priorizado
    assert ch.hp_max == ch.hp_current > 0
    assert ch.hit_dice_type == 6               # d6 de Mago
    assert ch.spell_slots, "Mago nível 3 precisa de spell slots"
    assert "provar seu valor" in ch.player_description


def test_ficha_popula_repertorio_de_magias_para_conjurador():
    """Regressão (13/06): Session Zero não populava spells_conhecidas → guard de
    cast liberava QUALQUER magia (o LLM deixava o jogador inventar feitiços fora
    da classe). Conjurador deve nascer com o repertório da classe; o nome só vale
    como conhecido se for da lista."""
    wm = _wm(session_zero=True)
    aplicar_pos_turno(
        wm, "Sou a Mira, uma maga.",
        "Que comece. [FICHA: Mira|Humana|maga|aprendiz expulsa|provar seu valor]",
    )
    from engine.magic.spell_list import spells_da_classe

    ch = wm.character
    assert ch.spells_conhecidas, "Mago nível 3 precisa nascer com magias conhecidas"
    # O repertório é estritamente um subconjunto da lista da classe — prova que é
    # class-scoped, não arbitrário. Magia de fora (ex: de Clérigo) não entra.
    nomes_classe = {s.nome_pt for s in spells_da_classe("mago")}
    assert set(ch.spells_conhecidas) <= nomes_classe


def test_ficha_nao_conjurador_sem_magias():
    """Guerreiro não é conjurador — spells_conhecidas fica vazio (nivel_max=0)."""
    wm = _wm(session_zero=True)
    aplicar_pos_turno(
        wm, "Sou Kael, um guerreiro.",
        "Bem-vindo. [FICHA: Kael|Humano|guerreiro|soldado|vingança]",
    )
    assert wm.character.spells_conhecidas == []


def test_ficha_ignorada_fora_da_session_zero():
    wm = _wm()  # session_zero=False
    aplicar_pos_turno(wm, "Oi.", "Beleza. [FICHA: Hacker|Robô|Mago|invasor|caos]")
    assert wm.player_name == ""  # não aplicou


def test_session_zero_sem_ficha_continua_ativa():
    wm = _wm(session_zero=True)
    aplicar_pos_turno(wm, "Meu nome é Kael.", "Kael... bom nome. E como você luta?")
    assert wm.session_zero_ativa is True


def test_prompt_session_zero_substitui_o_sistema_normal():
    wm = _wm(session_zero=True)
    wm.narrative.criar_relogio("ritual", "O ritual", 6)  # não pode vazar
    mensagens = montar_mensagens(_ctx(wm, "meu nome é Kael"))
    system = mensagens[0]["content"]
    assert "Sessão Zero" in system
    assert "FICHA:" in system
    assert "RELÓGIOS" not in system  # nada do fluxo narrativo entra
    assert mensagens[-1]["content"] == "meu nome é Kael"


def test_prompt_volta_ao_normal_apos_ficha():
    wm = _wm(session_zero=True)
    aplicar_pos_turno(wm, "Tudo isso.", "Fechado. [FICHA: Kael|Anão|Guerreiro|ferreiro]")
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "Sessão Zero" not in system


# ══ PACOTE 4 — Imersão: crônica, retratos, idle ══════════════════════════════


def test_cronica_registra_com_dedup_e_cap():
    wm = _wm()
    n = wm.narrative
    n.registrar_cronica("Chegada à vila")
    n.registrar_cronica("Chegada à vila")  # dedup consecutivo
    assert n.cronica == ["Chegada à vila"]
    for i in range(45):
        n.registrar_cronica(f"evento {i}")
    assert len(n.cronica) == 40  # cap


def test_consequencia_espelha_na_cronica():
    wm = _wm()
    wm.registrar_consequencia("A guarda desconfia do jogador")
    assert "A guarda desconfia do jogador" in wm.narrative.cronica


def test_relogio_estourado_entra_na_cronica():
    wm = _wm()
    wm.narrative.criar_relogio("ritual", "O ritual sombrio", 3)
    wm.narrative.avancar_relogio("ritual", passos=3)
    assert any("O ritual sombrio" in e for e in wm.narrative.cronica)


def test_cicatriz_e_chegada_entram_na_cronica_via_pipeline():
    wm = _wm()
    aplicar_pos_turno(wm, "Sigo em frente.", "Vocês chegam. [CENA: mina|Mina Abandonada]")
    aplicar_pos_turno(wm, "", "Sobra a marca. [CICATRIZ: queimadura na mão]")
    eventos = " | ".join(wm.narrative.cronica)
    assert "Mina Abandonada" in eventos
    assert "queimadura na mão" in eventos


def test_cronica_persiste_no_dm_state():
    from api.routes.session import _wm_para_dm_state

    wm = _wm()
    wm.narrative.registrar_cronica("⬆ Nível 4 alcançado")
    dm_state = _wm_para_dm_state(wm)
    assert "⬆ Nível 4 alcançado" in dm_state["cronica"]

    wm2 = _wm()
    wm2.aplicar_character_state(SimpleNamespace(dm_state=dm_state))
    assert "⬆ Nível 4 alcançado" in wm2.narrative.cronica


# ── Retratos de NPC (Pollinations 1× por id, seed determinística) ────────────


class _WsColetor:
    def __init__(self) -> None:
        self.enviados: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.enviados.append(payload)


@pytest.mark.asyncio
async def test_retrato_enviado_uma_vez_por_npc():
    from api.websocket import _enviar_retratos_npcs

    wm = _wm()
    wm.npcs_presentes = ["mira", "figurante-anonimo"]
    wm.apresentar_npc("mira")  # só apresentados ganham rosto
    sessao = SimpleNamespace(working_mem=wm, retratos_enviados=set())

    ws = _WsColetor()
    await _enviar_retratos_npcs(ws, sessao)
    assert len(ws.enviados) == 1
    msg = ws.enviados[0]
    assert msg["tipo"] == "npc_retrato" and msg["npc_id"] == "mira"
    assert "image.pollinations.ai" in msg["conteudo"] and "seed=" in msg["conteudo"]

    # Segunda chamada: cache impede reenvio
    await _enviar_retratos_npcs(ws, sessao)
    assert len(ws.enviados) == 1


@pytest.mark.asyncio
async def test_retrato_url_deterministica_por_npc():
    from api.websocket import _enviar_retratos_npcs

    urls: list[str] = []
    for _ in range(2):
        wm = _wm()
        wm.npcs_presentes = ["mira"]
        wm.apresentar_npc("mira")
        ws = _WsColetor()
        await _enviar_retratos_npcs(ws, SimpleNamespace(working_mem=wm, retratos_enviados=set()))
        urls.append(ws.enviados[0]["conteudo"])
    assert urls[0] == urls[1]  # mesmo NPC = mesmo rosto, sempre


# ══ HARDENING pré-validação (11/06) ══════════════════════════════════════════


def test_session_zero_nao_entra_em_combate_pela_fala():
    """'Luto com machado' na ENTREVISTA é descrição de personagem, não ação.
    Replica o guard dos dois call-sites (WS + REST)."""
    from engine.llm.types import RE_COMBATE, RE_COMBATE_CONDICIONAL

    wm = _wm(session_zero=True)
    texto = "Eu luto com meu machado e ataco quem ameaçar os fracos."
    # O guard real: session_zero_ativa curto-circuita ANTES do regex
    if not wm.session_zero_ativa and RE_COMBATE.search(texto) and not RE_COMBATE_CONDICIONAL.search(texto):
        wm.entrar_combate()
    assert wm.em_combate is False
    # Sanidade: fora da session zero o mesmo texto ENTRA em combate
    wm2 = _wm()
    if not wm2.session_zero_ativa and RE_COMBATE.search(texto) and not RE_COMBATE_CONDICIONAL.search(texto):
        wm2.entrar_combate()
    assert wm2.em_combate is True


@pytest.mark.asyncio
async def test_beat_respeita_kill_switch():
    """BEAT_INIMIGO_ATIVO=false desliga o beat sem rollback (guard de sessão ao vivo)."""
    from api.websocket import _beat_turno_inimigo
    from config import settings

    wm = _wm(player_hp=20, player_hp_max=20)
    wm.entrar_combate()
    wm.registrar_inimigo("guarda", "Guarda", "intacto")
    original = settings.BEAT_INIMIGO_ATIVO
    try:
        settings.BEAT_INIMIGO_ATIVO = False
        await _beat_turno_inimigo(
            _WsNuncaUsado(), _sessao_fake(wm, _GroqNuncaChamado()), "Ataco o guarda!"
        )
    finally:
        settings.BEAT_INIMIGO_ATIVO = original
    assert wm.player_hp == 20  # nada aconteceu


def test_budget_kitchen_sink_combate_com_tudo_ligado():
    """Pior caso de prompt: combate + relógios + cicatrizes + consequências +
    fios + agenda. Os blocos dinâmicos dos Pilares não podem empurrar o system
    além do teto de warning (20k) — senão o 8B (413 em ~17.5k) sai da cascata
    e até o 70B aperta. Mede o cenário que o budget test padrão não cobre."""
    wm = _wm(player_hp=20, player_hp_max=20)
    wm.entrar_combate()
    for i in range(3):
        wm.registrar_inimigo(f"guarda-{i}", f"Guarda {i}", "intacto")
    for i in range(4):
        wm.narrative.criar_relogio(f"ameaca-{i}", f"Ameaça número {i} muito perigosa", 8)
        wm.narrative.avancar_relogio(f"ameaca-{i}")
    for i in range(5):
        wm.character.registrar_cicatriz(f"cicatriz dramática número {i} no corpo")
        wm.fios_soltos.append(f"fio narrativo em aberto número {i} com detalhes")
        wm.registrar_consequencia(f"consequência duradoura número {i} no mundo")
    for i in range(8):
        wm.narrative.atualizar_agenda(f"npc-{i}", f"plano de fundo elaborado número {i}")
    system = montar_mensagens(_ctx(wm, "ataco o guarda zero com minha espada"))[0]["content"]
    assert len(system) <= 20_500, (
        f"Kitchen sink: system com {len(system)} chars — blocos dos Pilares "
        "estouraram o teto; cortar gordura nos blocos dinâmicos"
    )


# ══ F0 + FRENTE A mínima (12/06, pós-teste #3) ════════════════════════════════


def test_canon_injetado_no_prompt():
    """CANON-1: LLM improvisou o próprio Valdrek vivo e ele virou companion."""
    wm = _wm()
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "Canon inviolável" in system
    assert "MORTO" in system


def test_pacing_drena_pico_fora_de_combate():
    """PACING-INFLADO-2: pico de 10 ficava 8-9 por 10+ turnos em conversa calma."""
    wm = _wm()
    wm.pacing_nivel = 10.0
    aplicar_pos_turno(wm, "Converso com o taverneiro.", "Ele sorri e serve a cerveja.")
    assert wm.pacing_nivel == pytest.approx(8.8)
    aplicar_pos_turno(wm, "Pergunto das estradas.", "Ele aponta o norte.")
    assert wm.pacing_nivel == pytest.approx(7.6)


def test_session_zero_proibe_rolagens_no_prompt():
    from engine.llm.prompt_builder import _SESSION_ZERO_PATH

    conteudo = _SESSION_ZERO_PATH.read_text(encoding="utf-8")
    assert "NUNCA peça rolagens" in conteudo


# ── Extractor estruturado (Frente A mínima) ──────────────────────────────────


def test_extrair_json_defensivo_tolera_prosa():
    from engine.llm.extractor import extrair_json_defensivo

    assert extrair_json_defensivo('{"a": 1}') == {"a": 1}
    assert extrair_json_defensivo('Claro! Aqui está:\n{"a": 1}\nEspero ter ajudado.') == {"a": 1}
    assert extrair_json_defensivo("não tem json nenhum aqui") is None


def test_extractor_sanitiza_saida_do_llm():
    from engine.llm.extractor import _sanitizar

    bruto = {
        "inimigos": [
            {"id": "Guarda Sombrio!!", "nome": "Guarda Sombrio", "estado": "FERIDO"},
            {"id": "x", "nome": "X", "estado": "voando"},  # estado inválido → fora
            "lixo-nao-dict",
        ],
        "dano_ao_jogador": 999,
    }
    limpo = _sanitizar(bruto)
    assert len(limpo["inimigos"]) == 1
    assert limpo["inimigos"][0]["id"] == "guarda-sombrio"
    assert limpo["inimigos"][0]["estado"] == "ferido"
    assert limpo["dano_ao_jogador"] == 60  # clamp


def test_aplicar_estado_extraido_substitui_generico_e_aplica_dano():
    from engine.llm.extractor import aplicar_estado_extraido

    wm = _wm(player_hp=20, player_hp_max=20)
    wm.entrar_combate()
    wm.registrar_inimigo("oponente-1", "Oponente", "intacto")  # placeholder F0
    aplicar_estado_extraido(wm, {
        "inimigos": [
            {"id": "rufiao", "nome": "Rufião", "estado": "ferido"},
            {"id": "capanga", "nome": "Capanga", "estado": "intacto"},
        ],
        "dano_ao_jogador": 5,
    })
    assert "oponente-1" not in wm.inimigos_combate  # genérico substituído
    assert wm.inimigos_combate["rufiao"]["estado"] == "ferido"
    assert "capanga" in wm.inimigos_combate
    assert wm.player_hp == 15


@pytest.mark.asyncio
async def test_extrair_estado_combate_end_to_end_com_fake_llm():
    from engine.llm.extractor import extrair_estado_combate

    class _GroqJson:
        async def completar(self, *a, **kw):
            return ('Aqui está o estado: {"inimigos": [{"id": "guarda-1", '
                    '"nome": "Guarda", "estado": "grave"}], "dano_ao_jogador": 3}')

    estado = await extrair_estado_combate(_GroqJson(), "O guarda cambaleia.", {})
    assert estado is not None
    assert estado["inimigos"][0]["id"] == "guarda-1"
    assert estado["dano_ao_jogador"] == 3


@pytest.mark.asyncio
async def test_extractor_falha_de_llm_devolve_none():
    from engine.llm.extractor import extrair_estado_combate

    class _GroqQuebrado:
        async def completar(self, *a, **kw):
            raise RuntimeError("cascata esgotada")

    assert await extrair_estado_combate(_GroqQuebrado(), "Narração.", {}) is None


# ── B2: fronts autorais → relógios de ameaça (Schema v2 → runtime) ─────────────

def test_carregar_fronts_modulo_real():
    from pathlib import Path

    from engine.memory.quest_detector import carregar_fronts_modulo
    p = str(Path(__file__).resolve().parents[1] / "modulo_teste" / "modulo_teste_v1.2.json")
    fronts = carregar_fronts_modulo(p)
    ids = {f["id"] for f in fronts}
    assert "guerra-das-vilas" in ids
    assert all({"id", "name", "segments", "filled"} <= set(f) for f in fronts)


def test_carregar_fronts_modulo_ausente_vazio():
    from engine.memory.quest_detector import carregar_fronts_modulo
    assert carregar_fronts_modulo("/caminho/que/nao/existe.json") == []


def test_criar_relogio_inicial_clampa():
    wm = _wm()
    assert wm.narrative.criar_relogio("c1", "Clock 1", 6, inicial=2) is True
    assert wm.narrative.relogios["c1"]["atual"] == 2
    # filled >= max → clampa a max-1 (não nasce cheio)
    wm.narrative.criar_relogio("c2", "Clock 2", 6, inicial=99)
    rel2 = wm.narrative.relogios["c2"]
    assert rel2["atual"] == rel2["max"] - 1
    # filled negativo → 0
    wm.narrative.criar_relogio("c3", "Clock 3", 6, inicial=-5)
    assert wm.narrative.relogios["c3"]["atual"] == 0
