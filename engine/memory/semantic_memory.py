"""
Query híbrida: Qdrant (similaridade semântica) + Neo4j (relações do grafo).

Por que existe: a busca pura por vetor retorna chunks de texto mas não sabe
    quem conhece quem. Enriquecer cada resultado com relações do Neo4j dá ao
    LLM contexto narrativo mais rico sem aumentar o número de queries ao Qdrant.
Dependências: engine/memory/{qdrant_client,neo4j_client}, structlog
Armadilha: Neo4j pode não ter a entidade (source_id ausente no grafo) — tratar
    silenciosamente, retornando o chunk sem enriquecimento.

Exemplo:
    mem = SemanticMemory()
    resultados = await mem.buscar_enriquecido("onde está Fael?", top_k=5)
    # → [{"text": "...", "source_id": "fael-valdreksson",
    #      "relacoes": [{"tipo": "CONHECE", "alvo_id": "osmund-ferreiro", ...}]}]
"""

from typing import Any

import structlog

from engine.memory.neo4j_client import Neo4jMemoryClient
from engine.memory.qdrant_client import QdrantMemoryClient

log = structlog.get_logger()

# Máximo de relações Neo4j anexadas por chunk — evita explodir o contexto
MAX_RELACOES_POR_CHUNK = 4


class SemanticMemory:
    """
    Busca híbrida: recupera chunks semanticamente similares e os enriquece
    com relações do grafo para os source_ids encontrados.

    Instanciar uma vez por sessão e reutilizar.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()
        self._neo4j = Neo4jMemoryClient()

    async def buscar_enriquecido(
        self,
        query: str,
        colecao: str = "voxdm_modules",
        top_k: int = 5,
        filtro: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Busca semântica no Qdrant seguida de enriquecimento com grafo Neo4j.

        Para cada chunk retornado, tenta buscar as relações da entidade
        referenciada (source_id) e as adiciona ao dict de resultado.

        Args:
            query: Texto da query (transcrição + contexto).
            colecao: Coleção Qdrant alvo.
            top_k: Número de chunks a recuperar.
            filtro: Filtro de payload Qdrant opcional.

        Returns:
            Lista de chunks com campo adicional "relacoes" (pode ser []).
        """
        chunks = await self._qdrant.buscar(query, colecao=colecao, top_k=top_k, filtro=filtro)

        enriquecidos: list[dict[str, Any]] = []
        for chunk in chunks:
            source_id: str = chunk.get("source_id", "")
            relacoes: list[dict[str, Any]] = []

            if source_id:
                try:
                    todas = await self._neo4j.buscar_relacionamentos(source_id)
                    relacoes = todas[:MAX_RELACOES_POR_CHUNK]
                except Exception as e:
                    log.debug("sem_relacoes_no_grafo", source_id=source_id, erro=str(e))

            enriquecidos.append({**chunk, "relacoes": relacoes})

        log.info(
            "semantic_memory_enriquecida",
            query_resumida=query[:60],
            chunks=len(enriquecidos),
            com_relacoes=sum(1 for c in enriquecidos if c["relacoes"]),
        )
        return enriquecidos

    async def buscar_npc(self, npc_id: str) -> dict[str, Any] | None:
        """
        Retorna dados completos de um NPC: propriedades do grafo + chunk semântico.

        Útil para o mestre saber tudo sobre um NPC antes de dar-lhe voz.
        """
        props = await self._neo4j.buscar_entidade(npc_id)
        if not props:
            return None

        chunks = await self._qdrant.buscar(
            query=npc_id,
            colecao="voxdm_modules",
            top_k=1,
            filtro={"source_id": npc_id},
        )
        texto = chunks[0].get("text", "") if chunks else ""

        return {**props, "chunk_descricao": texto, "id": npc_id}

    async def fechar(self) -> None:
        await self._neo4j.fechar()
