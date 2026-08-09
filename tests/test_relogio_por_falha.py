"""
P7 — falhar num teste move o mundo.

Por que existe: os quatro gatilhos de relógio que existiam mediam TEMPO (viagem,
    descanso longo) ou NARRAÇÃO (marcador `[RELOGIO_AVANCA]`, efeito de quest).
    Nenhum media o jogador ERRANDO — falhar num teste doía só na cena e o mundo
    seguia parado. É o gatilho que serve o gate aberto da Camada 2 ("minhas
    escolhas podem dar errado").
Dependências: nenhuma (estado puro, sem I/O).
Armadilha: a cadência (N falhas por fatia) não é decoração. No playtest de 24/06
    ticar a cada evento encheu a ameaça rápido demais, e foi por isso que o tick
    de VIAGEM ganhou cadência 2. Uma sessão tem dezenas de testes e boa parte
    falha — 1:1 estouraria todo relógio numa sessão.

Exemplo:
    uv run pytest tests/test_relogio_por_falha.py -q
"""

from engine.state.narrative import _FALHAS_POR_FATIA, NarrativeState


def _com_relogio(segmentos: int = 6) -> NarrativeState:
    n = NarrativeState()
    n.criar_relogio("ritual", "Ritual do Culto", segmentos=segmentos)
    return n


# ── O gatilho existe e tem cadência ──────────────────────────────────────────


def test_falhas_abaixo_da_cadencia_nao_movem_nada():
    n = _com_relogio()
    for _ in range(_FALHAS_POR_FATIA - 1):
        assert n.tick_relogios_falha() == []
    assert n.relogios["ritual"]["atual"] == 0


def test_a_enesima_falha_move_uma_fatia():
    n = _com_relogio()
    for _ in range(_FALHAS_POR_FATIA):
        n.tick_relogios_falha()
    assert n.relogios["ritual"]["atual"] == 1


def test_o_contador_zera_e_a_cadencia_se_repete():
    n = _com_relogio()
    for _ in range(_FALHAS_POR_FATIA * 2):
        n.tick_relogios_falha()
    assert n.relogios["ritual"]["atual"] == 2


def test_cadencia_e_mais_lenta_que_a_de_viagem():
    """Viagem tica a cada 2. Falha é mais conservadora de propósito: uma sessão
    tem dezenas de testes e boa parte falha."""
    assert _FALHAS_POR_FATIA > 2


# ── Relógio cheio dispara uma vez só ─────────────────────────────────────────


def test_relogio_cheio_irrompe_uma_vez():
    # 4 é o MÍNIMO real: `criar_relogio` clampa em [4, 8] desde o playtest de
    # 24/06 ("relógio de ameaça é slow-burn"). Pedir 1 aqui não cria um relógio
    # de 1 fatia — cria um de 4, e o teste passaria a medir outra coisa.
    n = _com_relogio(segmentos=4)
    estourados: list[str] = []
    for _ in range(_FALHAS_POR_FATIA * 4):
        estourados += n.tick_relogios_falha()
    assert estourados == ["Ritual do Culto"]
    # e ele sai da lista — não pode estourar de novo
    assert "ritual" not in n.relogios
    for _ in range(_FALHAS_POR_FATIA * 3):
        assert n.tick_relogios_falha() == []


def test_sem_relogio_o_gatilho_e_inerte():
    """Falhar antes de existir ameaça no mundo não pode quebrar nada."""
    n = NarrativeState()
    for _ in range(_FALHAS_POR_FATIA * 2):
        assert n.tick_relogios_falha() == []


# ── Independência entre gatilhos ─────────────────────────────────────────────


def test_contador_de_falha_nao_mexe_no_de_viagem():
    """Dois contadores separados — senão um gatilho consumiria a cadência do
    outro e o mundo andaria no dobro da velocidade sem ninguém entender por quê."""
    n = _com_relogio()
    n.tick_relogios_falha()
    assert n.viagens_desde_tick_relogio == 0
    n.tick_relogios_viagem()
    assert n.falhas_desde_tick_relogio == 1


def test_falha_e_viagem_somam_no_mesmo_relogio():
    n = _com_relogio()
    for _ in range(_FALHAS_POR_FATIA):
        n.tick_relogios_falha()
    n.tick_relogios_viagem()
    n.tick_relogios_viagem()      # cadência de viagem é 2
    assert n.relogios["ritual"]["atual"] == 2


# ── Sobrevive ao checkpoint (teste que o P7 pede) ────────────────────────────


def test_estado_do_relogio_sobrevive_ao_roundtrip_do_checkpoint():
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.narrative.criar_relogio("ritual", "Ritual do Culto", segmentos=6)
    for _ in range(_FALHAS_POR_FATIA):
        wm.narrative.tick_relogios_falha()

    # O mesmo shape que api/routes/session.py grava, entregue pela mesma porta
    # que a produção usa (`aplicar_character_state` lê `state.dm_state`).
    class _StateFake:
        dm_state = {"relogios": {k: dict(v) for k, v in wm.narrative.relogios.items()}}

    novo = WorkingMemory.nova_sessao(session_id="t2", location_id="x", location_nome="X")
    novo.aplicar_character_state(_StateFake())
    assert novo.narrative.relogios["ritual"]["atual"] == 1
