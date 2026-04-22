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

    # Estado do jogador
    player_hp: int
    player_hp_max: int
    player_conditions: list[str]       # ex: ["envenenado", "exausto"]
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
            player_hp=player_hp,
            player_hp_max=player_hp_max,
            player_conditions=[],
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

    def atualizar_quest_stage(self, quest_id: str, stage_id: str) -> None:
        self.quest_stages[quest_id] = stage_id
        if quest_id not in self.active_quest_hooks:
            self.active_quest_hooks.append(quest_id)

    def para_texto(self) -> str:
        """Serializa o estado atual para texto formatado para o prompt."""
        linhas: list[str] = [
            f"=== CENA ATUAL ===",
            f"Local: {self.location_nome} ({self.location_id})",
            f"Hora: {self.time_of_day} | Clima: {self.weather}",
            f"Jogador: {self.player_hp}/{self.player_hp_max} HP",
        ]

        if self.player_conditions:
            linhas.append(f"Condições: {', '.join(self.player_conditions)}")

        if self.npcs_presentes:
            linhas.append(f"\nNPCs presentes: {', '.join(self.npcs_presentes)}")

        if self.npc_estados_emocionais:
            linhas.append("Estados emocionais:")
            for npc_id, estado in self.npc_estados_emocionais.items():
                trust = self.trust_levels.get(npc_id, 0)
                linhas.append(f"  {npc_id}: {estado} (confiança: {trust}/5)")

        if self.active_quest_hooks:
            linhas.append(f"\nQuests ativas: {', '.join(self.active_quest_hooks)}")
            for qid, stage in self.quest_stages.items():
                linhas.append(f"  {qid} → estágio: {stage}")

        if self.dialogo_recente:
            linhas.append("\n=== DIÁLOGO RECENTE ===")
            for turno in self.dialogo_recente:
                prefixo = "Jogador" if turno.falante == "player" else turno.falante
                linhas.append(f"{prefixo}: {turno.texto}")

        return "\n".join(linhas)
