"""
Recuperação de memórias de sessões anteriores armazenadas no Qdrant — por dono.

Por que existe: o mestre precisa de continuidade entre sessões — referências
    a eventos passados, NPCs mortos, promessas feitas. Essa camada busca
    resumos de sessões anteriores gravados pelo session_writer.
Dependências: engine/memory/qdrant_client, engine/auth/identity, structlog
Armadilha: a coleção "voxdm_episodic" pode não existir na primeira sessão —
    tratar a ausência silenciosamente (retorna lista vazia, não levanta exceção).
Armadilha: TODO método recebe `Owner` como primeiro argumento posicional e
    obrigatório. O `try/except` que engole coleção ausente NÃO pode engolir
    `DonoObrigatorio` — chamar sem dono é bug de programação e tem que subir,
    não virar "sem memórias".

Exemplo:
    mem = EpisodicMemory()
    dono = Owner(email="jogador@example.com")
    eventos = await mem.buscar(dono, "o que aconteceu com Bjorn?", top_k=3)
    # → [{"text": "Na sessão 2, Bjorn foi capturado...", "session_id": "sess-02", ...}]
"""

from typing import Any

import structlog

from engine.auth.identity import Owner, exigir_dono
from engine.memory.qdrant_client import QdrantMemoryClient

log = structlog.get_logger()

# Campos de METADADO de uma entrada episódica — o que um admin pode ver da
# sessão de outra pessoa. O resto (resumo, dm_state, companions, confiança,
# quests) é CONTEÚDO de narrativa e não sai daqui sem ser do dono.
_CAMPOS_METADADO: tuple[str, ...] = (
    "session_id", "owner_email", "timestamp", "location_final", "player_level",
)


class EpisodicMemory:
    """
    Recupera memórias de sessões anteriores do Qdrant, sempre de UM dono.

    Instanciar uma vez por sessão e reutilizar — o cliente mantém conexão.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()

    async def buscar(
        self,
        owner: Owner,
        query: str,
        top_k: int = 3,
        session_id_filtro: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Busca memórias episódicas deste dono relevantes para a query atual.

        Se a coleção ainda não existe (primeira sessão), retorna lista vazia.

        Args:
            owner: Dono das memórias — obrigatório.
            query: Texto da query — geralmente a transcrição do jogador.
            top_k: Máximo de resultados.
            session_id_filtro: Se fornecido, filtra por uma sessão específica.

        Returns:
            Lista de chunks de memória episódica, ou [] se coleção ausente.
        """
        exigir_dono(owner)  # fora do try: sem dono é erro, não "coleção ausente"
        try:
            filtro = {"session_id": session_id_filtro} if session_id_filtro else None
            resultados = await self._qdrant.buscar_memoria(
                owner, query, top_k=top_k, filtro=filtro,
            )
            log.info("episodic_memory_busca", query_resumida=query[:60], encontrados=len(resultados))
            return resultados
        except Exception as e:
            # Coleção ausente na primeira sessão é esperado — não é erro
            log.info("episodic_memory_ausente", motivo=str(e))
            return []

    async def buscar_por_npc(
        self, owner: Owner, npc_id: str, top_k: int = 2
    ) -> list[dict[str, Any]]:
        """
        Recupera memórias deste dono que mencionam um NPC específico.

        Útil para o mestre lembrar interações passadas com o personagem.
        """
        exigir_dono(owner)
        try:
            return await self._qdrant.buscar_memoria(
                owner, npc_id, top_k=top_k, filtro={"npcs_mencionados": npc_id},
            )
        except Exception as e:
            log.info("episodic_buscar_por_npc_falhou", npc_id=npc_id, motivo=str(e))
            return []

    async def listar_sessoes(self, owner: Owner) -> list[str]:
        """
        Retorna os session_ids deste dono presentes na memória episódica.

        Baseado em scroll da coleção — não usa embedding.
        """
        exigir_dono(owner)
        try:
            payloads = await self._qdrant.listar_memoria(owner, limite=100)
        except Exception as e:
            log.info("episodic_listar_sessoes_ausente", motivo=str(e))
            return []
        return sorted({
            str(p.get("session_id", "")) for p in payloads if p.get("session_id")
        })

    async def listar_com_metadata(self, owner: Owner) -> list[dict[str, Any]]:
        """
        Sessões DESTE dono com metadados para o seletor de sessão.

        Para cada session_id, retorna o ponto mais recente com:
        session_id, timestamp, location_final, npcs_mencionados, resumo_curto.
        Ordenado por timestamp descendente (mais recente primeiro).
        """
        exigir_dono(owner)
        try:
            payloads = await self._qdrant.listar_memoria(owner, limite=200)
        except Exception as e:
            log.info("episodic_listar_metadata_ausente", motivo=str(e))
            return []

        # Agrupa por session_id, mantém ponto mais recente por sessão
        por_sessao: dict[str, dict[str, Any]] = {}
        for payload in payloads:
            sid = str(payload.get("session_id", ""))
            if not sid:
                continue
            ts = float(payload.get("timestamp", 0))
            existente = por_sessao.get(sid)
            if existente is None or ts > existente["timestamp"]:
                texto = str(payload.get("text", ""))
                por_sessao[sid] = {
                    "session_id": sid,
                    "owner_email": str(payload.get("owner_email", "")),
                    "timestamp": ts,
                    "location_final": str(payload.get("location_final", "")),
                    "npcs_mencionados": list(payload.get("npcs_mencionados", [])),
                    "resumo_curto": texto[:200],
                    # Campos novos — restauração de continuidade
                    "player_level": int(payload.get("player_level", 1)),
                    "xp": int(payload.get("xp", 0)),
                    "gold": int(payload.get("gold", 0)),
                    "companions": dict(payload.get("companions", {})),
                    "dm_state": payload.get("dm_state", {}) or {},
                }

        resultado = sorted(por_sessao.values(), key=lambda x: x["timestamp"], reverse=True)
        log.info("episodic_listar_metadata", total_sessoes=len(resultado))
        return resultado

    async def buscar_por_session_id(
        self, owner: Owner, session_id: str
    ) -> dict[str, Any] | None:
        """
        Recupera a entrada episódica mais recente de uma sessão DESTE dono.

        Usado para restaurar trust_levels, quest_stages, dm_state e companions ao
        continuar uma sessão. Sessão de outro dono devolve None — idêntico a
        "não existe", de propósito: não se confirma a existência de dado alheio.

        Armadilha: é scroll com filtro exato, NÃO busca semântica — o session_id
        (UUID-like) não tem similaridade com o texto do resumo, e com o
        score_threshold padrão a busca sempre voltaria vazia.
        """
        exigir_dono(owner)
        try:
            payloads = await self._qdrant.listar_memoria(
                owner, filtro={"session_id": session_id}, limite=10,
            )
        except Exception as e:
            log.info("episodic_buscar_por_session_id_falhou", session_id=session_id, motivo=str(e))
            return None
        if not payloads:
            return None
        # Retorna o ponto mais recente (maior timestamp)
        return max(payloads, key=lambda p: float(p.get("timestamp", 0)))


def so_metadado(entrada: dict[str, Any]) -> dict[str, Any]:
    """Reduz uma entrada episódica aos campos de METADADO.

    É o que sobra quando quem olha não é o dono: existe, de quem é, quando,
    onde parou, em que nível. Nada de resumo, fios, companions ou confiança.
    """
    return {k: entrada[k] for k in _CAMPOS_METADADO if k in entrada}
