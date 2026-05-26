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
from engine.memory.quest_detector import strip_marcadores
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

# Repetition Guard: LLM emite [ANCORA: fato já resolvido] após virada narrativa importante.
# Ex: "[ANCORA: O segredo de Valdrek foi revelado ao jogador]"
# Backend acumula max 5; prompt_builder injeta como "Não repetir narrativa já dita".
_RE_ANCORA = re.compile(r"\[ANCORA:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Assinatura de voz de NPC: [VOZ: npc-id|pitch|rate]
# Ex: "[VOZ: lyssa|+5Hz|-10%]" — armazenado em wm.npc_vozes para o restante da sessão.
# Pitch: "+NHz" ou "-NHz". Rate: "+N%" ou "-N%".
_RE_VOZ = re.compile(
    r"\[VOZ:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*([+\-]?\d+Hz)\s*\|\s*([+\-]?\d+%)\s*\]",
    re.IGNORECASE,
)

# Engine-authority markers (preferíveis sobre regex de vocab):
# `[INIMIGO_MORTO: id]` — LLM declara explicitamente quem morreu. Resolve
# COMBAT-1 (22 padrões de vocab PT-BR frágeis). Regex existente permanece
# como fallback de defesa caso o LLM não emita o marker.
_RE_INIMIGO_MORTO_MARKER = re.compile(
    r"\[INIMIGO_MORTO:\s*([a-z0-9][a-z0-9-]{0,48})\s*\]",
    re.IGNORECASE,
)

# `[DESCANSO: curto|longo]` — LLM declara descanso explicitamente após
# narrativa ambígua. Substitui regex frágil (`_RE_DESCANSO_LONGO` falha em
# "vou tirar uma soneca" e similares). Regex permanece como fallback.
_RE_DESCANSO_MARKER = re.compile(
    r"\[DESCANSO:\s*(curto|longo)\s*\]",
    re.IGNORECASE,
)

# `[COMBATE: iniciar]` — LLM declara início de combate quando a ação do jogador
# é claramente bélica mas o regex de verbos não casou (sparring narrado, "uso X
# em Y" não coberto, declarações indiretas). Bug COMBATE-VERB-1 (26/05).
# Engine-authority complementar à RE_COMBATE no texto do jogador.
_RE_COMBATE_MARKER = re.compile(
    r"\[COMBATE:\s*iniciar\s*\]",
    re.IGNORECASE,
)

# Estado afetivo de NPC: [AFETO: npc-id|campo|delta]
# Ex: "[AFETO: fael-valdreksson|respeito|+2]" — salvo no Neo4j (persistência entre sessões).
# Campos: afeto | medo | respeito | rancor. Delta: int com sinal (+/-).
_RE_AFETO = re.compile(
    r"\[AFETO:\s*([a-z0-9][a-z0-9-]{0,48})\s*\|\s*(afeto|medo|respeito|rancor)\s*\|\s*([+\-]?\d+)\s*\]",
    re.IGNORECASE,
)

# Feature 3: Consequências visíveis — LLM emite [CONSEQUÊNCIA: efeito duradouro no mundo]
# Ex: "[CONSEQUÊNCIA: A guarda de Valdrek passou a reconhecer Drevamor como suspeito]"
# Efeitos válidos: NPC morto, aliança formada, local destruído, reputação alterada.
_RE_CONSEQUENCIA = re.compile(r"\[CONSEQUÊNCIA:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Feature progressão: LLM emite [XP: +N motivo] em vitórias, descobertas, quests.
# Ex: "[XP: +50 derrotou goblin patrulheiro]", "[XP: +200 quest concluída]"
# Backend acumula em wm.xp e detecta level up via tabela SRD.
_RE_XP = re.compile(r"\[XP:\s*\+?(\d+)\s*([^\]]*?)\s*\]", re.IGNORECASE)

# Lampejo — visão dramática emitida pelo LLM. Conteúdo entre `:` e `]` vira
# uma mensagem WS `tipo="lampejo"` separada, com voz alterada (rate/pitch).
# Usado por _extrair_lampejos / _enviar_lampejo no websocket — a regex vive
# aqui pra ficar com os demais markers (futura tabela única em D4).
_RE_LAMPEJO = re.compile(r"\[LAMPEJO:\s*([^\]]+?)\s*\]", re.IGNORECASE)

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
    # Bug R5-1: "lanço" removido — causava falso positivo onde armas/feitiços
    # eram registrados como inimigos: "lanço a flecha no orc" → "Flecha" virava
    # inimigo no CombatTracker. "lanço" é detectado separadamente pelo spell_detector
    # (spell_detector.py:_RE_CASTING) que extrai o nome da magia corretamente.
    r"\b(?:ataco?|atacar|golpei?o|firo|apunhalo|atinge?|atinjo|acerto)\s+"
    r"(?:o|a|ao?s?|na?s?)\s+"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,30}?)(?=\s+(?:com|de|usando|n[ao])\b|[.!,?]|$)",
    re.IGNORECASE,
)
_RE_INIMIGO_MORTO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:caiu|morreu|morre|está morto|está morta|foi abatido|foi abatida|jaz|tombou|"
    r"desmorona|sucumbe|sucumbiu|pereceu|perece|fenece|feneceu|"
    r"se dissolve|dissolveu|se dissipa|dissipou|"
    r"cai sem vida|caiu sem vida|cai morto|caiu morto|cai inerte|caiu inerte|"
    r"entra em colapso|entrou em colapso|desaba|desabou|"
    r"não se levanta|não se move mais|exala o último|"
    r"foi eliminado|foi eliminada|é eliminado|é eliminada|"
    r"foi destruído|foi destruída|é destruído|é destruída|"
    r"se fragmenta|fragmentou|"
    r"expira|expirou|"
    r"não respira|deixou de respirar)\b",
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
    # Declarações diretas de fim de combate
    r"o combate termina|a luta termina|combate encerrado|batalha encerrada|"
    r"a batalha chegou ao fim|o confronto termina|o confronto acabou|"
    # Estado de ausência de ameaças
    r"não há mais inimigos|sem mais ameaças|ambiente está seguro|"
    r"área está segura|local está seguro|ameaça foi neutralizada|"
    r"ameaças foram neutralizadas|não resta[m]? inimigos|"
    # Silêncio pós-combate (muito comum em PT-BR)
    r"silêncio retorna|silêncio toma conta|silêncio se instala|"
    r"silêncio cai sobre|o barulho cessa|o caos cessa|"
    # Todos os inimigos caíram
    r"todos os inimigos ca[íi]ram|inimigos foram derrotados|"
    r"todos ca[íi]ram|todos foram abatidos|todos pereceram|"
    # Último inimigo
    r"último inimigo|únic[oa] sobrevivente|nenhum sobreviveu|"
    # Recuo dos inimigos (também encerra combate para o jogador)
    r"inimigos recuaram|fugiram em desbandada|debandam|desbandada"
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
    working_mem: WorkingMemory,
    texto_jogador: str,
    resposta_llm: str,
    *,
    ids_ja_marcados_morte: set[str] | None = None,
) -> None:
    """Popula e atualiza inimigos_combate a partir do turno atual.

    1. Se jogador declara ataque com alvo nomeado → registrar inimigo (intacto)
    2. Varrer resposta do LLM por descritores de saúde e atualizar estado

    Args:
        ids_ja_marcados_morte: set de IDs já processados via marker [INIMIGO_MORTO].
            Esses são pulados na detecção regex de morte para evitar dupla
            atualização e log spam. Demais estados (ferido, grave) ainda são
            processados normalmente.
    """
    if not working_mem.em_combate:
        return
    _ja_mortos = ids_ja_marcados_morte or set()

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
        if iid and iid not in _ja_mortos:
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
    # 1. Registra fala do mestre + apresenta NPCs mencionados.
    # Strips marcadores internos ([FIO:], [CONSEQUÊNCIA:], [XP:], etc.) ANTES de
    # armazenar em dialogo_recente — o histórico enviado ao LLM como "assistant"
    # messages não deve conter marcadores de engine, senão o modelo aprende a
    # emiti-los desnecessariamente ou a referenciar seu próprio scaffolding interno.
    # A extração dos marcadores (steps 10-14) ainda usa `resposta_completa` original.
    fala_limpa = strip_marcadores(resposta_completa)
    working_mem.registrar_fala("mestre", fala_limpa)
    working_mem.apresentar_npcs_mencionados(resposta_completa)

    # 1b. Entrar em combate via marker — LLM tem autoridade para iniciar combate
    #     quando a ação do jogador é narrativamente bélica mas o regex de verbos
    #     não casou (sparring, "uso X em Y", declaração indireta). Bug
    #     COMBATE-VERB-1 (26/05): jogador dizia "vou usar chama sagrada nele"
    #     e o combate não iniciava — Mestre ficava em modo exploração tentando
    #     narrar troca de golpes sem combat.md/saves.md/initiative.
    if not working_mem.em_combate and _RE_COMBATE_MARKER.search(resposta_completa):
        working_mem.entrar_combate()
        log.info("combate_iniciado_por_marker")

    # 2. Sync de inimigos ANTES de detectar fim de combate (ordem crítica —
    #    sair_combate limpa inimigos_combate, perderíamos a última morte).
    # 2a. Engine-authority: marker [INIMIGO_MORTO: id] tem prioridade sobre regex.
    #     LLM declara explicitamente quem morreu. Resolve COMBAT-1 onde vocab
    #     PT-BR sutil ("o último orc cai ao chão") não casava com regex.
    # Audit FIX-1: rastreia IDs já marcados via marker para que o regex fallback
    # não os reprocesse (evita log duplicado + double-set idempotente).
    ids_via_marker: set[str] = set()
    if working_mem.em_combate:
        for m in _RE_INIMIGO_MORTO_MARKER.finditer(resposta_completa):
            iid = m.group(1).strip().lower()
            if iid in working_mem.inimigos_combate:
                working_mem.atualizar_estado_inimigo(iid, "morto", "sem vida")
                ids_via_marker.add(iid)
                log.info("combate_inimigo_morto_marker", id=iid)
    # 2b. Fallback de defesa: regex de vocab para casos onde LLM não emitiu marker.
    sincronizar_inimigos_combate(
        working_mem, texto_jogador, resposta_completa,
        ids_ja_marcados_morte=ids_via_marker,
    )

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
        # Volta o cursor visual pro JOGADOR — é a próxima vez que ele vai agir.
        # Bug R4-1: turno_atual_idx=0 sempre apontava para a posição 0 da lista,
        # que é o inimigo de MAIOR iniciativa (fallback 20,19,18...), não o jogador.
        # Jogador começa com 10+mod_des ≈ 12 — fica após os inimigos. Solução:
        # encontrar o índice real do token "jogador" entre os vivos.
        _ordem_ini = working_mem.calcular_ordem_iniciativa()
        _vivos = [t for t in _ordem_ini if not t.morto]
        _idx_jogador = next(
            (i for i, t in enumerate(_vivos) if t.id == "jogador"), 0
        )
        working_mem.turno_atual_idx = _idx_jogador

    # 4. Descanso — restaura spell slots se jogador declarou descanso neste turno.
    # Engine-authority: marker [DESCANSO: curto|longo] na resposta do LLM tem
    # prioridade sobre regex no texto do jogador. Resolve casos onde o LLM
    # confirma descanso em narrativa ambígua ("você desperta horas depois").
    # Fallback: regex 1ª pessoa em texto_jogador.
    tipo_descanso = None
    m_descanso = _RE_DESCANSO_MARKER.search(resposta_completa)
    if m_descanso:
        tipo_descanso = m_descanso.group(1).strip().lower()
        log.info("descanso_marker_detectado", tipo=tipo_descanso)
    if not tipo_descanso:
        tipo_descanso = detectar_descanso(texto_jogador)
    if tipo_descanso:
        restaurados = restaurar_slots(working_mem, tipo_descanso)
        # Também restaura class features (Action Surge, Rage, etc.) — fix de bug
        # latente: descanso só restaurava slots, features ficavam gastas.
        working_mem.restaurar_features(tipo_descanso)
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

    # 6. Avanço de rodada (só faz sentido em combate E com ação real do jogador).
    # Bug R5-5: `aplicar_pos_turno` é chamado com `texto_jogador=""` na abertura
    # (_enviar_abertura). Se a sessão era continuada em combate, `em_combate=True`
    # e `avancar_rodada()` incrementava `rodada_combate` sem rodada real acontecer —
    # player retomava em "Rodada 2" ao invés de "Rodada 1".
    if working_mem.em_combate and texto_jogador.strip():
        working_mem.avancar_rodada()

    # 7. [FUGIU] — jogador escapou do combate. Encerra combate imediatamente.
    # Distinct do _RE_FIM_COMBATE_LLM que detecta resolução da cena: fuga é a
    # decisão ativa de sair sem derrotar os inimigos. Strip do TTS já feito por
    # _RE_MESTRE_VET em quest_detector.strip_marcadores().
    if working_mem.em_combate and re.search(r"\[FUGIU\]", resposta_completa, re.IGNORECASE):
        working_mem.sair_combate()
        log.info("combate_encerrado_fuga")

    # 7. Fim de combate detectado na narração — POR ÚLTIMO, depois do sync
    if working_mem.em_combate and _RE_FIM_COMBATE_LLM.search(resposta_completa):
        working_mem.sair_combate()
        log.info("combate_encerrado_por_llm")

    # 7b. Auto-encerrar combate quando TODOS os inimigos estão mortos.
    # Garante que combates terminam mesmo quando o LLM usa frases de morte fora
    # do vocabulário de _RE_FIM_COMBATE_LLM (ex: "o último orc respira seu
    # último fôlego" sem dizer "combate termina"). Executado SÓ se o passo 7
    # não já chamou sair_combate() — por isso checa em_combate novamente.
    if working_mem.em_combate and working_mem.inimigos_combate:
        todos_mortos = all(
            d.get("estado") == "morto"
            for d in working_mem.inimigos_combate.values()
        )
        if todos_mortos:
            working_mem.sair_combate()
            log.info("combate_encerrado_auto_todos_mortos")

    # 7c. Timeout — combate sem nenhum inimigo registrado por 2+ rodadas, ou sem
    # menção a inimigos vivos por 3+ rodadas. Evita "combate eterno" quando a
    # cena migra silenciosamente para fora de combate (jogador foge, mestre
    # esquece de declarar). Sem isso, vinheta vermelha + animação de turno +
    # combat.md/saves.md injetados desperdiçam tokens indefinidamente.
    if working_mem.em_combate and texto_jogador.strip():
        # Inimigos vivos esperados na narração
        vivos = [
            d.get("nome", "")
            for d in working_mem.inimigos_combate.values()
            if d.get("estado") not in ("morto",)
        ]
        if not vivos:
            # Combate ativo sem inimigos vivos registrados — aguarda 2 rodadas
            working_mem.rodadas_sem_acao_inimigo += 1
            if working_mem.rodadas_sem_acao_inimigo >= 2:
                working_mem.sair_combate()
                log.info("combate_encerrado_sem_inimigos_vivos")
        else:
            # Algum inimigo vivo precisa ser mencionado na narração
            resp_lower = resposta_completa.lower()
            mencionado = any(n.lower() in resp_lower for n in vivos if n)
            if mencionado:
                working_mem.rodadas_sem_acao_inimigo = 0
            else:
                working_mem.rodadas_sem_acao_inimigo += 1
                if working_mem.rodadas_sem_acao_inimigo >= 3:
                    working_mem.sair_combate()
                    log.info("combate_encerrado_timeout_sem_mencao")

    # 7d. Decay das cartas de improviso — após 5 turnos sem uso explícito, descarta.
    # Sem isso o prompt carrega 3 cartas (~260 chars) todo turno mesmo se o mestre
    # nunca as invoca, queimando 2-3k tokens em sessão de 1h.
    # CRIT-4: só decay em turno real do jogador — abertura/reconexão NÃO conta.
    if working_mem.cartas_improviso and texto_jogador.strip():
        working_mem.turnos_desde_cartas += 1
        if working_mem.turnos_desde_cartas >= 5:
            log.info("cartas_improviso_descartadas", motivo="decay 5 turnos sem uso")
            working_mem.cartas_improviso = []
            working_mem.turnos_desde_cartas = 0

    # CRIT-4: steps 8 e 9 só rodam em turnos REAIS do jogador. A abertura e
    # reconexões chamam aplicar_pos_turno(wm, "", resposta_intro) — sem guard,
    # essas chamadas incrementavam turnos_sem_tensao e mexiam no pacing sem
    # ter havido ação do jogador, causando drift cumulativo em reconexões e
    # PACING [BAIXO] disparado cedo demais.
    if texto_jogador.strip():
        # 8. Contador de tensão narrativa fora de combate.
        # Zera também quando trust muda neste turno — cenas sociais com consequências
        # (interrogatório, barganha, confronto) são tensas mesmo sem espadas.
        # Sem isso, um roleplay dramático de 5 turnos recebe [PACING: BAIXO].
        if working_mem.em_combate or mudancas_trust:
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
    # Cap: máx 8 agendas ativas. Quando excede, remove a entrada mais antiga
    # (primeira chave inserida no dict — Python 3.7+ preserva ordem de inserção).
    # Sem esse teto, sessões longas com muitos NPCs namedropped acumulam agendas
    # indefinidamente e inflam o prompt em ~30-50 tokens por entrada extra.
    _MAX_AGENDA = 8
    for m in _RE_AGENDA.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        plano = m.group(2).strip()
        if npc_id and plano:
            working_mem.agenda_npcs[npc_id] = plano
            log.info("agenda_npc_atualizada", npc_id=npc_id, plano=plano[:60])
            # Remove a agenda mais antiga se o teto for ultrapassado
            while len(working_mem.agenda_npcs) > _MAX_AGENDA:
                oldest = next(iter(working_mem.agenda_npcs))
                del working_mem.agenda_npcs[oldest]
                log.debug("agenda_npc_removida_por_limite", npc_id=oldest)

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

    # ROB-4: teto de 50 itens e truncamento em 80 chars para evitar prompt inflation.
    # O sync_inventory do WebSocket já aplica esses limites para edições manuais;
    # este bloco espelha a mesma política para itens adicionados pelo LLM via [LOOT:].
    _MAX_INVENTARIO = 50
    for m in _RE_LOOT.finditer(resposta_completa):
        item = m.group(1).strip()[:80]  # trunca nomes extravagantes do LLM
        if item and item.lower() not in (i.lower() for i in working_mem.player_inventory):
            if len(working_mem.player_inventory) >= _MAX_INVENTARIO:
                log.warning("loot_ignorado_inventario_cheio", item=item[:60],
                            total=len(working_mem.player_inventory))
                continue
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
        working_mem.turnos_sem_mercado = 0
        log.info("mercado_aberto")
    elif _RE_FIM_MERCADO.search(resposta_completa):
        working_mem.em_mercado = False
        working_mem.turnos_sem_mercado = 0
        log.info("mercado_fechado")
    elif working_mem.em_mercado:
        # Sem [MERCADO] nem [FIM_MERCADO] neste turno — incrementa contador de inatividade.
        # Se o LLM "esqueceu" de emitir [FIM_MERCADO] ao sair da loja, o botão de venda
        # fecha automaticamente após 3 turnos sem reconfirmação (evita UI travada).
        working_mem.turnos_sem_mercado += 1
        if working_mem.turnos_sem_mercado >= 3:
            working_mem.em_mercado = False
            working_mem.turnos_sem_mercado = 0
            log.info("mercado_fechado_auto_timeout")

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

    # 15. Repetition Guard — coleta [ANCORA: fato] para evitar re-narração em sessões longas.
    for m in _RE_ANCORA.finditer(resposta_completa):
        ancora = m.group(1).strip()
        if ancora:
            working_mem.registrar_ancora(ancora)
            log.info("ancora_registrada", texto=ancora[:80])

    # 16. Assinaturas de voz de NPC — [VOZ: npc-id|pitch|rate] define parâmetros TTS por NPC.
    # Cap: 20 vozes por sessão (eviction oldest). Sessão longa pode introduzir
    # 30+ NPCs falantes; sem cap, dict cresce indefinidamente.
    _MAX_VOZES = 20
    for m in _RE_VOZ.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        pitch = m.group(2).strip()
        rate = m.group(3).strip()
        if npc_id and not working_mem.npc_vozes.get(npc_id):
            if len(working_mem.npc_vozes) >= _MAX_VOZES:
                # Remove a voz mais antiga (Python 3.7+ preserva ordem de inserção)
                mais_antiga = next(iter(working_mem.npc_vozes))
                del working_mem.npc_vozes[mais_antiga]
            working_mem.npc_vozes[npc_id] = {"pitch": pitch, "rate": rate}
            log.info("voz_npc_registrada", npc_id=npc_id, pitch=pitch, rate=rate)

    return mudancas_trust


async def aplicar_afeto_npcs(
    resposta_completa: str,
    neo4j_client: Any,
) -> None:
    """Extrai marcadores [AFETO: npc-id|campo|delta] e persiste no Neo4j.

    Por que existe: estado afetivo de NPC (afeto/medo/respeito/rancor) precisa
        de persistência entre sessões. Neo4j é a fonte verdadeira; WorkingMemory
        não armazena — o LLM recebe via semantic_memory quando consulta o NPC.

    Armadilha: NUNCA lançar exceção — Neo4j pode estar offline; o jogo deve continuar.
        Chamada fire-and-forget em websocket.py via asyncio.create_task.
    """
    for m in _RE_AFETO.finditer(resposta_completa):
        npc_id = m.group(1).strip().lower()
        campo = m.group(2).strip().lower()
        try:
            delta = int(m.group(3).strip())
        except ValueError:
            continue
        if npc_id and campo and delta != 0:
            await neo4j_client.atualizar_afeto_npc(npc_id, campo, delta)


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
    _xp_vistos: set[tuple[int, str]] = set()  # dedup: mesmo marker duplicado na resposta
    for m in _RE_XP.finditer(resposta_completa):
        try:
            qtd = int(m.group(1))
        except ValueError:
            continue
        motivo = m.group(2).strip() or "ganho de experiência"
        chave = (qtd, motivo.lower())
        if chave in _xp_vistos:
            continue
        _xp_vistos.add(chave)
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
