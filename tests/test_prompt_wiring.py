"""
Testes do wiring de prompts — drifts #60/#61/#62.

- #61: social.md é carregado e injetado em cena social (gated: NPCs presentes,
  fora de combate). NÃO entra em combate (mutex + segurança de budget).
- #60: session_eval.md é usado como SYSTEM message no resumo de sessão.
- #62: recap.md é carregado pela abertura de sessão continuada.

Offline — sem Qdrant/Neo4j/Groq reais.
"""

import asyncio
from unittest.mock import AsyncMock, patch

from engine.llm.prompt_builder import _carregar_recap, _carregar_social, montar_mensagens
from engine.llm.types import ContextoMontado
from engine.memory.session_writer import _carregar_session_eval
from engine.memory.working_memory import WorkingMemory


def _ctx(wm, transcricao="o que você sabe sobre a vila?"):
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


# ── #61 — social.md ───────────────────────────────────────────────────────────

def test_social_carrega():
    s = _carregar_social()
    assert s and "assinatura de voz" in s


def test_social_injetado_em_cena_social():
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.npcs_presentes = ["fael-valdreksson"]
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "assinatura de voz" in system  # social.md presente


def test_social_ausente_em_combate():
    """Cena social é mutuamente exclusiva com combate → social.md não soma ao combate."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.npcs_presentes = ["orc-1"]
    wm.entrar_combate()
    system = montar_mensagens(_ctx(wm, "ataco o orc"))[0]["content"]
    assert "assinatura de voz" not in system


def test_social_ausente_sem_npcs():
    """Exploração sem NPCs presentes não injeta social.md (economia)."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    system = montar_mensagens(_ctx(wm))[0]["content"]
    assert "assinatura de voz" not in system


# ── #62 — recap.md ────────────────────────────────────────────────────────────

def test_recap_carrega():
    r = _carregar_recap()
    assert r and "Da última vez" in r


# ── #60 — session_eval.md ─────────────────────────────────────────────────────

def test_session_eval_carrega():
    e = _carregar_session_eval()
    assert e and "diário de campanha" in e


def test_resumo_usa_session_eval_como_system():
    """_resumir_via_groq manda session_eval.md como system + os dados como user."""
    from engine.memory import session_writer

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.registrar_fala("player", "eu falo com o ferreiro")
    capturado: dict = {}

    async def fake_completar(mensagens, **kw):
        capturado["msgs"] = mensagens
        return "resumo gerado"

    with patch.object(session_writer, "GroqClient") as MockG:
        MockG.return_value.completar = AsyncMock(side_effect=fake_completar)
        out = asyncio.run(session_writer._resumir_via_groq(wm))

    assert out == "resumo gerado"
    msgs = capturado["msgs"]
    assert msgs[0]["role"] == "system"
    assert "diário de campanha" in msgs[0]["content"]      # session_eval como system
    assert msgs[1]["role"] == "user"
    assert "Última janela de diálogo" in msgs[1]["content"]  # dados no user
