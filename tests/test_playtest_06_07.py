"""
Testes dos fixes do playtest 06/07 (sess-0d8321eaf3b3, 46 turnos).

Cobre 4 achados de causa-raiz:
- STT-ECO-HOTWORDS-1: Whisper alucina o próprio vocabulário de hotwords em
  silêncio/ruído — a "fala" transcrita era literalmente o vocabulário injetado.
- NPC-DEDUP-CANONICO-1: dedup comparava só npcs_presentes atual, perdendo o
  histórico da sessão quando a re-inferência de cena substituía a lista; uma
  pessoa virou 7 entradas (grimbold → grimbol → tabernero → taverneiro → ...).
- ALVO-PRONOME-1: "vou atacar ele" com só 1 NPC na cena nunca virava
  combate_pendente — pronome descartado incondicionalmente.
- NPC-REVEAL-TELEMETRIA-1: npc_name_reveal_ambiguo sem contexto suficiente
  pra calibrar a heurística de âncora.

Dependências: pytest, pytest-asyncio.
"""

import pytest

# ══ STT-ECO-HOTWORDS-1 ════════════════════════════════════════════════════════


def test_eco_hotwords_descarta_lista_de_termos_concatenada():
    """A transcrição real do playtest: eco quase-literal do vocabulário injetado."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Tharnvik, Kaelmund, Os Kael, Faccao de Kaelmund, Drevamor"
    texto = "Tharnvik, Faccao de Kaelmund, Os Kael, Faccao de Kaelmund,"
    assert _e_eco_de_hotwords(texto, hotwords) is True


def test_eco_hotwords_preserva_mencao_pontual_a_npc():
    """'ataco o Bjorn Tharnsson' tem overlap com hotwords mas SEM estrutura de
    lista (1 segmento, sem vírgula) — não pode ser descartada."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Bjorn Tharnsson, Kael, Drevamor"
    texto = "Eu ataco o Bjorn Tharnsson com minha espada!"
    assert _e_eco_de_hotwords(texto, hotwords) is False


def test_eco_hotwords_preserva_fala_natural_com_virgulas():
    """Fala real com vírgulas normais ('Bom, eu acho que...') não deve ter
    overlap suficiente com o vocabulário pra ser confundida com eco."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Tharnvik, Kaelmund, Drevamor"
    texto = "Bom, eu acho que devemos ir embora, não é seguro aqui."
    assert _e_eco_de_hotwords(texto, hotwords) is False


def test_eco_hotwords_sem_hotwords_nunca_descarta():
    from engine.voice.stt import _e_eco_de_hotwords

    assert _e_eco_de_hotwords("Tharnvik, Kaelmund, Drevamor", None) is False
    assert _e_eco_de_hotwords("Tharnvik, Kaelmund, Drevamor", "") is False


def test_eco_hotwords_texto_vazio_nunca_descarta():
    from engine.voice.stt import _e_eco_de_hotwords

    assert _e_eco_de_hotwords("", "Thor, Tharnvik, Drevamor") is False


def test_eco_hotwords_minoria_de_batidas_preserva():
    """Só 1 de 3 segmentos bate com hotwords — abaixo do limiar, preserva."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Tharnvik, Kaelmund"
    texto = "Eu quero ir, encontrar o Thor, e depois descansar um pouco"
    assert _e_eco_de_hotwords(texto, hotwords) is False


@pytest.mark.asyncio
async def test_transcrever_bytes_descarta_eco_e2e(monkeypatch):
    """Integração: transcrever_bytes retorna "" quando o modelo mockado devolve
    eco do hotwords injetado, em vez de propagar a alucinação pro jogo."""
    import engine.voice.stt as stt_mod

    class _Segmento:
        def __init__(self, text: str) -> None:
            self.text = text

    class _ModeloEco:
        def transcribe(self, *a, **kw):
            return [_Segmento("Tharnvik, Faccao de Kaelmund, Os Kael,")], None

    monkeypatch.setattr(stt_mod, "_obter_whisper", lambda: _ModeloEco())
    texto = await stt_mod.transcrever_bytes(
        b"audio-fake",
        hotwords_extra="Tharnvik, Faccao de Kaelmund, Os Kael, Drevamor",
    )
    assert texto == ""


@pytest.mark.asyncio
async def test_transcrever_bytes_preserva_fala_real_e2e(monkeypatch):
    import engine.voice.stt as stt_mod

    class _Segmento:
        def __init__(self, text: str) -> None:
            self.text = text

    class _ModeloReal:
        def transcribe(self, *a, **kw):
            return [_Segmento("Eu ataco o goblin com meu machado!")], None

    monkeypatch.setattr(stt_mod, "_obter_whisper", lambda: _ModeloReal())
    texto = await stt_mod.transcrever_bytes(
        b"audio-fake",
        hotwords_extra="Tharnvik, Faccao de Kaelmund, Drevamor",
    )
    assert texto == "Eu ataco o goblin com meu machado!"
