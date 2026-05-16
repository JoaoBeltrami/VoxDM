"""
Testes para engine/image/scene_image.py.

Por que existe: garante que a construção de prompt e utilitários de URL/hash
    funcionam deterministicamente sem depender de rede ou de I/O externo.
    A função gerar_e_enviar_imagem usa httpx real — testada via mock para
    evitar chamadas ao Pollinations.ai em CI.
Dependências: pytest, pytest-asyncio
Armadilha: importar scene_image antes de setar variáveis de ambiente não é
    problema — o módulo não lê settings. Mas o conftest.py já cobre o setup.
"""

import pytest

from engine.image.scene_image import (
    _montar_url,
    _prompt_hash,
    construir_prompt_cena,
)


# ── Testes de construção de prompt ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_construir_prompt_cena_noite():
    prompt = await construir_prompt_cena("Taverna do Lobo", "noite", False)
    assert "Taverna do Lobo" in prompt
    assert "night" in prompt
    assert "fantasy art" in prompt


@pytest.mark.asyncio
async def test_construir_prompt_cena_combate():
    prompt = await construir_prompt_cena("Floresta", "tarde", True)
    assert "combat" in prompt
    assert "dramatic" in prompt


@pytest.mark.asyncio
async def test_construir_prompt_cena_sem_combate():
    prompt = await construir_prompt_cena("Vila Drevamor", "manhã", False)
    assert "Vila Drevamor" in prompt
    assert "morning light" in prompt
    assert "combat" not in prompt


@pytest.mark.asyncio
async def test_construir_prompt_manha_alias():
    """'manha' sem acento deve mapear igual a 'manhã'."""
    prompt = await construir_prompt_cena("Praça Central", "manha", False)
    assert "morning light" in prompt


@pytest.mark.asyncio
async def test_construir_prompt_com_weather():
    prompt = await construir_prompt_cena("Clareira", "noite", False, weather="neve")
    assert "snow" in prompt


@pytest.mark.asyncio
async def test_construir_prompt_weather_normal_ignorado():
    """Weather 'normal' não deve aparecer no prompt."""
    prompt = await construir_prompt_cena("Taverna", "tarde", False, weather="normal")
    assert "normal" not in prompt


@pytest.mark.asyncio
async def test_construir_prompt_weather_vazio_ignorado():
    prompt_sem = await construir_prompt_cena("Castelo", "noite", False, weather="")
    prompt_com = await construir_prompt_cena("Castelo", "noite", False, weather="chuva")
    assert "rain" in prompt_com
    assert "rain" not in prompt_sem


@pytest.mark.asyncio
async def test_construir_prompt_contem_qualidade():
    """Prompt deve sempre conter palavras-chave de qualidade de arte fantástica."""
    prompt = await construir_prompt_cena("Dungeon", "meia-noite", False)
    assert "cinematic lighting" in prompt
    assert "no text" in prompt


@pytest.mark.asyncio
async def test_construir_prompt_hora_desconhecida():
    """Hora não mapeada deve aparecer literalmente no prompt."""
    prompt = await construir_prompt_cena("Ilha", "crepúsculo", False)
    assert "crepúsculo" in prompt


# ── Testes de URL e hash ────────────────────────────────────────────────────

def test_url_contem_pollinations():
    url = _montar_url("taverna, noite, fantasy art")
    assert "pollinations.ai" in url


def test_url_contem_prompt_encoded():
    url = _montar_url("taverna, noite, fantasy art")
    # vírgula deve estar encoded — URL não deve ter espaços nem vírgulas cruas
    assert "taverna" in url
    assert " " not in url  # URL encode aplicado


def test_url_parametros_coretos():
    url = _montar_url("floresta")
    assert "width=1024" in url
    assert "height=576" in url
    assert "model=flux" in url
    assert "nologo=true" in url


def test_hash_deterministico():
    """Mesmo input → mesmo hash (idempotência)."""
    assert _prompt_hash("abc") == _prompt_hash("abc")


def test_hash_diferente_para_inputs_distintos():
    assert _prompt_hash("abc") != _prompt_hash("xyz")


def test_hash_tamanho_fixo():
    """Hash deve ter exatamente 12 chars em qualquer input."""
    assert len(_prompt_hash("qualquer coisa")) == 12
    assert len(_prompt_hash("")) == 12
    assert len(_prompt_hash("a" * 1000)) == 12


# ── Testes de cache via mock ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gerar_e_enviar_usa_cache(monkeypatch):
    """Segunda chamada com mesma cache_key não deve chamar httpx."""
    import engine.image.scene_image as m

    # Pré-popula cache diretamente
    chave = m._prompt_hash("test-key")
    url_fake = "https://image.pollinations.ai/prompt/fake?width=1024&height=576"
    m._cache[chave] = url_fake

    enviados: list[str] = []

    class FakeWS:
        async def send_text(self, text: str) -> None:
            enviados.append(text)

    await m.gerar_e_enviar_imagem(FakeWS(), "irrelevante", "test-key")  # type: ignore[arg-type]

    assert len(enviados) == 1
    assert url_fake in enviados[0]
    assert '"tipo":"scene_image"' in enviados[0]

    # Limpa cache após o teste para não vazar entre testes
    del m._cache[chave]


@pytest.mark.asyncio
async def test_gerar_e_enviar_falha_silenciosa_em_erro_http(monkeypatch):
    """Erro de rede deve ser silencioso — não propagar exceção."""
    import httpx
    import engine.image.scene_image as m

    async def _head_falha(*args, **kwargs):
        raise httpx.ConnectError("conexão recusada")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def head(self, url: str):
            raise httpx.ConnectError("conexão recusada")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: FakeClient())

    class FakeWS:
        async def send_text(self, text: str) -> None:
            raise AssertionError("não deve ser chamado")

    # Não deve levantar exceção
    await m.gerar_e_enviar_imagem(FakeWS(), "prompt qualquer", "key-inexistente-xyz")  # type: ignore[arg-type]
