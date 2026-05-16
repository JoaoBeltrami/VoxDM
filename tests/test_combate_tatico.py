"""Testes para a feature de combate tático (posicionamento + movimento)."""

import pytest

from api.turn_pipeline import aplicar_pos_turno, _RE_POSICAO, _RE_MOVIMENTO
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("dungeon", "Masmorra", "sess-tact")
    wm.entrar_combate()
    return wm


# ── Regex de detecção ────────────────────────────────────────────────────────


def test_re_posicao_simples():
    m = _RE_POSICAO.search("[POSICAO: goblin = 15 ft]")
    assert m is not None
    assert m.group(1) == "goblin"
    assert m.group(2) == "15"
    assert not m.group(3)


def test_re_posicao_com_cobertura():
    m = _RE_POSICAO.search("[POSICAO: orco-arqueiro = 60 ft cobertura]")
    assert m is not None
    assert m.group(1) == "orco-arqueiro"
    assert m.group(3) is not None


def test_re_movimento_simples():
    m = _RE_MOVIMENTO.search("[MOV: -20 ft em direção ao orc]")
    assert m is not None
    assert m.group(1) == "20"
    assert "direção" in m.group(2)


def test_re_movimento_sem_motivo():
    m = _RE_MOVIMENTO.search("[MOV: -10 ft]")
    assert m is not None
    assert m.group(1) == "10"


# ── Métodos da WorkingMemory ────────────────────────────────────────────────


def test_registrar_posicao_basico():
    wm = _wm()
    wm.registrar_posicao("goblin", 15)
    assert wm.posicoes_combate["goblin"]["distancia_ft"] == 15
    assert wm.posicoes_combate["goblin"]["cobertura"] is False


def test_registrar_posicao_com_cobertura():
    wm = _wm()
    wm.registrar_posicao("orco", 60, cobertura=True)
    assert wm.posicoes_combate["orco"]["cobertura"] is True


def test_registrar_posicao_clamp_negativo():
    wm = _wm()
    wm.registrar_posicao("goblin", -10)
    assert wm.posicoes_combate["goblin"]["distancia_ft"] == 0


def test_aplicar_movimento_decrementa():
    wm = _wm()
    consumido = wm.aplicar_movimento(20)
    assert consumido == 20
    assert wm.movimento_restante_ft == 10


def test_aplicar_movimento_clampa_no_restante():
    """Não pode mover além do que sobrou na rodada."""
    wm = _wm()
    wm.movimento_restante_ft = 5
    consumido = wm.aplicar_movimento(30)
    assert consumido == 5
    assert wm.movimento_restante_ft == 0


def test_aplicar_movimento_zero_no_op():
    wm = _wm()
    wm.aplicar_movimento(0)
    assert wm.movimento_restante_ft == 30


def test_avancar_rodada_renova_movimento():
    wm = _wm()
    wm.aplicar_movimento(25)
    assert wm.movimento_restante_ft == 5
    wm.avancar_rodada()
    assert wm.movimento_restante_ft == 30


def test_sair_combate_limpa_posicoes():
    wm = _wm()
    wm.registrar_posicao("goblin", 15)
    wm.aplicar_movimento(20)
    wm.sair_combate()
    assert wm.posicoes_combate == {}
    assert wm.movimento_restante_ft == wm.movimento_total_ft


# ── Pipeline: extração das marcações ────────────────────────────────────────


def test_pipeline_extrai_posicao():
    wm = _wm()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    resposta = "O goblin avança. [POSICAO: goblin = 10 ft]"
    aplicar_pos_turno(wm, "", resposta)
    assert wm.posicoes_combate.get("goblin", {}).get("distancia_ft") == 10


def test_pipeline_extrai_movimento():
    wm = _wm()
    resposta = "Você corre. [MOV: -20 ft em direção ao orc]"
    aplicar_pos_turno(wm, "Corro em direção ao orc.", resposta)
    assert wm.movimento_restante_ft == 10


def test_pipeline_ignora_marcadores_fora_de_combate():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-paz")
    resposta = "Eles seguem. [POSICAO: ferreiro = 20 ft]"
    aplicar_pos_turno(wm, "", resposta)
    # Fora de combate, posições não são extraídas (irrelevantes)
    assert wm.posicoes_combate == {}


def test_strip_marcadores_remove_posicao_e_mov():
    """Tactical markers não devem chegar ao TTS."""
    from engine.memory.quest_detector import strip_marcadores

    texto = "O orco se aproxima. [POSICAO: orco = 5 ft] Você recua. [MOV: -10 ft]"
    limpo = strip_marcadores(texto)
    assert "POSICAO" not in limpo
    assert "MOV" not in limpo
    assert "ft]" not in limpo
    assert "orco se aproxima" in limpo
