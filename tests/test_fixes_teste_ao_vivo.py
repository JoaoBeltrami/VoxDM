"""Testes dos fixes do teste ao vivo 09-10/06 (sess-55df1ce230a1, 75 turnos).

Cobre os 5 fixes de causa-raiz do Lote A + calibração de pacing:
- COMBAT-GHOST-2: ataque do jogador zera o contador de combate-fantasma
- FEATURE_GASTA: marker LLM→engine para gastar class features
- BESTIARY-SRD-1: índice placeholder "srd" não vira lookup; negative-cache
- STT-NOMES-1: vocabulário do módulo (hotwords) contém os nomes próprios
- TTS-MIN-1: fragmento sem conteúdo falável não chega ao Edge TTS
- Pacing decay pós-combate mais agressivo (pinava em 10 por 40min)

Dependências: pytest, pytest-asyncio.
"""

import pytest

from api.turn_pipeline import _RE_FEATURE_GASTA, aplicar_pos_turno
from engine.memory.working_memory import WorkingMemory


def _wm_combate_sem_inimigos() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("estrada", "Estrada", "sess-test")
    wm.entrar_combate()
    assert wm.em_combate and not wm.inimigos_combate
    return wm


# ── COMBAT-GHOST-2 ────────────────────────────────────────────────────────────


def test_ataque_do_jogador_zera_contador_de_combate_fantasma():
    """'Ataco ele' (pronome → sem inimigo registrado) NÃO pode expirar o combate.

    Bug do teste ao vivo: 4 turnos de luta real contra 'o cavaleiro' encerraram
    o combate no meio ('combate_encerrado_sem_inimigos_vivos') porque nenhum
    inimigo fora registrado e cada turno incrementava o contador.
    """
    wm = _wm_combate_sem_inimigos()
    for _ in range(6):  # bem além do threshold de 4
        aplicar_pos_turno(wm, "Eu ataco ele e tento matar ele.", "A lâmina corta o ar.")
    assert wm.em_combate, "combate legítimo expirou enquanto o jogador atacava"
    assert wm.rodadas_sem_acao_inimigo == 0


def test_combate_fantasma_sem_acao_ainda_expira():
    """Sem verbo de ataque (cena migrou pra conversa), o guard continua expirando."""
    wm = _wm_combate_sem_inimigos()
    for _ in range(4):
        aplicar_pos_turno(wm, "Eu olho ao redor procurando uma saída.", "O salão está vazio.")
    assert not wm.em_combate


# ── FEATURE_GASTA ─────────────────────────────────────────────────────────────


def _wm_com_feature() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.class_features = {
        "action-surge": {"nome": "Action Surge", "usos_max": 1, "usos_atual": 1,
                         "disponivel": True, "restaura": "short"},
        "sneak-attack": {"nome": "Sneak Attack", "usos_max": -1, "usos_atual": -1,
                         "disponivel": True, "restaura": ""},
    }
    return wm


def test_regex_feature_gasta():
    m = _RE_FEATURE_GASTA.search("Você canaliza tudo. [FEATURE_GASTA: action-surge]")
    assert m is not None and m.group(1) == "action-surge"


def test_feature_gasta_decrementa_uso():
    wm = _wm_com_feature()
    aplicar_pos_turno(wm, "Uso meu Action Surge!", "Você explode em velocidade. [FEATURE_GASTA: action-surge]")
    feat = wm.class_features["action-surge"]
    assert feat["usos_atual"] == 0
    assert feat["disponivel"] is False


def test_feature_gasta_nao_fica_negativa():
    wm = _wm_com_feature()
    wm.class_features["action-surge"]["usos_atual"] = 0
    wm.class_features["action-surge"]["disponivel"] = False
    aplicar_pos_turno(wm, "De novo!", "[FEATURE_GASTA: action-surge]")
    assert wm.class_features["action-surge"]["usos_atual"] == 0


def test_feature_gasta_ilimitada_e_noop():
    wm = _wm_com_feature()
    aplicar_pos_turno(wm, "Ataque furtivo.", "[FEATURE_GASTA: sneak-attack]")
    assert wm.class_features["sneak-attack"]["usos_atual"] == -1  # intocada


# ── BESTIARY-SRD-1 / PERF-1 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bestiario_indice_placeholder_nao_consulta_rede(monkeypatch):
    """'srd' literal sem nome → None imediato, sem tocar o cliente Qdrant."""
    from engine.bestiary import bestiary

    chamadas = {"n": 0}

    def _cliente_proibido():
        chamadas["n"] += 1
        raise AssertionError("não deveria criar cliente para índice placeholder")

    monkeypatch.setattr(bestiary, "_obter_cliente", _cliente_proibido)
    assert await bestiary.buscar_ficha_monstro(srd_index="srd", nome="") is None
    assert await bestiary.buscar_ficha_monstro(srd_index="", nome="") is None
    assert chamadas["n"] == 0


@pytest.mark.asyncio
async def test_bestiario_placeholder_cai_pro_slug_do_nome(monkeypatch):
    """srd_index='srd' + nome='Goblin' → consulta com índice 'goblin' (não 'srd')."""
    from engine.bestiary import bestiary

    consultas: list[str] = []

    class _FakeCliente:
        async def buscar(self, query, colecao, top_k, filtro, score_threshold):
            consultas.append(filtro["source_id"])
            return [{"text": "Goblin — CA 15 | PV 7"}]

    monkeypatch.setattr(bestiary, "_obter_cliente", lambda: _FakeCliente())
    bestiary._indices_sem_ficha.clear()
    ficha = await bestiary.buscar_ficha_monstro(srd_index="srd", nome="Goblin")
    assert ficha == "Goblin — CA 15 | PV 7"
    assert consultas == ["goblin"]


@pytest.mark.asyncio
async def test_bestiario_miss_e_cacheado(monkeypatch):
    """Primeiro miss consulta; segundo retorna None sem nova ida ao Qdrant."""
    from engine.bestiary import bestiary

    chamadas = {"n": 0}

    class _FakeCliente:
        async def buscar(self, **kw):
            chamadas["n"] += 1
            return []

    monkeypatch.setattr(bestiary, "_obter_cliente", lambda: _FakeCliente())
    bestiary._indices_sem_ficha.discard("guarda-patrulha")
    assert await bestiary.buscar_ficha_monstro(nome="Guarda Patrulha") is None
    assert await bestiary.buscar_ficha_monstro(nome="Guarda Patrulha") is None
    assert chamadas["n"] == 1, "miss deveria ter sido cacheado após a 1ª consulta"


# ── STT-NOMES-1 ───────────────────────────────────────────────────────────────


def test_vocabulario_modulo_contem_nomes_proprios():
    from engine.voice import stt

    stt._VOCAB_MODULO = None  # força rebuild (cache module-level)
    vocab = stt._vocabulario_modulo()
    assert "Tharnvik" in vocab, "cidade do módulo ausente das hotwords do Whisper"
    assert "Drevamor" in vocab
    assert len(vocab) <= 600


# ── TTS-MIN-1 ─────────────────────────────────────────────────────────────────


class _TTSEspiao:
    def __init__(self) -> None:
        self.chamadas: list[str] = []

    async def sintetizar(self, texto: str, **kw) -> bytes:
        self.chamadas.append(texto)
        return b"mp3"


@pytest.mark.asyncio
async def test_fragmento_sem_conteudo_nao_chega_ao_tts():
    from api.websocket import _sintetizar_com_timeout

    tts = _TTSEspiao()
    assert await _sintetizar_com_timeout(tts, "…", 5.0) == b""
    assert await _sintetizar_com_timeout(tts, "!", 5.0) == b""
    assert await _sintetizar_com_timeout(tts, " ", 5.0) == b""
    assert tts.chamadas == []
    # Texto real continua passando
    assert await _sintetizar_com_timeout(tts, "Você avança.", 5.0) == b"mp3"
    assert tts.chamadas == ["Você avança."]


# ── Pacing decay pós-combate ──────────────────────────────────────────────────


def test_pacing_decai_firme_apos_combate():
    """Pós-combate era -0.5/turno: pacing 10 levava 14 turnos pra normalizar e
    mantinha markers/climax ativos a sessão toda. Agora -1.5."""
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.pacing_nivel = 10.0
    wm.saiu_combate_recentemente = True
    aplicar_pos_turno(wm, "Respiro fundo e olho ao redor.", "A poeira assenta.")
    assert wm.pacing_nivel == pytest.approx(8.5)
