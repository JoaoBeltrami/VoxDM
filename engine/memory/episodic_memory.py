"""
Recuperação de memórias de sessões anteriores armazenadas no Qdrant.

Por que existe: o mestre precisa de continuidade entre sessões — referências
    a eventos passados, NPCs mortos, promessas feitas. Essa camada busca
    resumos de sessões anteriores gravados pelo session_writer.
Dependências: engine/memory/qdrant_client, structlog
Armadilha: a coleção "voxdm_episodic" pode não existir na primeira sessão —
    tratar a ausência silenciosamente (retorna lista vazia, não levanta exceção).

Exemplo:
    mem = EpisodicMemory()
    eventos = await mem.buscar("o que aconteceu com Bjorn?", top_k=3)
    # → [{"text": "Na sessão 2, Bjorn foi capturado...", "session_id": "sess-02", ...}]
"""

from typing import Any

import structlog

from engine.memory.qdrant_client import QdrantMemoryClient

log = structlog.get_logger()

_COLECAO = "voxdm_episodic"


class EpisodicMemory:
    """
    Recupera memórias de sessões anteriores do Qdrant.

    Instanciar uma vez por sessão e reutilizar — o cliente mantém conexão.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()

    async def buscar(
        self,
        query: str,
        top_k: int = 3,
        session_id_filtro: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Busca memórias episódicas relevantes para a query atual.

        A coleção voxdm_episodic é gravada pelo session_writer ao fim de cada sessão.
        Se a coleção ainda não existe (primeira sessão), retorna lista vazia.

        Args:
            query: Texto da query — geralmente a transcrição do jogador.
            top_k: Máximo de resultados.
            session_id_filtro: Se fornecido, filtra por uma sessão específica.

        Returns:
            Lista de chunks de memória episódica, ou [] se coleção ausente.
        """
        try:
            filtro = {"session_id": session_id_filtro} if session_id_filtro else None
            resultados = await self._qdrant.buscar(
                query=query,
                colecao=_COLECAO,
                top_k=top_k,
                filtro=filtro,
            )
            log.info("episodic_memory_busca", query_resumida=query[:60], encontrados=len(resultados))
            return resultados
        except Exception as e:
            # Coleção ausente na primeira sessão é esperado — não é erro
            log.info("episodic_memory_ausente", motivo=str(e))
            return []

    async def buscar_por_npc(self, npc_id: str, top_k: int = 2) -> list[dict[str, Any]]:
        """
        Recupera memórias que mencionam um NPC específico.

        Útil para o mestre lembrar interações passadas com o personagem.
        """
        try:
            return await self._qdrant.buscar(
                query=npc_id,
                colecao=_COLECAO,
                top_k=top_k,
                filtro={"npcs_mencionados": npc_id},
            )
        except Exception:
            return []

    async def listar_sessoes(self) -> list[str]:
        """
        Retorna lista de session_ids disponíveis na memória episódica.

        Baseado em scroll simples da coleção — não usa embedding.
        """
        try:
            from qdrant_client import QdrantClient
            from config import settings

            client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

            import asyncio
            loop = asyncio.get_event_loop()
            pontos, _ = await loop.run_in_executor(
                None,
                lambda: client.scroll(
                    collection_name=_COLECAO,
                    limit=100,
                    with_payload=True,
                    with_vectors=False,
                ),
            )

            sessoes = list({
                str(p.payload.get("session_id", ""))
                for p in pontos
                if p.payload and p.payload.get("session_id")
            })
            return sorted(sessoes)
        except Exception:
            return []
