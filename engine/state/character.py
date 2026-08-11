"""
Estado do personagem jogador — atributos D&D 5e, HP, recursos, magias.

Por que existe: o personagem é a entidade de vida mais longa na sessão.
    HP, slots, features, gold, XP, condições — tudo persiste no SQLite via
    character_store e precisa de uma camada cache em memória que centralize
    operações (level up, descanso, dano/cura) sem espalhar pela WorkingMemory.

Dependências: apenas stdlib

Armadilha: properties D&D 5e (mod_*, prof_bonus, ca, passive_perception) são
    derivadas de attrs base. NÃO duplicar fórmulas em outros módulos — sempre
    consultar via property. Mudou um attr → properties atualizam automaticamente.
"""

from dataclasses import dataclass, field
from typing import Any

from engine.state.inventario import (
    ItemInventario,
    adicionar,
    arma_equipada,
    equipar,
    para_exibicao,
    para_strings,
    remover,
    sincronizar,
)

# Mapa de perícia D&D 5e → atributo abreviado
_PERICIA_ATRIBUTO: dict[str, str] = {
    "Acrobacia": "des", "Adestrar Animais": "sab", "Arcanismo": "int",
    "Atletismo": "for", "Enganação": "car", "História": "int",
    "Intuição": "sab", "Intimidação": "car", "Investigação": "int",
    "Medicina": "sab", "Natureza": "int", "Percepção": "sab",
    "Atuação": "car", "Persuasão": "car", "Religião": "int",
    "Prestidigitação": "des", "Furtividade": "des", "Sobrevivência": "sab",
}


@dataclass
class PlayerCharacter:
    """Personagem jogador completo — identidade, atributos, recursos, magias."""

    # Identidade
    player_name: str = ""
    player_race: str = ""
    player_class: str = ""
    player_subclass: str = ""
    player_background: str = ""
    player_description: str = ""
    player_level: int = 1

    # HP e condições
    hp_current: int = 30
    hp_max: int = 30
    player_conditions: list[str] = field(default_factory=list)
    # INVENTARIO-SEM-ESTADO-1 (10/08): era `list[str]` — nomes soltos que só o
    # LLM interpretava. A engine não sabia com que ARMA o jogador atacava (o
    # Mestre pediu Força a um Ranger de arco) e "duas poções" era literalmente
    # uma string. Agora a lista ESTRUTURADA é a fonte única, e `player_inventory`
    # continua existindo como vista derivada — meio sistema consulta posse com
    # `"Poção de Cura" in wm.player_inventory`, e isso segue funcionando.
    inventario: list[ItemInventario] = field(default_factory=list)
    active_quest_hooks: list[str] = field(default_factory=list)
    quest_stages: dict[str, str] = field(default_factory=dict)

    # Atributos D&D 5e (Standard Array default)
    str_score: int = 10
    dex_score: int = 10
    con_score: int = 10
    int_score: int = 10
    wis_score: int = 10
    cha_score: int = 10

    # Proficiências
    skill_profs: list[str] = field(default_factory=list)
    save_profs: list[str] = field(default_factory=list)

    # Magias e slots
    spell_slots: dict[int, dict[str, int]] = field(default_factory=dict)
    spells_conhecidas: list[str] = field(default_factory=list)

    # Hit Dice (descanso curto)
    hit_dice_current: int = 3
    hit_dice_max: int = 3
    hit_dice_type: int = 8

    # Death saves
    death_saves_successes: int = 0
    death_saves_failures: int = 0
    death_saves_stable: bool = False

    # Economia e progressão
    gold: int = 0
    xp: int = 0
    inspiration: bool = False

    # Features de classe — feature_id → {nome, disponivel, usos_max, usos_atual, restaura}
    class_features: dict[str, dict[str, Any]] = field(default_factory=dict)

    # LEVELUP-SEM-ESCOLHA-1 (playtest 26/07): fila de escolhas que o JOGADOR deve
    # ao subir de nível, no formato de `progression.escolhas_do_nivel` mais o
    # campo `nivel`. Precisa ser ESTADO (e não só o retorno de `aplicar_level_up`)
    # porque a oferta tem que sobreviver a fechar o browser: os scores já
    # persistem via personagem_config, mas a OFERTA não persistia em lugar nenhum
    # — quem fechasse antes de escolher ficava "devendo" um ASI pra sempre, sem
    # nenhum jeito de resgatar.
    asi_pendente: list[dict[str, Any]] = field(default_factory=list)

    # Alinhamento (decisão Beltrami 29-30/07). O rótulo é DECLARADO na criação —
    # à mão no CharacterForm ou por voz na Sessão Zero — e vira a POSIÇÃO INICIAL
    # dos eixos. Dali em diante são os atos do jogador que mandam: o declarado é
    # quem você diz que é; os eixos são quem você provou ser.
    alinhamento_declarado: str = ""
    alinhamento_eixos: dict[str, Any] = field(default_factory=dict)

    # Cicatrizes narrativas — marcas permanentes de quase-morte (Pilar Perigo
    # 10/06). NPCs reagem a elas; persistem entre sessões via dm_state. Cap 5.
    cicatrizes: list[str] = field(default_factory=list)

    # Gate de [CICATRIZ] (playtest 03/07): true se o jogador chegou a 0 PV em
    # algum momento DESTA sessão. Não persiste — flag "nesta sessão" por
    # definição; cura posterior NÃO limpa (a quase-morte já aconteceu).
    chegou_a_zero_hp: bool = False

    # ── Properties D&D 5e (single source of truth) ───────────────────────────

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
        """10 + mod_SAB + prof_bonus se Percepção em skill_profs."""
        bonus = self.prof_bonus if "Percepção" in self.skill_profs else 0
        return 10 + self.mod_sab + bonus

    # ── Operações ────────────────────────────────────────────────────────────

    @property
    def player_inventory(self) -> list[str]:
        """Vista `list[str]` do inventário — nomes planos, sem decoração.

        Derivada de `inventario`, que é a fonte única. Escrever nesta lista NÃO
        muda o estado (ela é uma cópia): use `adicionar_item`/`remover_item`, ou
        atribua a lista inteira (o setter reconstrói a estrutura).
        """
        return para_strings(self.inventario)

    @player_inventory.setter
    def player_inventory(self, nomes: list[str]) -> None:
        """Aceita o formato antigo — é por aqui que sessão e banco antigos entram.

        Faz MERGE, não substituição: o frontend sincroniza a ficha mandando só
        nomes, e reconstruir do zero apagaria o que a engine sabe e o cliente não
        (arma equipada, quantidade) toda vez que o jogador abrisse a ficha.
        """
        self.inventario = sincronizar(self.inventario, list(nomes or []))

    def adicionar_item(self, item_id: str, quantidade: int = 1) -> None:
        """Adiciona o item, empilhando quantidade quando já existe."""
        adicionar(self.inventario, item_id, quantidade)

    def remover_item(self, item_id: str, quantidade: int = 1) -> None:
        """Tira `quantidade`; o item some da lista quando zera."""
        remover(self.inventario, item_id, quantidade)

    def equipar_item(self, item_id: str) -> bool:
        """Equipa arma/armadura, desequipando o que ocupava o mesmo slot."""
        return equipar(self.inventario, item_id)

    def arma_equipada(self) -> str:
        """Índice SRD da arma equipada; "" quando nenhuma."""
        return arma_equipada(self.inventario)

    # DANO-SEM-CAUSA-1 (playtest 26/07): a engine aplicava [DANO] e o motivo era
    # descartado por `strip_marcadores` antes do texto chegar ao jogador — sobrava
    # o HP caindo. Ele tomou 8 de dano FORA de combate narrando só "sigo o
    # caminho" e reportou "tomei dano do nada". Risco que não é LEGÍVEL não é
    # risco sentido (Camada 2 do ADR-005): a engine sabia a causa e jogava fora.
    # Cada item: {"tipo": "dano"|"cura", "valor": int, "motivo": str,
    #             "hp": int, "hp_max": int}. Drenado 1×/turno pelo websocket.
    eventos_vitais_turno: list[dict] = field(default_factory=list)

    def registrar_evento_vital(
        self, tipo: str, valor: int, motivo: str, hp: int, hp_max: int
    ) -> None:
        """Guarda a CAUSA de uma mudança de HP pra que ela alcance o jogador."""
        self.eventos_vitais_turno.append({
            "tipo": tipo, "valor": int(valor), "motivo": (motivo or "").strip()[:80],
            "hp": int(hp), "hp_max": int(hp_max),
        })

    def drenar_eventos_vitais(self) -> list[dict]:
        """Devolve e limpa os eventos do turno (mesmo idioma de eventos_relacao)."""
        eventos = list(self.eventos_vitais_turno)
        self.eventos_vitais_turno.clear()
        return eventos

    # Os 6 atributos, na ordem do SRD. Fonte única pra validação do ASI.
    ATRIBUTOS_ASI: tuple[str, ...] = (
        "str_score", "dex_score", "con_score", "int_score", "wis_score", "cha_score",
    )
    _TETO_ATRIBUTO = 20

    def definir_alinhamento_inicial(self, rotulo: str) -> bool:
        """Fixa o alinhamento declarado e posiciona os eixos nele.

        Meio caminho entre neutro e cravado (±50): longe o bastante pra o mundo
        já te tratar como o que você disse ser, perto o bastante pra dois ou três
        atos contrários te moverem. Declarar "Leal e Bom" e agir como monstro
        DEVE te levar pro outro lado — senão a ficha vira álibi.
        """
        from engine.alinhamento import EixosAlinhamento, rotulo_para_eixos

        eixos = rotulo_para_eixos(rotulo)
        if eixos is None:
            return False
        ordem, moral = eixos
        self.alinhamento_declarado = rotulo.strip()
        self.alinhamento_eixos = EixosAlinhamento(moral=moral, ordem=ordem).to_dict()
        return True

    def aplicar_asi(self, nivel: int, aumentos: dict[str, int]) -> bool:
        """Gasta um Incremento de Atributo da fila. Retorna False se inválido.

        A REGRA vive aqui, no backend, de propósito: +2 num atributo OU +1 em
        dois, nenhum passando de 20. Validar só no frontend deixaria um cliente
        adulterado subir +2 num atributo que já está em 19 e furar o SRD.

        Tudo-ou-nada: se qualquer parte não valida, nada é mutado e a fila fica
        intacta — o jogador não perde a escolha por causa de um payload torto.
        """
        entrada = next(
            (e for e in self.asi_pendente if int(e.get("nivel", -1)) == int(nivel)),
            None,
        )
        if entrada is None:
            return False  # não há ASI devido nesse nível

        limpos: dict[str, int] = {}
        for attr, delta in (aumentos or {}).items():
            if attr not in self.ATRIBUTOS_ASI:
                return False
            try:
                d = int(delta)
            except (TypeError, ValueError):
                return False
            if d not in (1, 2):
                return False
            limpos[attr] = d

        # +2 num só OU +1 em dois: a soma é sempre 2, e um +2 não pode vir
        # acompanhado. Escrito como duas condições porque {"a":1} soma 1 e
        # {"a":2,"b":2} soma 4 — ambos precisam cair fora.
        if sum(limpos.values()) != 2:
            return False
        if 2 in limpos.values() and len(limpos) != 1:
            return False

        for attr, d in limpos.items():
            if int(getattr(self, attr, 10)) + d > self._TETO_ATRIBUTO:
                return False

        for attr, d in limpos.items():
            setattr(self, attr, int(getattr(self, attr, 10)) + d)
        self.asi_pendente.remove(entrada)
        return True

    def aplicar_dano(self, quantidade: int) -> int:
        """Aplica dano do marker [DANO] com clamps. Retorna HP resultante.

        Cap por aplicação = hp_max: um único golpe pode no máximo derrubar
        de full pra 0 — guarda contra alucinação tipo [DANO: -999].
        """
        quantidade = max(0, min(int(quantidade), self.hp_max))
        self.hp_current = max(0, self.hp_current - quantidade)
        if self.hp_current == 0:
            # Marca a quase-morte da sessão — libera o gate de [CICATRIZ].
            self.chegou_a_zero_hp = True
        return self.hp_current

    def aplicar_cura(self, quantidade: int) -> int:
        """Aplica cura do marker [CURA] com clamp em hp_max. Retorna HP.

        Voltar a >0 reseta death saves (regra 5e: qualquer cura estabiliza).
        """
        quantidade = max(0, min(int(quantidade), self.hp_max))
        self.hp_current = min(self.hp_max, self.hp_current + quantidade)
        if self.hp_current > 0:
            self.death_saves_successes = 0
            self.death_saves_failures = 0
            self.death_saves_stable = False
        return self.hp_current

    def registrar_cicatriz(self, texto: str) -> bool:
        """Registra cicatriz permanente (dedup, trunca 120 chars, cap 5)."""
        texto = texto.strip()[:120]
        if not texto or texto in self.cicatrizes:
            return False
        self.cicatrizes.append(texto)
        if len(self.cicatrizes) > 5:
            self.cicatrizes.pop(0)
        return True

    def atualizar_quest_stage(self, quest_id: str, stage_id: str) -> None:
        """Avança quest com cap de 15 active_quest_hooks (eviction oldest)."""
        self.quest_stages[quest_id] = stage_id
        if quest_id not in self.active_quest_hooks:
            self.active_quest_hooks.append(quest_id)
            if len(self.active_quest_hooks) > 15:
                self.active_quest_hooks.pop(0)

    def inicializar_features_classe(self, player_class: str, player_subclass: str = "") -> None:
        """Popula class_features com features da classe/subclasse.

        Sobrescreve completamente — usa restaurar_features() para repor usos gastos.
        """
        features: dict[str, dict[str, Any]] = {}
        classe = player_class.lower()
        sub = player_subclass.lower()

        if "guerreiro" in classe or "fighter" in classe:
            features["action-surge"] = {"nome": "Action Surge", "disponivel": True, "usos_max": 1, "usos_atual": 1, "restaura": "curto"}
            features["second-wind"] = {"nome": "Second Wind", "disponivel": True, "usos_max": 1, "usos_atual": 1, "restaura": "curto"}
            if "mestre de batalha" in sub:
                features["superiority-dice"] = {"nome": "Dados de Superioridade", "disponivel": True, "usos_max": 4, "usos_atual": 4, "restaura": "curto"}

        if "barbaro" in classe or "bárbaro" in classe:
            features["rage"] = {"nome": "Fúria", "disponivel": True, "usos_max": 3, "usos_atual": 3, "restaura": "longo"}
            features["reckless-attack"] = {"nome": "Ataque Imprudente", "disponivel": True, "usos_max": -1, "usos_atual": -1, "restaura": "turno"}

        if "ladino" in classe or "rogue" in classe:
            features["sneak-attack"] = {"nome": "Ataque Furtivo", "disponivel": True, "usos_max": -1, "usos_atual": -1, "restaura": "turno"}
            features["cunning-action"] = {"nome": "Ação Ardilosa", "disponivel": True, "usos_max": -1, "usos_atual": -1, "restaura": "turno"}

        if "paladino" in classe:
            features["divine-smite"] = {"nome": "Investida Divina", "disponivel": True, "usos_max": -1, "usos_atual": -1, "restaura": "turno"}
            features["lay-on-hands"] = {"nome": "Imposição de Mãos", "disponivel": True, "usos_max": 15, "usos_atual": 15, "restaura": "longo"}

        if "monge" in classe:
            features["ki"] = {"nome": "Ki", "disponivel": True, "usos_max": 3, "usos_atual": 3, "restaura": "curto"}

        if "mago" in classe or "feiticeiro" in classe:
            features["arcane-recovery"] = {"nome": "Recuperação Arcana", "disponivel": True, "usos_max": 1, "usos_atual": 1, "restaura": "longo"}

        self.class_features = features

    def restaurar_features(self, tipo_descanso: str) -> None:
        """Restaura class_features conforme tipo. 'longo' restaura tudo; 'curto' restaura
        features com restaura in {'curto', 'turno'}."""
        for _fid, dados in self.class_features.items():
            restaura = dados.get("restaura", "longo")
            if tipo_descanso == "longo" or (
                tipo_descanso == "curto" and restaura in ("curto", "turno")
            ):
                dados["disponivel"] = True
                if dados.get("usos_max", -1) > 0:
                    dados["usos_atual"] = dados["usos_max"]

    # ── Serialização para prompt ─────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Bloco completo do personagem para o system prompt."""
        # Identidade
        if self.player_name:
            partes = [self.player_name]
            if self.player_race: partes.append(self.player_race)
            if self.player_class: partes.append(self.player_class)
            if self.player_level > 1: partes.append(f"Nível {self.player_level}")
            if self.player_background: partes.append(f"Background: {self.player_background}")
            bloco_id = f"Personagem: {' | '.join(partes)}"
        else:
            bloco_id = "Personagem: desconhecido (aguardando apresentação)"

        # HP com aviso narrativo
        hp_ratio = self.hp_current / self.hp_max if self.hp_max > 0 else 1.0
        hp_linha = f"HP: {self.hp_current}/{self.hp_max}"
        if hp_ratio <= 0.3:
            hp_linha += " — ESTADO CRÍTICO: jogador severamente ferido; narrar exaustão, dor, desespero"
        elif hp_ratio <= 0.5:
            hp_linha += " — FERIDO: abaixo da metade; narrar esforço e cansaço acumulado"

        linhas = [bloco_id, hp_linha]

        # Subclasse
        if self.player_subclass:
            linhas.insert(1, f"Subclasse: {self.player_subclass}")

        # Atributos
        def _m(v: int) -> str:
            return f"+{v}" if v >= 0 else str(v)
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

        # Saves proficientes
        if self.save_profs:
            _mods = {"FOR": self.mod_for, "DES": self.mod_des, "CON": self.mod_con,
                     "INT": self.mod_int, "SAB": self.mod_sab, "CAR": self.mod_car}
            saves = [f"{s}({_m(_mods.get(s, 0) + self.prof_bonus)})" for s in self.save_profs]
            linhas.append(f"Saves: {', '.join(saves)}")

        # Perícias proficientes
        if self.skill_profs:
            skills = []
            for sk in self.skill_profs:
                attr = _PERICIA_ATRIBUTO.get(sk, "int")
                total = getattr(self, f"mod_{attr}") + self.prof_bonus
                skills.append(f"{sk}({_m(total)})")
            linhas.append(f"Perícias: {', '.join(skills)}")

        # Condições
        if self.player_conditions:
            linhas.append(f"Condições: {', '.join(self.player_conditions)}")

        # Inventário (cap 20 no prompt)
        if self.inventario:
            # `para_exibicao`, não `player_inventory`: o Mestre precisa saber que
            # sobrou UMA poção e qual arma está na mão. A vista plana existe pra
            # CHECAGEM de posse (`"Poção" in inventario`) e mostrá-la aqui era
            # jogar fora justamente o que o inventário estruturado passou a saber.
            itens = para_exibicao(self.inventario)
            sufixo = f" … e {len(itens) - 20} mais" if len(itens) > 20 else ""
            linhas.append(f"Inventário: {', '.join(itens[:20])}{sufixo}")

        # Quests ativas (5 mais recentes)
        if self.active_quest_hooks:
            hooks = self.active_quest_hooks[-5:]
            linhas.append(f"\nQuests ativas: {', '.join(hooks)}")
            for qid in hooks:
                stage = self.quest_stages.get(qid)
                if stage:
                    linhas.append(f"  {qid} → estágio: {stage}")

        return "\n".join(linhas)
