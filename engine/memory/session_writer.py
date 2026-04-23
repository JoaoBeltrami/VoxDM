"""
Comprime e persiste uma sessão ao final — ponte entre sessões do VoxDM.

Por que existe: ao encerrar a sessão, o diálogo completo é resumido via Groq
    e gravado no Qdrant (coleção voxdm_episodic). Na próxima sessão, o
    context_builder recupera esse resumo como memória episódica.
Dependências: engine/llm/groq_client, engine/memory/{working_memory,qdrant_client}
    ingestor/embedder, structlog, config
Armadilha: o resumo usa Groq — se indisponível, gravar o diálogo bruto truncado
    em vez de falhar silenciosamente.

Exemplo:
    writer = SessionWriter()
    resumo = await writer.fechar_sessao(working_mem, session_id="sess-02")
    # → {"session_id": "sess-02", "resumo": "O grupo chegou à aldeia...",
    #    "trust_levels": {"fael-valdreksson": 3}, "quest_stages": {...}}
"""

import time
import uuid
from typing import Any

import structlog

from config import settings
from engine.llm.groq_client import GroqClient
from engine.memory.working_memory import WorkingMemory
from engine.memory.qdrant_client import QdrantMemoryClient

log = structlog.get_logger()

_COLECAO = "voxdm_episodic"

# Máximo de caracteres do diálogo passado ao Groq para resumo
_MAX_DIALOGO_CHARS = 6000

_PROMPT_RESUMO = """\
Você é um assistente que resume sessões de RPG de mesa de forma compacta.
Dado o diálogo e estado abaixo, gere um parágrafo de 3-5 frases em português
brasileiro descrevendo: o que aconteceu, quais NPCs foram encontrados e como
a relação com eles evoluiu, e que quests avançaram.
Seja factual e narrativo — sem opiniões, sem listas.

Estado da sessão:
{estado}

Diálogo da sessão:
{dialogo}
"""


def _montar_dialogo(working_mem: WorkingMemory) -> str:
    """Formata o diálogo recente da working memory como texto simples."""
    linhas: list[str] = []
    for turno in working_mem.dialogo_recente:
        prefixo = "Jogador" if turno.falante == "player" else turno.falante
        linhas.append(f"{prefixo}: {turno.texto}")
    return "\n".join(linhas)


async def _resumir_via_groq(working_mem: WorkingMemory) -> str:
    """Gera resumo narrativo da sessão usando Groq. Fallback: diálogo bruto."""
    dialogo = _montar_dialogo(working_mem)[:_MAX_DIALOGO_CHARS]
    estado = working_mem.para_texto()

    prompt = _PROMPT_RESUMO.format(estado=estado, dialogo=dialogo)
    mensagens = [{"role": "user", "content": prompt}]

    try:
        groq = GroqClient()
        resumo = await groq.completar(mensagens, temperatura=0.4, max_tokens=512)
        log.info("resumo_gerado_groq", chars=len(resumo))
        return resumo
    except Exception as e:
        log.warning("resumo_groq_falhou_usando_dialogo", erro=str(e))
        # Fallback: primeiros 1000 chars do diálogo bruto
        return dialogo[:1000] if dialogo else "Sessão sem diálogo registrado."


class SessionWriter:
    """
    Serializa e persiste o estado de uma sessão ao final.

    Uso típico: instanciar uma vez, chamar fechar_sessao() ao término.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()

    async def fechar_sessao(
        self,
        working_mem: WorkingMemory,
        session_id: str | None = None,
        npcs_mencionados: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Resumo + upsert no Qdrant. Retorna o dict de estado persistido.

        Args:
            working_mem: Estado da sessão ao momento do encerramento.
            session_id: ID da sessão (usa working_mem.session_id se omitido).
            npcs_mencionados: NPCs relevantes para indexação (usa npcs_presentes se omitido).

        Returns:
            Dict com session_id, resumo, trust_levels, quest_stages e timestamp.
        """
        sid = session_id or working_mem.session_id
        npcs = npcs_mencionados or working_mem.npcs_presentes

        resumo = await _resumir_via_groq(working_mem)

        payload: dict[str, Any] = {
            "session_id": sid,
            "text": resumo,
            "trust_levels": working_mem.trust_levels,
            "faction_standings": working_mem.faction_standings,
            "quest_stages": working_mem.quest_stages,
            "location_final": working_mem.location_id,
            "npcs_mencionados": npcs,
            "timestamp": time.time(),
            "source_type": "episodic",
            "source_id": sid,
            "source_name": f"Sessão {sid}",
        }

        await self._fazer_upsert(payload)

        log.info(
            "sessao_persistida",
            session_id=sid,
            trust_levels=working_mem.trust_levels,
            quest_stages=working_mem.quest_stages,
        )
        return payload

    async def _fazer_upsert(self, payload: dict[str, Any]) -> None:
        """Gera embedding do resumo e faz upsert no Qdrant."""
        from ingestor.embedder import Embedder
        import asyncio
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, Distance, VectorParams

        embedder = Embedder()
        vetor_array = embedder.gerar([payload["text"]])
        vetor: list[float] = vetor_array[0].tolist()
        dim = len(vetor)

        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        loop = asyncio.get_event_loop()

        # Garantir que a coleção existe (idempotente)
        try:
            await loop.run_in_executor(None, lambda: client.get_collection(_COLECAO))
        except Exception:
            await loop.run_in_executor(
                None,
                lambda: client.create_collection(
                    collection_name=_COLECAO,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                ),
            )
            log.info("colecao_episodic_criada", dim=dim)

        # ID determinístico por session_id
        ponto_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"voxdm-episodic-{payload['session_id']}"))

        ponto = PointStruct(id=ponto_id, vector=vetor, payload=payload)
        await loop.run_in_executor(
            None,
            lambda: client.upsert(collection_name=_COLECAO, points=[ponto]),
        )
        log.info("episodic_upsert_ok", ponto_id=ponto_id, colecao=_COLECAO)
