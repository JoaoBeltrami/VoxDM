"""
Testes do thinking_cache voice-aware (PT-5, playtest #7).

Garante que o áudio de "pensamento" usa a voz da sessão quando disponível, cai
no fallback da voz padrão quando não, e que o aquecimento lazy não quebra sem
event loop. Sem rede — TTS é mockado no teste de síntese.

    pytest tests/test_thinking_cache.py -q
"""

import pytest

from engine.voice import thinking_cache as tc


@pytest.fixture(autouse=True)
def _cache_limpo():
    """Isola o estado global do módulo entre testes."""
    cache_bak = {v: dict(p) for v, p in tc._cache.items()}
    aq_bak = set(tc._aquecendo)
    tc._cache.clear()
    tc._aquecendo.clear()
    yield
    tc._cache.clear()
    tc._cache.update(cache_bak)
    tc._aquecendo.clear()
    tc._aquecendo.update(aq_bak)


def test_pegar_random_cache_vazio():
    assert tc.pegar_random() is None
    assert tc.pegar_random(voz="pt-BR-AntonioNeural") is None


def test_pegar_random_voz_padrao_e_fallback():
    tc._cache[tc._VOZ_PADRAO] = {"Hmm...": b"fem"}
    assert tc.pegar_random() == ("Hmm...", b"fem")
    # voz da sessão ainda não aquecida → fallback pra padrão (nunca pior que antes)
    assert tc.pegar_random(voz="pt-BR-AntonioNeural") == ("Hmm...", b"fem")


def test_pegar_random_usa_voz_da_sessao_quando_aquecida():
    tc._cache[tc._VOZ_PADRAO] = {"Hmm...": b"fem"}
    tc._cache["pt-BR-AntonioNeural"] = {"Hmm...": b"masc"}
    assert tc.pegar_random(voz="pt-BR-AntonioNeural") == ("Hmm...", b"masc")


def test_pegar_random_evita_a_frase_exceto():
    tc._cache[tc._VOZ_PADRAO] = {"A": b"1", "B": b"2"}
    frase, _ = tc.pegar_random(exceto="A")
    assert frase == "B"


def test_path_voz_padrao_preserva_disco_antigo():
    # voz padrão / vazio → hash só da frase (compat com MP3s já gravados)
    assert tc._path_para_frase("Hmm...") == tc._path_para_frase("Hmm...", tc._VOZ_PADRAO)
    # voz nomeada → caminho diferente
    assert tc._path_para_frase("Hmm...", "pt-BR-AntonioNeural") != tc._path_para_frase("Hmm...")


def test_garantir_voz_noop_padrao_e_cacheada():
    tc.garantir_voz(None)
    tc.garantir_voz("")
    tc.garantir_voz(tc._VOZ_PADRAO)
    assert tc._aquecendo == set()
    tc._cache["pt-BR-AntonioNeural"] = {"Hmm...": b"x"}
    tc.garantir_voz("pt-BR-AntonioNeural")  # já cacheada
    assert tc._aquecendo == set()


def test_garantir_voz_sem_loop_nao_quebra():
    # Sem event loop rodando, create_task levanta RuntimeError — deve ser capturado
    # e o flag de "aquecendo" desfeito, sem propagar exceção.
    tc.garantir_voz("pt-BR-AntonioNeural")
    assert "pt-BR-AntonioNeural" not in tc._aquecendo


@pytest.mark.asyncio
async def test_aquecer_voz_sintetiza_na_voz_pedida(monkeypatch):
    class _FakeTTS:
        async def sintetizar(self, frase, idioma=None, voice=None):
            return f"audio|{voice}|{frase}".encode()

    monkeypatch.setattr("engine.voice.tts.TTSEngine", _FakeTTS)
    monkeypatch.setattr(tc, "_salvar_no_disco", lambda *a, **k: None)
    # Hermético: não carregar MP3s reais que uma sessão ao vivo possa ter gravado.
    monkeypatch.setattr(tc, "_carregar_do_disco", lambda voz: 0)
    await tc.aquecer_voz("pt-BR-AntonioNeural")
    pool = tc._cache.get("pt-BR-AntonioNeural")
    assert pool, "deveria ter sintetizado o pool da voz"
    amostra = next(iter(pool.values()))
    assert amostra.startswith(b"audio|pt-BR-AntonioNeural|")


@pytest.mark.asyncio
async def test_aquecer_voz_ignora_padrao(monkeypatch):
    chamou = False

    class _FakeTTS:
        async def sintetizar(self, *a, **k):
            nonlocal chamou
            chamou = True
            return b"x"

    monkeypatch.setattr("engine.voice.tts.TTSEngine", _FakeTTS)
    await tc.aquecer_voz(tc._VOZ_PADRAO)
    await tc.aquecer_voz("")
    assert chamou is False  # padrão/vazio não dispara síntese de voz nova
