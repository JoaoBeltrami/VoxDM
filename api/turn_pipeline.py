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

# Feature 3: Consequências visíveis — LLM emite [CONSEQUÊNCIA: efeito duradouro no mundo]
# Ex: "[CONSEQUÊNCIA: A guarda de Valdrek passou a reconhecer Drevamor como suspeito]"
# Efeitos válidos: NPC morto, aliança formada, local destruído, reputação alterada.
_RE_CONSEQUENCIA = re.compile(r"\[CONSEQUÊNCIA:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Feature progressão: LLM emite [XP: +N motivo] em vitórias, descobertas, quests.
# Ex: "[XP: +50 derrotou goblin patrulheiro]", "[XP: +200 quest concluída]"
# Backend acumula em wm.xp e detecta level up via tabela SRD.
_RE_XP = re.compile(r"\[XP:\s*\+?(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)

# Feature combate tático: LLM emite [POSICAO: npc-id = N ft] (ou "= N ft cobertura").
# Ex: "[POSICAO: goblin = 10 ft]", "[POSICAO: orco-arqueiro = 60 ft cobertura]"
# Engine atualiza wm.posicoes_combate para o CombatTracker mostrar chip de distância.
_RE_POSICAO = re.compile(
    r"\[POSICAO:\s*([a-z0-9-]+)\s*=\s*(\d+)\s*ft\s*(cobertura)?\s*\]",
    re.IGNORECASE,
)

# Movimento do jogador na rodada — LLM emite [MOV: -N ft motivo] quando o jogador
# se desloca. Backend decrementa wm.movimento_restante_ft (max 30 padrão).
# Ex: "[MOV: -20 ft em direção ao orc]" → restante 30→10.
_RE_MOVIMENTO = re.compile(r"\[MOV:\s*-?(\d+)\s*ft\s*([^\]]*?)\s*\]", re.IGNORECASE)

# Feature economia: [OURO: ±N motivo] / [LOOT: item] / [PERDEU: item]
# [OURO: +50 saque do orc] adiciona 50 po; [OURO: -10 paga a pousada] tira 10.
# [LOOT: poção de cura] adiciona ao inventário; [PERDEU: poção de cura] remove.
# [MERCADO] / [FIM_MERCADO] flag pra UI de venda no frontend.
_RE_OURO = re.compile(r"\[OURO:\s*([+-]?)(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)
_RE_LOOT = re.compile(r"\[LOOT:\s*([^\]]+?)\s*\]", re.IGNORECASE)
_RE_PERDEU = re.compile(r"\[PERDEU:\s*([^\]]+?)\s*\]", re.IGNORECASE)
_RE_MERCADO = re.compile(r"\[MERCADO\]", re.IGNORECASE)
_RE_FIM_MERCADO = re.compile(r"\[FIM_MERCADO\]", re.IGNORECASE)

# Feature companions/party: aliados que lutam ao lado do jogador.
# `[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano]` — adiciona/atualiza companion.
#   Ex: `[COMPANION_ADD: lyssa|Lyssa|hireling|25|15|+4|1d8 cortante]`
# `[COMPANION_HP: id|±N motivo]` — ajusta HP (dano/cura).
# `[COMPANION_REMOVE: id]` — companion morre/dispensa/fim de summon.
_RE_COMPANION_ADD = re.compile(
    r"\[COMPANION_ADD:\s*([^|\]]+)\|([^|\]]+)\|([^|\]]+)\|(\d+)\|(\d+)\|([^|\]]+)\|([^\]]+?)\s*\]",
    re.IGNORECASE,
)
_RE_COMPANION_HP = re.compile(
    r"\[COMPANION_HP:\s*([^|\]]+)\|\s*([+-]?\d+)\s*([^\]]*?)\s*\]",
    re.IGNORECASE,
)
_RE_COMPANION_REMOVE = re.compile(r"\[COMPANION_REMOVE:\s*([^\]]+?)\s*\]", re.IGNORECASE)

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


# Pronomes em PT-BR que NUNCA devem virar id de inimigo. Sem isso, frases como
# "você está ferido" ou "ataco o você" (LLM gago) viram registro espúrio.
_PRONOMES: frozenset[str] = frozenset({
    "você", "vocês", "voce", "voces",
    "eu", "nós", "nos",
    "me", "te", "lhe", "se",
    "ele", "ela", "eles", "elas",
    "isso", "isto", "aquilo",
})


def _slugify(nome: str) -> str:
    """Converte nome livre para id kebab-case."""
    normalizado = unicodedata.normalize("NFD", nome.strip().lower())
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


def _encontrar_id_inimigo(
    trecho: str, nomes_registrados: dict[str, str]
) -> str | None:
    """Mapeia um trecho do LLM para o id de um inimigo registrado.

    Regra: o nome registrado precisa aparecer como **palavra inteira** dentro do
    trecho. Se vários candidatos baterem, vence o nome registrado mais **longo**
    (mais específico) — assim "goblin arqueiro" não colide com "goblin" simples
    quando o LLM narra "o goblin arqueiro caiu".

    Pronomes (você/eu/nós/...) nunca casam — protege contra LLM narrar "você
    está ferido" virando registro espúrio de inimigo chamado "você".
    """
    trecho_lower = trecho.strip().lower()
    if not trecho_lower or trecho_lower in _PRONOMES:
        return None
    candidatos: list[tuple[int, str]] = []
    for nome_reg, iid in nomes_registrados.items():
        if re.search(rf"\b{re.escape(nome_reg)}\b", trecho_lower):
            candidatos.append((len(nome_reg), iid))
    if not candidatos:
        return None
    # Maior tamanho primeiro; tiebreaker por id (determinístico)
    candidatos.sort(key=lambda t: (-t[0], t[1]))
    return candidatos[0][1]


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
        if not nome:
            continue
        # Rejeita se o nome inteiro ou a PRIMEIRA palavra é pronome — protege
        # contra LLM/STT gerando frases como "ataco o você" ou "atinjo nós dois"
        primeira_palavra = nome.split()[0].lower() if nome.split() else ""
        if nome.lower() in _PRONOMES or primeira_palavra in _PRONOMES:
            continue
        inimigo_id = _slugify(nome)
        if not inimigo_id:
            continue
        if inimigo_id not in working_mem.inimigos_combate:
            working_mem.registrar_inimigo(inimigo_id, nome.title(), "intacto")
            log.info("combate_inimigo_registrado", id=inimigo_id, nome=nome)

    if not working_mem.inimigos_combate:
        return

    nomes_registrados = {
        dados["nome"].lower(): iid
        for iid, dados in working_mem.inimigos_combate.items()
    }

    for m in _RE_INIMIGO_MORTO.finditer(resposta_llm):
        iid = _encontrar_id_inimigo(m.group(1), nomes_registrados)
        if iid:
            working_mem.atualizar_estado_inimigo(iid, "morto", "sem vida")
            log.info("combate_inimigo_morto", id=iid)

    for m in _RE_INIMIGO_GRAVE.finditer(resposta_llm):
        iid = _encontrar_id_inimigo(m.group(1), nomes_registrados)
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") not in ("morto",):
            working_mem.atualizar_estado_inimigo(iid, "gravemente ferido", "quase sem forças")

    for m in _RE_INIMIGO_FERIDO.finditer(resposta_llm):
        iid = _encontrar_id_inimigo(m.group(1), nomes_registrados)
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
    # Bug #8: cada chamada de pipeline = uma rodada COMPLETA (jogador age,
    # narração descreve player + todos NPCs). Antes incrementávamos
    # turno_atual_idx em +1 a cada turno do jogador, fazendo a InitiativeBar
    # mostrar "orc1" highlighted enquanto era a vez do jogador digitar.
    # Agora: popular iniciativa (idempotente) e voltar pro jogador (idx=0).
    # O avanço de rodada acontece no step 6, mais abaixo.
    if working_mem.em_combate and working_mem.inimigos_combate:
        inimigos_sem_ini = [
            iid for iid in working_mem.inimigos_combate
            if iid not in working_mem.iniciativa_cache
        ]
        if inimigos_sem_ini:
            log.warning("iniciativa_fallback", inimigos=inimigos_sem_ini)
        working_mem.popular_iniciativa()
        # Volta o cursor visual pro jogador — é a próxima vez que ele vai agir.
        working_mem.turno_atual_idx = 0

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

    # 13. Consequências visíveis (Feature 3) — coleta [CONSEQUÊNCIA: efeito duradouro]
    # Efeitos que persistem além da cena: NPCs mortos, alianças, locais destruídos,
    # reputação alterada. Lista circular de máx 5 via registrar_consequencia().
    for m in _RE_CONSEQUENCIA.finditer(resposta_completa):
        consequencia = m.group(1).strip()
        if consequencia and not any(consequencia in ex for ex in working_mem.log_consequencias):
            working_mem.registrar_consequencia(consequencia)
            log.info("consequencia_registrada_llm", texto=consequencia[:80])

    # 13.5. Economia — ouro, loot, mercado.
    # Idempotência: cada marcador é processado uma vez por turno. Não há buffer
    # entre turnos, então re-aplicar a mesma resposta dobraria o efeito (ok pq
    # cada resposta é única no tempo).
    for m in _RE_OURO.finditer(resposta_completa):
        sinal = m.group(1)
        try:
            qtd = int(m.group(2))
        except ValueError:
            continue
        if sinal == "-":
            qtd = -qtd
        working_mem.gold = max(0, working_mem.gold + qtd)
        log.info("ouro_alterado", delta=qtd, novo=working_mem.gold,
                 motivo=m.group(3)[:60])

    for m in _RE_LOOT.finditer(resposta_completa):
        item = m.group(1).strip()
        if item and item.lower() not in (i.lower() for i in working_mem.player_inventory):
            working_mem.player_inventory.append(item)
            log.info("loot_adicionado", item=item[:60])

    for m in _RE_PERDEU.finditer(resposta_completa):
        item_alvo = m.group(1).strip().lower()
        for i, item_existente in enumerate(working_mem.player_inventory):
            if item_existente.lower() == item_alvo:
                removido = working_mem.player_inventory.pop(i)
                log.info("item_removido", item=removido[:60])
                break

    if _RE_MERCADO.search(resposta_completa):
        working_mem.em_mercado = True
        log.info("mercado_aberto")
    if _RE_FIM_MERCADO.search(resposta_completa):
        working_mem.em_mercado = False
        log.info("mercado_fechado")

    # 13.6. Companions/party — aliados controlados.
    for m in _RE_COMPANION_ADD.finditer(resposta_completa):
        try:
            cid = m.group(1).strip().lower()
            nome = m.group(2)
            tipo = m.group(3)
            hp = int(m.group(4))
            ca = int(m.group(5))
            atq = m.group(6)
            dano = m.group(7)
        except (ValueError, AttributeError):
            continue
        if cid:
            working_mem.registrar_companion(cid, nome, tipo, hp, ca, atq, dano)
            log.info("companion_registrado", id=cid, nome=nome, tipo=tipo)

    for m in _RE_COMPANION_HP.finditer(resposta_completa):
        cid = m.group(1).strip().lower()
        try:
            delta = int(m.group(2))
        except ValueError:
            continue
        ok = working_mem.ajustar_hp_companion(cid, delta)
        if ok:
            log.info("companion_hp_ajustado", id=cid, delta=delta,
                     hp_novo=working_mem.companions[cid].get("hp"))

    for m in _RE_COMPANION_REMOVE.finditer(resposta_completa):
        cid = m.group(1).strip().lower()
        if working_mem.remover_companion(cid):
            log.info("companion_removido", id=cid)

    # 14. Combate tático — posições de inimigos e movimento do jogador.
    # Só processa se estamos em combate (posições fora de combate são
    # irrelevantes e podem confundir o estado).
    if working_mem.em_combate:
        for m in _RE_POSICAO.finditer(resposta_completa):
            npc_id = m.group(1).strip().lower()
            try:
                dist = int(m.group(2))
            except ValueError:
                continue
            cobertura = bool(m.group(3))
            if npc_id:
                working_mem.registrar_posicao(npc_id, dist, cobertura=cobertura)
                log.info("posicao_registrada", npc_id=npc_id, dist=dist, cobertura=cobertura)

        for m in _RE_MOVIMENTO.finditer(resposta_completa):
            try:
                ft = int(m.group(1))
            except ValueError:
                continue
            motivo = m.group(2).strip() or "movimento"
            consumido = working_mem.aplicar_movimento(ft)
            log.info("movimento_consumido", ft=consumido, motivo=motivo,
                     restante=working_mem.movimento_restante_ft)

    return mudancas_trust


def aplicar_xp_e_detectar_level_up(
    working_mem: WorkingMemory, resposta_completa: str
) -> dict[str, int | list[str]] | None:
    """Extrai [XP: +N motivo] da resposta do LLM e aplica progressão.

    Separado de `aplicar_pos_turno` porque o caller precisa do resumo do level
    up pra emitir como mensagem WebSocket dedicada (modal no frontend).

    Returns:
        Dict resumo do level up se o jogador subiu de nível, ou None se só
        acumulou XP sem progredir. O resumo vem direto de `aplicar_level_up`.
    """
    from engine.progression import calcular_novo_nivel, aplicar_level_up

    ganhos: list[tuple[int, str]] = []
    for m in _RE_XP.finditer(resposta_completa):
        try:
            qtd = int(m.group(1))
        except ValueError:
            continue
        motivo = m.group(2).strip() or "ganho de experiência"
        ganhos.append((qtd, motivo))

    if not ganhos:
        return None

    total = sum(q for q, _ in ganhos)
    working_mem.xp += total
    log.info("xp_ganho", total=total, ganhos=ganhos, xp_novo=working_mem.xp)

    novo_nivel = calcular_novo_nivel(working_mem.xp, working_mem.player_level)
    if novo_nivel > working_mem.player_level:
        return aplicar_level_up(working_mem, novo_nivel)
    return None
