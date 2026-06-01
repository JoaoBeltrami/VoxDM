"""
Estado da cena atual — local, hora, NPCs presentes, diálogo recente, trust.

Por que existe: tudo que muda quando o jogador troca de local fica aqui.
    NPCs presentes, suas emoções, confiança, e a janela de diálogo recente
    (MAX_DIALOGOS=6) que vai pro LLM como pares user/assistant.

Dependências: apenas stdlib + helper _id_para_nome de working_memory (export)

Armadilha: npcs_apresentados é set — NPCs do local mas que não foram nomeados
    pelo mestre ainda. Só os apresentados aparecem no HUD do frontend.
"""

import time
from dataclasses import dataclass, field

# Janela deslizante de diálogo
MAX_DIALOGOS = 6

# Cap de estados emocionais (locais antigos não devem inflar prompt)
_MAX_ESTADOS = 15


@dataclass
class DialogueTurn:
    """Uma linha de diálogo na cena atual."""
    falante: str   # "player" ou id do NPC
    texto: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SceneState:
    """Tudo que pertence à cena atual."""

    location_id: str = ""
    location_nome: str = ""
    time_of_day: str = "Dia"
    weather: str = "Limpo"

    # NPCs no local (todos os ids)
    npcs_presentes: list[str] = field(default_factory=list)

    # NPCs que foram apresentados ao jogador (subset de npcs_presentes)
    npcs_apresentados: set[str] = field(default_factory=set)

    # Estado emocional atual de cada NPC (cap de 15)
    npc_estados_emocionais: dict[str, str] = field(default_factory=dict)

    # Relação jogador↔NPC: 0-3 (Schema v1.2)
    trust_levels: dict[str, int] = field(default_factory=dict)

    # Facções e standings
    faction_standings: dict[str, int] = field(default_factory=dict)

    # Janela deslizante de diálogo
    dialogo_recente: list[DialogueTurn] = field(default_factory=list)

    # ── Operações ────────────────────────────────────────────────────────────

    def registrar_fala(self, falante: str, texto: str) -> None:
        """Adiciona fala à janela deslizante."""
        self.dialogo_recente.append(DialogueTurn(falante=falante, texto=texto))
        if len(self.dialogo_recente) > MAX_DIALOGOS:
            self.dialogo_recente.pop(0)

    def atualizar_trust(self, npc_id: str, delta: int) -> None:
        """Ajusta trust [0, 3]. Interação implica apresentação."""
        atual = self.trust_levels.get(npc_id, 0)
        self.trust_levels[npc_id] = max(0, min(3, atual + delta))
        self.npcs_apresentados.add(npc_id)

    def apresentar_npc(self, npc_id: str) -> None:
        """Marca NPC como apresentado — aparece no HUD."""
        self.npcs_apresentados.add(npc_id)

    def apresentar_npcs_mencionados(self, texto: str) -> None:
        """Varre texto e marca como apresentado qualquer NPC mencionado."""
        texto_lower = texto.lower()
        for npc_id in self.npcs_presentes:
            if npc_id in self.npcs_apresentados:
                continue
            primeiro_nome = npc_id.split("-")[0]
            if primeiro_nome in texto_lower or npc_id.replace("-", " ") in texto_lower:
                self.npcs_apresentados.add(npc_id)

    def atualizar_estado_emocional(self, npc_id: str, estado: str) -> None:
        """Atualiza estado emocional com cap de 15 (eviction oldest)."""
        self.npc_estados_emocionais[npc_id] = estado
        if len(self.npc_estados_emocionais) > _MAX_ESTADOS:
            oldest = next(iter(self.npc_estados_emocionais))
            if oldest != npc_id:
                del self.npc_estados_emocionais[oldest]

    # ── Serialização ─────────────────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Bloco de cena para o system prompt."""
        from engine.memory.working_memory import _id_para_nome  # evita ciclo

        linhas = [
            f"Local: {self.location_nome} ({self.location_id})",
            f"Hora: {self.time_of_day} | Clima: {self.weather}",
        ]

        if self.npcs_presentes:
            linhas.append(f"\nNPCs presentes: {', '.join(self.npcs_presentes)}")

        if self.npc_estados_emocionais:
            presentes = set(self.npcs_presentes)
            estados_em_cena = {
                npc_id: estado
                for npc_id, estado in self.npc_estados_emocionais.items()
                if npc_id in presentes
            }
            if estados_em_cena:
                linhas.append("Estados emocionais:")
                for npc_id, estado in estados_em_cena.items():
                    trust = self.trust_levels.get(npc_id, 0)
                    linhas.append(f"  {_id_para_nome(npc_id)}: {estado} (confiança: {trust}/3)")

        return "\n".join(linhas)
