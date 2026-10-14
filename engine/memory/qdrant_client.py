"""
Cliente Qdrant — acervo compartilhado de um lado, memória de jogo por dono do outro.

Por que existe: encapsula queries ao Qdrant Cloud com retry e embedding
    automático, e é o ÚNICO lugar que monta o filtro de dono. Acervo (módulo
    publicado, regras do SRD, bestiário) é o mesmo para todo mundo e não tem
    dono; memória de jogo (resumo episódico de sessão) é de quem jogou, e não
    existe método que a consulte sem um `Owner`.
Dependências: qdrant-client, sentence-transformers, tenacity, structlog, config
Armadilha: QdrantClient é síncrono — toda chamada roda em executor para não
    bloquear o loop asyncio. Não chamar métodos síncronos diretamente em async.
Armadilha: o filtro de dono é montado AQUI DENTRO, a partir do `Owner`, e
    combinado por `must` com o filtro do caller. O caller não consegue
    removê-lo nem sobrescrevê-lo: `owner_email` no filtro dele levanta erro.
    Não abra um `buscar()` genérico de novo — foi por ele que o episódico
    caía todo no mesmo balde (achado do P11).

Exemplo:
    cliente = QdrantMemoryClient()
    lore = await cliente.buscar_modulo("onde está Fael?", top_k=5)
    # → [{"text": "Fael Valdreksson encontra-se...", "source_id": "fael-valdreksson", ...}]
    dono = Owner(email="jogador@example.com")
    memorias = await cliente.buscar_memoria(dono, "o que houve com Bjorn?")
    # → só pontos cujo payload tem owner_email == "jogador@example.com"
"""

import asyncio
import functools
from typing import Any

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    KeywordIndexParams,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    VectorParams,
)
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from engine.auth.identity import Owner, emails_visiveis, exigir_dono
from ingestor.embedder import Embedder

# Campo de payload que carrega o dono — a chave de tenant da coleção.
CAMPO_DONO: str = "owner_email"

# Memória de JOGO: uma coleção só, particionada por dono no payload (padrão de
# multitenancy do próprio Qdrant). Coleção por usuário não escala e o free tier
# limita o número de coleções.
COLECAO_EPISODICA: str = "voxdm_episodic"
COLECOES_MEMORIA: frozenset[str] = frozenset({COLECAO_EPISODICA})


def colecoes_acervo() -> frozenset[str]:
    """Coleções de acervo compartilhado — as únicas consultáveis sem dono.

    Função (e não constante) porque dois nomes vêm do settings, e teste troca
    settings em runtime.
    """
    return frozenset({
        "voxdm_modules",
        settings.QDRANT_COLECAO_RULES,
        settings.QDRANT_COLECAO_BESTIARY,
    })


def _nao_e_404(exc: BaseException | None) -> bool:
    """Não faz retry em 404 — coleção ausente não vai aparecer sozinha."""
    return "Not found" not in str(exc) and "404" not in str(exc)


log = structlog.get_logger()


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "qdrant_busca_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


def _condicoes_do_caller(filtro: dict[str, Any] | None) -> list[FieldCondition]:
    """Converte o filtro do caller em condições `must`. Recusa mexer no dono."""
    if not filtro:
        return []
    if CAMPO_DONO in filtro:
        raise ValueError(
            f"'{CAMPO_DONO}' não pode vir no filtro do caller — o dono é montado "
            "pelo cliente a partir do Owner"
        )
    return [FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filtro.items()]


def filtro_de_dono(owner: Owner, filtro: dict[str, Any] | None = None) -> Filter:
    """Filtro Qdrant que restringe ao dono, somado ao filtro do caller.

    Não-admin: só o próprio email. Admin: o próprio + a marca de legado (legado
    é admin-only). Nunca o dado de outro jogador.
    """
    visiveis = emails_visiveis(owner)
    condicao_dono = (
        FieldCondition(key=CAMPO_DONO, match=MatchValue(value=visiveis[0]))
        if len(visiveis) == 1
        else FieldCondition(key=CAMPO_DONO, match=MatchAny(any=visiveis))
    )
    return Filter(must=[condicao_dono, *_condicoes_do_caller(filtro)])


class QdrantMemoryClient:
    """Busca semântica no Qdrant com embedding automático e retry."""

    def __init__(self) -> None:
        self._client: QdrantClient | None = None
        self._embedder: Embedder | None = None
        # Coleções de memória cuja existência + índices já foram garantidos por
        # esta instância — evita três round-trips a cada gravação.
        self._memoria_garantida: set[str] = set()

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            # check_compatibility=False silencia o UserWarning do qdrant-client
            # ao falhar GET /version no Qdrant Cloud (rota não exposta no free tier).
            # O check é apenas informativo — desligar não afeta queries.
            self._client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                check_compatibility=False,
            )
        return self._client

    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    @retry(
        retry=lambda rs: retry_if_exception_type(Exception)(rs)
        and _nao_e_404(rs.outcome.exception() if rs.outcome else None),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    def _buscar_sync(
        self,
        vetor: list[float],
        colecao: str,
        top_k: int,
        query_filter: Filter | None,
        score_threshold: float,
    ) -> list[ScoredPoint]:
        """Busca síncrona com retry — executada em thread pool."""
        resultado = self._get_client().query_points(
            collection_name=colecao,
            query=vetor,
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
        return list(resultado.points)

    # Score mínimo de cosseno para aceitar um chunk como relevante.
    # Chunks abaixo deste limiar são descartados — evita poluir o prompt
    # com conteúdo tangencialmente relacionado à query.
    # Calibrado empiricamente para paraphrase-multilingual-MiniLM-L12-v2.
    SCORE_THRESHOLD_DEFAULT: float = 0.45

    async def _vetor_de(self, texto: str, modo: str) -> list[float]:
        """Embedding em executor — sentence-transformers bloqueia CPU por 200-500ms."""
        embedder = self._get_embedder()
        loop = asyncio.get_running_loop()
        vetor_array = await loop.run_in_executor(
            None, functools.partial(embedder.gerar, [texto], modo=modo)
        )
        return vetor_array[0].tolist()

    async def _buscar(
        self,
        query: str,
        colecao: str,
        top_k: int,
        query_filter: Filter | None,
        score_threshold: float | None,
    ) -> list[dict[str, Any]]:
        """Núcleo da busca — PRIVADO. As portas públicas decidem o filtro."""
        threshold = score_threshold if score_threshold is not None else self.SCORE_THRESHOLD_DEFAULT
        # modo="query": a família E5 distingue pergunta de documento (ver
        # _EXIGE_PREFIXO_E5 no embedder). Sem isso, a busca degrada.
        vetor = await self._vetor_de(query, modo="query")
        loop = asyncio.get_running_loop()
        resultados = await loop.run_in_executor(
            None, self._buscar_sync, vetor, colecao, top_k, query_filter, threshold
        )

        chunks: list[dict[str, Any]] = []
        for ponto in resultados:
            payload = dict(ponto.payload or {})
            payload["_score"] = round(float(ponto.score), 4)
            chunks.append(payload)

        log.info(
            "qdrant_busca_concluida",
            colecao=colecao,
            query_resumida=query[:60],
            resultados=len(chunks),
            threshold=threshold,
        )
        return chunks

    # ── ACERVO — compartilhado, sem dono ─────────────────────────────────────

    async def buscar_acervo(
        self,
        query: str,
        colecao: str,
        top_k: int = 5,
        filtro: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Busca em coleção de ACERVO (módulo, regras, bestiário) — sem dono.

        Recusa qualquer coleção fora do acervo: apontar esta porta para a
        memória de jogo seria exatamente a consulta sem dono que não pode existir.

        Args:
            query: Texto da pergunta ou contexto da busca.
            colecao: Coleção de acervo (ex: "voxdm_modules", "voxdm_rules").
            top_k: Número máximo de resultados.
            filtro: Filtro por campo de payload (ex: {"source_type": "npc"}).
            score_threshold: Score mínimo (0-1). None usa SCORE_THRESHOLD_DEFAULT.

        Returns:
            Lista de dicts com payload + score de cada resultado.
        """
        if colecao not in colecoes_acervo():
            raise ValueError(
                f"'{colecao}' não é coleção de acervo — memória de jogo só por "
                "buscar_memoria(owner, ...)"
            )
        condicoes = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in (filtro or {}).items()
        ]
        query_filter = Filter(must=condicoes) if condicoes else None
        return await self._buscar(query, colecao, top_k, query_filter, score_threshold)

    async def buscar_modulo(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Atalho para busca na coleção de módulos (acervo)."""
        return await self.buscar_acervo(query, colecao="voxdm_modules", top_k=top_k)

    async def buscar_regras(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Atalho para busca na coleção de regras SRD (acervo)."""
        return await self.buscar_acervo(
            query, colecao=settings.QDRANT_COLECAO_RULES, top_k=top_k
        )

    # ── MEMÓRIA DE JOGO — sempre por dono ────────────────────────────────────

    @staticmethod
    def _exigir_colecao_memoria(colecao: str) -> None:
        if colecao not in COLECOES_MEMORIA:
            raise ValueError(f"'{colecao}' não é coleção de memória de jogo")

    async def buscar_memoria(
        self,
        owner: Owner,
        query: str,
        top_k: int = 3,
        filtro: dict[str, Any] | None = None,
        score_threshold: float | None = None,
        colecao: str = COLECAO_EPISODICA,
    ) -> list[dict[str, Any]]:
        """Busca semântica na memória de jogo DESTE dono.

        O filtro de dono entra por `must` junto do filtro do caller; não há
        argumento que o desligue.
        """
        self._exigir_colecao_memoria(colecao)
        query_filter = filtro_de_dono(owner, filtro)
        return await self._buscar(query, colecao, top_k, query_filter, score_threshold)

    async def listar_memoria(
        self,
        owner: Owner,
        filtro: dict[str, Any] | None = None,
        limite: int = 200,
        colecao: str = COLECAO_EPISODICA,
    ) -> list[dict[str, Any]]:
        """Payloads da memória de jogo deste dono, sem embedding (scroll)."""
        self._exigir_colecao_memoria(colecao)
        query_filter = filtro_de_dono(owner, filtro)
        loop = asyncio.get_running_loop()
        pontos, _ = await loop.run_in_executor(
            None,
            lambda: self._get_client().scroll(
                collection_name=colecao,
                scroll_filter=query_filter,
                limit=limite,
                with_payload=True,
                with_vectors=False,
            ),
        )
        return [dict(p.payload) for p in pontos if p.payload]

    def _garantir_colecao_memoria_sync(self, colecao: str, dim: int) -> None:
        """Cria coleção + índices se faltarem. Idempotente; síncrono (executor)."""
        client = self._get_client()
        if not client.collection_exists(colecao):
            client.create_collection(
                collection_name=colecao,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            log.info("colecao_memoria_criada", colecao=colecao, dim=dim)
        # Índice de tenant no dono: o Qdrant co-localiza os pontos de cada dono
        # e o filtro por dono deixa de varrer a coleção. Sem índice, filtro em
        # Qdrant Cloud devolve 400 "Index required but not found".
        client.create_payload_index(
            collection_name=colecao,
            field_name=CAMPO_DONO,
            field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
        )
        client.create_payload_index(
            collection_name=colecao,
            field_name="session_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

    async def garantir_colecao_memoria(
        self, dim: int, colecao: str = COLECAO_EPISODICA
    ) -> None:
        """Garante coleção de memória + índice de tenant em `owner_email`."""
        self._exigir_colecao_memoria(colecao)
        if colecao in self._memoria_garantida:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._garantir_colecao_memoria_sync, colecao, dim
        )
        self._memoria_garantida.add(colecao)

    async def gravar_memoria(
        self,
        owner: Owner,
        ponto_id: str,
        texto: str,
        payload: dict[str, Any],
        colecao: str = COLECAO_EPISODICA,
    ) -> None:
        """Grava um ponto na memória de jogo, carimbado com o dono.

        O `owner_email` do payload é SEMPRE o do `Owner` recebido — o que vier
        no dict é sobrescrito. Sem dono válido, levanta `DonoObrigatorio` antes
        de tocar a rede.
        """
        self._exigir_colecao_memoria(colecao)
        email = exigir_dono(owner)
        vetor = await self._vetor_de(texto, modo="passage")
        await self.garantir_colecao_memoria(len(vetor), colecao)
        ponto = PointStruct(
            id=ponto_id, vector=vetor, payload={**payload, CAMPO_DONO: email}
        )
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._get_client().upsert(collection_name=colecao, points=[ponto]),
        )
        log.info("memoria_gravada", colecao=colecao, ponto_id=ponto_id)
