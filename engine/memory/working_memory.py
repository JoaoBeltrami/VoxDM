"""
Dataclass da cena atual — memória de trabalho do mestre de jogo.

Por que existe: centraliza todo o estado volátil da sessão em andamento —
    localização, NPCs, diálogo recente, trust levels — para ser montado
    no prompt sem nunca ser cortado por budget de tokens.
Dependências: apenas stdlib (dataclasses)
Armadilha: working_memory nunca é persistida entre sessões sozinha —
    session_writer.py extrai trust_levels e faction_standings antes de fechar.

Exemplo:
    mem = WorkingMemory.nova_sessao("grande-salao", "Noite", session_id="sess-01")
    mem.registrar_fala("player", "Eu quero falar com Fael.")
    mem.atualizar_trust("fael-valdreksson", delta=1)
    texto = mem.para_texto()  # → string formatada para o prompt
"""

import time
from dataclasses import dataclass, field


MAX_DIALOGOS = 8  # últimas N trocas mantidas em RAM

# Mapeamento de perícia D&D 5e → atributo abreviado (usado em para_texto)
_PERICIA_ATRIBUTO: dict[str, str] = {
    "Acrobacia": "des", "Adestrar Animais": "sab", "Arcanismo": "int",
    "Atletismo": "for", "Enganação": "car", "História": "int",
    "Intuição": "sab", "Intimidação": "car", "Investigação": "int",
    "Medicina": "sab", "Natureza": "int", "Percepção": "sab",
    "Atuação": "car", "Persuasão": "car", "Religião": "int",
    "Prestidigitação": "des", "Furtividade": "des", "Sobrevivência": "sab",
}


def _id_para_nome(id_kebab: str) -> str:
    """Converte 'fael-valdreksson' → 'Fael Valdreksson'."""
    return " ".join(parte.capitalize() for parte in id_kebab.split("-"))


@dataclass
class DialogueTurn:
    """Uma linha de diálogo na cena atual."""
    falante: str   # "player" ou id do NPC (ex: "fael-valdreksson")
    texto: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class WorkingMemory:
    """
    Estado completo da cena atual.

    Prioridade máxima no budget de tokens — nunca cortada.
    Budget alvo: 1600 tokens (40% do contexto total).
    """
    # Localização e ambiente
    location_id: str
    location_nome: str
    time_of_day: str
    weather: str

    # NPCs presentes (ids)
    npcs_presentes: list[str]
    # Estado emocional atual de cada NPC (pode mudar durante a sessão)
    npc_estados_emocionais: dict[str, str]

    # Relações jogador↔mundo (persistem entre cenas, zeradas entre sessões)
    trust_levels: dict[str, int]       # npc_id → 0-3 (Schema v1.2)
    faction_standings: dict[str, int]  # faction_id → pontos

    # Diálogo recente — janela deslizante de MAX_DIALOGOS trocas
    dialogo_recente: list[DialogueTurn]

    # Personagem do jogador (D&D 5e)
    player_name: str
    player_race: str
    player_class: str
    player_background: str
    player_level: int

    # Estado do jogador
    player_hp: int
    player_hp_max: int
    player_conditions: list[str]       # ex: ["envenenado", "exausto"]
    player_inventory: list[str]        # ids de itens portados — usado por trigger item_used
    active_quest_hooks: list[str]      # ids de quests/stages ativos

    # Progresso de quests — quest_id → stage_id atual
    quest_stages: dict[str, str]

    # Metadados da sessão
    session_id: str
    # Voz Edge TTS selecionada nas Opções (padrão: Francisca Neural)
    tts_voice: str = "pt-BR-FranciscaNeural"
    # Perfil de personalidade do Mestre — controla overlay injetado pelo prompt_builder
    dm_profile: str = "equilibrado"
    # Catálogo compacto das quests do módulo — texto injetado no prompt para o LLM
    # saber os IDs exatos a usar no sinal [Q:id:stage]. Vazio = módulo sem quests.
    # Exemplo: "Quests disponíveis: combate-inicial(encontro-carnicais) | ..."
    quests_modulo: str = ""
    # Sinaliza cena de combate ativo — ativa injeção de combat.md no prompt
    em_combate: bool = False
    # Iniciativa do jogador no combate atual (d20+DES; None = combate não iniciado)
    iniciativa_jogador: int | None = None
    # Rodada atual dentro do combate (1-based; 0 fora de combate)
    rodada_combate: int = 0

    # Atributos D&D 5e — Standard Array [15,14,13,12,10,8] atribuído na criação
    str_score: int = 10
    dex_score: int = 10
    con_score: int = 10
    int_score: int = 10
    wis_score: int = 10
    cha_score: int = 10
    # Proficiências derivadas de classe + background
    skill_profs: list[str] = field(default_factory=list)
    save_profs: list[str] = field(default_factory=list)

    # Inimigos em combate: id → {nome, estado, hp_rel}
    # estado: "intacto" | "ferido" | "gravemente ferido" | "incapacitado" | "morto"
    # hp_rel: impressão narrativa ("cansado mas de pé", "sangrando bastante", etc.)
    inimigos_combate: dict[str, dict[str, str]] = field(default_factory=dict)

    # Cache de iniciativa: token_id ("jogador" ou inimigo_id) → valor cacheado.
    # Populado no primeiro turno de combate. Mantido até sair_combate().
    # Authority = engine: o LLM pode propor, mas a engine decide a ordem final.
    iniciativa_cache: dict[str, int] = field(default_factory=dict)
    # Índice no array de iniciativa ordenado (pulando mortos) — quem age agora
    turno_atual_idx: int = 0

    # NPCs que foram formalmente apresentados ao jogador (mencionados pelo DM).
    # Apenas estes aparecem no HUD — os demais estão no local mas não foram introduzidos.
    npcs_apresentados: set[str] = field(default_factory=set)

    # Log de consequências da sessão (max 5, rolling) — o mundo lembra
    log_consequencias: list[str] = field(default_factory=list)


    # Aftermath: True no turno imediatamente após fim de combate — injeta cue de silêncio
    saiu_combate_recentemente: bool = False
    # Turnos consecutivos sem combate ou drama — escalada automática de tensão após 5
    turnos_sem_tensao: int = 0

    # ── Mecânicas RPG persistíveis ────────────────────────────────────────────
    # Spell slots: nível → {current, max} — vazio para classes não-conjuradoras
    spell_slots: dict[int, dict[str, int]] = field(default_factory=dict)
    # Hit Dice para descanso curto
    hit_dice_current: int = 3
    hit_dice_max: int = 3
    hit_dice_type: int = 8   # d8 padrão — sobrescrito por classe em nova_sessao
    # Death saves — só relevantes quando player_hp == 0
    death_saves_successes: int = 0
    death_saves_failures: int = 0
    death_saves_stable: bool = False
    # Economia e progressão
    gold: int = 0
    xp: int = 0
    inspiration: bool = False

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
        player_background: str = "",
        player_level: int = 1,
        tts_voice: str = "pt-BR-FranciscaNeural",
        dm_profile: str = "equilibrado",
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
    ) -> "WorkingMemory":
        """Cria uma WorkingMemory com estado inicial zerado."""
        # Tipo do dado de vida por classe (SRD 5e)
        _HIT_DICE_TIPO: dict[str, int] = {
            "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10, "Ranger": 10,
            "Bardo": 8, "Clérigo": 8, "Druida": 8, "Monge": 8, "Ladino": 8,
            "Feiticeiro": 6, "Bruxo": 6, "Mago": 6,
        }
        hd_tipo = hit_dice_type if hit_dice_type is not None else _HIT_DICE_TIPO.get(player_class, 8)
        hd_atual = hit_dice_current if hit_dice_current is not None else player_level

        return cls(
            location_id=location_id,
            location_nome=location_nome,
            time_of_day=time_of_day,
            weather=weather,
            npcs_presentes=[],
            npc_estados_emocionais={},
            trust_levels={},
            faction_standings={},
            dialogo_recente=[],
            player_name=player_name,
            player_race=player_race,
            player_class=player_class,
            player_background=player_background,
            player_level=player_level,
            player_hp=player_hp,
            player_hp_max=player_hp_max,
            player_conditions=[],
            player_inventory=[],
            active_quest_hooks=[],
            quest_stages={},
            session_id=session_id,
            tts_voice=tts_voice,
            dm_profile=dm_profile if dm_profile in {"rigoroso", "equilibrado", "tranquilo", "rule_of_cool"} else "equilibrado",
            em_combate=False,
            str_score=str_score,
            dex_score=dex_score,
            con_score=con_score,
            int_score=int_score,
            wis_score=wis_score,
            cha_score=cha_score,
            skill_profs=skill_profs or [],
            save_profs=save_profs or [],
            spell_slots=spell_slots or {},
            hit_dice_current=hd_atual,
            hit_dice_max=player_level,
            hit_dice_type=hd_tipo,
            death_saves_successes=0,
            death_saves_failures=0,
            death_saves_stable=False,
            gold=gold,
            xp=xp,
            inspiration=inspiration,
        )

    def aplicar_character_state(self, state: "object") -> None:
        """Aplica estado carregado do SQLite sobre esta WorkingMemory.

        Chamado em nova_sessao quando session_anterior_id existe — restaura
        spell slots, gold, XP, etc. sem sobrescrever trust/quests episódicos.
        """
        self.spell_slots = getattr(state, "spell_slots", {})
        self.hit_dice_current = getattr(state, "hit_dice_current", self.hit_dice_current)
        self.hit_dice_max = getattr(state, "hit_dice_max", self.hit_dice_max)
        self.hit_dice_type = getattr(state, "hit_dice_type", self.hit_dice_type)
        self.death_saves_successes = getattr(state, "death_saves_successes", 0)
        self.death_saves_failures = getattr(state, "death_saves_failures", 0)
        self.death_saves_stable = getattr(state, "death_saves_stable", False)
        self.gold = getattr(state, "gold", 0)
        self.xp = getattr(state, "xp", 0)
        self.inspiration = getattr(state, "inspiration", False)
        # HP, inventário e condições também são restaurados
        self.player_hp = getattr(state, "hp_current", self.player_hp)
        self.player_hp_max = getattr(state, "hp_max", self.player_hp_max)
        self.player_inventory = list(getattr(state, "inventory", self.player_inventory))
        self.player_conditions = list(getattr(state, "conditions", self.player_conditions))

    def registrar_fala(self, falante: str, texto: str) -> None:
        """Adiciona uma fala ao diálogo recente, mantendo a janela deslizante."""
        self.dialogo_recente.append(DialogueTurn(falante=falante, texto=texto))
        if len(self.dialogo_recente) > MAX_DIALOGOS:
            self.dialogo_recente.pop(0)

    def atualizar_trust(self, npc_id: str, delta: int) -> None:
        """Ajusta trust de um NPC, limitando ao intervalo [0, 3] conforme Schema v1.2.
        Qualquer interação de trust implica que o NPC foi apresentado ao jogador."""
        atual = self.trust_levels.get(npc_id, 0)
        self.trust_levels[npc_id] = max(0, min(3, atual + delta))
        self.npcs_apresentados.add(npc_id)

    def entrar_combate(self) -> None:
        """Ativa modo combate — prompt_builder injeta combat.md no próximo turno."""
        self.em_combate = True
        self.rodada_combate = 1
        self.iniciativa_jogador = None
        # Reseta cache de iniciativa — será populado quando primeiros inimigos aparecerem
        self.iniciativa_cache = {}
        self.turno_atual_idx = 0

    def avancar_rodada(self) -> None:
        """Incrementa contador de rodada dentro do combate ativo."""
        if self.em_combate:
            self.rodada_combate += 1

    # ── Inimigos em combate ───────────────────────────────────────────────────

    _ESTADOS_INIMIGO = frozenset(
        {"intacto", "ferido", "gravemente ferido", "incapacitado", "morto"}
    )

    def registrar_inimigo(
        self, inimigo_id: str, nome: str, estado: str = "intacto", hp_rel: str = ""
    ) -> None:
        """Adiciona ou atualiza um inimigo no combate atual."""
        self.inimigos_combate[inimigo_id] = {
            "nome": nome,
            "estado": estado if estado in self._ESTADOS_INIMIGO else "intacto",
            "hp_rel": hp_rel,
        }

    def atualizar_estado_inimigo(self, inimigo_id: str, estado: str, hp_rel: str = "") -> None:
        """Atualiza o estado narrativo de um inimigo existente."""
        if inimigo_id in self.inimigos_combate:
            self.inimigos_combate[inimigo_id]["estado"] = (
                estado if estado in self._ESTADOS_INIMIGO else "ferido"
            )
            if hp_rel:
                self.inimigos_combate[inimigo_id]["hp_rel"] = hp_rel

    def remover_inimigo(self, inimigo_id: str) -> None:
        """Remove inimigo do combate (morto ou fugiu)."""
        self.inimigos_combate.pop(inimigo_id, None)

    def sair_combate(self) -> None:
        """Desativa modo combate quando a cena é resolvida."""
        # Registra consequência antes de limpar inimigos
        mortos = sum(1 for d in self.inimigos_combate.values() if d.get("estado") == "morto")
        if mortos > 0:
            self.registrar_consequencia(f"Combate encerrado — {mortos} inimigo(s) abatido(s)")
        elif self.em_combate:
            self.registrar_consequencia("Combate encerrado")

        self.em_combate = False
        self.iniciativa_jogador = None
        self.rodada_combate = 0
        self.inimigos_combate.clear()
        # Limpa cache de iniciativa — próximo combate rola tudo de novo
        self.iniciativa_cache.clear()
        self.turno_atual_idx = 0
        self.saiu_combate_recentemente = True
        self.turnos_sem_tensao = 0

    # ── Consequências da sessão ───────────────────────────────────────────────

    _MAX_CONSEQUENCIAS = 5

    def registrar_consequencia(self, texto: str) -> None:
        """Adiciona consequência ao log rolling (máx 5)."""
        self.log_consequencias.append(texto)
        if len(self.log_consequencias) > self._MAX_CONSEQUENCIAS:
            self.log_consequencias.pop(0)

    # ── Propriedades computadas D&D 5e (SRD) ─────────────────────────────────

    @property
    def prof_bonus(self) -> int:
        return (self.player_level - 1) // 4 + 2

    @property
    def mod_for(self) -> int: return (self.str_score - 10) // 2
    @property
    def mod_des(self) -> int: return (self.dex_score - 10) // 2
    @property
    def mod_con(self) -> int: return (self.con_score - 10) // 2
    @property
    def mod_int(self) -> int: return (self.int_score - 10) // 2
    @property
    def mod_sab(self) -> int: return (self.wis_score - 10) // 2
    @property
    def mod_car(self) -> int: return (self.cha_score - 10) // 2

    @property
    def ca(self) -> int:
        """CA base sem armadura. Bárbaro: +CON. Monge: +SAB."""
        if self.player_class == "Bárbaro":
            return 10 + self.mod_des + self.mod_con
        if self.player_class == "Monge":
            return 10 + self.mod_des + self.mod_sab
        return 10 + self.mod_des

    @property
    def passive_perception(self) -> int:
        """Percepção passiva: 10 + mod_SAB + prof_bonus se Percepção em skill_profs."""
        bonus = self.prof_bonus if "Percepção" in self.skill_profs else 0
        return 10 + self.mod_sab + bonus

    def apresentar_npc(self, npc_id: str) -> None:
        """Marca NPC como apresentado — passa a aparecer no HUD."""
        self.npcs_apresentados.add(npc_id)

    def apresentar_npcs_mencionados(self, texto: str) -> None:
        """Varre o texto do DM e apresenta qualquer NPC cujo primeiro nome apareça."""
        texto_lower = texto.lower()
        for npc_id in self.npcs_presentes:
            if npc_id in self.npcs_apresentados:
                continue
            # Checa tanto o id completo ('bjorn-tharnsson') quanto o primeiro segmento ('bjorn')
            primeiro_nome = npc_id.split("-")[0]
            if primeiro_nome in texto_lower or npc_id.replace("-", " ") in texto_lower:
                self.npcs_apresentados.add(npc_id)

    def atualizar_estado_emocional(self, npc_id: str, estado: str) -> None:
        self.npc_estados_emocionais[npc_id] = estado

    def adicionar_item(self, item_id: str) -> None:
        """Adiciona item ao inventário se ainda não estiver presente."""
        if item_id not in self.player_inventory:
            self.player_inventory.append(item_id)

    def remover_item(self, item_id: str) -> None:
        """Remove item do inventário se presente."""
        if item_id in self.player_inventory:
            self.player_inventory.remove(item_id)

    # ── Iniciativa de combate ─────────────────────────────────────────────────
    #
    # Authority = engine. O LLM pode propor iniciativa narrativamente, mas é a
    # engine que cacheia, ordena e cicla os turnos. Implementação:
    #   1. No primeiro turno em que há inimigos, popular_iniciativa() roda fallback
    #      decrescente (20, 19, 18…) se LLM não emitiu valores.
    #   2. avancar_turno_iniciativa() cicla turno_atual_idx pulando mortos.
    #   3. calcular_ordem_iniciativa() devolve list[TokenIniciativa] pra UI.

    def popular_iniciativa(self, proposta_llm: dict[str, int] | None = None) -> None:
        """Popula o cache de iniciativa no primeiro turno de combate.

        Args:
            proposta_llm: opcional, mapeia inimigo_id → iniciativa proposta pelo
                LLM. Se ausente ou parcial, usa fallback decrescente (20, 19, …).

        Idempotente — só popula entradas que ainda não estão no cache.
        Jogador entra com `mod_des + 10` (rolagem fake estável) ou
        `iniciativa_jogador` se já tiver sido definida via [Rolagem: d20 = N].
        """
        # Jogador — se já temos um valor explícito de rolagem, usar; senão fake
        if "jogador" not in self.iniciativa_cache:
            if self.iniciativa_jogador is not None:
                self.iniciativa_cache["jogador"] = self.iniciativa_jogador
            else:
                self.iniciativa_cache["jogador"] = 10 + self.mod_des

        # Inimigos — preencher na ordem em que apareceram, valor decrescente do
        # topo se LLM não propôs. Começa em 20 e desce, pulando o valor do jogador
        # pra evitar empate sem critério de desempate.
        proposta_llm = proposta_llm or {}
        # valores já em uso para evitar duplicatas no fallback
        em_uso = set(self.iniciativa_cache.values())
        proximo_fallback = 20
        for inimigo_id in self.inimigos_combate.keys():
            if inimigo_id in self.iniciativa_cache:
                continue
            valor = proposta_llm.get(inimigo_id)
            if valor is None:
                while proximo_fallback in em_uso and proximo_fallback > 1:
                    proximo_fallback -= 1
                valor = max(1, proximo_fallback)
                proximo_fallback -= 1
            self.iniciativa_cache[inimigo_id] = valor
            em_uso.add(valor)

    def avancar_turno_iniciativa(self) -> None:
        """Cicla turno_atual_idx para o próximo token vivo na ordem."""
        if not self.em_combate or not self.iniciativa_cache:
            return
        ordem = self.calcular_ordem_iniciativa()
        vivos = [t for t in ordem if not t.morto]
        if not vivos:
            return
        self.turno_atual_idx = (self.turno_atual_idx + 1) % len(vivos)

    def calcular_ordem_iniciativa(self) -> list["TokenIniciativa"]:
        """Retorna a barra de iniciativa atual ordenada (desc por valor).

        Combina jogador + inimigos do combate, usando o cache. Marca turno_atual
        no token correspondente a turno_atual_idx (entre os vivos). Mortos têm
        morto=True e são pulados no ciclo de turno.
        """
        from engine.llm.types import TokenIniciativa  # import tardio: types importa working_memory

        tokens: list[TokenIniciativa] = []

        # Jogador
        ini_jogador = self.iniciativa_cache.get("jogador", 10 + self.mod_des)
        tokens.append(TokenIniciativa(
            id="jogador",
            nome=self.player_name or "Jogador",
            tipo="jogador",
            iniciativa=ini_jogador,
            hp_atual=self.player_hp,
            hp_max=self.player_hp_max,
            morto=self.player_hp <= 0,
        ))

        # Inimigos
        for inimigo_id, dados in self.inimigos_combate.items():
            ini = self.iniciativa_cache.get(inimigo_id, 0)
            estado = dados.get("estado", "intacto")
            tokens.append(TokenIniciativa(
                id=inimigo_id,
                nome=dados.get("nome", inimigo_id),
                tipo="inimigo",
                iniciativa=ini,
                # Sem hp numérico — usar estado narrativo como proxy visual
                hp_atual=0 if estado == "morto" else 1,
                hp_max=1,
                morto=estado == "morto",
            ))

        # Ordenar por iniciativa desc — desempate por tipo (jogador primeiro) só
        # importa visualmente; numericamente já basta pra estabilidade.
        tokens.sort(key=lambda t: (-t.iniciativa, 0 if t.tipo == "jogador" else 1))

        # Marca turno atual entre os vivos
        vivos = [t for t in tokens if not t.morto]
        if vivos and 0 <= self.turno_atual_idx < len(vivos):
            token_atual = vivos[self.turno_atual_idx]
            for t in tokens:
                if t.id == token_atual.id:
                    t.turno_atual = True
                    break

        return tokens

    def atualizar_quest_stage(self, quest_id: str, stage_id: str) -> None:
        self.quest_stages[quest_id] = stage_id
        if quest_id not in self.active_quest_hooks:
            self.active_quest_hooks.append(quest_id)

    def para_texto(self, incluir_dialogo: bool = False) -> str:
        """Serializa o estado atual para texto formatado para o prompt.

        Args:
            incluir_dialogo: Se True, inclui DIÁLOGO RECENTE no texto.
                             Por padrão False — o histórico é passado como
                             pares user/assistant reais pelo prompt_builder.
        """
        # Bloco do personagem — mostrado apenas se nome foi definido
        if self.player_name:
            partes_personagem = [self.player_name]
            if self.player_race:
                partes_personagem.append(self.player_race)
            if self.player_class:
                partes_personagem.append(self.player_class)
            if self.player_level > 1:
                partes_personagem.append(f"Nível {self.player_level}")
            if self.player_background:
                partes_personagem.append(f"Background: {self.player_background}")
            bloco_personagem = f"Personagem: {' | '.join(partes_personagem)}"
        else:
            bloco_personagem = "Personagem: desconhecido (aguardando apresentação)"

        # Aviso de HP crítico — muda tonalidade da narração
        hp_ratio = self.player_hp / self.player_hp_max if self.player_hp_max > 0 else 1.0
        hp_linha = f"HP: {self.player_hp}/{self.player_hp_max}"
        if hp_ratio <= 0.3:
            hp_linha += " — ESTADO CRÍTICO: jogador severamente ferido; narrar exaustão, dor, desespero"
        elif hp_ratio <= 0.5:
            hp_linha += " — FERIDO: abaixo da metade; narrar esforço e cansaço acumulado"

        linhas: list[str] = [
            f"=== CENA ATUAL ===",
            bloco_personagem,
            f"Local: {self.location_nome} ({self.location_id})",
            f"Hora: {self.time_of_day} | Clima: {self.weather}",
            hp_linha,
        ]

        _m = lambda v: f"+{v}" if v >= 0 else str(v)
        linhas.append(
            f"FOR {self.str_score}({_m(self.mod_for)}) "
            f"DES {self.dex_score}({_m(self.mod_des)}) "
            f"CON {self.con_score}({_m(self.mod_con)}) "
            f"INT {self.int_score}({_m(self.mod_int)}) "
            f"SAB {self.wis_score}({_m(self.mod_sab)}) "
            f"CAR {self.cha_score}({_m(self.mod_car)})"
        )
        linhas.append(
            f"Proef +{self.prof_bonus} | CA {self.ca} | Percepção Passiva {self.passive_perception}"
        )
        if self.saiu_combate_recentemente:
            linhas.append(
                "APÓS COMBATE — narre o silêncio que retorna, as feridas, "
                "o estado dos inimigos caídos, o que mudou no cenário; "
                "um momento de respiração antes de seguir"
            )

        if self.em_combate:
            rodada_str = f"Rodada {self.rodada_combate}" if self.rodada_combate else "combate iniciando"
            ini_str = (
                f"iniciativa {self.iniciativa_jogador}" if self.iniciativa_jogador is not None
                else "aguardando iniciativa"
            )
            linhas.append(f"COMBATE ATIVO — {rodada_str} — {ini_str}")
            if self.inimigos_combate:
                partes_ini = []
                for dados in self.inimigos_combate.values():
                    desc = dados["nome"]
                    if dados.get("estado") and dados["estado"] != "intacto":
                        desc += f" ({dados['estado']})"
                    if dados.get("hp_rel"):
                        desc += f" [{dados['hp_rel']}]"
                    partes_ini.append(desc)
                linhas.append(f"Inimigos: {', '.join(partes_ini)}")
        if self.save_profs:
            _save_mods = {
                "FOR": self.mod_for, "DES": self.mod_des, "CON": self.mod_con,
                "INT": self.mod_int, "SAB": self.mod_sab, "CAR": self.mod_car,
            }
            saves = [f"{s}({_m(_save_mods.get(s, 0) + self.prof_bonus)})" for s in self.save_profs]
            linhas.append(f"Saves: {', '.join(saves)}")
        if self.skill_profs:
            skills = []
            for sk in self.skill_profs:
                attr = _PERICIA_ATRIBUTO.get(sk, "int")
                total = getattr(self, f"mod_{attr}") + self.prof_bonus
                skills.append(f"{sk}({_m(total)})")
            linhas.append(f"Perícias: {', '.join(skills)}")

        if self.player_conditions:
            linhas.append(f"Condições: {', '.join(self.player_conditions)}")
        if self.player_inventory:
            linhas.append(f"Inventário: {', '.join(self.player_inventory)}")

        if self.npcs_presentes:
            linhas.append(f"\nNPCs presentes: {', '.join(self.npcs_presentes)}")

        if self.npc_estados_emocionais:
            linhas.append("Estados emocionais:")
            for npc_id, estado in self.npc_estados_emocionais.items():
                trust = self.trust_levels.get(npc_id, 0)
                linhas.append(f"  {_id_para_nome(npc_id)}: {estado} (confiança: {trust}/3)")

        if self.active_quest_hooks:
            linhas.append(f"\nQuests ativas: {', '.join(self.active_quest_hooks)}")
            for qid, stage in self.quest_stages.items():
                linhas.append(f"  {qid} → estágio: {stage}")

        if self.quests_modulo:
            linhas.append(f"\n{self.quests_modulo}")

        if self.log_consequencias:
            linhas.append(f"\nCONSEQUÊNCIAS: {'; '.join(self.log_consequencias)}")

        if not self.em_combate and self.turnos_sem_tensao >= 5:
            linhas.append(
                f"\nTENSÃO: {self.turnos_sem_tensao} turnos sem confronto — "
                "o mundo não está parado; introduza pressão ambiental, rumor, "
                "sinal de ameaça próxima ou evento inesperado neste turno"
            )

        if incluir_dialogo and self.dialogo_recente:
            linhas.append("\n=== DIÁLOGO RECENTE ===")
            for turno in self.dialogo_recente:
                prefixo = "Jogador" if turno.falante == "player" else turno.falante
                linhas.append(f"{prefixo}: {turno.texto}")

        return "\n".join(linhas)
