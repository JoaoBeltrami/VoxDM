"""
Endpoint de saúde profunda — pinga Qdrant, Neo4j e Groq em paralelo.

Por que existe: o `/health` simples só confirma que o processo subiu. Antes de
    qualquer deploy ou gravação ao vivo, precisamos saber se as três dependências
    externas estão respondendo. Esse endpoint mede latência e status de cada uma,
    sem segredos no payload.
Dependências: asyncio, httpx, qdrant-client, neo4j (todos já no requirements)
Armadilha: timeout curto (3s) por dependência para o endpoint não virar gargalo.
    Em caso de timeout, retornamos "down" — não estouramos exceção.

Exemplo:
    GET /health/deps →
    {
      "status": "ok",
      "checked_at": 1715459200.42,
      "deps": {
        "qdrant": {"status": "ok",   "latency_ms": 124, "detalhe": "2 coleções"},
        "neo4j":  {"status": "ok",   "latency_ms":  98, "detalhe": "n.id index ok"},
        "groq":   {"status": "ok",   "latency_ms": 210, "detalhe": "llama-3.3-70b-versatile"}
      }
    }
"""

import asyncio
import time
from typing import Any

import structlog
from fastapi import APIRouter

from config import settings

log = structlog.get_logger()
router = APIRouter(tags=["infra"])

# Timeout por dependência — endpoint inteiro não deve passar de ~3.5s
_TIMEOUT_DEP_SECONDS: float = 3.0


async def _check_qdrant() -> dict[str, Any]:
    """Lista coleções no Qdrant. Sucesso se a chamada retorna < 3s."""
    t0 = time.perf_counter()
    try:
        from qdrant_client import QdrantClient
        loop = asyncio.get_running_loop()

        def _sync_check() -> int:
            client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                timeout=int(_TIMEOUT_DEP_SECONDS),
            )
            resposta = client.get_collections()
            return len(resposta.collections)

        total = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_check),
            timeout=_TIMEOUT_DEP_SECONDS,
        )
        return {
            "status": "ok",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "detalhe": f"{total} coleção(ões)",
        }
    except TimeoutError:
        return {"status": "timeout", "latency_ms": int(_TIMEOUT_DEP_SECONDS * 1000), "detalhe": f"sem resposta em {_TIMEOUT_DEP_SECONDS}s"}
    except Exception as e:
        return {"status": "down", "latency_ms": int((time.perf_counter() - t0) * 1000), "detalhe": str(e)[:160]}


async def _check_neo4j() -> dict[str, Any]:
    """Roda `RETURN 1 AS ok` no Neo4j. Confirma driver + auth + rede."""
    t0 = time.perf_counter()
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        try:
            async def _run() -> int:
                async with driver.session() as sess:
                    result = await sess.run("RETURN 1 AS ok")
                    record = await result.single()
                    return int(record["ok"]) if record else 0

            valor = await asyncio.wait_for(_run(), timeout=_TIMEOUT_DEP_SECONDS)
        finally:
            await driver.close()

        if valor == 1:
            return {
                "status": "ok",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "detalhe": "RETURN 1 OK",
            }
        return {"status": "down", "latency_ms": int((time.perf_counter() - t0) * 1000), "detalhe": "query não retornou 1"}
    except TimeoutError:
        return {"status": "timeout", "latency_ms": int(_TIMEOUT_DEP_SECONDS * 1000), "detalhe": f"sem resposta em {_TIMEOUT_DEP_SECONDS}s"}
    except Exception as e:
        return {"status": "down", "latency_ms": int((time.perf_counter() - t0) * 1000), "detalhe": str(e)[:160]}


async def _check_groq() -> dict[str, Any]:
    """Lista modelos via HTTP — não consome tokens, só valida a API key."""
    t0 = time.perf_counter()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_TIMEOUT_DEP_SECONDS) as client:
            resp = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            )
            if resp.status_code == 200:
                return {
                    "status": "ok",
                    "latency_ms": int((time.perf_counter() - t0) * 1000),
                    "detalhe": settings.GROQ_MODEL,
                }
            return {
                "status": "down",
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "detalhe": f"HTTP {resp.status_code}",
            }
    except TimeoutError:
        return {"status": "timeout", "latency_ms": int(_TIMEOUT_DEP_SECONDS * 1000), "detalhe": f"sem resposta em {_TIMEOUT_DEP_SECONDS}s"}
    except Exception as e:
        return {"status": "down", "latency_ms": int((time.perf_counter() - t0) * 1000), "detalhe": str(e)[:160]}


@router.get("/health/deps")
async def health_deps() -> dict[str, Any]:
    """Pinga Qdrant, Neo4j e Groq em paralelo e retorna estado de cada um."""
    t0 = time.perf_counter()
    qdrant_r, neo4j_r, groq_r = await asyncio.gather(
        _check_qdrant(),
        _check_neo4j(),
        _check_groq(),
        return_exceptions=False,
    )

    deps = {"qdrant": qdrant_r, "neo4j": neo4j_r, "groq": groq_r}
    # Agregado: ok se todas OK; degraded se alguma não-ok mas pelo menos uma OK; down se todas fora
    statuses = [d["status"] for d in deps.values()]
    if all(s == "ok" for s in statuses):
        agregado = "ok"
    elif any(s == "ok" for s in statuses):
        agregado = "degraded"
    else:
        agregado = "down"

    total_ms = int((time.perf_counter() - t0) * 1000)
    log.info("health_deps_check", agregado=agregado, total_ms=total_ms, **{
        f"{k}_status": v["status"] for k, v in deps.items()
    })
    return {
        "status": agregado,
        "checked_at": time.time(),
        "total_ms": total_ms,
        "deps": deps,
    }
