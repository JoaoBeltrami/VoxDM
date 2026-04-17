"""
Testa conectividade com todos os serviços externos do VoxDM.

Por que existe: verificação rápida de que Groq, Qdrant e Neo4j estão acessíveis
    antes de rodar a pipeline — evita falhas silenciosas no meio do processo.
Dependências: groq, qdrant-client, neo4j, structlog
Armadilha: Neo4j AuraDB usa o ID da instância como username (ex: 54b6147b),
    não "neo4j" — verifique NEO4J_USER no .env.

Exemplo:
    uv run connection_test.py
    # → [OK] Groq | [OK] Qdrant | [OK] Neo4j
"""

import asyncio
import sys

import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger("connection-test")

from config import settings


async def _testar_groq() -> bool:
    """Envia uma mensagem mínima ao Groq e verifica resposta."""
    try:
        from groq import AsyncGroq

        cliente = AsyncGroq(api_key=settings.GROQ_API_KEY)
        resposta = await cliente.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        conteudo = resposta.choices[0].message.content or ""
        log.info("[OK] Groq", modelo=settings.GROQ_MODEL, resposta=conteudo.strip())
        return True
    except Exception as exc:
        log.error("[FALHA] Groq", erro=str(exc))
        return False


async def _testar_qdrant() -> bool:
    """Lista coleções do Qdrant Cloud."""
    try:
        from qdrant_client import QdrantClient

        cliente = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
        )
        colecoes = cliente.get_collections()
        nomes = [c.name for c in colecoes.collections]
        log.info("[OK] Qdrant", colecoes=nomes or "(nenhuma)")
        return True
    except Exception as exc:
        log.error("[FALHA] Qdrant", erro=str(exc))
        return False


async def _testar_neo4j() -> bool:
    """Executa query mínima no Neo4j AuraDB."""
    try:
        from neo4j import AsyncGraphDatabase

        driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        async with driver.session() as sessao:
            resultado = await sessao.run("RETURN 1 AS ok")
            registro = await resultado.single()
            ok = registro["ok"] if registro else None
        await driver.close()

        if ok == 1:
            log.info("[OK] Neo4j", uri=settings.NEO4J_URI, user=settings.NEO4J_USER)
            return True
        else:
            log.error("[FALHA] Neo4j", motivo="query retornou valor inesperado", valor=ok)
            return False
    except Exception as exc:
        log.error("[FALHA] Neo4j", erro=str(exc))
        return False


async def main() -> None:
    log.info("Testando conectividade VoxDM...")

    resultados = await asyncio.gather(
        _testar_groq(),
        _testar_qdrant(),
        _testar_neo4j(),
    )

    nomes = ["Groq", "Qdrant", "Neo4j"]
    total_ok = sum(resultados)
    total = len(resultados)

    print("\n" + "=" * 50)
    print(f"RESULTADO: {total_ok}/{total} serviços OK")
    for nome, ok in zip(nomes, resultados):
        status = "[OK]" if ok else "[FALHA]"
        print(f"  {status} {nome}")
    print("=" * 50 + "\n")

    if total_ok < total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
