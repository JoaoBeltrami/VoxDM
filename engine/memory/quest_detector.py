"""
Detecta progressão de quests e aplica recompensas de milestone.

Por que existe: o LLM emite [Q:quest_id:stage_id] ao final da resposta quando uma
    quest inicia ou avança. Este módulo extrai, valida e aplica esses marcadores
    na WorkingMemory. Depois, aplica efeitos player-facing definidos no on_complete
    de cada stage (XP, ouro, itens, informações narrativas).

Dependências: engine/memory/working_memory
Armadilha: validar SEMPRE contra o catálogo do módulo. Um quest_id inexistente
    no catálogo é rejeitado silenciosamente — o LLM não pode inventar quests.
    Efeitos world-state (faction, npc_disposition, location_state) são logados
    mas não alteram WorkingMemory — o LLM os narra naturalmente via prompt.

Exemplo:
    resposta_limpa, avancos = detectar_e_aplicar_quests(
        resposta_llm, working_mem, catalog
    )
    recompensas = aplicar_recompensas_avancos(avancos, quest_efeitos, working_mem)
    # recompensas: {("o-reconhecimento", "reportar"): ["+300 XP", "+25 PO"]}
"""

import re
from typing import Any

import structlog

from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Formato: [Q:kebab-case-id:kebab-case-stage]
# Restrito a letras minúsculas, números e hífens para prevenir injeção de texto
# Tolera espaço em volta dos dois-pontos: TODOS os outros marcadores do projeto
# são `[NOME: valor]`, então o LLM tem prior forte pra escrever `[Q: id:stage]`.
# Sem essa folga o marcador é silenciosamente descartado e a quest NUNCA avança
# — e, desde o Diretor de Arco, a campanha nunca chega ao final (21/07).
_RE_Q = re.compile(
    r"\[Q:\s*([a-z0-9][a-z0-9-]{0,48})\s*:\s*([a-z0-9][a-z0-9-]{0,48})\s*\]",
    re.IGNORECASE,
)

# Marcadores de Mestre Veterano — fonte única em engine/markers.py (D4 26/05).
# COMBATE, INIMIGO_MORTO e todos os outros estão na tabela canônica lá.
# Re-exportado como _RE_MESTRE_VET pra preservar imports externos.
from engine.markers import RE_STRIP_MARCADORES as _RE_MESTRE_VET  # noqa: E402

# Também limpa espaços/newlines residuais deixados pelos marcadores
_RE_TRAILING_WS = re.compile(r"\n{3,}")


def carregar_quests_legiveis(modulo_path: str) -> list[dict[str, Any]]:
    """Quests com NOME e DESCRIÇÃO por estágio — o que o Mestre precisa pra agir.

    QUEST-OPACA-1 (mini-playtest 22/07): `carregar_catalog_modulo` devolve só
    ids, e `catalog_para_texto` imprimia `esforco-guerra-kaelmund(contrato-de-
    ferro,o-lacre,...)`. O módulo TEM título ("O contrato de Kaelmünd") e
    descrição por estágio — tudo descartado. Resultado: joguei 4 turnos indo
    exatamente atrás dessa quest, o Mestre narrou o beat inteiro (aceitou o
    trabalho, escoltou o ferro, entregou, pagou) e não emitiu um `[Q:]` sequer.
    Ele não tinha como saber o que o slug significava.

    Returns:
        [{id, nome, descricao, stages: [{id, descricao}]}] — vazio se ausente.
    """
    import json
    from pathlib import Path

    path = Path(modulo_path)
    if not path.exists():
        return []
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        saida: list[dict[str, Any]] = []
        for q in dados.get("quests", []):
            qid = str(q.get("id", "")).strip()
            if not qid:
                continue
            stages = [
                {"id": str(s.get("id", "")).strip(),
                 "descricao": str(s.get("description", "") or "").strip()}
                for s in q.get("stages", []) if s.get("id")
            ]
            if stages:
                saida.append({
                    "id": qid,
                    "nome": str(q.get("name", "") or "").strip(),
                    "descricao": str(q.get("description", "") or "").strip(),
                    "stages": stages,
                })
        return saida
    except Exception as e:
        log.warning("quests_legiveis_falhou", erro=str(e))
        return []


def carregar_catalog_modulo(modulo_path: str) -> dict[str, list[str]]:
    """Carrega o catálogo de quests e stages de um módulo JSON.

    Returns:
        dict[quest_id, list[stage_id]] — vazio se o módulo não tiver quests
        ou se o arquivo não existir/for inválido.
    """
    import json
    from pathlib import Path

    path = Path(modulo_path)
    if not path.exists():
        log.warning("modulo_nao_encontrado_para_quests", path=str(path))
        return {}

    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        quests = dados.get("quests", [])
        catalog: dict[str, list[str]] = {}
        for q in quests:
            qid = q.get("id", "").strip()
            if not qid:
                continue
            stages = [s.get("id", "").strip() for s in q.get("stages", []) if s.get("id")]
            if stages:
                catalog[qid] = stages
        log.info("quest_catalog_carregado", total_quests=len(catalog))
        return catalog
    except Exception as e:
        log.warning("quest_catalog_falhou", erro=str(e))
        return {}


def carregar_fronts_modulo(modulo_path: str) -> list[dict[str, object]]:
    """Carrega os fronts (relógios de ameaça autorais) de um módulo — Schema v2.

    Returns:
        Lista de {id, name, segments, filled} válidos. Vazio se o módulo não
        declara `fronts` (v1.2 puro) ou se o arquivo não existir/for inválido.
        Entradas sem id/name são puladas.
    """
    import json
    from pathlib import Path

    path = Path(modulo_path)
    if not path.exists():
        return []
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        fronts: list[dict[str, object]] = []
        for f in dados.get("fronts", []):
            fid = str(f.get("id", "")).strip()
            nome = str(f.get("name", "")).strip()
            if not fid or not nome:
                continue
            fronts.append({
                "id": fid,
                "name": nome,
                "segments": int(f.get("segments", 6) or 6),
                "filled": int(f.get("filled", 0) or 0),
            })
        if fronts:
            log.info("fronts_modulo_carregados", total=len(fronts))
        return fronts
    except Exception as e:
        log.warning("fronts_modulo_falhou", erro=str(e))
        return []


def carregar_agendas_modulo(modulo_path: str) -> dict[str, str]:
    """Agendas de fundo dos NPCs declaradas no módulo (Schema v2 npc.agenda).

    Returns:
        dict[npc_id, plano] — planos de fundo que o autor definiu. Vazio se
        nenhum NPC declara `agenda` (v1.2 puro) ou arquivo inválido. Plano
        truncado a 200 chars.
    """
    import json
    from pathlib import Path

    path = Path(modulo_path)
    if not path.exists():
        return {}
    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        agendas: dict[str, str] = {}
        for npc in dados.get("npcs", []):
            nid = str(npc.get("id", "")).strip()
            plano = str(npc.get("agenda", "")).strip()
            if nid and plano:
                agendas[nid] = plano[:200]
        if agendas:
            log.info("agendas_modulo_carregadas", total=len(agendas))
        return agendas
    except Exception as e:
        log.warning("agendas_modulo_falhou", erro=str(e))
        return {}


# Teto por descrição de estágio. O módulo tem descrições de até ~180 chars;
# 110 basta pra o Mestre reconhecer o beat sem virar um dump de roteiro.
_MAX_DESC_STAGE = 110


def catalog_para_texto(
    catalog: dict[str, list[str]],
    quests_legiveis: list[dict[str, Any]] | None = None,
    stages_atuais: dict[str, str] | None = None,
) -> str:
    """Serializa as quests pro prompt — o PRÓXIMO passo jogável de cada uma.

    QUEST-OPACA-1 (mini-playtest 22/07): a versão antiga imprimia só slugs
    (`esforco-guerra-kaelmund(contrato-de-ferro,o-lacre,a-verdade-reescrita)`).
    O Mestre narrou o beat inteiro de `contrato-de-ferro` — aceitar o trabalho,
    escoltar o ferro, entregar, receber o ouro — e não emitiu `[Q:]` nenhum,
    porque não tinha como saber o que aquele slug queria dizer.

    Mostra UM estágio por quest (o próximo não cumprido), não a lista inteira:
    é menor, é acionável, não entrega spoiler dos beats futuros e ainda induz a
    ordem certa — o detector aceita qualquer stage do catálogo, então um menu
    completo convidava a pular pro final.

    `quests_legiveis` vem de `carregar_quests_legiveis`; sem ele, cai no formato
    antigo de ids (compatibilidade com callers e testes existentes).
    """
    if not catalog:
        return ""

    if not quests_legiveis:
        partes = [f"{qid}({','.join(stages)})" for qid, stages in catalog.items()]
        return "Quests disponíveis: " + " | ".join(partes)

    stages_atuais = stages_atuais or {}
    linhas: list[str] = []
    for q in quests_legiveis:
        qid = q["id"]
        if qid not in catalog:
            continue
        stages = q["stages"]
        atual = stages_atuais.get(qid)
        proximo = stages[0]
        if atual:
            ids = [s["id"] for s in stages]
            if atual in ids:
                if ids.index(atual) >= len(ids) - 1:
                    continue                       # quest concluída — sai da lista
                proximo = stages[ids.index(atual) + 1]
        desc = proximo["descricao"][:_MAX_DESC_STAGE]
        nome = f" ({q['nome']})" if q.get("nome") else ""
        marca = "em curso" if atual else "não iniciada"
        linhas.append(f"• {qid}{nome} [{marca}] → próximo `{proximo['id']}`: {desc}")

    if not linhas:
        return ""
    return (
        "=== MISSÕES DO MÓDULO (o próximo passo de cada uma) ===\n"
        + "\n".join(linhas)
    )


# Cache do parse do módulo (mesmo padrão de `carregar_modulo_arco`): o arquivo
# não muda em runtime, e o bloco é re-renderizado a cada avanço de quest.
_CACHE_LEGIVEIS: dict[str, list[dict[str, Any]]] = {}


def renderizar_quests(working_mem: WorkingMemory, modulo_path: str | None = None) -> str:
    """Recalcula `wm.quests_modulo` com o próximo passo de cada quest.

    Chamado no início da sessão e a cada avanço — o bloco mostra o PRÓXIMO
    estágio, então ele muda quando uma quest anda. Sem isso o Mestre continuaria
    vendo o primeiro passo de uma missão que já cumpriu.
    """
    from config import settings

    caminho = modulo_path or settings.DEFAULT_MODULE_PATH
    if caminho not in _CACHE_LEGIVEIS:
        _CACHE_LEGIVEIS[caminho] = carregar_quests_legiveis(caminho)
    texto = catalog_para_texto(
        carregar_catalog_modulo(caminho),
        quests_legiveis=_CACHE_LEGIVEIS[caminho],
        stages_atuais=dict(working_mem.quest_stages),
    )
    working_mem.quests_modulo = texto
    return texto


def detectar_e_aplicar_quests(
    resposta: str,
    working_mem: WorkingMemory,
    catalog: dict[str, list[str]],
) -> tuple[str, list[tuple[str, str]]]:
    """Extrai marcadores [Q:quest_id:stage_id], valida e aplica na WorkingMemory.

    Args:
        resposta: Texto completo do LLM, possivelmente contendo marcadores.
        working_mem: Estado da sessão — atualizado in-place nos avanços válidos.
        catalog: dict[quest_id, list[stage_id]] carregado do módulo.
                 Se vazio, nenhum avanço é aplicado (safe no-op).

    Returns:
        (resposta_limpa, avancos)
        resposta_limpa: texto sem nenhum marcador [Q:...], pronto para TTS.
        avancos: lista de (quest_id, stage_id) que foram efetivamente aplicados.
    """
    if not catalog:
        return resposta, []

    avancos: list[tuple[str, str]] = []

    for m in _RE_Q.finditer(resposta):
        qid = m.group(1).lower()
        sid = m.group(2).lower()

        # Validação: (quest_id, stage_id) deve existir no catálogo do módulo
        stages_validos = catalog.get(qid)
        if not stages_validos:
            log.warning("quest_sinal_quest_desconhecida", quest_id=qid, stage_id=sid)
            continue
        if sid not in stages_validos:
            log.warning("quest_sinal_stage_invalido", quest_id=qid, stage_id=sid,
                        stages_validos=stages_validos)
            continue

        # Idempotência — não re-aplica o mesmo stage
        if working_mem.quest_stages.get(qid) == sid:
            continue

        working_mem.atualizar_quest_stage(qid, sid)
        avancos.append((qid, sid))
        log.info("quest_avancou", quest_id=qid, stage_id=sid,
                 era=working_mem.quest_stages.get(qid, "novo"))

        # Diretor de Arco (passo 3b): quest CONCLUÍDA = chegou na ÚLTIMA stage do
        # catálogo → entra em quests_completas (alimenta F2/trégua e as
        # war-effort quests que decidem F1/F3). Idempotente (set).
        if stages_validos and sid == stages_validos[-1]:
            working_mem.quests_completas.add(qid)
            log.info("quest_concluida", quest_id=qid, stage_final=sid)

    # O bloco de quests mostra o PRÓXIMO passo — avançou, mudou.
    if avancos:
        try:
            renderizar_quests(working_mem)
        except Exception as e:
            log.warning("quests_render_falhou", erro=str(e)[:100])

    # Limpa marcadores e colapsa linhas em branco residuais
    limpa = _RE_Q.sub("", resposta)
    limpa = _RE_TRAILING_WS.sub("\n\n", limpa).rstrip()
    return limpa, avancos


def strip_marcadores(texto: str) -> str:
    """Remove marcadores de sistema do texto antes de enviar para TTS.

    Remove:
        [Q:quest_id:stage_id]         — progressão de quest
        [FIO: ...]                    — fio narrativo em aberto
        [CLIFFHANGER: ...]            — encerramento dramático
        [AGENDA: npc → plano]         — agenda paralela de NPC
        [LAMPEJO: ...]                — flash de perspectiva (sintetizado à parte)
        [CONSEQUÊNCIA: ...]           — efeito duradouro no mundo (Feature 3)
        [Rolagem visível: dX = Y]     — rolagem do mestre (Fase 5.7); número já foi
                                        enviado como "dado_rolado" pelo websocket

    Não altera WorkingMemory — só higieniza o buffer para TTS.
    """
    limpa = _RE_Q.sub("", texto)
    limpa = _RE_MESTRE_VET.sub("", limpa)
    return limpa.strip()


# ── Rewards ────────────────────────────────────────────────────────────────────

# Limites anti-abuso para efeitos aplicados automaticamente via módulo
_MAX_XP_REWARD: int = 10_000        # XP máximo por stage (acima disso o módulo está errado)
_MAX_GOLD_REWARD: int = 10_000      # PO máximo por stage
_MAX_INVENT_REWARD: int = 40        # inventário máximo (deixa margem para itens manuais)
# Diretor de Arco: reputação de facção do jogador — clamp defensivo (allied=50).
_MIN_FACTION_STANDING: int = -100
_MAX_FACTION_STANDING: int = 100
# Flag RESERVADA com consequência mecânica (ver SCHEMA_ARCO.md): quebrar o
# artefato mata a magia no mundo E zera os slots do jogador.
_FLAG_MAGIA_MORTA: str = "magia-morta"


def carregar_efeitos_modulo(modulo_path: str) -> dict[str, dict[str, list[dict]]]:
    """Carrega os efeitos on_complete de cada stage do módulo.

    Returns:
        dict[quest_id, dict[stage_id, list[effect_dicts]]] — vazio se não houver
        efeitos ou se o arquivo não existir/for inválido.
    """
    import json
    from pathlib import Path

    path = Path(modulo_path)
    if not path.exists():
        log.warning("modulo_nao_encontrado_para_efeitos", path=str(path))
        return {}

    try:
        dados = json.loads(path.read_text(encoding="utf-8"))
        resultado: dict[str, dict[str, list[dict]]] = {}
        for q in dados.get("quests", []):
            qid = q.get("id", "").strip()
            if not qid:
                continue
            stages_dict: dict[str, list[dict]] = {}
            for s in q.get("stages", []):
                sid = s.get("id", "").strip()
                on_complete = s.get("on_complete", [])
                if sid and isinstance(on_complete, list) and on_complete:
                    stages_dict[sid] = on_complete
            if stages_dict:
                resultado[qid] = stages_dict
        log.info("quest_efeitos_carregados", total_quests=len(resultado))
        return resultado
    except Exception as e:
        log.warning("quest_efeitos_falhou", erro=str(e))
        return {}


def aplicar_recompensas_avancos(
    avancos: list[tuple[str, str]],
    efeitos_modulo: dict[str, dict[str, list[dict]]],
    working_mem: WorkingMemory,
) -> dict[tuple[str, str], list[str]]:
    """Aplica efeitos player-facing dos stages que avançaram e retorna strings legíveis.

    Tipos de efeito processados:
        xp_gain    → adiciona XP, retorna "+N XP"
        gold_gain  → adiciona ouro, retorna "+N PO"
        item_gain  → adiciona item ao inventário, retorna "Obteve: {nome}"
        information → adiciona ao log_consequencias, retorna "📜 {texto}"

    Tipos ignorados (sem efeito no personagem):
        faction_standing_change, npc_disposition_change, location_state_change
        — logados apenas. O LLM os narra naturalmente via prompt.

    Args:
        avancos: lista de (quest_id, stage_id) de detectar_e_aplicar_quests
        efeitos_modulo: {quest_id: {stage_id: [efeitos]}} de carregar_efeitos_modulo
        working_mem: estado da sessão — modificado in-place

    Returns:
        {(quest_id, stage_id): ["+300 XP", "+25 PO", ...]} — só avanços com recompensas
    """
    resultado: dict[tuple[str, str], list[str]] = {}

    for qid, sid in avancos:
        efeitos = efeitos_modulo.get(qid, {}).get(sid, [])
        if not efeitos:
            continue

        recompensas: list[str] = []

        for efeito in efeitos:
            tipo = efeito.get("effect", "")
            valor = efeito.get("value")

            if tipo == "xp_gain" and isinstance(valor, int) and 0 < valor <= _MAX_XP_REWARD:
                working_mem.xp += valor
                recompensas.append(f"+{valor} XP")
                log.info("recompensa_xp", quest_id=qid, stage_id=sid, xp=valor,
                         xp_total=working_mem.xp)

            elif tipo == "gold_gain" and isinstance(valor, int) and 0 < valor <= _MAX_GOLD_REWARD:
                working_mem.gold += valor
                recompensas.append(f"+{valor} PO")
                log.info("recompensa_gold", quest_id=qid, stage_id=sid, gold=valor,
                         gold_total=working_mem.gold)

            elif tipo == "item_gain" and isinstance(valor, str) and valor.strip():
                nome = valor.strip()[:80]
                if nome not in working_mem.player_inventory:
                    if len(working_mem.player_inventory) < _MAX_INVENT_REWARD:
                        working_mem.player_inventory.append(nome)
                        recompensas.append(f"Obteve: {nome}")
                        log.info("recompensa_item", quest_id=qid, stage_id=sid, item=nome)

            elif tipo == "information" and isinstance(valor, str) and valor.strip():
                info = valor.strip()[:200]
                working_mem.log_consequencias.append(info)
                if len(working_mem.log_consequencias) > 5:
                    working_mem.log_consequencias = working_mem.log_consequencias[-5:]
                recompensas.append(f"📜 {info}")
                log.info("recompensa_informacao", quest_id=qid, stage_id=sid,
                         preview=info[:60])

            elif tipo == "faction_standing_change" and isinstance(valor, int):
                # Diretor de Arco (passo 3a): APLICA de verdade — é o que faz a
                # reputação de facção do jogador se mover e, com ela, decide qual
                # final da guerra dispara (F1/F3). Antes era só logado → a guerra
                # nunca pendia. Clamp defensivo pra evitar runaway.
                alvo = str(efeito.get("target", "")).strip()
                if alvo:
                    novo = working_mem.faction_standings.get(alvo, 0) + valor
                    working_mem.faction_standings[alvo] = max(
                        _MIN_FACTION_STANDING, min(_MAX_FACTION_STANDING, novo)
                    )
                    log.info("faction_standing_aplicado", target=alvo, delta=valor,
                             novo=working_mem.faction_standings[alvo], quest_id=qid)

            elif tipo == "front_advance":
                # Diretor de Arco (passo 3a): avança a ESPINHA da campanha. A
                # espinha vive latente (persistente, sem deleção one-shot) — é
                # onde a guerra tica silenciosa até o clímax. Fallback: se o front
                # virou relógio ativo, usa a API do relógio.
                alvo = str(efeito.get("target", "")).strip().lower()
                passos = valor if isinstance(valor, int) and valor > 0 else 1
                narr = working_mem.narrative
                if alvo in getattr(narr, "relogios", {}):
                    narr.avancar_relogio(alvo, passos)
                    log.info("front_advance_relogio", target=alvo, passos=passos, quest_id=qid)
                elif alvo in getattr(narr, "fronts_latentes", {}):
                    fr = narr.fronts_latentes[alvo]
                    seg = int(fr.get("segmentos", 0))
                    fr["filled"] = max(0, min(seg, int(fr.get("filled", 0)) + passos))
                    log.info("front_advance_latente", target=alvo, passos=passos,
                             filled=fr["filled"], segmentos=seg, quest_id=qid)
                else:
                    log.warning("front_advance_alvo_desconhecido", target=alvo, quest_id=qid)

            elif tipo == "flag_set":
                # Diretor de Arco (passo 5): ato IRREVERSÍVEL fecha uma porta —
                # a flag entra em arc_flags e o ending correspondente passa a não
                # disparar mais (`flag X == false` no `when`). Decisão "c" 20/07:
                # só o irreversível tranca; logística/sabotagem são recuperáveis.
                alvo = str(efeito.get("target", "")).strip()
                if alvo:
                    working_mem.arc_flags[alvo] = True if valor is None else valor
                    log.info("arc_flag_setada", flag=alvo,
                             valor=working_mem.arc_flags[alvo], quest_id=qid)
                    # Flag RESERVADA com consequência mecânica: a magia morre no
                    # mundo E na ficha (decisão "a" 20/07) — quem quebrou o
                    # Cajado termina a campanha sem o que o define.
                    if alvo == _FLAG_MAGIA_MORTA and working_mem.arc_flags[alvo]:
                        for nivel in list(working_mem.spell_slots.keys()):
                            working_mem.spell_slots[nivel]["current"] = 0
                        recompensas.append("✦ A magia morreu no mundo")
                        log.info("magia_morta_slots_zerados", quest_id=qid)

            elif tipo in ("npc_disposition_change", "location_state_change"):
                # Efeitos de mundo — logados, não modificam WorkingMemory
                # (o LLM os narra naturalmente via prompt).
                log.info("efeito_mundo", tipo=tipo, target=efeito.get("target"),
                         value=valor, quest_id=qid, stage_id=sid)

        if recompensas:
            resultado[(qid, sid)] = recompensas

    return resultado
