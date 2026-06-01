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
    player_inventory: list[str] = field(default_factory=list)
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

    def adicionar_item(self, item_id: str) -> None:
        """Adiciona item se ainda não estiver presente."""
        if item_id not in self.player_inventory:
            self.player_inventory.append(item_id)

    def remover_item(self, item_id: str) -> None:
        """Remove item se presente."""
        if item_id in self.player_inventory:
            self.player_inventory.remove(item_id)

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
        if self.player_inventory:
            inv_exibido = self.player_inventory[:20]
            sufixo = f" … e {len(self.player_inventory) - 20} mais" if len(self.player_inventory) > 20 else ""
            linhas.append(f"Inventário: {', '.join(inv_exibido)}{sufixo}")

        # Quests ativas (5 mais recentes)
        if self.active_quest_hooks:
            hooks = self.active_quest_hooks[-5:]
            linhas.append(f"\nQuests ativas: {', '.join(hooks)}")
            for qid in hooks:
                stage = self.quest_stages.get(qid)
                if stage:
                    linhas.append(f"  {qid} → estágio: {stage}")

        return "\n".join(linhas)
