"""
Dossiê de personalidade por NPC — 2-3 traços DISTINTOS gerados no 1º encontro.

Por que existe: "depois de várias sessões os NPCs são muito iguais" (Beltrami,
    21/06) — sem um dossiê persistente, todo NPC converge pro tom do Mestre.
    Decisão travada em 12/07: o LLM gera os traços no PRIMEIRO encontro (mesma
    chamada barata do padrão extractor, ENTITY_EXTRACTION → 8B), a engine
    persiste no registro canônico de identidade (npc_registro, viaja no
    dm_state e sobrevive a rename) e injeta no prompt da cena — vale pra NPCs
    fixos do módulo e improvisados.
Dependências: engine/npc/identity (registro canônico); extrair_json_defensivo
    do extractor (import lazy — o extractor importa identity, nunca este
    módulo, então não há ciclo).
Armadilha: falha silenciosa SEMPRE — dossiê é tempero, nunca pode custar um
    turno. Kill-switch: settings.DOSSIE_NPC_ATIVO.

Exemplo:
    tracos = await gerar_dossie(groq, narracao, "gorvoth", "Gorvoth")
    aplicar_dossie(wm, "gorvoth", tracos)
    # → scene.to_prompt() passa a listar "gorvoth [voz baixa e pausada; ...]"
"""

from typing import Any

import structlog

from engine.llm.tasks import TaskType
from engine.npc.identity import registrar_npc, resolver_npc

log = structlog.get_logger()

# Caps do dossiê — tempero, não biografia. 3 traços de ≤60 chars cabem numa
# linha do prompt sem virar um segundo bloco de lore.
MAX_TRACOS = 3
MAX_CHARS_TRACO = 60

_SYSTEM_DOSSIE = (
    "Você cria dossiês de personalidade pra NPCs de RPG em PT-BR a partir da "
    "narração do Mestre. Responda APENAS com JSON válido, sem texto antes ou "
    'depois, no formato:\n{"tracos": ["traço 1", "traço 2", "traço 3"]}\n'
    "Regras:\n"
    "- 2 a 3 traços CONCRETOS e DISTINTOS entre si (maneirismo de fala, "
    "postura, valor, medo, tique) — coisas que mudam COMO ele fala e age.\n"
    "- Cada traço com no máximo 8 palavras.\n"
    "- PROIBIDO traço genérico ('é misterioso', 'é amigável', 'é forte').\n"
    "- Se a narração não der material suficiente, INVENTE traços coerentes "
    "com o que foi mostrado — nunca devolva lista vazia."
)


async def gerar_dossie(
    groq: Any, narracao: str, npc_id: str, nome: str
) -> list[str] | None:
    """Gera 2-3 traços pro NPC a partir da narração do turno de encontro.

    Chamada barata (ENTITY_EXTRACTION → 8B) no mesmo padrão de
    extrair_npcs_cena. Retorna a lista sanitizada ou None (falha = sem
    dossiê por ora; outro turno tenta de novo).
    """
    if not narracao.strip() or not npc_id:
        return None
    try:
        resposta = await groq.completar(
            [
                {"role": "system", "content": _SYSTEM_DOSSIE},
                {
                    "role": "user",
                    "content": (
                        f"NPC: {nome} (id: {npc_id})\n\n"
                        f"Narração do encontro:\n{narracao[:1500]}"
                    ),
                },
            ],
            temperatura=0.6,
            max_tokens=120,
            task=TaskType.ENTITY_EXTRACTION,
        )
    except Exception as e:
        log.warning("dossie_llm_falhou", npc_id=npc_id, erro=str(e)[:120])
        return None
    from engine.llm.extractor import extrair_json_defensivo  # lazy — sem ciclo
    bruto = extrair_json_defensivo(resposta or "")
    if not isinstance(bruto, dict):
        log.warning("dossie_json_invalido", npc_id=npc_id, amostra=(resposta or "")[:80])
        return None
    tracos = _sanitizar_tracos(bruto.get("tracos"))
    return tracos or None


def _sanitizar_tracos(bruto: Any) -> list[str]:
    """Lista de strings não-vazias, dedup, caps de tamanho e quantidade."""
    if not isinstance(bruto, list):
        return []
    vistos: set[str] = set()
    saida: list[str] = []
    for t in bruto:
        texto = str(t).strip().strip(".").strip()
        chave = texto.lower()
        if not texto or chave in vistos:
            continue
        vistos.add(chave)
        saida.append(texto[:MAX_CHARS_TRACO])
        if len(saida) >= MAX_TRACOS:
            break
    return saida


def aplicar_dossie(wm: Any, npc_id: str, tracos: list[str]) -> None:
    """Persiste os traços na entrada canônica do registro (idempotente-ish:
    só grava se ainda não há dossiê — o 1º encontro vence, sem re-gerar)."""
    tracos_ok = _sanitizar_tracos(tracos)
    if not tracos_ok:
        return
    canon = registrar_npc(wm, npc_id)
    entrada = wm.scene.npc_registro[canon]
    if entrada.get("tracos"):
        return
    entrada["tracos"] = tracos_ok
    log.info("dossie_aplicado", npc_id=canon, tracos=tracos_ok)


def tem_dossie(wm: Any, npc_id: str) -> bool:
    canon = resolver_npc(wm, str(npc_id))
    return bool(wm.scene.npc_registro.get(canon, {}).get("tracos"))


def npcs_sem_dossie_na_cena(wm: Any, cap: int = 2) -> list[str]:
    """Até `cap` NPCs em cena (presentes∩apresentados), vivos, sem dossiê —
    os candidatos do turno. Cap baixo: 1 chamada barata por NPC, nunca uma
    rajada quando uma cena lota de gente."""
    saida: list[str] = []
    apresentados = getattr(wm.scene, "npcs_apresentados", set()) or set()
    for nid in list(wm.npcs_presentes):
        if nid not in apresentados:
            continue
        canon = resolver_npc(wm, str(nid))
        entrada = wm.scene.npc_registro.get(canon, {})
        if entrada.get("morto") or entrada.get("tracos"):
            continue
        saida.append(canon)
        if len(saida) >= cap:
            break
    return saida
