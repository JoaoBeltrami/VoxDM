"""
Testes do rolling summary (Frente A) — resumo contínuo intra-sessão.

Cobre:
- NarrativeState.deve_resumir: dispara no intervalo, não antes, + clímax/local
- contador de turnos zera após aplicar_resumo_rolling (incl. truncamento no teto)
- atualizar_resumo_rolling: compressão incremental com LLM mockada
- task=MEMORY_COMPRESSION usada
- fallback gracioso: LLM falha → não propaga, contador zera, log.warning chamado
- sessão sintética longa (40 turnos, NPCs REAIS do módulo): conteúdo de turnos
  antigos (fora da janela de 6) permanece representado no resumo_rolling

Por que existe: o resumo rolling é memória de médio prazo — precisa acumular sem
    perder turnos antigos e NUNCA quebrar o turno se a LLM falhar. Estes testes
    travam essas duas invariantes. Toda I/O de LLM é mockada (offline).
Dependências: pytest, pytest-asyncio, unittest.mock
Armadilha: atualizar_resumo_rolling instancia GroqClient() internamente — patchear
    em engine.memory.rolling_summary.GroqClient, não no módulo groq_client.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config import settings
from engine.state.narrative import NarrativeState
from engine.memory.working_memory import WorkingMemory
from engine.memory import rolling_summary
from engine.llm.tasks import TaskType


# ── NarrativeState: predicado e contador (puro, sem I/O) ──────────────────────

def test_deve_resumir_dispara_exatamente_no_intervalo():
    n = NarrativeState()
    for _ in range(2):
        n.marcar_turno_resumo()
    assert n.deve_resumir(3) is False, "2 turnos não deve disparar resumo (intervalo 3)"
    n.marcar_turno_resumo()  # 3º
    assert n.deve_resumir(3) is True, "3 turnos deve disparar resumo"


def test_deve_resumir_por_climax_ou_mudanca_de_local():
    n = NarrativeState()  # contador zerado
    assert n.deve_resumir(6) is False
    assert n.deve_resumir(6, em_climax=True) is True
    assert n.deve_resumir(6, mudou_local=True) is True


def test_aplicar_resumo_seta_texto_e_zera_contador():
    n = NarrativeState()
    for _ in range(6):
        n.marcar_turno_resumo()
    n.aplicar_resumo_rolling("O grupo chegou a Tharnvik e negociou com Bjorn.")
    assert n.resumo_rolling.startswith("O grupo chegou")
    assert n.turnos_desde_resumo == 0


def test_aplicar_resumo_trunca_no_teto_sem_partir_palavra():
    n = NarrativeState()
    longo = "palavra " * 1000  # ~8000 chars, muito acima do teto
    n.aplicar_resumo_rolling(longo)
    assert len(n.resumo_rolling) <= settings.ROLLING_SUMMARY_MAX_CHARS
    assert not n.resumo_rolling.endswith("palavr"), "não deve cortar no meio da palavra"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wm_com_dialogo(turnos: list[tuple[str, str]]) -> WorkingMemory:
    wm = WorkingMemory()
    for falante, texto in turnos:
        wm.registrar_fala(falante, texto)
    return wm


def _mock_groq(retorno=None, erro=None):
    g = MagicMock()
    if erro is not None:
        g.completar = AsyncMock(side_effect=erro)
    else:
        g.completar = AsyncMock(return_value=retorno)
    return g


# ── atualizar_resumo_rolling: caminho feliz ───────────────────────────────────

@pytest.mark.asyncio
async def test_compressao_incremental_seta_resumo_e_zera_contador():
    wm = _wm_com_dialogo([
        ("player", "Ataco Bjorn com a espada."),
        ("mestre", "Bjorn recua ferido mas ainda de pé."),
    ])
    wm.narrative.resumo_rolling = "O grupo chegou a Tharnvik na manhã anterior."
    for _ in range(6):
        wm.narrative.marcar_turno_resumo()

    groq = _mock_groq(retorno="Em Tharnvik, o grupo enfrentou Bjorn, que recuou ferido.")
    with patch.object(rolling_summary, "GroqClient", return_value=groq):
        res = await rolling_summary.atualizar_resumo_rolling(wm)

    assert "Bjorn" in res
    assert wm.narrative.resumo_rolling == res
    assert wm.narrative.turnos_desde_resumo == 0
    groq.completar.assert_awaited_once()


def _groq_captura(capturado: list[dict]):
    """GroqClient mock cujo completar é uma coroutine real que captura kwargs.

    Usar coroutine real (não AsyncMock) evita um artefato de contagem do
    AsyncMock que, dependendo do payload, registra a última chamada com kwargs
    vazios — mascarando os kwargs reais (task, max_tokens) da chamada feita
    pelo código. A coroutine captura exatamente o que foi passado.
    """
    g = MagicMock()
    async def completar(mensagens, **kwargs):
        capturado.append(kwargs)
        return "Resumo de teste."
    g.completar = completar
    return g


@pytest.mark.asyncio
async def test_usa_task_memory_compression():
    wm = _wm_com_dialogo([("player", "Olá."), ("mestre", "Bem-vindo a Drevamor.")])
    cap: list[dict] = []
    with patch.object(rolling_summary, "GroqClient", return_value=_groq_captura(cap)):
        await rolling_summary.atualizar_resumo_rolling(wm)
    assert len(cap) == 1, f"completar deve ser chamado exatamente uma vez, foi {len(cap)}"
    assert cap[0].get("task") == TaskType.MEMORY_COMPRESSION, (
        f"Esperava task=MEMORY_COMPRESSION, recebeu {cap[0].get('task')}"
    )


@pytest.mark.asyncio
async def test_max_tokens_curto():
    wm = _wm_com_dialogo([("player", "Olá.")])
    cap: list[dict] = []
    with patch.object(rolling_summary, "GroqClient", return_value=_groq_captura(cap)):
        await rolling_summary.atualizar_resumo_rolling(wm)
    assert len(cap) == 1
    assert cap[0].get("max_tokens", 9999) <= 400, "resumo deve usar max_tokens curto"


# ── atualizar_resumo_rolling: fallback gracioso ───────────────────────────────

@pytest.mark.asyncio
async def test_fallback_quando_llm_falha_nao_propaga_e_zera_contador():
    wm = _wm_com_dialogo([
        ("player", "Converso com Runa sobre o ataque."),
        ("mestre", "Runa-tharnsdottir conta o que viu na ponte."),
    ])
    wm.narrative.resumo_rolling = "Antes disso, o grupo saiu de Drevamor."
    for _ in range(6):
        wm.narrative.marcar_turno_resumo()

    groq = _mock_groq(erro=Exception("Groq indisponível"))
    with patch.object(rolling_summary, "GroqClient", return_value=groq), \
         patch.object(rolling_summary, "log") as mock_log:
        # NÃO deve levantar exceção
        res = await rolling_summary.atualizar_resumo_rolling(wm)

    assert wm.narrative.turnos_desde_resumo == 0, "contador deve zerar mesmo no fallback"
    # O fallback concatena resumo anterior + diálogo bruto — conteúdo preservado
    assert "Runa" in res or "Drevamor" in res
    assert mock_log.warning.called, "fallback deve logar warning com contexto"


@pytest.mark.asyncio
async def test_fallback_quando_llm_retorna_vazio():
    wm = _wm_com_dialogo([("player", "Sigo em frente."), ("mestre", "A trilha desce para Kaelmund.")])
    for _ in range(6):
        wm.narrative.marcar_turno_resumo()
    groq = _mock_groq(retorno="   ")  # vazio após strip → trata como falha
    with patch.object(rolling_summary, "GroqClient", return_value=groq):
        res = await rolling_summary.atualizar_resumo_rolling(wm)
    assert wm.narrative.turnos_desde_resumo == 0
    assert "Kaelmund" in res  # caiu no fallback de diálogo bruto


# ── Sessão sintética longa — retenção de turnos antigos ───────────────────────

@pytest.mark.asyncio
async def test_sessao_longa_retem_conteudo_de_turnos_antigos():
    """40 turnos com NPCs reais do módulo. Um fato introduzido cedo (turno ~7)
    deve continuar representado no resumo ao fim, mesmo tendo saído há muito da
    janela de diálogo (MAX_DIALOGOS=6). Mock simula um bom summarizer cumulativo:
    extrai entidades do prompt (que inclui o resumo anterior + diálogo novo) e as
    carrega adiante — exatamente o comportamento incremental esperado.
    """
    entidades = ["bjorn-tharnsson", "runa-tharnsdottir", "tharnvik", "drevamor"]

    async def fake_completar(mensagens, **kwargs):
        conteudo = mensagens[0]["content"]
        vistas = [e for e in entidades if e in conteudo]
        return "Nesta sessão o grupo já lidou com: " + ", ".join(sorted(set(vistas))) + "."

    groq = MagicMock()
    groq.completar = AsyncMock(side_effect=fake_completar)

    wm = WorkingMemory()
    intervalo = settings.ROLLING_SUMMARY_INTERVALO

    with patch.object(rolling_summary, "GroqClient", return_value=groq):
        for turno in range(1, 41):
            # bjorn-tharnsson é introduzido cedo (turno 7) e nunca mais mencionado
            if turno == 7:
                wm.registrar_fala("mestre", "bjorn-tharnsson surge e jura vingança.")
            else:
                wm.registrar_fala("player", f"Avanço pela trilha rumo a tharnvik (turno {turno}).")
                wm.registrar_fala("mestre", f"A paisagem de drevamor muda no turno {turno}.")
            wm.narrative.marcar_turno_resumo()
            if wm.narrative.deve_resumir(intervalo):
                await rolling_summary.atualizar_resumo_rolling(wm)

    # Apesar de bjorn ter saído da janela de diálogo há ~30 turnos, o resumo
    # rolling ainda o representa (foi carregado adiante a cada compressão).
    assert "bjorn-tharnsson" in wm.narrative.resumo_rolling, (
        "fato antigo (turno 7) deveria persistir no resumo rolling ao fim da sessão"
    )
    assert wm.narrative.turnos_desde_resumo < intervalo
