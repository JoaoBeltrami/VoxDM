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
    trust_levels: dict[str, int]       # npc_id → 0-5
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
    ) -> "WorkingMemory":
        """Cria uma WorkingMemory com estado inicial zerado."""
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
        )

    def registrar_fala(self, falante: str, texto: str) -> None:
        """Adiciona uma fala ao diálogo recente, mantendo a janela deslizante."""
        self.dialogo_recente.append(DialogueTurn(falante=falante, texto=texto))
        if len(self.dialogo_recente) > MAX_DIALOGOS:
            self.dialogo_recente.pop(0)

    def atualizar_trust(self, npc_id: str, delta: int) -> None:
        """Ajusta trust de um NPC, limitando ao intervalo [0, 5]."""
        atual = self.trust_levels.get(npc_id, 0)
        self.trust_levels[npc_id] = max(0, min(5, atual + delta))

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

        linhas: list[str] = [
            f"=== CENA ATUAL ===",
            bloco_personagem,
            f"Local: {self.location_nome} ({self.location_id})",
            f"Hora: {self.time_of_day} | Clima: {self.weather}",
            f"HP: {self.player_hp}/{self.player_hp_max}",
        ]

        if self.player_conditions:
            linhas.append(f"Condições: {', '.join(self.player_conditions)}")

        if self.npcs_presentes:
            linhas.append(f"\nNPCs presentes: {', '.join(self.npcs_presentes)}")

        if self.npc_estados_emocionais:
            linhas.append("Estados emocionais:")
            for npc_id, estado in self.npc_estados_emocionais.items():
                trust = self.trust_levels.get(npc_id, 0)
                linhas.append(f"  {_id_para_nome(npc_id)}: {estado} (confiança: {trust}/5)")

        if self.active_quest_hooks:
            linhas.append(f"\nQuests ativas: {', '.join(self.active_quest_hooks)}")
            for qid, stage in self.quest_stages.items():
                linhas.append(f"  {qid} → estágio: {stage}")

        if incluir_dialogo and self.dialogo_recente:
            linhas.append("\n=== DIÁLOGO RECENTE ===")
            for turno in self.dialogo_recente:
                prefixo = "Jogador" if turno.falante == "player" else turno.falante
                linhas.append(f"{prefixo}: {turno.texto}")

        return "\n".join(linhas)
