"""
Estado narrativo do mestre — fios, cliffhanger, fatos âncora, pacing.

Por que existe: o mestre veterano lembra coisas para além da cena atual:
    plot threads em aberto, gancho dramático para encerrar, fatos já narrados
    (anti-repetição), pacing meter, cartas de improviso. Tudo isso vivia em
    WorkingMemory misturado com estado de cena/combate.

Dependências: apenas stdlib

Armadilha: cartas_improviso são one-shot — uma vez usadas (ou após decay),
    descartar. cliffhanger_pendente é consumido na próxima abertura (one-shot).
"""

from dataclasses import dataclass, field

from config import settings

# Caps anti-crescimento em sessão longa
_MAX_FIOS = 5
_MAX_ANCORAS = 5
_MAX_CONSEQUENCIAS = 5
_MAX_AGENDA = 8
_MAX_VOZES = 20


@dataclass
class NarrativeState:
    """Memória de longo prazo do mestre dentro da sessão atual."""

    # Plot threads em aberto — listadas no prompt como "Fios em aberto"
    fios_soltos: list[str] = field(default_factory=list)

    # Gancho dramático para encerrar a sessão atual (one-shot)
    cliffhanger_pendente: str = ""

    # Agenda paralela de NPCs: npc_id → plano em background
    agenda_npcs: dict[str, str] = field(default_factory=dict)

    # Cartas de improviso — pool de 3 sorteado no início, decay após 5 turnos
    cartas_improviso: list[str] = field(default_factory=list)
    turnos_desde_cartas: int = 0

    # Pacing meter 0-10 (0=calmo total, 10=clímax total)
    pacing_nivel: float = 3.0
    turnos_sem_tensao: int = 0

    # Repetition guard — fatos já narrados
    fatos_ancora: list[str] = field(default_factory=list)

    # Log de consequências (max 5, rolling)
    log_consequencias: list[str] = field(default_factory=list)

    # ── Rolling summary (resumo contínuo intra-sessão) ───────────────────────
    # Prosa que comprime tudo o que já aconteceu NESTA sessão. Injetada no
    # system prompt como memória interna do mestre — acumula incrementalmente
    # a cada janela de diálogo, evitando que turnos antigos (fora da janela de
    # MAX_DIALOGOS) se percam em sessões longas.
    resumo_rolling: str = ""
    turnos_desde_resumo: int = 0

    # ── Operações idempotentes ───────────────────────────────────────────────

    def adicionar_fio(self, texto: str) -> bool:
        """Adiciona fio se não duplicado. Retorna True se inserido."""
        texto = texto.strip()
        if not texto or texto in self.fios_soltos:
            return False
        self.fios_soltos.append(texto)
        if len(self.fios_soltos) > _MAX_FIOS:
            self.fios_soltos.pop(0)
        return True

    def registrar_ancora(self, texto: str) -> bool:
        """Adiciona fato âncora com dedup. Retorna True se inserido."""
        texto = texto.strip()
        if not texto or texto in self.fatos_ancora:
            return False
        self.fatos_ancora.append(texto)
        if len(self.fatos_ancora) > _MAX_ANCORAS:
            self.fatos_ancora.pop(0)
        return True

    def registrar_consequencia(self, texto: str) -> None:
        """Adiciona consequência ao log rolling."""
        self.log_consequencias.append(texto)
        if len(self.log_consequencias) > _MAX_CONSEQUENCIAS:
            self.log_consequencias.pop(0)

    def atualizar_agenda(self, npc_id: str, plano: str) -> None:
        """Atualiza agenda de NPC com cap de 8 (eviction oldest)."""
        self.agenda_npcs[npc_id] = plano
        while len(self.agenda_npcs) > _MAX_AGENDA:
            oldest = next(iter(self.agenda_npcs))
            del self.agenda_npcs[oldest]

    def consumir_cliffhanger(self) -> str:
        """Retorna e limpa cliffhanger (one-shot)."""
        ch = self.cliffhanger_pendente
        self.cliffhanger_pendente = ""
        return ch

    def decay_cartas(self) -> bool:
        """Incrementa contador e descarta cartas se ≥5 turnos sem uso. True se descartou."""
        if not self.cartas_improviso:
            return False
        self.turnos_desde_cartas += 1
        if self.turnos_desde_cartas >= 5:
            self.cartas_improviso = []
            self.turnos_desde_cartas = 0
            return True
        return False

    # ── Pacing ────────────────────────────────────────────────────────────────

    def ajustar_pacing(self, em_combate: bool, saiu_combate_recentemente: bool, trust_mudou: bool) -> None:
        """Aplica regras de pacing baseado no estado do turno."""
        # Tensão narrativa
        if em_combate or trust_mudou:
            self.turnos_sem_tensao = 0
        else:
            self.turnos_sem_tensao += 1

        # Pacing meter
        if em_combate:
            self.pacing_nivel = min(10.0, self.pacing_nivel + 1.5)
        elif saiu_combate_recentemente:
            self.pacing_nivel = max(0.0, self.pacing_nivel - 0.5)
        elif self.turnos_sem_tensao > 3:
            self.pacing_nivel = max(0.0, self.pacing_nivel - 0.3)
        else:
            self.pacing_nivel = min(10.0, self.pacing_nivel + 0.2)

    # ── Rolling summary ──────────────────────────────────────────────────────

    def marcar_turno_resumo(self) -> None:
        """Conta mais um turno desde o último resumo rolling."""
        self.turnos_desde_resumo += 1

    def deve_resumir(
        self,
        intervalo: int,
        em_climax: bool = False,
        mudou_local: bool = False,
    ) -> bool:
        """Predicado barato: hora de regerar o resumo rolling?

        True quando acumulou `intervalo` turnos desde o último resumo, ou em
        clímax narrativo, ou em mudança de cena (momentos em que consolidar a
        memória vale a pena mesmo antes de fechar o intervalo).
        """
        return (
            self.turnos_desde_resumo >= intervalo
            or em_climax
            or mudou_local
        )

    def aplicar_resumo_rolling(self, novo: str) -> None:
        """Substitui o resumo rolling e zera o contador de turnos.

        Trunca em settings.ROLLING_SUMMARY_MAX_CHARS (corte em espaço pra não
        partir palavra) — rede de segurança caso a LLM devolva texto longo.
        """
        texto = novo.strip()
        limite = settings.ROLLING_SUMMARY_MAX_CHARS
        if len(texto) > limite:
            texto = texto[:limite].rsplit(" ", 1)[0].rstrip()
        self.resumo_rolling = texto
        self.turnos_desde_resumo = 0

    # ── Serialização ─────────────────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Bloco de consequências para o system prompt.

        Fios/agenda/cartas/pacing/ancora são injetados em outros blocos pelo
        prompt_builder (formatação específica). Aqui só consequências, que
        é o único bloco que vem direto do para_texto() do WM original.
        """
        if not self.log_consequencias:
            return ""
        return f"CONSEQUÊNCIAS: {'; '.join(self.log_consequencias)}"
