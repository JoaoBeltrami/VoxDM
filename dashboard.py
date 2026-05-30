"""
Dashboard Streamlit de debug do VoxDM.

Por que existe: visibilidade em tempo real de conexões, métricas de latência
    e estado da working memory durante desenvolvimento e gravações de YouTube.
    Aba "Modo Vídeo" exibe contexto ativo com auto-refresh para captura de tela.
Dependências: streamlit, streamlit-autorefresh, qdrant-client, neo4j, groq, config
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

if not settings.DEBUG:
    st.warning("DEBUG=False no .env — ative para habilitar o dashboard completo.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rodar(coro) -> Any:
    """Executa coroutine síncrona a partir do Streamlit.

    asyncio.get_event_loop() é deprecated no Python 3.12 — usamos try/except sobre
    get_running_loop() para detectar se já existe loop ativo (Streamlit às vezes cria).
    """
    try:
        # Se um loop já está rodando, não dá pra chamar asyncio.run direto — usa thread
        asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=15)
    except RuntimeError:
        # Sem loop ativo — caminho normal
        return asyncio.run(coro)


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_debug, tab_video, tab_ultimo, tab_decisoes = st.tabs(["Debug", "Modo Video", "Ultimo Turno", "Decisoes LLM"])


# ── Tab: Modo Vídeo ───────────────────────────────────────────────────────────

with tab_video:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=500, key="video_refresh")
    except ImportError:
        st.caption("streamlit-autorefresh nao instalado — recarregue manualmente (uv pip install streamlit-autorefresh)")

    st.markdown(
        """
        <style>
        .vox-header { font-size: 1.6rem; font-weight: 700; color: #a78bfa; margin-bottom: 0.3rem; }
        .vox-label  { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: #6b7280; }
        .vox-chunk  { font-size: 1.05rem; line-height: 1.6; padding: 0.4rem 0; border-bottom: 1px solid #2d2d3d; }
        .vox-fala   { font-size: 1.25rem; line-height: 1.5; }
        .vox-stat   { font-size: 1.5rem; font-weight: 700; }
        .vox-ok     { color: #34d399; }
        .vox-warn   { color: #f59e0b; }
        .vox-err    { color: #f87171; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    from engine.telemetry import read_latest

    historico = read_latest(n=3)
    evento = historico[-1] if historico else {}

    # ── Cabeçalho com métricas de latência ───────────────────────────────────

    st.markdown('<div class="vox-header">VoxDM — Modo Video</div>', unsafe_allow_html=True)

    mc1, mc2, mc3, mc4 = st.columns(4)

    total_ms = evento.get("total_ms", 0)
    llm_ms = evento.get("llm_ms", 0)
    pa_ms = evento.get("primeiro_audio_ms", -1)
    status = evento.get("status", "—")
    pa_str = f"{pa_ms}ms" if pa_ms >= 0 else "—"

    total_cls = "vox-ok" if total_ms < 2000 else "vox-err"
    pa_cls = "vox-ok" if 0 <= pa_ms < 1200 else ("vox-warn" if pa_ms < 0 else "vox-err")

    mc1.markdown(f'<div class="vox-label">Total</div><div class="vox-stat {total_cls}">{total_ms}ms</div>', unsafe_allow_html=True)
    mc2.markdown(f'<div class="vox-label">LLM</div><div class="vox-stat">{llm_ms}ms</div>', unsafe_allow_html=True)
    mc3.markdown(f'<div class="vox-label">1o Audio</div><div class="vox-stat {pa_cls}">{pa_str}</div>', unsafe_allow_html=True)
    mc4.markdown(f'<div class="vox-label">Status</div><div class="vox-stat {"vox-ok" if status == "OK" else "vox-err"}">{status}</div>', unsafe_allow_html=True)

    st.divider()

    # ── Falas (último ciclo) + histórico compacto ──────────────────────────────

    fa1, fa2 = st.columns([3, 2])
    with fa1:
        st.markdown('<div class="vox-label">Jogador disse</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="vox-fala">{evento.get("texto_jogador", "—")}</div>', unsafe_allow_html=True)
        st.markdown('<div class="vox-label" style="margin-top:0.8rem">Mestre respondeu</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="vox-fala">{evento.get("resposta_mestre", "—")}</div>', unsafe_allow_html=True)

    with fa2:
        st.markdown('<div class="vox-label">Historico</div>', unsafe_allow_html=True)
        anteriores = historico[:-1] if len(historico) > 1 else []
        if anteriores:
            for ev in reversed(anteriores):
                jogador = ev.get("texto_jogador", "")[:50]
                mestre = ev.get("resposta_mestre", "")[:80]
                t = ev.get("total_ms", 0)
                st.markdown(
                    f'<div class="vox-chunk" style="opacity:0.65;font-size:0.9rem">'
                    f'<span style="color:#a78bfa">#{ev.get("iteracao","?")} [{t}ms]</span> '
                    f'{jogador} → {mestre}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("historico aparece apos 2+ ciclos")

    st.divider()

    # ── 3 colunas de contexto ─────────────────────────────────────────────────

    col_r, col_l, col_g = st.columns(3)

    with col_r:
        st.markdown('<div class="vox-header">Regras</div>', unsafe_allow_html=True)
        for chunk in evento.get("chunks_regras", []):
            st.markdown(f'<div class="vox-chunk">{chunk}</div>', unsafe_allow_html=True)
        if not evento.get("chunks_regras"):
            st.caption("nenhuma regra recuperada")

    with col_l:
        st.markdown('<div class="vox-header">Lore</div>', unsafe_allow_html=True)
        for chunk in evento.get("chunks_lore", []):
            st.markdown(f'<div class="vox-chunk">{chunk}</div>', unsafe_allow_html=True)
        if not evento.get("chunks_lore"):
            st.caption("nenhum lore recuperado")

    with col_g:
        st.markdown('<div class="vox-header">Grafo</div>', unsafe_allow_html=True)
        for rel in evento.get("relacoes_grafo", []):
            nome = rel.get("alvo_nome", rel.get("destino", "?"))
            tipo = rel.get("tipo", "?")
            peso = rel.get("weight", 0)
            st.markdown(
                f'<div class="vox-chunk">{nome} <span style="color:#6b7280">[{tipo}]</span> w={peso:.1f}</div>',
                unsafe_allow_html=True,
            )
        if not evento.get("relacoes_grafo"):
            st.caption("nenhuma relacao no grafo")

    if evento:
        st.caption(f"Ciclo #{evento.get('iteracao', '?')} — {evento.get('ts', '')}")
    else:
        st.info("Aguardando voice_loop emitir eventos... (rodar demo/voice_loop.py)")


# ── Tab: Último Turno ────────────────────────────────────────────────────────

with tab_ultimo:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=2000, key="ultimo_refresh")
    except ImportError:
        pass

    st.header("Ultimo Turno")

    from api.state import sessions as _sessions

    session_ids = list(_sessions.keys())
    if not session_ids:
        st.info("Nenhuma sessao ativa. Inicie uma sessao via POST /session/start.")
    else:
        sid_sel = st.selectbox("Sessao", session_ids)
        turno = _sessions[sid_sel].ultimo_turno if sid_sel in _sessions else {}

        if not turno:
            st.info("Nenhum turno registrado ainda — envie uma mensagem primeiro.")
        else:
            # Latência breakdown
            lats = turno.get("latencias", {})
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Context (RAG)", f"{lats.get('context_ms', 0)}ms")
            c2.metric("LLM 1o token", f"{lats.get('llm_first_token_ms', -1)}ms")
            c3.metric("TTS", f"{lats.get('tts_ms', 0)}ms")
            c4.metric("Total", f"{lats.get('total_ms', 0)}ms")

            # Erros do turno
            erros = turno.get("erros", [])
            if erros:
                st.error("Erros neste turno: " + " | ".join(erros))

            st.divider()

            # Jogador e RAG
            st.markdown(f"**Jogador:** {turno.get('texto_jogador', '—')}")

            col_lore, col_regras = st.columns(2)
            with col_lore:
                st.subheader("RAG — Lore")
                for c in turno.get("rag", {}).get("chunks_lore", []):
                    score = c.get("score", 0)
                    cor = "🟢" if score >= 0.7 else ("🟡" if score >= 0.5 else "🔴")
                    with st.expander(f"{cor} score={score:.3f}"):
                        st.write(c.get("text", ""))
                if not turno.get("rag", {}).get("chunks_lore"):
                    st.caption("nenhum chunk de lore")

            with col_regras:
                st.subheader("RAG — Regras")
                for c in turno.get("rag", {}).get("chunks_regras", []):
                    score = c.get("score", 0)
                    cor = "🟢" if score >= 0.7 else ("🟡" if score >= 0.5 else "🔴")
                    with st.expander(f"{cor} score={score:.3f}"):
                        st.write(c.get("text", ""))
                if not turno.get("rag", {}).get("chunks_regras"):
                    st.caption("nenhuma regra recuperada")

            st.divider()

            # Prompt enviado ao Groq
            with st.expander("Prompt enviado ao Groq (mensagens_groq)"):
                for msg in turno.get("mensagens_groq", []):
                    role = msg.get("role", "?")
                    content = msg.get("content", "")
                    st.markdown(f"**[{role}]**")
                    st.text(content[:2000] + ("..." if len(content) > 2000 else ""))


# ── Tab: Debug ────────────────────────────────────────────────────────────────

with tab_debug:
    st.header("Conexoes")
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
                        [{"role": "user", "content": "responda so: OK"}],
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
                st.caption(f"Colecoes: {', '.join(colecoes) or 'nenhuma'}")
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
                        return await c.buscar_npcs_no_local("tharnvik")
                npcs = _rodar(_ping_neo4j())
                ms = int((time.perf_counter() - inicio) * 1000)
                st.success(f"OK — {ms}ms")
                st.caption(f"NPCs em tharnvik: {len(npcs)}")
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.header("Busca Semantica — Modulo")

    query_input = st.text_input("Query de teste", placeholder="onde esta Fael?")
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

    st.divider()
    st.header("Memoria Episodica")

    if st.button("Listar sessoes gravadas"):
        try:
            from engine.memory.episodic_memory import EpisodicMemory
            async def _listar():
                m = EpisodicMemory()
                return await m.listar_sessoes()
            sessoes = _rodar(_listar())
            if sessoes:
                st.write(sessoes)
            else:
                st.info("Nenhuma sessao gravada ainda — feche uma sessao com session_writer primeiro.")
        except Exception as e:
            st.error(str(e))

    st.divider()
    with st.expander("Configuracao atual (settings)"):
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


# ===================================================================
# TAB: Decisoes LLM (perna 3 do pipeline multi-LLM)
# Le eventos "llm_decisao" do telemetry.jsonl e agrega por TaskType /
# provider. Responde "qual task e o gargalo?" e "qual provider cascateia?".
with tab_decisoes:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=_REFRESH_MS, key="decisoes_refresh")
    except ImportError:
        pass

    st.header("Decisoes LLM")

    eventos_all = read_latest(n=500)
    decisoes = [e for e in eventos_all
                if isinstance(e, dict) and e.get("evento") == "llm_decisao"]

    if not decisoes:
        st.info(
            "Nenhum evento 'llm_decisao' ainda. Eles aparecem assim que o "
            "Mestre gerar a primeira resposta numa sessao ao vivo."
        )
    else:
        total = len(decisoes)
        n_cascata = sum(1 for d in decisoes if d.get("cascata_disparou"))
        n_falha = sum(1 for d in decisoes if d.get("status") == "fallback_all_failed")
        lats = [d.get("latencia_ms", 0) for d in decisoes if d.get("latencia_ms")]
        lat_media = sum(lats) // len(lats) if lats else 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Decisoes", total)
        c2.metric("Cascata", f"{n_cascata} ({100*n_cascata//total}%)")
        c3.metric("Falha total", f"{n_falha} ({100*n_falha//total}%)")
        c4.metric("Latencia media", f"{lat_media}ms")

        st.divider()

        # ── Agregacao por TaskType ───────────────────────────────────────────
        st.subheader("Por TaskType")
        por_task: dict[str, dict[str, Any]] = {}
        for d in decisoes:
            t = d.get("task", "?")
            agg = por_task.setdefault(t, {"n": 0, "lat": [], "cascata": 0, "falha": 0})
            agg["n"] += 1
            if d.get("latencia_ms"):
                agg["lat"].append(d["latencia_ms"])
            if d.get("cascata_disparou"):
                agg["cascata"] += 1
            if d.get("status") == "fallback_all_failed":
                agg["falha"] += 1

        linhas_task = []
        for t, agg in sorted(por_task.items(), key=lambda kv: -kv[1]["n"]):
            lat = agg["lat"]
            linhas_task.append({
                "TaskType": t,
                "Chamadas": agg["n"],
                "Lat. media (ms)": (sum(lat) // len(lat)) if lat else 0,
                "Lat. max (ms)": max(lat) if lat else 0,
                "Cascata": agg["cascata"],
                "Falha total": agg["falha"],
            })
        st.dataframe(linhas_task, use_container_width=True, hide_index=True)

        # ── Agregacao por provider efetivo ───────────────────────────────────
        st.subheader("Por provider que respondeu")
        por_prov: dict[str, int] = {}
        for d in decisoes:
            p = d.get("provider_efetivo") or "(nenhum - falhou)"
            por_prov[p] = por_prov.get(p, 0) + 1
        linhas_prov = [
            {"Provider": p, "Respostas": n, "Fatia": f"{100*n//total}%"}
            for p, n in sorted(por_prov.items(), key=lambda kv: -kv[1])
        ]
        st.dataframe(linhas_prov, use_container_width=True, hide_index=True)

        # ── Eventos recentes (ultimos 15) ────────────────────────────────────
        st.subheader("Ultimas decisoes")
        recentes = []
        for d in reversed(decisoes[-15:]):
            recentes.append({
                "ts": (d.get("ts", "") or "")[11:19],
                "task": d.get("task", "?"),
                "primario": d.get("provider_primario", "?"),
                "efetivo": d.get("provider_efetivo") or "-",
                "status": d.get("status", "?"),
                "lat (ms)": d.get("latencia_ms", 0),
                "chars": d.get("chars_saida", 0),
                "erro": d.get("categoria_erro") or "",
            })
        st.dataframe(recentes, use_container_width=True, hide_index=True)
