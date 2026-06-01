"""
Testes de integração do rolling summary (Frente A).

Cobre o que toca outros módulos além do núcleo:
- Injeção no system prompt (prompt_builder.montar_mensagens): com resumo_rolling
  setado e flag ON o bloco aparece em prosa pura (sem === nem colchetes); com a
  flag OFF não aparece.
- Opcional: session_writer resume A PARTIR do resumo_rolling (placeholder no
  prompt) e inclui resumo_rolling no dm_state do payload episódico.

Por que existe: separado de test_rolling_summary.py (que cobre o núcleo puro)
    para isolar dependências de prompt_builder e session_writer.
Dependências: pytest, pytest-asyncio, unittest.mock
Armadilha: montar_mensagens lê master_system.md do disco — roda offline, mas o
    teste de injeção patcha settings no módulo prompt_builder (onde é lido).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.llm import prompt_builder
from engine.llm.prompt_builder import montar_mensagens
from engine.llm.types import ContextoMontado
from engine.memory.working_memory import WorkingMemory


def _ctx(working_memory: WorkingMemory, transcricao: str = "Olá") -> ContextoMontado:
    return ContextoMontado(
        working_memory=working_memory,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


def _system_content(mensagens: list[dict]) -> str:
    """Extrai o conteúdo da mensagem system (sempre a primeira)."""
    assert mensagens and mensagens[0]["role"] == "system"
    return mensagens[0]["content"]


# ── Injeção no system prompt ──────────────────────────────────────────────────

def test_injecao_aparece_com_flag_on():
    wm = WorkingMemory()
    wm.resumo_rolling = "O grupo chegou a Tharnvik e fez um pacto tenso com Bjorn."
    with patch.object(prompt_builder.settings, "ROLLING_SUMMARY_ATIVO", True):
        msgs = montar_mensagens(_ctx(wm))
    system = _system_content(msgs)
    assert "Tharnvik e fez um pacto" in system, "resumo rolling deveria estar no system prompt"
    assert "já aconteceu nesta sessão" in system, "rótulo natural deveria preceder o resumo"


def test_injecao_e_prosa_pura_sem_marcadores_de_codigo():
    """O bloco do resumo NÃO pode ter === nem colchetes — eles disparam 'modo
    leitura de código' no LLM. Verifica exatamente as duas linhas do bloco
    (rótulo + resumo), sem invadir blocos vizinhos do master_system."""
    wm = WorkingMemory()
    wm.resumo_rolling = "Runa revelou o segredo da ponte; a confiança dela subiu."
    with patch.object(prompt_builder.settings, "ROLLING_SUMMARY_ATIVO", True):
        msgs = montar_mensagens(_ctx(wm))
    system = _system_content(msgs)
    # Recorta exatamente o rótulo + a linha do resumo (até o próximo \n).
    idx = system.index("Você se lembra de tudo o que já aconteceu nesta sessão:")
    fim = system.index("\n", system.index(wm.resumo_rolling))
    bloco = system[idx:fim]
    assert wm.resumo_rolling in bloco
    assert "===" not in bloco, "bloco do resumo não deve conter ==="
    assert "[" not in bloco and "]" not in bloco, "bloco do resumo não deve conter colchetes"


def test_injecao_ausente_com_flag_off():
    wm = WorkingMemory()
    wm.resumo_rolling = "Texto que NÃO deve aparecer com a flag desligada."
    with patch.object(prompt_builder.settings, "ROLLING_SUMMARY_ATIVO", False):
        msgs = montar_mensagens(_ctx(wm))
    system = _system_content(msgs)
    assert "NÃO deve aparecer" not in system
    assert "já aconteceu nesta sessão" not in system


def test_injecao_ausente_quando_resumo_vazio():
    wm = WorkingMemory()  # resumo_rolling == ""
    with patch.object(prompt_builder.settings, "ROLLING_SUMMARY_ATIVO", True):
        msgs = montar_mensagens(_ctx(wm))
    system = _system_content(msgs)
    assert "já aconteceu nesta sessão" not in system


# ── Opcional: session_writer parte do resumo_rolling ──────────────────────────

def test_prompt_resumo_tem_placeholder_rolling():
    from engine.memory.session_writer import _PROMPT_RESUMO
    assert "{resumo_rolling}" in _PROMPT_RESUMO


@pytest.mark.asyncio
async def test_resumir_via_groq_passa_resumo_rolling_no_prompt():
    """O prompt enviado ao LLM no fechamento deve conter o resumo_rolling."""
    from engine.memory import session_writer

    wm = WorkingMemory()
    wm.resumo_rolling = "MARCADOR_ROLLING_UNICO: o grupo derrotou o ogro na ponte."

    capturado: list[str] = []

    async def fake_completar(mensagens, **kwargs):
        capturado.append(mensagens[0]["content"])
        return "Resumo episódico final."

    groq = MagicMock()
    groq.completar = AsyncMock(side_effect=fake_completar)

    with patch.object(session_writer, "GroqClient", return_value=groq):
        resumo = await session_writer._resumir_via_groq(wm)

    assert resumo == "Resumo episódico final."
    assert capturado, "completar deveria ter sido chamado"
    assert "MARCADOR_ROLLING_UNICO" in capturado[0], (
        "o resumo contínuo deveria alimentar o prompt de fechamento"
    )


def test_dm_state_inclui_resumo_rolling():
    """O payload de fechar_sessao deve carregar resumo_rolling no dm_state —
    verificado por inspeção do fonte (sem I/O de Qdrant)."""
    import inspect

    from engine.memory.session_writer import SessionWriter
    src = inspect.getsource(SessionWriter.fechar_sessao)
    assert '"resumo_rolling"' in src, "dm_state deve incluir a chave resumo_rolling"
    assert "working_mem.resumo_rolling" in src, "deve persistir o valor real do wm"
