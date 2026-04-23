"""
Dashboard Streamlit de debug do VoxDM.

Por que existe: visibilidade em tempo real de conexões, métricas de latência
    e estado da working memory durante desenvolvimento e gravações de YouTube.
Dependências: streamlit, qdrant-client, neo4j, groq, structlog, config
Armadilha: não expor em produção sem settings.DEBUG — o dashboard acessa
    dados internos da sessão sem autenticação.

Exemplo:
    streamlit run dashboard.py
"""

import asyncio
import time
from typing import Any

import streamlit as st

from config import settings

st.set_page_config(page_title="VoxDM Debug", page_icon="🎲", layout="wide")
st.title("VoxDM — Dashboard de Debug")

if not settings.DEBUG:
    st.warning("DEBUG=False no .env — ative para habilitar o dashboard completo.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rodar(coro) -> Any:
    """Executa coroutine síncrona a partir do Streamlit."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=10)
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)


# ── Painel: Conexões ──────────────────────────────────────────────────────────

st.header("Conexões")
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Groq")
    if st.button("Testar Groq"):
        inicio = time.perf_counter()
        try:
            from engine.llm.groq_client import GroqClient
            async def _ping_groq():
                c = GroqClient()
                return await c.completar(
                    [{"role": "user", "content": "responda só: OK"}],
                    max_tokens=5,
                )
            r = _rodar(_ping_groq())
            ms = int((time.perf_counter() - inicio) * 1000)
            st.success(f"OK — {ms}ms")
            st.caption(r[:100])
        except Exception as e:
            st.error(str(e))

with col2:
    st.subheader("Qdrant")
    if st.button("Testar Qdrant"):
        inicio = time.perf_counter()
        try:
            from qdrant_client import QdrantClient
            client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
            colecoes = [c.name for c in client.get_collections().collections]
            ms = int((time.perf_counter() - inicio) * 1000)
            st.success(f"OK — {ms}ms")
            st.caption(f"Coleções: {', '.join(colecoes) or 'nenhuma'}")
        except Exception as e:
            st.error(str(e))

with col3:
    st.subheader("Neo4j")
    if st.button("Testar Neo4j"):
        inicio = time.perf_counter()
        try:
            async def _ping_neo4j():
                from engine.memory.neo4j_client import Neo4jMemoryClient
                async with Neo4jMemoryClient() as c:
                    return await c.buscar_npcs_no_local("aldeia-valdrek")
            npcs = _rodar(_ping_neo4j())
            ms = int((time.perf_counter() - inicio) * 1000)
            st.success(f"OK — {ms}ms")
            st.caption(f"NPCs em aldeia-valdrek: {len(npcs)}")
        except Exception as e:
            st.error(str(e))


# ── Painel: Busca Semântica ───────────────────────────────────────────────────

st.divider()
st.header("Busca Semântica — Módulo")

query_input = st.text_input("Query de teste", placeholder="onde está Fael?")
top_k = st.slider("top_k", 1, 10, 5)

if st.button("Buscar") and query_input:
    with st.spinner("Buscando..."):
        inicio = time.perf_counter()
        try:
            from engine.memory.qdrant_client import QdrantMemoryClient
            async def _buscar():
                c = QdrantMemoryClient()
                return await c.buscar_modulo(query_input, top_k=top_k)
            resultados = _rodar(_buscar())
            ms = int((time.perf_counter() - inicio) * 1000)
            st.success(f"{len(resultados)} resultados em {ms}ms")
            for i, chunk in enumerate(resultados, 1):
                with st.expander(f"#{i} [{chunk.get('source_type','?')}] {chunk.get('source_name', chunk.get('source_id',''))} — score: {chunk.get('_score', 0):.3f}"):
                    st.write(chunk.get("text", ""))
        except Exception as e:
            st.error(str(e))


# ── Painel: Sessões Episódicas ────────────────────────────────────────────────

st.divider()
st.header("Memória Episódica")

if st.button("Listar sessões gravadas"):
    try:
        from engine.memory.episodic_memory import EpisodicMemory
        async def _listar():
            m = EpisodicMemory()
            return await m.listar_sessoes()
        sessoes = _rodar(_listar())
        if sessoes:
            st.write(sessoes)
        else:
            st.info("Nenhuma sessão gravada ainda — feche uma sessão com session_writer primeiro.")
    except Exception as e:
        st.error(str(e))


# ── Painel: Config ────────────────────────────────────────────────────────────

st.divider()
with st.expander("Configuração atual (settings)"):
    st.json({
        "GROQ_MODEL": settings.GROQ_MODEL,
        "STT_MODEL": settings.STT_MODEL,
        "STT_DEVICE": settings.STT_DEVICE,
        "TTS_VOICE_PTBR": settings.TTS_VOICE_PTBR,
        "QDRANT_URL": settings.QDRANT_URL,
        "NEO4J_URI": settings.NEO4J_URI,
        "DEFAULT_MODULE_PATH": settings.DEFAULT_MODULE_PATH,
        "DEBUG": settings.DEBUG,
        "LOG_LEVEL": settings.LOG_LEVEL,
    })
