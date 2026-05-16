"""
Pipeline pós-turno compartilhado entre REST `/turn` e WebSocket.

Por que existe: a lógica de "o que acontece depois que o LLM termina de falar"
    estava duplicada apenas no `api/websocket.py`. O endpoint REST `/session/{id}/turn`
    pulava trust_detector, sincronização de inimigos, avanço de rodada e detecção
    de fim de combate — causando divergência de estado entre os dois caminhos.
    Este módulo centraliza tudo em uma única função idempotente.

Dependências: engine/memory/working_memory, engine/memory/trust_detector,
    e os regexes de combate de api/websocket (re-exportados).

Armadilha: a ORDEM das operações importa.
    - Sync de inimigos DEVE rodar antes de detectar fim de combate, senão a
      última morte do combate é descartada (sair_combate limpa inimigos_combate).
    - Auto-registro de consequências também precisa rodar antes de sair_combate
      pelo mesmo motivo.

Exemplo:
    from api.turn_pipeline import aplicar_pos_turno
    mudancas_trust = aplicar_pos_turno(working_mem, texto_jogador, resposta_llm)
    # working_mem agora reflete: inimigos atualizados, trust ajustado,
    # rodada avançada, fim de combate detectado se aplicável.
"""

import re
import unicodedata
from typing import Any

import structlog

from engine.magic.slot_tracker import detectar_descanso, restaurar_slots
from engine.memory.trust_detector import detectar_mudancas_trust
from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# ── Regexes das Features de Mestre Veterano ───────────────────────────────────

# DM Feat 1: Fio solto — LLM emite [FIO: descrição do plot thread em aberto]
# Ex: "[FIO: O ferreiro mencionou ter visto Valdrek na mina há 3 semanas]"
_RE_FIO = re.compile(r"\[FIO:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# DM Feat 2: Cliffhanger — LLM emite [CLIFFHANGER: frase dramática de encerramento]
# Ex: "[CLIFFHANGER: E então a porta se abre — é Valdrek, segurando o corpo de Bjorn]"
_RE_CLIFFHANGER = re.compile(r"\[CLIFFHANGER:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# DM Feat 3: Agenda paralela de NPC — LLM emite [AGENDA: npc-id → descrição do plano]
# Ex: "[AGENDA: fael-valdreksson → planeja desertar à meia-noite com a chave do cofre]"
_RE_AGENDA = re.compile(r"\[AGENDA:\s*([a-z0-9-]+)\s*[→>-]+\s*([^\]]+?)\s*\]", re.IGNORECASE)

# ─── Regexes de detecção (compartilhados; espelham os do websocket.py) ────────

_RE_ALVO_ATAQUE = re.compile(
    r"\b(?:ataco?|atacar|golpei?o|firo|lanço|apunhalo|atinge?|atinjo|acerto)\s+"
    r"(?:o|a|ao?s?|na?s?)\s+"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,30}?)(?=\s+(?:com|de|usando|n[ao])\b|[.!,?]|$)",
    re.IGNORECASE,
)
_RE_INIMIGO_MORTO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:caiu|morreu|está morto|está morta|foi abatido|foi abatida|jaz|tombou|desmorona)\b",
    re.IGNORECASE,
)
_RE_INIMIGO_GRAVE = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:gravemente ferido|muito ferido|mal consegue|vacila|claudica|cambaleando|aos trancos)\b",
    re.IGNORECASE,
)
_RE_INIMIGO_FERIDO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:está ferido|foi atingido|foi atingida|sangra|grita de dor|recua|recuou|tropeçou)\b",
    re.IGNORECASE,
)
_RE_FIM_COMBATE_LLM = re.compile(
    r"\b("
    r"o combate termina|a luta termina|combate encerrado|batalha encerrada|"
    r"não há mais inimigos|sem mais ameaças|ambiente está seguro|"
    r"silêncio retorna|silêncio toma conta|"
    r"todos os inimigos ca[íi]ram|inimigos foram derrotados|"
    r"último inimigo|únic[oa] sobrevivente"
    r")\b",
    re.IGNORECASE,
)


def _slugify(nome: str) -> str:
    """Converte nome livre para id kebab-case."""
    normalizado = unicodedata.normalize("NFD", nome.strip().lower())
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


def sincronizar_inimigos_combate(
    working_mem: WorkingMemory, texto_jogador: str, resposta_llm: str
) -> None:
    """Popula e atualiza inimigos_combate a partir do turno atual.

    1. Se jogador declara ataque com alvo nomeado → registrar inimigo (intacto)
    2. Varrer resposta do LLM por descritores de saúde e atualizar estado
    """
    if not working_mem.em_combate:
        return

    for m in _RE_ALVO_ATAQUE.finditer(texto_jogador):
        nome = m.group(1).strip().rstrip(".,!?")
        if nome:
            inimigo_id = _slugify(nome)
            if inimigo_id not in working_mem.inimigos_combate:
                working_mem.registrar_inimigo(inimigo_id, nome.title(), "intacto")
                log.info("combate_inimigo_registrado", id=inimigo_id, nome=nome)

    if not working_mem.inimigos_combate:
        return

    nomes_registrados = {
        dados["nome"].lower(): iid
        for iid, dados in working_mem.inimigos_combate.items()
    }

    def _encontrar_id(trecho: str) -> str | None:
        trecho_lower = trecho.strip().lower()
        for nome_reg, iid in nomes_registrados.items():
            if nome_reg in trecho_lower or trecho_lower in nome_reg:
                return iid
        return None

    for m in _RE_INIMIGO_MORTO.finditer(resposta_llm):
        iid = _encontrar_id(m.group(1))
        if iid:
            working_mem.atualizar_estado_inimigo(iid, "morto", "sem vida")
            log.info("combate_inimigo_morto", id=iid)

    for m in _RE_INIMIGO_GRAVE.finditer(resposta_llm):
        iid = _encontrar_id(m.group(1))
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") not in ("morto",):
            working_mem.atualizar_estado_inimigo(iid, "gravemente ferido", "quase sem forças")

    for m in _RE_INIMIGO_FERIDO.finditer(resposta_llm):
        iid = _encontrar_id(m.group(1))
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") == "intacto":
            working_mem.atualizar_estado_inimigo(iid, "ferido", "ainda de pé")


def aplicar_pos_turno(
    working_mem: WorkingMemory,
    texto_jogador: str,
    resposta_completa: str,
) -> list[tuple[str, int]]:
    """Aplica todos os efeitos colaterais de um turno completo na WorkingMemory.

    Idempotente em relação a `dialogo_recente` desde que `registrar_fala("mestre", ...)`
    NÃO tenha sido chamado antes — esta função chama internamente.

    Returns:
        Lista de mudanças de trust aplicadas: [(npc_id, delta), ...].
        Útil para o caller emitir eventos / telemetria.
    """
    # 1. Registra fala do mestre + apresenta NPCs mencionados
    working_mem.registrar_fala("mestre", resposta_completa)
    working_mem.apresentar_npcs_mencionados(resposta_completa)

    # 2. Sync de inimigos ANTES de detectar fim de combate (ordem crítica —
    #    sair_combate limpa inimigos_combate, perderíamos a última morte)
    sincronizar_inimigos_combate(working_mem, texto_jogador, resposta_completa)

    # 3. Iniciativa — engine é authority
    if working_mem.em_combate and working_mem.inimigos_combate:
        inimigos_sem_ini = [
            iid for iid in working_mem.inimigos_combate
            if iid not in working_mem.iniciativa_cache
        ]
        if inimigos_sem_ini:
            log.warning("iniciativa_fallback", inimigos=inimigos_sem_ini)
        working_mem.popular_iniciativa()
        if working_mem.rodada_combate >= 1:
            working_mem.avancar_turno_iniciativa()

    # 4. Descanso — restaura spell slots se jogador declarou descanso neste turno.
    # Ordem: antes do trust, pois o descanso é uma ação completa do jogador.
    tipo_descanso = detectar_descanso(texto_jogador)
    if tipo_descanso:
        restaurados = restaurar_slots(working_mem, tipo_descanso)
        if restaurados > 0:
            log.info("slots_restaurados", tipo=tipo_descanso, quantidade=restaurados)

    # 5. Trust com base em ações do jogador
    mudancas_trust = detectar_mudancas_trust(texto_jogador, working_mem.npcs_presentes)
    for npc_id, delta in mudancas_trust:
        working_mem.atualizar_trust(npc_id, delta)
        log.info("trust_atualizado", npc_id=npc_id, delta=delta,
                 novo_valor=working_mem.trust_levels.get(npc_id))

    # 6. Auto-registra consequências: mortos neste turno + mudanças de trust
    for dados in working_mem.inimigos_combate.values():
        if dados.get("estado") == "morto":
            c = f"{dados['nome']} foi abatido"
            if not any(c in ex for ex in working_mem.log_consequencias):
                working_mem.registrar_consequencia(c)
    for npc_id, delta in mudancas_trust:
        nome = npc_id.split("-")[0].capitalize()
        direcao = "melhorou" if delta > 0 else "piorou"
        working_mem.registrar_consequencia(f"Relação com {nome} {direcao}")

    # 6. Avanço de rodada (só faz sentido em combate)
    if working_mem.em_combate:
        working_mem.avancar_rodada()

    # 7. Fim de combate detectado na narração — POR ÚLTIMO, depois do sync
    if working_mem.em_combate and _RE_FIM_COMBATE_LLM.search(resposta_completa):
        working_mem.sair_combate()
        log.info("combate_encerrado_por_llm")

    # 8. Contador de tensão narrativa fora de combate
    if working_mem.em_combate:
        working_mem.turnos_sem_tensao = 0
    else:
        working_mem.turnos_sem_tensao += 1

    # ── Features de Mestre Veterano ───────────────────────────────────────────

    # 9. Pacing Meter (Feat 5) — ajusta nível de tensão narrativa
    if working_mem.em_combate:
        # Combate eleva o pacing
        working_mem.pacing_nivel = min(10.0, working_mem.pacing_nivel + 1.5)
    elif working_mem.saiu_combate_recentemente:
        # Logo após combate: reduz levemente (respiração pós-batalha)
        working_mem.pacing_nivel = max(0.0, working_mem.pacing_nivel - 0.5)
    elif working_mem.turnos_sem_tensao > 3:
        # Muitos turnos calmos: reduz pacing gradualmente
        working_mem.pacing_nivel = max(0.0, working_mem.pacing_nivel - 0.3)
    else:
        # Turno normal de exploração/social: leve aumento
        working_mem.pacing_nivel = min(10.0, working_mem.pacing_nivel + 0.2)
    log.debug("pacing_atualizado", nivel=round(working_mem.pacing_nivel, 1))

    # 10. Fios Soltos (Feat 1) — coleta [FIO: ...] da resposta do LLM
    for m in _RE_FIO.finditer(resposta_completa):
        fio = m.group(1).strip()
        if fio and fio not in working_mem.fios_soltos:
            working_mem.fios_soltos.append(fio)
            # Mantém lista circular de max 5 fios — remove o mais antigo se exceder
            if len(working_mem.fios_soltos) > 5:
                working_mem.fios_soltos.pop(0)
            log.info("fio_solto_registrado", fio=fio[:60])

    # 11. Cliffhanger (Feat 2) — captura [CLIFFHANGER: ...] da resposta do LLM
    for m in _RE_CLIFFHANGER.finditer(resposta_completa):
        ch = m.group(1).strip()
        if ch:
            working_mem.cliffhanger_pendente = ch
            log.info("cliffhanger_registrado", texto=ch[:80])
            break  # Máx 1 cliffhanger por turno — o último vence

    # 12. Agenda NPC (Feat 3) — coleta [AGENDA: npc-id → plano]
    for m in _RE_AGENDA.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        plano = m.group(2).strip()
        if npc_id and plano:
            working_mem.agenda_npcs[npc_id] = plano
            log.info("agenda_npc_atualizada", npc_id=npc_id, plano=plano[:60])

    return mudancas_trust
