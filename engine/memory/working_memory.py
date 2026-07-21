"""
WorkingMemory — facade thin sobre 5 substates de `engine/state/`.

Por que existe: WorkingMemory cresceu para 1132 linhas com 5 domínios misturados
    (cena, combate, personagem, party, narrativa). Refactor delega cada domínio
    para um substate em engine/state/, e este arquivo virou agregador thin com
    properties que preservam a superfície pública (1135 referências externas a
    `wm.player_hp`, `wm.inimigos_combate`, etc. continuam funcionando idêntico).

Dependências: engine.state (cinco substates)

Armadilha: NÃO adicionar lógica de domínio aqui. Tudo que for combate vive em
    CombatState; cena em SceneState; etc. Esta camada APENAS:
      1. Compõe substates como campos
      2. Oferece properties/setters para backward compat
      3. Delega métodos para substate correto
      4. `para_texto()` concatena `to_prompt()` de cada substate

Exemplo:
    wm = WorkingMemory.nova_sessao("taverna", "Taverna", session_id="sess-01")
    wm.player_hp = 25                # → wm.character.hp_current = 25
    wm.registrar_fala("player", ".") # → wm.scene.registrar_fala("player", ".")
    wm.entrar_combate()              # → wm.combat.entrar()
    texto = wm.para_texto()          # → compõe slices dos 5 substates
"""

from dataclasses import dataclass, field
from typing import Any

from engine.state.character import _PERICIA_ATRIBUTO, PlayerCharacter
from engine.state.combat import CombatState
from engine.state.narrative import NarrativeState
from engine.state.party import PartyState
from engine.state.scene import MAX_DIALOGOS, DialogueTurn, SceneState

# Re-export para compat com testes legados e dashboard
__all__ = [
    "DialogueTurn",
    "MAX_DIALOGOS",
    "WorkingMemory",
    "_id_para_nome",
    "_PERICIA_ATRIBUTO",
]


def _id_para_nome(id_kebab: str) -> str:
    """Converte 'fael-valdreksson' → 'Fael Valdreksson'.

    Helper compartilhado (working_memory é o owner canônico — voice_manager e
    websocket._detectar_voz_npc importam daqui).
    """
    return " ".join(parte.capitalize() for parte in id_kebab.split("-"))


@dataclass
class WorkingMemory:
    """Facade thin sobre cinco substates de domínio.

    Cada substate é dono do seu estado e expõe `to_prompt()`. Esta classe
    apenas compõe, delega e mantém backward compat via properties.
    """

    # ── Substates (composição) ───────────────────────────────────────────────
    scene: SceneState = field(default_factory=SceneState)
    combat: CombatState = field(default_factory=CombatState)
    character: PlayerCharacter = field(default_factory=PlayerCharacter)
    party: PartyState = field(default_factory=PartyState)
    narrative: NarrativeState = field(default_factory=NarrativeState)

    # ── Metadados de sessão (vivem aqui mesmo — não é domínio) ───────────────
    session_id: str = ""
    tts_voice: str = "pt-BR-FranciscaNeural"
    dm_profile: str = "equilibrado"
    roll_visibility: str = "result_only"
    quests_modulo: str = ""
    # Pilar Perigo (10/06): "narrativo" = derrota tem custo mas nunca apaga o
    # personagem; "mortal" = morte real com death saves. Default narrativo.
    death_policy: str = "narrativo"
    # Ritual de mesa (10/06): mestre propõe fecho de episódio pós-clímax.
    modo_episodio: bool = False
    # Session Zero por voz (P3): True enquanto a entrevista de criação roda.
    # O prompt_builder troca o system pelo session_zero.md; o marker [FICHA]
    # aplica o personagem e desliga o flag (jogo normal começa).
    session_zero_ativa: bool = False

    # Mercado/economia: flag de UI, não domínio independente
    em_mercado: bool = False
    turnos_sem_mercado: int = 0

    # CANON-MORTOS-2 (A/B 17/07): abates cuja flag `morto` não pôde ser gravada
    # na hora — o inimigo ainda não era conhecido da cena quando a engine matou
    # (kill pré-LLM roda ANTES da extração/[NPC] do turno). Transiente: drenada
    # pelo aplicar_pos_turno após a extração registrar o combatente; nunca
    # persiste nem entra em prompt.
    mortos_pendentes: list[str] = field(default_factory=list)

    # ── Properties: SceneState ───────────────────────────────────────────────

    @property
    def location_id(self) -> str: return self.scene.location_id
    @location_id.setter
    def location_id(self, v: str) -> None: self.scene.location_id = v

    @property
    def location_nome(self) -> str: return self.scene.location_nome
    @location_nome.setter
    def location_nome(self, v: str) -> None: self.scene.location_nome = v

    @property
    def time_of_day(self) -> str: return self.scene.time_of_day
    @time_of_day.setter
    def time_of_day(self, v: str) -> None: self.scene.time_of_day = v

    @property
    def weather(self) -> str: return self.scene.weather
    @weather.setter
    def weather(self, v: str) -> None: self.scene.weather = v

    @property
    def npcs_presentes(self) -> list[str]: return self.scene.npcs_presentes
    @npcs_presentes.setter
    def npcs_presentes(self, v: list[str]) -> None: self.scene.npcs_presentes = v

    @property
    def npcs_apresentados(self) -> set[str]: return self.scene.npcs_apresentados
    @npcs_apresentados.setter
    def npcs_apresentados(self, v: set[str]) -> None: self.scene.npcs_apresentados = v

    @property
    def secrets_revelados(self) -> set[str]: return self.scene.secrets_revelados
    @secrets_revelados.setter
    def secrets_revelados(self, v: set[str]) -> None: self.scene.secrets_revelados = v

    @property
    def quests_completas(self) -> set[str]: return self.scene.quests_completas
    @quests_completas.setter
    def quests_completas(self, v: set[str]) -> None: self.scene.quests_completas = v

    @property
    def arc_flags(self) -> dict[str, Any]: return self.scene.arc_flags
    @arc_flags.setter
    def arc_flags(self, v: dict[str, Any]) -> None: self.scene.arc_flags = v

    @property
    def arc_fase(self) -> str: return self.scene.arc_fase
    @arc_fase.setter
    def arc_fase(self, v: str) -> None: self.scene.arc_fase = v

    @property
    def arc_ending_id(self) -> str: return self.scene.arc_ending_id
    @arc_ending_id.setter
    def arc_ending_id(self, v: str) -> None: self.scene.arc_ending_id = v

    @property
    def npc_estados_emocionais(self) -> dict[str, str]: return self.scene.npc_estados_emocionais
    @npc_estados_emocionais.setter
    def npc_estados_emocionais(self, v: dict[str, str]) -> None: self.scene.npc_estados_emocionais = v

    @property
    def trust_levels(self) -> dict[str, int]: return self.scene.trust_levels
    @trust_levels.setter
    def trust_levels(self, v: dict[str, int]) -> None: self.scene.trust_levels = v

    @property
    def faction_standings(self) -> dict[str, int]: return self.scene.faction_standings
    @faction_standings.setter
    def faction_standings(self, v: dict[str, int]) -> None: self.scene.faction_standings = v

    @property
    def dialogo_recente(self) -> list[DialogueTurn]: return self.scene.dialogo_recente
    @dialogo_recente.setter
    def dialogo_recente(self, v: list[DialogueTurn]) -> None: self.scene.dialogo_recente = v

    # ── Rolling summary (delega a NarrativeState) ─────────────────────
    @property
    def resumo_rolling(self) -> str: return self.narrative.resumo_rolling
    @resumo_rolling.setter
    def resumo_rolling(self, v: str) -> None: self.narrative.resumo_rolling = v

    @property
    def turnos_desde_resumo(self) -> int: return self.narrative.turnos_desde_resumo
    @turnos_desde_resumo.setter
    def turnos_desde_resumo(self, v: int) -> None: self.narrative.turnos_desde_resumo = v


    # ── Properties: CombatState ──────────────────────────────────────────────

    @property
    def em_combate(self) -> bool: return self.combat.em_combate
    @em_combate.setter
    def em_combate(self, v: bool) -> None: self.combat.em_combate = v

    @property
    def rodada_combate(self) -> int: return self.combat.rodada_combate
    @rodada_combate.setter
    def rodada_combate(self, v: int) -> None: self.combat.rodada_combate = v

    @property
    def iniciativa_jogador(self) -> int | None: return self.combat.iniciativa_jogador
    @iniciativa_jogador.setter
    def iniciativa_jogador(self, v: int | None) -> None: self.combat.iniciativa_jogador = v

    @property
    def inimigos_combate(self) -> dict[str, dict[str, str]]: return self.combat.inimigos_combate
    @inimigos_combate.setter
    def inimigos_combate(self, v: dict[str, dict[str, str]]) -> None: self.combat.inimigos_combate = v

    @property
    def iniciativa_cache(self) -> dict[str, int]: return self.combat.iniciativa_cache
    @iniciativa_cache.setter
    def iniciativa_cache(self, v: dict[str, int]) -> None: self.combat.iniciativa_cache = v

    @property
    def turno_atual_idx(self) -> int: return self.combat.turno_atual_idx
    @turno_atual_idx.setter
    def turno_atual_idx(self, v: int) -> None: self.combat.turno_atual_idx = v

    @property
    def posicoes_combate(self) -> dict[str, dict[str, int | bool]]: return self.combat.posicoes_combate
    @posicoes_combate.setter
    def posicoes_combate(self, v: dict[str, dict[str, int | bool]]) -> None: self.combat.posicoes_combate = v

    @property
    def movimento_restante_ft(self) -> int: return self.combat.movimento_restante_ft
    @movimento_restante_ft.setter
    def movimento_restante_ft(self, v: int) -> None: self.combat.movimento_restante_ft = v

    @property
    def movimento_total_ft(self) -> int: return self.combat.movimento_total_ft
    @movimento_total_ft.setter
    def movimento_total_ft(self, v: int) -> None: self.combat.movimento_total_ft = v

    @property
    def saiu_combate_recentemente(self) -> bool: return self.combat.saiu_combate_recentemente
    @saiu_combate_recentemente.setter
    def saiu_combate_recentemente(self, v: bool) -> None: self.combat.saiu_combate_recentemente = v

    @property
    def rodadas_sem_acao_inimigo(self) -> int: return self.combat.rodadas_sem_acao_inimigo
    @rodadas_sem_acao_inimigo.setter
    def rodadas_sem_acao_inimigo(self, v: int) -> None: self.combat.rodadas_sem_acao_inimigo = v

    @property
    def acao_usada(self) -> bool: return self.combat.acao_usada
    @acao_usada.setter
    def acao_usada(self, v: bool) -> None: self.combat.acao_usada = v

    @property
    def bonus_usada(self) -> bool: return self.combat.bonus_usada
    @bonus_usada.setter
    def bonus_usada(self, v: bool) -> None: self.combat.bonus_usada = v

    # ── Properties: PlayerCharacter ──────────────────────────────────────────

    @property
    def player_name(self) -> str: return self.character.player_name
    @player_name.setter
    def player_name(self, v: str) -> None: self.character.player_name = v

    @property
    def player_race(self) -> str: return self.character.player_race
    @player_race.setter
    def player_race(self, v: str) -> None: self.character.player_race = v

    @property
    def player_class(self) -> str: return self.character.player_class
    @player_class.setter
    def player_class(self, v: str) -> None: self.character.player_class = v

    @property
    def player_subclass(self) -> str: return self.character.player_subclass
    @player_subclass.setter
    def player_subclass(self, v: str) -> None: self.character.player_subclass = v

    @property
    def player_background(self) -> str: return self.character.player_background
    @player_background.setter
    def player_background(self, v: str) -> None: self.character.player_background = v

    @property
    def player_description(self) -> str: return self.character.player_description
    @player_description.setter
    def player_description(self, v: str) -> None: self.character.player_description = v

    @property
    def player_level(self) -> int: return self.character.player_level
    @player_level.setter
    def player_level(self, v: int) -> None: self.character.player_level = v

    @property
    def player_hp(self) -> int: return self.character.hp_current
    @player_hp.setter
    def player_hp(self, v: int) -> None: self.character.hp_current = v

    @property
    def player_hp_max(self) -> int: return self.character.hp_max
    @player_hp_max.setter
    def player_hp_max(self, v: int) -> None: self.character.hp_max = v

    @property
    def player_conditions(self) -> list[str]: return self.character.player_conditions
    @player_conditions.setter
    def player_conditions(self, v: list[str]) -> None: self.character.player_conditions = v

    @property
    def player_inventory(self) -> list[str]: return self.character.player_inventory
    @player_inventory.setter
    def player_inventory(self, v: list[str]) -> None: self.character.player_inventory = v

    @property
    def active_quest_hooks(self) -> list[str]: return self.character.active_quest_hooks
    @active_quest_hooks.setter
    def active_quest_hooks(self, v: list[str]) -> None: self.character.active_quest_hooks = v

    @property
    def quest_stages(self) -> dict[str, str]: return self.character.quest_stages
    @quest_stages.setter
    def quest_stages(self, v: dict[str, str]) -> None: self.character.quest_stages = v

    @property
    def str_score(self) -> int: return self.character.str_score
    @str_score.setter
    def str_score(self, v: int) -> None: self.character.str_score = v

    @property
    def dex_score(self) -> int: return self.character.dex_score
    @dex_score.setter
    def dex_score(self, v: int) -> None: self.character.dex_score = v

    @property
    def con_score(self) -> int: return self.character.con_score
    @con_score.setter
    def con_score(self, v: int) -> None: self.character.con_score = v

    @property
    def int_score(self) -> int: return self.character.int_score
    @int_score.setter
    def int_score(self, v: int) -> None: self.character.int_score = v

    @property
    def wis_score(self) -> int: return self.character.wis_score
    @wis_score.setter
    def wis_score(self, v: int) -> None: self.character.wis_score = v

    @property
    def cha_score(self) -> int: return self.character.cha_score
    @cha_score.setter
    def cha_score(self, v: int) -> None: self.character.cha_score = v

    @property
    def skill_profs(self) -> list[str]: return self.character.skill_profs
    @skill_profs.setter
    def skill_profs(self, v: list[str]) -> None: self.character.skill_profs = v

    @property
    def save_profs(self) -> list[str]: return self.character.save_profs
    @save_profs.setter
    def save_profs(self, v: list[str]) -> None: self.character.save_profs = v

    @property
    def spell_slots(self) -> dict[int, dict[str, int]]: return self.character.spell_slots
    @spell_slots.setter
    def spell_slots(self, v: dict[int, dict[str, int]]) -> None: self.character.spell_slots = v

    @property
    def spells_conhecidas(self) -> list[str]: return self.character.spells_conhecidas
    @spells_conhecidas.setter
    def spells_conhecidas(self, v: list[str]) -> None: self.character.spells_conhecidas = v

    @property
    def hit_dice_current(self) -> int: return self.character.hit_dice_current
    @hit_dice_current.setter
    def hit_dice_current(self, v: int) -> None: self.character.hit_dice_current = v

    @property
    def hit_dice_max(self) -> int: return self.character.hit_dice_max
    @hit_dice_max.setter
    def hit_dice_max(self, v: int) -> None: self.character.hit_dice_max = v

    @property
    def hit_dice_type(self) -> int: return self.character.hit_dice_type
    @hit_dice_type.setter
    def hit_dice_type(self, v: int) -> None: self.character.hit_dice_type = v

    @property
    def death_saves_successes(self) -> int: return self.character.death_saves_successes
    @death_saves_successes.setter
    def death_saves_successes(self, v: int) -> None: self.character.death_saves_successes = v

    @property
    def death_saves_failures(self) -> int: return self.character.death_saves_failures
    @death_saves_failures.setter
    def death_saves_failures(self, v: int) -> None: self.character.death_saves_failures = v

    @property
    def death_saves_stable(self) -> bool: return self.character.death_saves_stable
    @death_saves_stable.setter
    def death_saves_stable(self, v: bool) -> None: self.character.death_saves_stable = v

    @property
    def gold(self) -> int: return self.character.gold
    @gold.setter
    def gold(self, v: int) -> None: self.character.gold = v

    @property
    def xp(self) -> int: return self.character.xp
    @xp.setter
    def xp(self, v: int) -> None: self.character.xp = v

    @property
    def inspiration(self) -> bool: return self.character.inspiration
    @inspiration.setter
    def inspiration(self, v: bool) -> None: self.character.inspiration = v

    @property
    def class_features(self) -> dict: return self.character.class_features
    @class_features.setter
    def class_features(self, v: dict) -> None: self.character.class_features = v

    @property
    def cicatrizes(self) -> list[str]: return self.character.cicatrizes
    @cicatrizes.setter
    def cicatrizes(self, v: list[str]) -> None: self.character.cicatrizes = v

    # Properties derivadas D&D 5e (read-only — não fazem sentido setar)
    @property
    def prof_bonus(self) -> int: return self.character.prof_bonus
    @property
    def mod_for(self) -> int: return self.character.mod_for
    @property
    def mod_des(self) -> int: return self.character.mod_des
    @property
    def mod_con(self) -> int: return self.character.mod_con
    @property
    def mod_int(self) -> int: return self.character.mod_int
    @property
    def mod_sab(self) -> int: return self.character.mod_sab
    @property
    def mod_car(self) -> int: return self.character.mod_car
    @property
    def ca(self) -> int: return self.character.ca
    @property
    def passive_perception(self) -> int: return self.character.passive_perception

    # ── Properties: PartyState ───────────────────────────────────────────────

    @property
    def companions(self) -> dict[str, dict]: return self.party.companions
    @companions.setter
    def companions(self, v: dict[str, dict]) -> None: self.party.companions = v

    @property
    def npc_vozes(self) -> dict[str, dict[str, str]]: return self.party.npc_vozes
    @npc_vozes.setter
    def npc_vozes(self, v: dict[str, dict[str, str]]) -> None: self.party.npc_vozes = v

    # ── Properties: NarrativeState ───────────────────────────────────────────

    @property
    def fios_soltos(self) -> list[str]: return self.narrative.fios_soltos
    @fios_soltos.setter
    def fios_soltos(self, v: list[str]) -> None: self.narrative.fios_soltos = v

    @property
    def cliffhanger_pendente(self) -> str: return self.narrative.cliffhanger_pendente
    @cliffhanger_pendente.setter
    def cliffhanger_pendente(self, v: str) -> None: self.narrative.cliffhanger_pendente = v

    @property
    def agenda_npcs(self) -> dict[str, str]: return self.narrative.agenda_npcs
    @agenda_npcs.setter
    def agenda_npcs(self, v: dict[str, str]) -> None: self.narrative.agenda_npcs = v

    @property
    def cartas_improviso(self) -> list[str]: return self.narrative.cartas_improviso
    @cartas_improviso.setter
    def cartas_improviso(self, v: list[str]) -> None: self.narrative.cartas_improviso = v

    @property
    def turnos_desde_cartas(self) -> int: return self.narrative.turnos_desde_cartas
    @turnos_desde_cartas.setter
    def turnos_desde_cartas(self, v: int) -> None: self.narrative.turnos_desde_cartas = v

    @property
    def pacing_nivel(self) -> float: return self.narrative.pacing_nivel
    @pacing_nivel.setter
    def pacing_nivel(self, v: float) -> None: self.narrative.pacing_nivel = v

    @property
    def turnos_sem_tensao(self) -> int: return self.narrative.turnos_sem_tensao
    @turnos_sem_tensao.setter
    def turnos_sem_tensao(self, v: int) -> None: self.narrative.turnos_sem_tensao = v

    @property
    def turnos_light_consecutivos(self) -> int: return self.narrative.turnos_light_consecutivos
    @turnos_light_consecutivos.setter
    def turnos_light_consecutivos(self, v: int) -> None: self.narrative.turnos_light_consecutivos = v

    @property
    def fatos_ancora(self) -> list[str]: return self.narrative.fatos_ancora
    @fatos_ancora.setter
    def fatos_ancora(self, v: list[str]) -> None: self.narrative.fatos_ancora = v

    @property
    def ambiente_recente(self) -> list[str]: return self.narrative.ambiente_recente
    @ambiente_recente.setter
    def ambiente_recente(self, v: list[str]) -> None: self.narrative.ambiente_recente = v

    @property
    def quests_improvisadas(self) -> list[dict]: return self.narrative.quests_improvisadas
    @quests_improvisadas.setter
    def quests_improvisadas(self, v: list[dict]) -> None: self.narrative.quests_improvisadas = v

    @property
    def log_consequencias(self) -> list[str]: return self.narrative.log_consequencias
    @log_consequencias.setter
    def log_consequencias(self, v: list[str]) -> None: self.narrative.log_consequencias = v

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def nova_sessao(
        cls,
        location_id: str,
        location_nome: str,
        session_id: str,
        time_of_day: str = "Dia",
        weather: str = "Limpo",
        player_hp: int = 30,
        player_hp_max: int = 30,
        player_name: str = "",
        player_race: str = "",
        player_class: str = "",
        player_subclass: str = "",
        player_background: str = "",
        player_description: str = "",
        player_level: int = 1,
        tts_voice: str = "pt-BR-FranciscaNeural",
        dm_profile: str = "equilibrado",
        roll_visibility: str = "result_only",
        str_score: int = 10,
        dex_score: int = 10,
        con_score: int = 10,
        int_score: int = 10,
        wis_score: int = 10,
        cha_score: int = 10,
        skill_profs: list[str] | None = None,
        save_profs: list[str] | None = None,
        spell_slots: dict[int, dict[str, int]] | None = None,
        hit_dice_current: int | None = None,
        hit_dice_type: int | None = None,
        gold: int = 0,
        xp: int = 0,
        inspiration: bool = False,
        player_spells: list[str] | None = None,
        death_policy: str = "narrativo",
        modo_episodio: bool = False,
        session_zero: bool = False,
    ) -> "WorkingMemory":
        """Cria WorkingMemory com substates inicializados."""
        _HIT_DICE_TIPO: dict[str, int] = {
            "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10, "Ranger": 10,
            "Bardo": 8, "Clérigo": 8, "Druida": 8, "Monge": 8, "Ladino": 8,
            "Feiticeiro": 6, "Bruxo": 6, "Mago": 6,
        }
        hd_tipo = hit_dice_type if hit_dice_type is not None else _HIT_DICE_TIPO.get(player_class, 8)
        hd_atual = hit_dice_current if hit_dice_current is not None else player_level

        # Inicializa spell_slots pela tabela SRD se conjurador
        if not spell_slots and player_class:
            from engine.magic.spell_list import slots_padrao
            spell_slots = slots_padrao(player_class, player_level)

        scene = SceneState(
            location_id=location_id,
            location_nome=location_nome,
            time_of_day=time_of_day,
            weather=weather,
        )
        character = PlayerCharacter(
            player_name=player_name,
            player_race=player_race,
            player_class=player_class,
            player_subclass=player_subclass,
            player_background=player_background,
            player_description=player_description,
            player_level=player_level,
            hp_current=player_hp,
            hp_max=player_hp_max,
            str_score=str_score, dex_score=dex_score, con_score=con_score,
            int_score=int_score, wis_score=wis_score, cha_score=cha_score,
            skill_profs=skill_profs or [],
            save_profs=save_profs or [],
            spell_slots=spell_slots or {},
            hit_dice_current=hd_atual,
            hit_dice_max=player_level,
            hit_dice_type=hd_tipo,
            gold=gold,
            xp=xp,
            inspiration=inspiration,
        )
        if player_class:
            character.inicializar_features_classe(player_class, player_subclass)
        if player_spells:
            character.spells_conhecidas = list(player_spells)

        wm = cls(
            scene=scene,
            character=character,
            session_id=session_id,
            tts_voice=tts_voice,
            dm_profile=dm_profile if dm_profile in {"rigoroso", "equilibrado", "tranquilo", "rule_of_cool", "sombrio"} else "equilibrado",
            roll_visibility=roll_visibility if roll_visibility in {"open", "result_only", "narrated"} else "result_only",
            death_policy=death_policy if death_policy in {"narrativo", "mortal"} else "narrativo",
            modo_episodio=bool(modo_episodio),
            session_zero_ativa=bool(session_zero),
        )
        return wm

    # ── Delegations: SceneState ──────────────────────────────────────────────

    def registrar_fala(self, falante: str, texto: str) -> None:
        self.scene.registrar_fala(falante, texto)

    def atualizar_trust(self, npc_id: str, delta: int) -> None:
        self.scene.atualizar_trust(npc_id, delta)

    def drenar_eventos_relacao(self) -> list:
        """Eventos de relação do turno (autoridade social) — one-shot."""
        return self.scene.drenar_eventos_relacao()

    def apresentar_npc(self, npc_id: str) -> None:
        self.scene.apresentar_npc(npc_id)

    def apresentar_npcs_mencionados(self, texto: str) -> None:
        self.scene.apresentar_npcs_mencionados(texto)

    def atualizar_estado_emocional(self, npc_id: str, estado: str) -> None:
        self.scene.atualizar_estado_emocional(npc_id, estado)

    # ── Delegations: CombatState ─────────────────────────────────────────────

    def entrar_combate(self) -> None:
        """Ativa combate. Após chamada, prompt_builder injeta combat.md."""
        self.combat.entrar()

    def avancar_rodada(self) -> None:
        self.combat.avancar_rodada()

    def usar_acao(self) -> bool:
        return self.combat.usar_acao()

    def usar_bonus(self) -> bool:
        return self.combat.usar_bonus()

    def pode_agir(self) -> bool:
        return self.combat.pode_agir()

    def reset_economia(self) -> None:
        self.combat.reset_economia()

    def mod_ataque(self) -> int:
        """Bônus de ataque do jogador: MELHOR modificador relevante + proficiência.

        Playtest 29/06: antes usava só max(FOR, DES) — um Bruxo nv3 (ataque por
        CHA) atacava com mod ~0 e ERRAVA tudo. Agora usa o melhor de TODOS os
        atributos de ataque (FOR/DES marcial; INT/SAB/CAR conjurador) — cobre
        marcial E caster sem precisar saber a arma/magia exata. A engine soma
        isto ao d20 do jogador (resolver_ataque), não o LLM.
        """
        c = self.character
        return max(c.mod_for, c.mod_des, c.mod_int, c.mod_sab, c.mod_car) + c.prof_bonus

    def mod_dano(self) -> int:
        """Mod de dano: melhor modificador relevante (sem proficiência no dano)."""
        c = self.character
        return max(c.mod_for, c.mod_des, c.mod_int, c.mod_sab, c.mod_car)

    def mod_atributo(self, attr: str) -> int:
        """Modificador de um atributo por código (FOR/DES/CON/INT/SAB/CAR). 0 se inválido.

        Aceita código OU nome PT-BR (Força→FOR, Destreza→DES, …) — os 3 primeiros
        caracteres maiúsculos coincidem com o código nos seis atributos.
        """
        c = self.character
        mapa = {
            "FOR": c.mod_for, "DES": c.mod_des, "CON": c.mod_con,
            "INT": c.mod_int, "SAB": c.mod_sab, "CAR": c.mod_car,
        }
        return mapa.get(str(attr).strip().upper()[:3], 0)

    def mod_salvaguarda(self, attr: str) -> int:
        """Mod de salvaguarda: atributo + proficiência se o PJ for proficiente nele.

        Robusto ao formato de `save_profs` (código ou nome PT-BR) via a mesma
        normalização [:3] do atributo.
        """
        code = str(attr).strip().upper()[:3]
        base = self.mod_atributo(code)
        profs = {str(p).strip().upper()[:3] for p in (self.character.save_profs or [])}
        return base + (self.character.prof_bonus if code in profs else 0)

    def registrar_inimigo(
        self,
        inimigo_id: str,
        nome: str,
        estado: str = "intacto",
        hp_rel: str = "",
        srd_index: str = "",
    ) -> None:
        self.combat.registrar_inimigo(inimigo_id, nome, estado, hp_rel, srd_index)

    def atualizar_estado_inimigo(self, inimigo_id: str, estado: str, hp_rel: str = "") -> None:
        self.combat.atualizar_estado_inimigo(inimigo_id, estado, hp_rel)
        if estado == "morto":
            self._marcar_npc_morto(inimigo_id)

    def remover_inimigo(self, inimigo_id: str) -> None:
        self.combat.remover_inimigo(inimigo_id)

    def aplicar_stats_inimigo(self, inimigo_id: str, ca: int, hp_max: int) -> None:
        self.combat.aplicar_stats_inimigo(inimigo_id, ca, hp_max)

    def aplicar_dano_inimigo(self, inimigo_id: str, dano: int) -> str:
        estado = self.combat.aplicar_dano_inimigo(inimigo_id, dano)
        if estado == "morto":
            self._marcar_npc_morto(inimigo_id)
        return estado

    def _marcar_npc_morto(self, inimigo_id: str) -> None:
        """CANON-MORTOS (decisão 12/07): morte de combatente que É um NPC da
        cena marca a flag no registro canônico — o corpo fica na cena (prompt
        anota "morto, não fala"; frontend mostra grayscale). A facade é o
        choke point dos DOIS caminhos de morte (dano determinístico do
        orchestrator e marker/regex via atualizar_estado_inimigo). Falha
        silenciosa: stub de teste sem scene.npc_registro não pode quebrar
        combate."""
        try:
            from engine.npc.identity import marcar_morto
            # CANON-MORTOS-2: marcar_morto é conservador — devolve None quando a
            # cena ainda não conhece o id (kill da engine roda pré-LLM, antes da
            # extração registrar o combatente). Guarda o abate pra reconciliação
            # no fim do aplicar_pos_turno, quando o NPC já terá sido registrado.
            if marcar_morto(self, inimigo_id) is None:
                if inimigo_id not in self.mortos_pendentes:
                    self.mortos_pendentes.append(inimigo_id)
        except Exception:
            pass

    def sair_combate(self) -> None:
        """Encerra combate — registra consequência antes de zerar inimigos."""
        mortos = sum(
            1 for d in self.combat.inimigos_combate.values() if d.get("estado") == "morto"
        )
        if mortos > 0:
            self.narrative.registrar_consequencia(
                f"Combate encerrado — {mortos} inimigo(s) abatido(s)"
            )
        elif self.combat.em_combate:
            self.narrative.registrar_consequencia("Combate encerrado")

        self.combat.sair()
        self.narrative.turnos_sem_tensao = 0

    def registrar_posicao(self, npc_id: str, distancia_ft: int, cobertura: bool = False) -> None:
        self.combat.registrar_posicao(npc_id, distancia_ft, cobertura)

    def aplicar_movimento(self, delta_ft: int) -> int:
        return self.combat.aplicar_movimento(delta_ft)

    def popular_iniciativa(self, proposta_llm: dict[str, int] | None = None) -> None:
        """Popula iniciativa usando mod_des do personagem."""
        self.combat.popular_iniciativa(self.character.mod_des, proposta_llm)

    def avancar_turno_iniciativa(self) -> None:
        """Avança turno na ordem de iniciativa (pula mortos)."""
        self.combat.avancar_turno_iniciativa(self.calcular_ordem_iniciativa)

    def calcular_ordem_iniciativa(self) -> list:
        """Retorna ordem de iniciativa (player + inimigos), sorted desc, com turno_atual marcado."""
        from engine.llm.types import TokenIniciativa

        tokens: list[TokenIniciativa] = []

        ini_jogador = self.combat.iniciativa_cache.get("jogador", 10 + self.character.mod_des)
        tokens.append(TokenIniciativa(
            id="jogador",
            nome=self.character.player_name or "Jogador",
            tipo="jogador",
            iniciativa=ini_jogador,
            hp_atual=self.character.hp_current,
            hp_max=self.character.hp_max,
            morto=self.character.hp_current <= 0,
        ))

        for inimigo_id, dados in self.combat.inimigos_combate.items():
            ini = self.combat.iniciativa_cache.get(inimigo_id, 0)
            estado = dados.get("estado", "intacto")
            tokens.append(TokenIniciativa(
                id=inimigo_id,
                nome=dados.get("nome", inimigo_id),
                tipo="inimigo",
                iniciativa=ini,
                hp_atual=0 if estado == "morto" else 1,
                hp_max=1,
                morto=estado == "morto",
            ))

        tokens.sort(key=lambda t: (
            -t.iniciativa,
            0 if t.tipo == "jogador" else 1,
            t.id,
        ))

        vivos = [t for t in tokens if not t.morto]
        if vivos and 0 <= self.combat.turno_atual_idx < len(vivos):
            token_atual = vivos[self.combat.turno_atual_idx]
            for t in tokens:
                if t.id == token_atual.id:
                    t.turno_atual = True
                    break

        return tokens

    # ── Delegations: PlayerCharacter ─────────────────────────────────────────

    def adicionar_item(self, item_id: str) -> None:
        self.character.adicionar_item(item_id)

    def remover_item(self, item_id: str) -> None:
        self.character.remover_item(item_id)

    def atualizar_quest_stage(self, quest_id: str, stage_id: str) -> None:
        self.character.atualizar_quest_stage(quest_id, stage_id)

    def inicializar_features_classe(self, player_class: str, player_subclass: str = "") -> None:
        self.character.inicializar_features_classe(player_class, player_subclass)

    def restaurar_features(self, tipo_descanso: str) -> None:
        self.character.restaurar_features(tipo_descanso)

    def aplicar_character_state(self, state: object) -> None:
        """Aplica estado carregado do SQLite sobre esta WorkingMemory.

        Restaura: spell_slots, hit_dice, death_saves, gold, xp, inspiration,
        HP, inventário, condições, nível, class_features (merge de usos_atual),
        companions (só se memória estiver vazia), dm_state (fios/agenda/cliffhanger).
        """
        self.character.spell_slots = getattr(state, "spell_slots", {})
        self.character.hit_dice_current = getattr(state, "hit_dice_current", self.character.hit_dice_current)
        self.character.hit_dice_max = getattr(state, "hit_dice_max", self.character.hit_dice_max)
        self.character.hit_dice_type = getattr(state, "hit_dice_type", self.character.hit_dice_type)
        self.character.death_saves_successes = getattr(state, "death_saves_successes", 0)
        self.character.death_saves_failures = getattr(state, "death_saves_failures", 0)
        self.character.death_saves_stable = getattr(state, "death_saves_stable", False)
        self.character.gold = getattr(state, "gold", 0)
        self.character.xp = getattr(state, "xp", 0)
        self.character.inspiration = getattr(state, "inspiration", False)
        self.character.hp_current = getattr(state, "hp_current", self.character.hp_current)
        self.character.hp_max = getattr(state, "hp_max", self.character.hp_max)
        self.character.player_inventory = list(getattr(state, "inventory", self.character.player_inventory))
        self.character.player_conditions = list(getattr(state, "conditions", self.character.player_conditions))
        persisted_level = getattr(state, "player_level", self.character.player_level)
        if persisted_level and persisted_level > self.character.player_level:
            self.character.player_level = persisted_level
        # Class features — merge sobre estrutura inicializada
        persisted_features: dict[str, dict] = getattr(state, "class_features", {})
        for fid, saved in persisted_features.items():
            if fid in self.character.class_features:
                wm_feat = self.character.class_features[fid]
                wm_feat["usos_atual"] = min(
                    saved.get("usos_atual", wm_feat.get("usos_atual", 0)),
                    wm_feat.get("usos_max", 1),
                )
                if wm_feat.get("usos_max", 0) > 0:
                    wm_feat["disponivel"] = wm_feat["usos_atual"] > 0
        # Companions — restaura só se memória estiver vazia
        persisted_companions: dict[str, dict] = getattr(state, "companions", {})
        if persisted_companions and not self.party.companions:
            self.party.companions = {k: dict(v) for k, v in persisted_companions.items()}
        # DM state — restaura narrativo do mestre persistido em SQLite
        dm_state: dict = getattr(state, "dm_state", {})
        if dm_state:
            fios = dm_state.get("fios_soltos", [])
            if fios and not self.narrative.fios_soltos:
                self.narrative.fios_soltos = list(fios)
            agenda = dm_state.get("agenda_npcs", {})
            if agenda and not self.narrative.agenda_npcs:
                self.narrative.agenda_npcs = dict(agenda)
            cliff = dm_state.get("cliffhanger_pendente", "")
            if cliff and not self.narrative.cliffhanger_pendente:
                self.narrative.cliffhanger_pendente = cliff
            # Etapa 6: fatos_ancora + pacing_nivel persistidos.
            # Sem isso, sessão restaurada perde repetition guard (LLM pode re-narrar
            # revelações antigas) e o pacing volta para 3.0 default mesmo após
            # combate intenso — quebra continuidade dramática.
            ancoras = dm_state.get("fatos_ancora", [])
            if ancoras and not self.narrative.fatos_ancora:
                self.narrative.fatos_ancora = list(ancoras)
            # PLAY5-QUEST: missões improvisadas restauradas (só se vazias) — o
            # Mestre não esquece o que prometeu ao reconectar/após crash.
            qimprov = dm_state.get("quests_improvisadas", [])
            if qimprov and not self.narrative.quests_improvisadas:
                self.narrative.quests_improvisadas = [
                    dict(q) for q in qimprov if isinstance(q, dict) and q.get("id")
                ]
            pacing = dm_state.get("pacing_nivel")
            if isinstance(pacing, (int, float)) and pacing != 3.0:
                # Só restaura se diferente do default — evita sobrescrever valor
                # válido com persistência "vazia" de sessões antigas.
                self.narrative.pacing_nivel = float(pacing)
            # Pilar Perigo: cicatrizes são permanentes — sobrevivem a qualquer
            # restart. Merge defensivo (não sobrescreve as da memória ativa).
            for cic in dm_state.get("cicatrizes", []):
                self.character.registrar_cicatriz(str(cic))
            # Mundo Vivo: relógios de ameaça restaurados (substituição só se vazio)
            relogios = dm_state.get("relogios", {})
            if relogios and not self.narrative.relogios:
                self.narrative.relogios = {
                    str(k): dict(v) for k, v in relogios.items() if isinstance(v, dict)
                }
            # PLAY5-FRONTS: ameaças latentes ainda não introduzidas (idem: só se vazio)
            fronts_lat = dm_state.get("fronts_latentes", {})
            if fronts_lat and not self.narrative.fronts_latentes:
                self.narrative.fronts_latentes = {
                    str(k): dict(v) for k, v in fronts_lat.items() if isinstance(v, dict)
                }
            # Ritual P2: perfil do jogador acumula entre sessões (merge se vazio)
            estilo = dm_state.get("estilo_jogador", {})
            if estilo and not self.narrative.estilo_jogador:
                self.narrative.estilo_jogador = {
                    str(k): int(v) for k, v in estilo.items()
                    if isinstance(v, (int, float))
                }
            # Mundo Vivo P2: locais visitados — união (ecos sobrevivem a restart)
            for loc in dm_state.get("locais_visitados", []):
                self.scene.locais_visitados.add(str(loc))
            # Imersão P4: crônica restaurada (substituição só se vazia)
            cronica = dm_state.get("cronica", [])
            if cronica and not self.narrative.cronica:
                self.narrative.cronica = [str(c)[:140] for c in cronica][-40:]
            # NPC-IDENTIDADE (05/07): registro canônico + aliases (só se vazios)
            # — name-reveal e retrato_seed não se desfazem num restart.
            npc_reg = dm_state.get("npc_registro", {})
            if npc_reg and not self.scene.npc_registro:
                self.scene.npc_registro = {
                    str(k): dict(v) for k, v in npc_reg.items() if isinstance(v, dict)
                }
            npc_ali = dm_state.get("npc_aliases", {})
            if npc_ali and not self.scene.npc_aliases:
                self.scene.npc_aliases = {str(k): str(v) for k, v in npc_ali.items()}

    # ── Delegations: PartyState ──────────────────────────────────────────────

    def registrar_companion(
        self, companion_id: str, nome: str, tipo: str,
        hp: int, ca: int, atq: str, dano: str,
    ) -> None:
        self.party.registrar_companion(companion_id, nome, tipo, hp, ca, atq, dano)

    def ajustar_hp_companion(self, companion_id: str, delta: int) -> bool:
        return self.party.ajustar_hp_companion(companion_id, delta)

    def remover_companion(self, companion_id: str) -> bool:
        return self.party.remover_companion(companion_id)

    def registrar_voz_npc(self, npc_id: str, pitch: str, rate: str) -> bool:
        return self.party.registrar_voz_npc(npc_id, pitch, rate)

    # ── Delegations: NarrativeState ──────────────────────────────────────────

    def registrar_consequencia(self, texto: str) -> None:
        self.narrative.registrar_consequencia(texto)

    def registrar_ancora(self, texto: str) -> None:
        self.narrative.registrar_ancora(texto)

    def registrar_ambiente(self, texto: str) -> bool:
        return self.narrative.registrar_ambiente(texto)

    def adicionar_fio(self, texto: str) -> bool:
        return self.narrative.adicionar_fio(texto)

    def atualizar_agenda(self, npc_id: str, plano: str) -> None:
        self.narrative.atualizar_agenda(npc_id, plano)

    def consumir_cliffhanger(self) -> str:
        return self.narrative.consumir_cliffhanger()

    def decay_cartas(self) -> bool:
        return self.narrative.decay_cartas()

    def ajustar_pacing(self, em_combate: bool, saiu_combate_recentemente: bool, trust_mudou: bool) -> None:
        self.narrative.ajustar_pacing(em_combate, saiu_combate_recentemente, trust_mudou)

    # ── Composição do prompt ─────────────────────────────────────────────────

    def para_texto(self, incluir_dialogo: bool = False) -> str:
        """Compõe `=== CENA ATUAL ===` a partir das slices dos substates.

        Ordem cuidadosamente preservada para não quebrar testes de regressão:
        cabeçalho → Personagem → Local/Hora → HP/attrs → Combate → NPCs →
        Quests → Consequências → Aliados → Tensão → Diálogo (opcional).
        """
        # Character: 1ª linha "Personagem: ..." + resto (HP, attrs, etc.)
        char_lines = self.character.to_prompt().split("\n")
        bloco_id = char_lines[0]
        resto_char = "\n".join(char_lines[1:])

        # Scene: linhas Local/Hora + (opcional) NPCs + estados
        scene_lines = self.scene.to_prompt().split("\n")

        linhas: list[str] = ["=== CENA ATUAL ==="]
        linhas.append(bloco_id)
        # Local + Hora (linhas 0 e 1 do scene)
        linhas.extend(scene_lines[:2])
        # HP, attrs, perícias, condições, inventário, quests
        if resto_char:
            linhas.append(resto_char)
        # Aftermath
        if self.combat.saiu_combate_recentemente:
            linhas.append(
                "APÓS COMBATE — narre o silêncio que retorna, as feridas, "
                "o estado dos inimigos caídos, o que mudou no cenário; "
                "um momento de respiração antes de seguir"
            )
        # Combate ativo
        combat_txt = self.combat.to_prompt()
        if combat_txt:
            linhas.append(combat_txt)
        # NPCs presentes + estados emocionais (resto do scene)
        if len(scene_lines) > 2:
            linhas.append("\n".join(scene_lines[2:]))
        # Catálogo de quests só com quests engajadas
        if self.quests_modulo and self.character.active_quest_hooks:
            linhas.append(f"\n{self.quests_modulo}")
        # Consequências
        narr_txt = self.narrative.to_prompt()
        if narr_txt:
            linhas.append(f"\n{narr_txt}")
        # Aliados (graduado: stats em combate, status fora)
        party_txt = self.party.to_prompt(em_combate=self.combat.em_combate)
        if party_txt:
            linhas.append(f"\n{party_txt}")
        # Tensão narrativa
        if not self.combat.em_combate and self.narrative.turnos_sem_tensao >= 5:
            linhas.append(
                f"\nTENSÃO: {self.narrative.turnos_sem_tensao} turnos sem confronto — "
                "o mundo não está parado; introduza pressão ambiental, rumor, "
                "sinal de ameaça próxima ou evento inesperado neste turno"
            )
        # Diálogo opcional (testes podem pedir)
        if incluir_dialogo and self.scene.dialogo_recente:
            linhas.append("\n=== DIÁLOGO RECENTE ===")
            for turno in self.scene.dialogo_recente:
                prefixo = "Jogador" if turno.falante == "player" else turno.falante
                linhas.append(f"{prefixo}: {turno.texto}")

        return "\n".join(linhas)
