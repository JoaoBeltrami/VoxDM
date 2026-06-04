"""
Lookup de fichas (stat blocks) de monstro do SRD e enriquecimento do combate.

Por que existe: o Mestre improvisa HP/CA/ataques de inimigo sem dados reais. Este
    módulo busca a ficha compacta de um monstro na coleção voxdm_bestiary (indexada
    por ingest_rules.py) e a guarda no inimigo registrado, pra o prompt de combate
    narrar com consistência mecânica (gêmeo do engine/magic/spell_detector.py).
Dependências: engine/memory/qdrant_client
Armadilha: lookup é DETERMINÍSTICO por source_id (filtro exato), nunca fuzzy —
    evita injetar a ficha errada. Se o índice não existe na coleção, retorna None
    silenciosamente e o combate segue com narração improvisada (como hoje).

Exemplo:
    ficha = await buscar_ficha_monstro(srd_index="goblin")
    # → "Goblin — Pequeno humanoide, CR 1/4 (50 XP). CA 15 | PV 7 (2d6) ..."
    # → None se não indexado / Qdrant fora
"""

import re
import unicodedata
from typing import Any

import structlog

from config import settings

log = structlog.get_logger()

# Teto de lookups por turno — protege contra um turno declarando dezenas de
# inimigos novos (cada lookup é uma ida ao Qdrant). Os já cacheados não contam.
_MAX_LOOKUPS_POR_TURNO = 5


def _slugify(nome: str) -> str:
    """Converte nome livre em índice kebab-case candidato (ex: 'Goblin' → 'goblin')."""
    normalizado = unicodedata.normalize("NFD", nome.strip().lower())
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


async def buscar_ficha_monstro(srd_index: str = "", nome: str = "") -> str | None:
    """Busca a ficha compacta de um monstro na coleção voxdm_bestiary.

    Estratégia (determinística, sem fuzzy):
      1. Se `srd_index` fornecido, filtra por source_id exato.
      2. Senão, tenta slugify(nome) como índice (ex: "Goblin" → "goblin").
    Em ambos os casos é um match exato por source_id — se o índice não existe,
    retorna None (sem semântico, pra nunca injetar a ficha de outro monstro).

    Returns:
        O texto do stat block, ou None se não encontrado / erro de rede.
    """
    indice = (srd_index or _slugify(nome)).strip().lower()
    if not indice:
        return None
    try:
        from engine.memory.qdrant_client import QdrantMemoryClient

        cliente = QdrantMemoryClient()
        # query é só pra gerar o vetor exigido pelo query_points; o filtro exato
        # por source_id é quem decide o resultado. score_threshold=0 → não filtra.
        resultados = await cliente.buscar(
            query=indice,
            colecao=settings.QDRANT_COLECAO_BESTIARY,
            top_k=1,
            filtro={"source_id": indice},
            score_threshold=0.0,
        )
        if not resultados:
            return None
        texto = str(resultados[0].get("text", "")).strip()
        if texto:
            log.info("bestiario_ficha_encontrada", indice=indice)
        return texto or None
    except Exception as exc:
        # Falha silenciosa — Qdrant fora, coleção ausente, etc. Combate segue.
        log.warning("bestiario_busca_falhou", indice=indice, erro=str(exc)[:120])
        return None


async def enriquecer_fichas_inimigos(working_mem: Any) -> int:
    """Carrega a ficha SRD dos inimigos em combate que ainda não a têm.

    Idempotente: pula inimigos mortos, os que já têm `ficha`, e os cujo índice
    (srd_index ou slug do nome) não bate em nenhum monstro indexado. Roda no
    websocket (contexto async) DEPOIS do pipeline pós-turno — a ficha fica
    disponível no prompt do turno seguinte. Falha de lookup é silenciosa.

    Returns:
        Quantas fichas novas foram carregadas (útil pra telemetria/testes).
    """
    if not getattr(working_mem, "em_combate", False):
        return 0
    carregadas = 0
    for dados in working_mem.inimigos_combate.values():
        if carregadas >= _MAX_LOOKUPS_POR_TURNO:
            break
        if dados.get("estado") == "morto" or dados.get("ficha"):
            continue
        ficha = await buscar_ficha_monstro(
            srd_index=dados.get("srd_index", ""),
            nome=dados.get("nome", ""),
        )
        if ficha:
            dados["ficha"] = ficha
            carregadas += 1
    if carregadas:
        log.info("bestiario_fichas_carregadas", quantidade=carregadas)
    return carregadas
