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
_RE_Q = re.compile(
    r"\[Q:([a-z0-9][a-z0-9-]{0,48}):([a-z0-9][a-z0-9-]{0,48})\]",
    re.IGNORECASE,
)

# Marcadores de Mestre Veterano (features Fase 4.6 DM) — removidos do TTS
# mas mantidos na resposta completa para extração pelo turn_pipeline
_RE_MESTRE_VET = re.compile(
    r"\[(?:FIO|CLIFFHANGER|AGENDA|LAMPEJO):[^\]]*\]",
    re.IGNORECASE,
)

# Também limpa espaços/newlines residuais deixados pelos marcadores
_RE_TRAILING_WS = re.compile(r"\n{3,}")


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


def catalog_para_texto(catalog: dict[str, list[str]]) -> str:
    """Serializa o catálogo para texto compacto injetado no prompt do LLM.

    Exemplo de saída:
        Quests disponíveis: combate-inicial(encontro-carnicais) | o-reconhecimento(receber-missao,visitar-vilas,reportar)
    """
    if not catalog:
        return ""
    partes = [
        f"{qid}({','.join(stages)})"
        for qid, stages in catalog.items()
    ]
    return "Quests disponíveis: " + " | ".join(partes)


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

    # Limpa marcadores e colapsa linhas em branco residuais
    limpa = _RE_Q.sub("", resposta)
    limpa = _RE_TRAILING_WS.sub("\n\n", limpa).rstrip()
    return limpa, avancos


def strip_marcadores(texto: str) -> str:
    """Remove marcadores de sistema do texto antes de enviar para TTS.

    Remove:
        [Q:quest_id:stage_id]   — progressão de quest
        [FIO: ...]              — fio narrativo em aberto
        [CLIFFHANGER: ...]      — encerramento dramático
        [AGENDA: npc → plano]   — agenda paralela de NPC
        [LAMPEJO: ...]          — flash de perspectiva (sintetizado à parte)

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

            elif tipo in ("faction_standing_change", "npc_disposition_change",
                          "location_state_change"):
                # Efeitos de mundo — logados, não modificam WorkingMemory
                log.info("efeito_mundo", tipo=tipo, target=efeito.get("target"),
                         value=valor, quest_id=qid, stage_id=sid)

        if recompensas:
            resultado[(qid, sid)] = recompensas

    return resultado
