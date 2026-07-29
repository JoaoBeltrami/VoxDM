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

import random
from collections.abc import Iterable
from dataclasses import dataclass, field

from config import settings

# Caps anti-crescimento em sessão longa
_MAX_FIOS = 5
_MAX_ANCORAS = 5
_MAX_CONSEQUENCIAS = 5
_MAX_AGENDA = 8
_MAX_VOZES = 20
_MAX_QUESTS_IMPROV = 6
_MAX_AMBIENTE = 4



# ── Pacing: curva por evento (PACING-INTEGRADOR-1, 26/07) ────────────────────
# Nível de repouso. É o mesmo default de `pacing_nivel` — a curva SEMPRE tende
# pra cá quando nada acontece, nos dois sentidos.
_PACING_BASE = 3.0
# Fração do caminho até a base percorrida por turno (τ ≈ 6 turnos). Baixo demais
# e o meter cola nos extremos de novo; alto demais e o clímax não dura nada.
_PACING_ALPHA = 0.15
# O que EMPURRA. Nota de design: `turno_combate` é fraco de propósito — estar em
# combate não é perigo, tomar dano é. Foi confundir os dois que produziu um
# clímax de 10 turnos com o jogador em HP cheio.
_IMPULSO_PACING: dict[str, float] = {
    "entrar_combate": 2.0,
    "dano_no_jogador": 2.2,
    "abate": 1.6,
    "critico": 1.4,
    "trust": 1.0,
    "turno_combate": 0.35,
    "aftermath": -1.2,
}

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

    # QUEST-RAPIDA-1 (playtest 26/07): quest_id → valor de `turnos_total` quando o
    # estágio ATUAL começou. É bookkeeping PURO: nada na engine consulta isto pra
    # decidir se um `[Q:]` vale. O piso é NARRATIVO — vira um lembrete no prompt
    # (ver catalog_para_texto). Uma tentativa anterior colocou o piso dentro de
    # `detectar_e_aplicar_quests` e quebrou 7 testes de alcançabilidade do arco:
    # eles chamam o núcleo direto, de propósito sem simular turnos, e 3 deles
    # exercitam o QUEST-SKIP-1 (creditar estágios pulados NA MESMA chamada), que
    # é o oposto exato de adiar. Mesma lição do PACING-INTEGRADOR-1: gate rígido
    # no motor satura; empurrão suave no lugar certo funciona.
    estagio_desde: dict[str, int] = field(default_factory=dict)

    # Quantos turnos narrativos seguidos foram roteados para o 8B (LIGHT).
    # Usado pelo cap anti-robô: o 8B encadeado repete estruturas ("X diz",
    # clichês), então um 70B periódico reseta o estilo. Ver
    # escolher_task_type_narrativo em engine/llm/tasks.py.
    turnos_light_consecutivos: int = 0

    # Repetition guard — fatos já narrados
    fatos_ancora: list[str] = field(default_factory=list)

    # REPETICAO-FRIO (playtest 21/06): o Mestre repete a MESMA imagem sensorial
    # ("frio cortante da noite") TODO turno. Aqui ficam as últimas imagens de
    # ambiente/clima que ele usou — injetadas no prompt como "já descrito, varie"
    # (mesma ideia do fatos_ancora, mas pra clima/sensação). Rolling, cap pequeno.
    ambiente_recente: list[str] = field(default_factory=list)

    # PLAY5-QUEST: quests improvisadas pelo Mestre (fora do catálogo do módulo).
    # O sistema [Q:id:stage] valida contra o catálogo e rejeita o que o autor
    # não escreveu → missões que o Mestre cria na hora sumiam no chat (playtest
    # #5). Aqui viram estado rastreável: injetadas no prompt (continuidade),
    # persistidas (dm_state) e expostas no snapshot (quest log do Palco).
    # Cada item: {id, titulo, objetivo, status: "ativa"|"concluida"}. Cap 6.
    quests_improvisadas: list[dict] = field(default_factory=list)

    # Relógios de Ameaça (fronts) — id → {nome, atual, max}. O mundo anda
    # sem o jogador: engine avança em descanso longo e viagem; LLM avança
    # por drama via [RELOGIO_AVANCA]. Cheio → evento irrompe (one-shot).
    relogios: dict[str, dict] = field(default_factory=dict)
    # Irrupção pendente (one-shot): nome do relógio que encheu, consumido
    # pelo prompt_builder no próximo turno.
    relogio_irrompido: str = ""
    # Cadência do tick de viagem (PLAYTEST 24/06): só avança relógios a cada 2ª
    # troca de cena — andar de sala em sala num hub social não enche a ameaça.
    viagens_desde_tick_relogio: int = 0

    # PLAY5-FRONTS: ameaças latentes (fronts autorais do Schema v2) — id →
    # {nome, segmentos, filled}. Mostrar um front como relógio do HUD no turno 1
    # é "ameaça que o personagem não sabe por que está lá" (playtest #5/#6). Aqui
    # ficam LATENTES: a engine os entrega ao LLM como ameaças A SEMEAR; só viram
    # relógio visível (`relogios`) quando a cena estabelece a ameaça e o LLM emite
    # [RELOGIO: id|...]. Não avançam (ticks) enquanto latentes.
    fronts_latentes: dict[str, dict] = field(default_factory=dict)

    # Mundo Vivo P2: NPC toma a iniciativa — em cena calma, um NPC com agenda
    # age por conta própria. Cooldown em turnos + pendência one-shot
    # (npc_id, plano, presente_na_cena) consumida pelo prompt_builder.
    turnos_desde_iniciativa_npc: int = 0
    iniciativa_npc_pendente: tuple[str, str, bool] | None = None

    # Ritual P2: perfil do jogador — contadores de estilo por turno real
    # (combate/social/exploracao). Persiste via dm_state: o mestre te conhece
    # entre sessões.
    estilo_jogador: dict[str, int] = field(default_factory=dict)

    # Imersão P4: crônica da sessão — timeline de eventos-chave em ordem
    # (consequências, chegadas, level ups, cicatrizes, relógios estourados).
    # Cap 40, dedup consecutivo. Persiste via dm_state; painel 📜 no frontend.
    cronica: list[str] = field(default_factory=list)

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

    def registrar_ambiente(self, texto: str) -> bool:
        """Adiciona imagem de ambiente já descrita (REPETICAO-FRIO), com dedup.

        Retorna True se inserida. Rolling cap _MAX_AMBIENTE — só as mais recentes
        importam (o LLM repete a última imagem usada, não as antigas)."""
        texto = texto.strip()
        if not texto or texto in self.ambiente_recente:
            return False
        self.ambiente_recente.append(texto)
        if len(self.ambiente_recente) > _MAX_AMBIENTE:
            self.ambiente_recente.pop(0)
        return True

    def registrar_quest_improvisada(self, quest_id: str, titulo: str, objetivo: str) -> bool:
        """Registra uma quest improvisada pelo Mestre. Retorna True se inserida.

        Dedup por id; cap _MAX_QUESTS_IMPROV (eviction oldest). Toda quest nova
        entra na crônica como evento-chave da sessão.
        """
        quest_id = quest_id.strip().lower()
        if not quest_id:
            return False
        if any(q.get("id") == quest_id for q in self.quests_improvisadas):
            return False
        titulo = titulo.strip()[:80] or quest_id
        self.quests_improvisadas.append({
            "id": quest_id,
            "titulo": titulo,
            "objetivo": objetivo.strip()[:200],
            "status": "ativa",
        })
        self.registrar_cronica(f"📜 Nova missão: {titulo}")
        while len(self.quests_improvisadas) > _MAX_QUESTS_IMPROV:
            self.quests_improvisadas.pop(0)
        return True

    def concluir_quest_improvisada(self, quest_id: str) -> bool:
        """Marca uma quest improvisada como concluída. True se mudou de estado."""
        quest_id = quest_id.strip().lower()
        for q in self.quests_improvisadas:
            if q.get("id") == quest_id and q.get("status") != "concluida":
                q["status"] = "concluida"
                self.registrar_cronica(f"✓ Missão cumprida: {q.get('titulo', quest_id)}")
                return True
        return False

    def registrar_consequencia(self, texto: str) -> None:
        """Adiciona consequência ao log rolling (e espelha na crônica)."""
        self.log_consequencias.append(texto)
        if len(self.log_consequencias) > _MAX_CONSEQUENCIAS:
            self.log_consequencias.pop(0)
        self.registrar_cronica(texto)

    def registrar_cronica(self, evento: str) -> None:
        """Acrescenta evento à timeline da sessão (cap 40, dedup consecutivo)."""
        evento = evento.strip()[:140]
        if not evento:
            return
        if self.cronica and self.cronica[-1] == evento:
            return
        self.cronica.append(evento)
        if len(self.cronica) > 40:
            self.cronica.pop(0)

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

    def criar_relogio(
        self, relogio_id: str, nome: str, segmentos: int = 6, inicial: int = 0
    ) -> bool:
        """Cria relógio de ameaça (idempotente por id; máx 4 relógios ativos).

        Segmentos clampados em [3, 8] — abaixo de 3 estoura rápido demais,
        acima de 8 o jogador nunca vê a ameaça se concretizar. `inicial` permite
        um front autoral (Schema v2) começar parcialmente preenchido — clampado
        a [0, max-1] (um relógio que já nasce cheio não faria sentido).
        """
        relogio_id = relogio_id.strip().lower()
        if not relogio_id or relogio_id in self.relogios:
            return False
        if len(self.relogios) >= 4:
            return False
        # PLAYTEST 24/06: min subido 3→4 — relógio de ameaça é slow-burn, não pode
        # encher em 3 ticks (o "relógio da guerra" disparava rápido demais).
        seg_max = max(4, min(8, int(segmentos)))
        self.relogios[relogio_id] = {
            "nome": nome.strip()[:60] or relogio_id,
            "atual": max(0, min(seg_max - 1, int(inicial))),
            "max": seg_max,
        }
        return True

    def registrar_front_latente(
        self, front_id: str, nome: str, segmentos: int = 6, filled: int = 0
    ) -> bool:
        """Registra ameaça latente (front autoral ainda invisível ao jogador).

        Idempotente por id; ignora se o id já é um relógio ATIVO. Cap 8 — o módulo
        pode declarar vários fronts, mas só 4 viram relógio ativo de cada vez
        (cap de criar_relogio). Segmentos/filled são preservados pra ativação.
        """
        front_id = front_id.strip().lower()
        if not front_id or front_id in self.relogios or front_id in self.fronts_latentes:
            return False
        if len(self.fronts_latentes) >= 8:
            return False
        self.fronts_latentes[front_id] = {
            "nome": nome.strip()[:60] or front_id,
            "segmentos": max(4, min(8, int(segmentos))),
            "filled": max(0, int(filled)),
        }
        return True

    def ativar_front_latente(self, front_id: str) -> bool:
        """Promove ameaça latente a relógio ativo (visível), preservando os
        segmentos/filled autorais. Retorna True se ativou.

        Só remove da lista latente se o relógio for de fato criado — respeita o
        cap de 4 relógios ativos: se estourar, a ameaça segue latente pra próxima.
        """
        front_id = front_id.strip().lower()
        front = self.fronts_latentes.get(front_id)
        if front is None:
            return False
        if self.criar_relogio(
            front_id, front["nome"], front["segmentos"], inicial=front["filled"]
        ):
            del self.fronts_latentes[front_id]
            return True
        return False

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
            self.registrar_cronica(f"⏳ A ameaça se concretizou: {rel['nome']}")
            return True
        return False

    def tick_relogios_viagem(self) -> list[str]:
        """Tick de relógios por VIAGEM com cadência — avança só a cada 2ª troca de
        cena (PLAYTEST 24/06: ticar todo [CENA], incl. sala-a-sala num hub social,
        enchia a ameaça rápido demais). Descanso longo e [RELOGIO_AVANCA] seguem
        ticando direto (tempo/drama reais). Retorna nomes que encheram."""
        self.viagens_desde_tick_relogio += 1
        if self.viagens_desde_tick_relogio < 2:
            return []
        self.viagens_desde_tick_relogio = 0
        return self.avancar_todos_relogios(1)

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

    # ── NPC toma a iniciativa (Mundo Vivo P2) ────────────────────────────────

    def avaliar_iniciativa_npc(self, npcs_presentes: list[str], em_combate: bool) -> None:
        """Decide se um NPC com agenda age por conta própria neste turno.

        Condições: fora de combate, agenda não-vazia, cena calma há ≥3 turnos
        e cooldown de ≥5 turnos desde a última iniciativa. Prioriza NPC presente
        na cena (age em pessoa); ausente vira "sinal" (mensageiro, rumor).
        Pendência é one-shot — não re-arma enquanto não consumida.
        """
        if em_combate or not self.agenda_npcs:
            return
        self.turnos_desde_iniciativa_npc += 1
        if self.iniciativa_npc_pendente is not None:
            return
        if self.turnos_sem_tensao < 3 or self.turnos_desde_iniciativa_npc < 5:
            return
        presentes = [n for n in self.agenda_npcs if n in set(npcs_presentes)]
        candidatos = presentes or list(self.agenda_npcs.keys())
        npc_id = random.choice(candidatos)
        self.iniciativa_npc_pendente = (npc_id, self.agenda_npcs[npc_id], bool(presentes))
        self.turnos_desde_iniciativa_npc = 0

    def consumir_iniciativa_npc(self) -> tuple[str, str, bool] | None:
        """Retorna e limpa a iniciativa pendente (one-shot)."""
        p = self.iniciativa_npc_pendente
        self.iniciativa_npc_pendente = None
        return p

    # ── Perfil do jogador (Ritual P2) ────────────────────────────────────────

    def registrar_estilo(self, categoria: str) -> None:
        """Conta um turno do estilo dado (combate|social|exploracao)."""
        if categoria not in ("combate", "social", "exploracao"):
            return
        self.estilo_jogador[categoria] = self.estilo_jogador.get(categoria, 0) + 1

    def estilo_dominante(self, minimo: int = 10) -> tuple[str, int, int] | None:
        """(categoria, contagem, total) do estilo dominante, ou None.

        None quando há menos de `minimo` turnos classificados (amostra curta)
        ou quando nenhum estilo atinge 45% do total (perfil equilibrado não
        merece bloco no prompt — seria ruído).
        """
        total = sum(self.estilo_jogador.values())
        if total < minimo:
            return None
        categoria, contagem = max(self.estilo_jogador.items(), key=lambda kv: kv[1])
        if contagem / total < 0.45:
            return None
        return categoria, contagem, total

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

    def ajustar_pacing(
        self,
        em_combate: bool,
        saiu_combate_recentemente: bool,
        trust_mudou: bool,
        eventos: Iterable[str] | None = None,
    ) -> None:
        """Move o pacing por EVENTO, com retorno à média. Único ponto de verdade.

        PACING-INTEGRADOR-1 (playtest 26/07). A versão anterior era um acumulador
        de sinal constante com clamp duro e sem força restauradora, e saturava nos
        DOIS extremos — medido na telemetria de 50 turnos: colou em 0.0 nos turnos
        15-30 e em 10.0 nos turnos 37-46.

        - PISO ABSORVENTE: o único ramo que subia fora de combate (`+0.2`) exigia
          `turnos_sem_tensao <= 3`, mas esse contador é um LATCH que só zera com
          combate ou trust. Do 4º turno calmo em diante só existia o ramo `-0.6`,
          e `max(0.0, ...)` prendia em 0.0 pra sempre. Sair do piso sem combate
          era impossível.
        - TETO: `+1.5` por FLAG de combate ligada, sem dreno durante a luta. E a
          flag mentia — no playtest ela ficou ligada ~19 turnos numa cena de
          jantar (ver COMBATE-FANTASMA-RAIZ), com HP 28/28 do começo ao fim, e
          mesmo assim o meter foi de 0.4 a 10.0. Ele media "a flag está ligada",
          não "há perigo".

        Agora o nível é empurrado por eventos REAIS (`eventos`) e puxado de volta
        pra `_PACING_BASE` por uma fração fixa a cada turno (τ ≈ 6 turnos). O
        clamp vira rede de segurança em vez de regime de operação: combate denso
        oscila alto sem colar em 10, combate fantasma (flag ligada, zero eventos)
        estabiliza perto da base, e exploração pós-clímax desce sozinha sem travar
        no zero.

        `eventos` é opcional pra manter a assinatura antiga válida — sem eventos,
        `em_combate` ainda vale como um empurrão fraco (`turno_combate`), que é o
        comportamento mínimo que os callers legados esperam.
        """
        # Arco da sessão (modo episódio): turno real contado + pico registrado
        self.turnos_total += 1
        # Tensão narrativa
        if em_combate or trust_mudou:
            self.turnos_sem_tensao = 0
        else:
            self.turnos_sem_tensao += 1

        marcados = set(eventos or ())
        if em_combate:
            marcados.add("turno_combate")
        if trust_mudou:
            marcados.add("trust")
        if saiu_combate_recentemente:
            marcados.add("aftermath")

        for ev in marcados:
            self.pacing_nivel += _IMPULSO_PACING.get(ev, 0.0)
        # Retorno à média: o que puxa o meter de volta ao normal quando nada
        # acontece — é isto que faltava, e sem isto os extremos eram absorventes.
        self.pacing_nivel += (_PACING_BASE - self.pacing_nivel) * _PACING_ALPHA
        self.pacing_nivel = max(0.0, min(10.0, self.pacing_nivel))
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
