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
# Nota: a implementação usa QdrantClient.scroll() diretamente (não self._qdrant.buscar)
# para evitar score_threshold=0.45 que bloquearia UUIDs não-semânticos como queries.

def _ponto_fake(payload: dict):
    """Cria um ponto Qdrant fake com atributos mínimos."""
    p = MagicMock()
    p.payload = payload
    return p


@pytest.mark.asyncio
async def test_buscar_por_session_id_retorna_dict_quando_ha_entrada():
    """buscar_por_session_id deve retornar o payload quando existe entrada."""
    entrada_fake = {
        "text": "Resumo da sessão 1: o grupo derrotou os goblins.",
        "session_id": "sess-abc123",
        "trust_levels": {"fael": 2},
        "quest_stages": {},
        "timestamp": 1000.0,
        "dm_state": {"fios_soltos": [], "agenda_npcs": {}, "cliffhanger_pendente": ""},
        "companions": {},
    }
    ponto = _ponto_fake(entrada_fake)

    # QdrantClient é importado dentro do método — patchear no módulo qdrant_client
    with patch("qdrant_client.QdrantClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.scroll.return_value = ([ponto], None)

        mem = EpisodicMemory()
        resultado = await mem.buscar_por_session_id("sess-abc123")

    assert resultado is not None
    assert resultado["session_id"] == "sess-abc123"
    assert resultado["text"].startswith("Resumo")


@pytest.mark.asyncio
async def test_buscar_por_session_id_retorna_none_quando_ausente():
    """buscar_por_session_id deve retornar None se não há memória episódica."""
    with patch("qdrant_client.QdrantClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.scroll.return_value = ([], None)

        mem = EpisodicMemory()
        resultado = await mem.buscar_por_session_id("sess-inexistente")

    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_por_session_id_silencioso_em_excecao():
    """buscar_por_session_id deve retornar None em vez de propagar exceção."""
    with patch("qdrant_client.QdrantClient") as mock_cls:
        mock_cls.side_effect = Exception("Qdrant offline")

        mem = EpisodicMemory()
        resultado = await mem.buscar_por_session_id("sess-qualquer")

    assert resultado is None


@pytest.mark.asyncio
async def test_buscar_por_session_id_retorna_ponto_mais_recente():
    """Quando há múltiplos pontos, retorna o de maior timestamp."""
    antigo = _ponto_fake({"session_id": "s1", "text": "velho", "timestamp": 100.0})
    recente = _ponto_fake({"session_id": "s1", "text": "recente", "timestamp": 500.0})

    with patch("qdrant_client.QdrantClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.scroll.return_value = ([antigo, recente], None)

        mem = EpisodicMemory()
        resultado = await mem.buscar_por_session_id("s1")

    assert resultado is not None
    assert resultado["text"] == "recente"


# ── _enviar_recap_sessao_anterior — comportamento silencioso ──────────────────

def _montar_sessao_fake(resumo: str = "Resumo da sessão anterior.") -> MagicMock:
    """Cria um mock de SessaoAtiva com resumo_anterior e groq configurados."""
    sessao = MagicMock()
    sessao.session_id = "sess-teste-01"
    sessao.resumo_anterior = resumo
    sessao.working_mem = MagicMock()
    sessao.working_mem.tts_voice = "pt-BR-FranciscaNeural"
    sessao.working_mem.companions = {}
    sessao.working_mem.fios_soltos = []
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


# ── Novos testes — Continuidade entre sessões ─────────────────────────────────

@pytest.mark.asyncio
async def test_recap_prompt_menciona_companion_quando_presente():
    """Quando há companions ativos, o prompt do recap inclui 'Aliados'."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()
    sessao.working_mem.companions = {
        "lyssa": {"nome": "Lyssa", "tipo": "hireling", "hp": 24, "hp_max": 30}
    }

    capturado: list[str] = []
    async def groq_capture(**kwargs) -> str:
        # Captura o conteúdo do prompt para inspecionar
        for msg in kwargs.get("mensagens", []):
            capturado.append(msg.get("content", ""))
        return "Da última vez, Lyssa acompanhou o grupo."

    sessao.groq.completar = groq_capture  # type: ignore

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    # Algum trecho do prompt deve mencionar "Aliados" ou "Lyssa"
    prompt_completo = " ".join(capturado)
    assert "Lyssa" in prompt_completo or "Aliados" in prompt_completo


@pytest.mark.asyncio
async def test_recap_prompt_menciona_fios_quando_presentes():
    """Quando há fios soltos, o prompt do recap os inclui."""
    from api.websocket import _enviar_recap_sessao_anterior

    websocket = AsyncMock()
    sessao = _montar_sessao_fake()
    sessao.working_mem.fios_soltos = ["Valdrek mencionou a chave da torre"]

    capturado: list[str] = []
    async def groq_capture(**kwargs) -> str:
        for msg in kwargs.get("mensagens", []):
            capturado.append(msg.get("content", ""))
        return "Da última vez, o grupo descobriu algo sobre a torre."

    sessao.groq.completar = groq_capture  # type: ignore

    with patch("api.websocket._obter_tts", return_value=None):
        await _enviar_recap_sessao_anterior(websocket, sessao)

    prompt_completo = " ".join(capturado)
    assert "Valdrek" in prompt_completo or "torre" in prompt_completo or "Fios" in prompt_completo


def test_session_writer_payload_inclui_campos_continuidade():
    """Payload do session_writer deve incluir companions, dm_state, level, xp, gold."""
    # Verifica o prompt de resumo contém os novos placeholders
    from engine.memory.session_writer import _PROMPT_RESUMO
    assert "{companions}" in _PROMPT_RESUMO, "Prompt deve ter placeholder {companions}"
    assert "{fios_soltos}" in _PROMPT_RESUMO, "Prompt deve ter placeholder {fios_soltos}"
    # Frente A opcional: resumo episódico parte do resumo contínuo da sessão.
    assert "{resumo_rolling}" in _PROMPT_RESUMO, "Prompt deve ter placeholder {resumo_rolling}"


def test_buscar_por_session_id_nao_usa_buscar_semantico():
    """buscar_por_session_id NÃO deve chamar self._qdrant.buscar (usa scroll direto)."""
    import inspect
    from engine.memory.episodic_memory import EpisodicMemory
    src = inspect.getsource(EpisodicMemory.buscar_por_session_id)
    # Método novo usa scroll, não self.buscar
    assert "self.buscar(" not in src, (
        "buscar_por_session_id não deve usar self.buscar() — UUID como query "
        "nunca passa score_threshold=0.45. Usar scroll com filtro exato."
    )
    assert "scroll" in src, "buscar_por_session_id deve usar scroll()"


def test_iniciar_sessao_le_campo_text_nao_resumo_curto():
    """iniciar_sessao deve ler 'text' do payload episódico, não 'resumo_curto'."""
    import inspect
    from api.routes.session import iniciar_sessao
    src = inspect.getsource(iniciar_sessao)
    # Bug #2: campo no Qdrant é "text", não "resumo_curto"
    assert 'entrada.get("text"' in src or "entrada.get('text'" in src, (
        "iniciar_sessao deve ler campo 'text' do payload episódico "
        "(não 'resumo_curto' que não existe no Qdrant payload)"
    )


def test_cliffhanger_limpo_apos_uso_na_abertura():
    """wm.cliffhanger_pendente deve ser zerado após ser usado como gancho de abertura."""
    import inspect
    from api.websocket import _enviar_abertura
    src = inspect.getsource(_enviar_abertura)
    assert 'cliffhanger_pendente = ""' in src, (
        "Cliffhanger deve ser limpo (one-shot) após ser injetado no intro_user"
    )
