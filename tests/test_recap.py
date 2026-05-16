"""
Testes para o sistema de recap oral de sessão anterior.

Cobre:
- buscar_por_session_id (mock do Qdrant) retorna estrutura correta
- _enviar_recap_sessao_anterior retorna silenciosamente quando não há memória
- Prompt do recap contém as frases de abertura esperadas
- MensagemWS aceita tipo="recap"
- Falha silenciosa: exceção no LLM não propaga para a abertura

Por que existe: recap é funcionalidade crítica de UX mas NUNCA deve bloquear
    o jogo. Esses testes garantem as invariantes de silêncio e de contrato.
Dependências: pytest, pytest-asyncio, unittest.mock
Armadilha: _enviar_recap_sessao_anterior está em api/websocket.py — precisa
    de mock completo de WebSocket, sessao.groq e sessao.working_mem.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models.schemas import MensagemWS
from engine.memory.episodic_memory import EpisodicMemory


# ── MensagemWS — tipo="recap" ─────────────────────────────────────────────────

def test_mensagem_ws_aceita_tipo_recap():
    """MensagemWS deve serializar tipo='recap' sem levantar exceção."""
    msg = MensagemWS(tipo="recap", conteudo="Da última vez, o grupo entrou na taverna.")
    payload = msg.model_dump_json()
    assert '"recap"' in payload
    assert "Da última vez" in payload


def test_mensagem_ws_recap_conteudo_vazio():
    """Tipo='recap' com conteúdo vazio é válido — frontend apenas não renderiza."""
    msg = MensagemWS(tipo="recap", conteudo="")
    assert msg.tipo == "recap"
    assert msg.conteudo == ""


def test_mensagem_ws_tipo_nao_quebra_outros_campos():
    """Campos padrão não devem ser afetados ao usar tipo='recap'."""
    msg = MensagemWS(tipo="recap", conteudo="Teste")
    assert msg.latencia_ms == 0
    assert msg.sequencia == 0
    assert msg.fios_soltos == []


# ── EpisodicMemory.buscar_por_session_id ─────────────────────────────────────

@pytest.mark.asyncio
async def test_buscar_por_session_id_retorna_dict_quando_ha_entrada():
    """buscar_por_session_id deve retornar o primeiro resultado quando existe."""
    mem = EpisodicMemory()
    entrada_fake = {
        "text": "Resumo da sessão 1: o grupo derrotou os goblins.",
        "session_id": "sess-abc123",
        "trust_levels": {"fael": 2},
        "quest_stages": {},
        "resumo_curto": "O grupo derrotou os goblins na floresta.",
    }
    mem.buscar = AsyncMock(return_value=[entrada_fake])

    resultado = await mem.buscar_por_session_id("sess-abc123")

    assert resultado is not None
    assert resultado["session_id"] == "sess-abc123"
    assert "resumo_curto" in resultado


@pytest.mark.asyncio
async def test_buscar_por_session_id_retorna_none_quando_ausente():
    """buscar_por_session_id deve retornar None se não há memória episódica."""
    mem = EpisodicMemory()
    mem.buscar = AsyncMock(return_value=[])

    resultado = await mem.buscar_por_session_id("sess-inexistente")

    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_por_session_id_silencioso_em_excecao():
    """buscar_por_session_id deve retornar None em vez de propagar exceção."""
    mem = EpisodicMemory()
    mem.buscar = AsyncMock(side_effect=Exception("Qdrant offline"))

    resultado = await mem.buscar_por_session_id("sess-qualquer")

    assert resultado is None


# ── _enviar_recap_sessao_anterior — comportamento silencioso ──────────────────

def _montar_sessao_fake(resumo: str = "Resumo da sessão anterior.") -> MagicMock:
    """Cria um mock de SessaoAtiva com resumo_anterior e groq configurados."""
    sessao = MagicMock()
    sessao.session_id = "sess-teste-01"
    sessao.resumo_anterior = resumo
    sessao.working_mem = MagicMock()
    sessao.working_mem.tts_voice = "pt-BR-FranciscaNeural"
    # groq.completar é async — retorna o texto do recap gerado
    sessao.groq = MagicMock()
    sessao.groq.completar = AsyncMock(
        return_value="Da última vez, o grupo entrou na caverna dos goblins."
    )
    return sessao


@pytest.mark.asyncio
async def test_recap_retorna_silenciosamente_sem_resumo():
    """Quando resumo_anterior é vazio, função deve retornar sem enviar nada."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake(resumo="")

    await _enviar_recap_sessao_anterior(websocket, sessao)

    websocket.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_recap_envia_mensagem_tipo_recap():
    """Quando há resumo_anterior, deve enviar mensagem WS tipo='recap'."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    # Verifica que send_text foi chamado pelo menos uma vez com tipo="recap"
    chamadas = [c.args[0] for c in websocket.send_text.call_args_list]
    assert any('"recap"' in texto for texto in chamadas), (
        "Esperava mensagem tipo='recap' mas não encontrou"
    )


@pytest.mark.asyncio
async def test_recap_texto_contem_frase_abertura():
    """O texto do recap gerado deve conter 'Da última vez' ou 'Na sessão anterior'."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()

    sessao_ultima_vez = _montar_sessao_fake()
    sessao_ultima_vez.groq.completar = AsyncMock(
        return_value="Da última vez, o grupo explorou as ruínas."
    )

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao_ultima_vez)

    # Extrai o conteúdo da mensagem recap
    chamadas = [c.args[0] for c in websocket.send_text.call_args_list]
    recap_msgs = [t for t in chamadas if '"recap"' in t]
    assert len(recap_msgs) >= 1
    assert any(
        "Da última vez" in m or "Na sessão anterior" in m
        for m in recap_msgs
    )


@pytest.mark.asyncio
async def test_recap_silencioso_quando_llm_levanta_excecao():
    """Se o LLM falhar, _enviar_recap_sessao_anterior não deve propagar a exceção."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()
    sessao.groq.completar = AsyncMock(side_effect=Exception("Groq indisponível"))

    # Não deve levantar exceção
    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    # Nenhuma mensagem deve ser enviada quando o LLM falha
    # (pode ter nenhuma ou apenas as que chegaram antes da exceção)
    # O importante é que não propagou a exceção acima


@pytest.mark.asyncio
async def test_recap_silencioso_quando_llm_retorna_vazio():
    """Se o LLM retornar string vazia, não deve enviar mensagem nem áudio."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()
    sessao.groq.completar = AsyncMock(return_value="   ")  # só espaços

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    chamadas = [c.args[0] for c in websocket.send_text.call_args_list]
    assert not any('"recap"' in t for t in chamadas), (
        "Não deveria enviar recap quando LLM retorna vazio"
    )


@pytest.mark.asyncio
async def test_recap_envia_audio_chunk_quando_tts_disponivel():
    """Quando TTS está disponível, deve enviar audio_chunk após a mensagem recap."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()

    tts_mock = AsyncMock()
    tts_mock.sintetizar = AsyncMock(return_value=b"\xff\xfbMP3FAKEDATA")

    with patch("api.websocket._obter_tts", return_value=tts_mock):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    chamadas = [c.args[0] for c in websocket.send_text.call_args_list]
    assert any('"audio_chunk"' in t for t in chamadas), (
        "Esperava mensagem audio_chunk após TTS do recap"
    )


@pytest.mark.asyncio
async def test_recap_sem_audio_quando_tts_retorna_vazio():
    """Quando TTS retorna bytes vazios, não deve enviar audio_chunk."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()

    tts_mock = AsyncMock()
    tts_mock.sintetizar = AsyncMock(return_value=b"")

    with patch("api.websocket._obter_tts", return_value=tts_mock):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    chamadas = [c.args[0] for c in websocket.send_text.call_args_list]
    assert not any('"audio_chunk"' in t for t in chamadas)


@pytest.mark.asyncio
async def test_recap_usa_task_type_summarization():
    """completar() deve ser chamado com task=TaskType.SUMMARIZATION."""
    from api.websocket import _enviar_recap_sessao_anterior
    from engine.llm.tasks import TaskType

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    sessao.groq.completar.assert_called_once()
    kwargs = sessao.groq.completar.call_args.kwargs
    assert kwargs.get("task") == TaskType.SUMMARIZATION, (
        f"Esperava task=SUMMARIZATION, recebeu {kwargs.get('task')}"
    )


@pytest.mark.asyncio
async def test_recap_max_tokens_limitado():
    """completar() deve ser chamado com max_tokens <= 120 (recap curto)."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    kwargs = sessao.groq.completar.call_args.kwargs
    assert kwargs.get("max_tokens", 9999) <= 120, (
        "Recap deve ser gerado com max_tokens <= 120 para manter 2-3 frases"
    )


@pytest.mark.asyncio
async def test_recap_silencioso_quando_tts_levanta_excecao():
    """Se TTS falhar, não deve propagar exceção — jogo continua sem áudio."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()

    tts_mock = AsyncMock()
    tts_mock.sintetizar = AsyncMock(side_effect=Exception("Edge TTS offline"))

    with patch("api.websocket._obter_tts", return_value=tts_mock):
        # Não deve levantar exceção
        await _enviar_recap_sessao_anterior(websocket, sessao)

    # Recap de texto ainda foi enviado antes do TTS falhar
    chamadas = [c.args[0] for c in websocket.send_text.call_args_list]
    assert any('"recap"' in t for t in chamadas), (
        "Texto do recap deve ser enviado mesmo quando TTS falha"
    )
