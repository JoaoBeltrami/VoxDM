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

    # Modo episódio (Ritual de mesa, 10/06): rastreia o arco da sessão.
    # pico_pacing = maior pacing já atingido; fecho_sugerido = one-shot (o
    # mestre só propõe encerrar UMA vez por sessão); turnos_total = contador
    # de turnos reais (ajustar_pacing roda 1×/turno de jogador).
    pico_pacing: float = 3.0
    fecho_sugerido: bool = False
    turnos_total: int = 0

    # Quantos turnos narrativos seguidos foram roteados para o 8B (LIGHT).
    # Usado pelo cap anti-robô: o 8B encadeado repete estruturas ("X diz",
    # clichês), então um 70B periódico reseta o estilo. Ver
    # escolher_task_type_narrativo em engine/llm/tasks.py.
    turnos_light_consecutivos: int = 0

    # Repetition guard — fatos já narrados
    fatos_ancora: list[str] = field(default_factory=list)

    # Relógios de Ameaça (fronts) — id → {nome, atual, max}. O mundo anda
    # sem o jogador: engine avança em descanso longo e viagem; LLM avança
    # por drama via [RELOGIO_AVANCA]. Cheio → evento irrompe (one-shot).
    relogios: dict[str, dict] = field(default_factory=dict)
    # Irrupção pendente (one-shot): nome do relógio que encheu, consumido
    # pelo prompt_builder no próximo turno.
    relogio_irrompido: str = ""

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

    # ── Relógios de Ameaça (fronts) ──────────────────────────────────────────

    def criar_relogio(self, relogio_id: str, nome: str, segmentos: int = 6) -> bool:
        """Cria relógio de ameaça (idempotente por id; máx 4 relógios ativos).

        Segmentos clampados em [3, 8] — abaixo de 3 estoura rápido demais,
        acima de 8 o jogador nunca vê a ameaça se concretizar.
        """
        relogio_id = relogio_id.strip().lower()
        if not relogio_id or relogio_id in self.relogios:
            return False
        if len(self.relogios) >= 4:
            return False
        self.relogios[relogio_id] = {
            "nome": nome.strip()[:60] or relogio_id,
            "atual": 0,
            "max": max(3, min(8, int(segmentos))),
        }
        return True

    def avancar_relogio(self, relogio_id: str, passos: int = 1) -> bool:
        """Avança relógio. Retorna True se ENCHEU agora (irrupção pendente).

        Relógio cheio é removido e seu nome vai pra `relogio_irrompido` —
        o prompt_builder consome (one-shot) instruindo o evento a irromper.
        """
        rel = self.relogios.get(relogio_id.strip().lower())
        if rel is None:
            return False
        rel["atual"] = min(rel["max"], rel["atual"] + max(1, int(passos)))
        if rel["atual"] >= rel["max"]:
            self.relogio_irrompido = rel["nome"]
            del self.relogios[relogio_id.strip().lower()]
            return True
        return False

    def avancar_todos_relogios(self, passos: int = 1) -> list[str]:
        """Tick global (descanso longo / viagem). Retorna nomes que encheram."""
        estourados: list[str] = []
        for rid in list(self.relogios.keys()):
            nome = self.relogios[rid]["nome"]
            if self.avancar_relogio(rid, passos):
                estourados.append(nome)
        return estourados

    def consumir_relogio_irrompido(self) -> str:
        """Retorna e limpa a irrupção pendente (one-shot)."""
        nome = self.relogio_irrompido
        self.relogio_irrompido = ""
        return nome

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
        # Arco da sessão (modo episódio): turno real contado + pico registrado
        self.turnos_total += 1
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
        self.pico_pacing = max(self.pico_pacing, self.pacing_nivel)

    def momento_de_fecho(self) -> bool:
        """Modo episódio: hora de propor encerrar? (one-shot)

        True quando o arco fechou — a sessão teve um clímax real (pico ≥ 7),
        o ritmo assentou de volta (pacing ≤ 3), já há substância (≥ 20 turnos)
        e o fecho ainda não foi proposto. Consome o one-shot.
        """
        if (
            self.fecho_sugerido
            or self.turnos_total < 20
            or self.pico_pacing < 7.0
            or self.pacing_nivel > 3.0
        ):
            return False
        self.fecho_sugerido = True
        return True

    def registrar_task_narrativo(self, foi_light: bool) -> None:
        """Atualiza o contador de turnos LIGHT consecutivos.

        Incrementa quando o turno foi roteado para o 8B (LIGHT); zera quando
        foi 70B/CLIMAX. Alimenta o cap anti-robô na próxima decisão de routing.
        """
        if foi_light:
            self.turnos_light_consecutivos += 1
        else:
            self.turnos_light_consecutivos = 0

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
