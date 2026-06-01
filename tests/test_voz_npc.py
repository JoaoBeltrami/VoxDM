"""
Testes da deteccao de voz de NPC com quote-dominance + tracking de foco.

Cobre:
- _calc_quote_ratio: fracao de chars dentro de aspas (retas e curvas)
- _extrair_atribuicao: padrao 'Nome verbo' / 'verbo Nome' em mesma sentenca
- _detectar_voz_npc: regra de 3 guards (quote-dominance + nome OU pronome+foco)
- _clamp_pitch / _clamp_rate: caps para evitar voz caricata
"""

import pytest

from api.turn_pipeline import _clamp_pitch, _clamp_rate, aplicar_pos_turno
from api.websocket import (
    _calc_quote_ratio,
    _detectar_voz_npc,
    _extrair_atribuicao,
)
from engine.memory.working_memory import WorkingMemory

# ── _calc_quote_ratio ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("texto,esperado_min,esperado_max", [
    ("Sem aspas aqui.", 0.0, 0.0),
    ('"Tudo entre aspas"', 0.85, 1.0),
    ('Narração e "uma fala curta"', 0.40, 0.55),
    ('"Saia daqui," diz Lyssa.', 0.40, 0.55),  # ~48%
    ('Lyssa diz, "cuidado".', 0.30, 0.40),     # ~33% — abaixo do threshold
    ('"Saia," ela responde, "agora mesmo."', 0.45, 0.70),  # 2 trechos
    ("", 0.0, 0.0),  # vazio nao quebra
])
def test_calc_quote_ratio_intervalos(texto, esperado_min, esperado_max):
    ratio = _calc_quote_ratio(texto)
    assert esperado_min <= ratio <= esperado_max, (
        f"texto='{texto}' ratio={ratio:.2f} fora de [{esperado_min}, {esperado_max}]"
    )


def test_calc_quote_ratio_aspas_curvas():
    """Aspas tipograficas (Word) sao normalizadas como aspas retas."""
    texto = '“Saia daqui”, diz Lyssa.'
    assert _calc_quote_ratio(texto) > 0.40


# ── _extrair_atribuicao ────────────────────────────────────────────────────────

@pytest.fixture
def vozes():
    return {
        "lyssa": {"pitch": "+5Hz", "rate": "-10%"},
        "toric": {"pitch": "-5Hz", "rate": "+5%"},
    }


@pytest.mark.parametrize("texto,esperado", [
    ("Lyssa diz, 'cuidado.'", "lyssa"),
    ("Lyssa murmura baixinho.", "lyssa"),
    ("'Saia,' diz Tóric.", "toric"),
    ("Tóric, com a voz baixa, fala.", "toric"),
    ("'Saia,' responde Lyssa.", "lyssa"),
    ("O guarda manda dar a volta.", None),
    ("Lyssa luta com a espada.", None),   # acao, sem verbo de fala
    ("", None),
])
def test_extrair_atribuicao(texto, esperado, vozes):
    assert _extrair_atribuicao(texto, vozes) == esperado


def test_extrair_atribuicao_npc_sem_voz_registrada():
    """NPC mencionado mas sem voz registrada → None."""
    vozes_so_lyssa = {"lyssa": {"pitch": "+5Hz", "rate": "-10%"}}
    assert _extrair_atribuicao("Valdrek diz que nao.", vozes_so_lyssa) is None


# ── _detectar_voz_npc — guard 1 (quote dominance) ──────────────────────────────

def test_detectar_voz_npc_narracao_pura_retorna_none(vozes):
    """Sentenca sem aspas → Mestre voice mesmo com nome de NPC presente."""
    assert _detectar_voz_npc("Lyssa olha pra voce com desconfiança.", vozes) is None
    assert _detectar_voz_npc("Lyssa franze a testa e aperta a espada.", vozes) is None


def test_detectar_voz_npc_atribuicao_curta_retorna_none(vozes):
    """Atribuicao domina (quote < 40%) → Mestre voice."""
    # "OK." dentro de aspas = 3 chars; total ~18 chars; ratio ~17% → Mestre
    assert _detectar_voz_npc('Lyssa diz, "OK."', vozes) is None


# ── _detectar_voz_npc — guard 2a (nome explicito) ──────────────────────────────

def test_detectar_voz_npc_fala_dominante_com_nome(vozes):
    """Aspas >= 40% + nome de NPC → voz dele."""
    texto = '"Saia daqui agora," diz Lyssa.'
    assert _detectar_voz_npc(texto, vozes) == vozes["lyssa"]


def test_detectar_voz_npc_fala_dominante_npc_diferente(vozes):
    """Quote dominante + nome de Tóric → voz do Tóric."""
    texto = '"Cuidado com Valdrek," murmura Tóric, baixo.'
    assert _detectar_voz_npc(texto, vozes) == vozes["toric"]


def test_detectar_voz_npc_fala_inteira_aspas(vozes):
    """Sentenca quase 100% aspas (sem atribuicao) — primeiro NPC encontrado."""
    texto = '"Lyssa, voce nao deveria estar aqui agora."'
    # Contém "lyssa" no texto → match guard 2a
    assert _detectar_voz_npc(texto, vozes) == vozes["lyssa"]


# ── _detectar_voz_npc — guard 2b (pronome + npc_em_foco) ───────────────────────

def test_detectar_voz_npc_pronome_com_foco(vozes):
    """'ela diz' + npc_em_foco='lyssa' → voz da Lyssa."""
    texto = '"Voce nao deveria estar aqui," ela diz com calma.'
    assert _detectar_voz_npc(texto, vozes, npc_em_foco="lyssa") == vozes["lyssa"]


def test_detectar_voz_npc_pronome_sem_foco_retorna_none(vozes):
    """'ela diz' sem npc_em_foco setado → None (Mestre seguro)."""
    texto = '"Voce nao deveria estar aqui," ela diz com calma.'
    assert _detectar_voz_npc(texto, vozes, npc_em_foco=None) is None


def test_detectar_voz_npc_pronome_com_foco_invalido(vozes):
    """npc_em_foco aponta pra NPC sem voz registrada → None."""
    texto = '"Cuidado," ela murmura.'
    assert _detectar_voz_npc(texto, vozes, npc_em_foco="valdrek") is None


def test_detectar_voz_npc_vozes_vazias_retorna_none():
    """Sem nenhuma voz registrada → None (mesmo com sentenca perfeita)."""
    texto = '"Saia daqui," diz Lyssa.'
    assert _detectar_voz_npc(texto, {}, npc_em_foco=None) is None


# ── _clamp_pitch / _clamp_rate ─────────────────────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [
    ("+5Hz", "+5Hz"),       # dentro do cap → preservado
    ("-8Hz", "-8Hz"),
    ("+20Hz", "+10Hz"),     # cap superior
    ("-30Hz", "-10Hz"),     # cap inferior
    ("0Hz", "+0Hz"),        # zero normaliza pra +0
    ("malformado", "malformado"),  # passa intacto se nao casar regex
])
def test_clamp_pitch(entrada, esperado):
    assert _clamp_pitch(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("+10%", "+10%"),
    ("-12%", "-12%"),
    ("+25%", "+15%"),       # cap superior
    ("-30%", "-15%"),       # cap inferior
    ("0%", "+0%"),
    ("foo", "foo"),
])
def test_clamp_rate(entrada, esperado):
    assert _clamp_rate(entrada) == esperado


# ── Integracao com [VOZ:] em aplicar_pos_turno ────────────────────────────────

def test_voz_npc_clampada_no_registro():
    """[VOZ: id|+25Hz|-40%] eh armazenado clampado em wm.npc_vozes."""
    wm = WorkingMemory.nova_sessao("loc", "Local", "sess-voz-clamp")
    aplicar_pos_turno(wm, "t", 'Lyssa fala. [VOZ: lyssa|+25Hz|-40%]')
    assert wm.npc_vozes["lyssa"]["pitch"] == "+10Hz"
    assert wm.npc_vozes["lyssa"]["rate"] == "-15%"


def test_voz_npc_sem_clamp_passa_intacto():
    """Valores dentro dos caps sao preservados exatamente."""
    wm = WorkingMemory.nova_sessao("loc", "Local", "sess-voz-ok")
    aplicar_pos_turno(wm, "t", 'Toric fala. [VOZ: toric|-5Hz|+8%]')
    assert wm.npc_vozes["toric"]["pitch"] == "-5Hz"
    assert wm.npc_vozes["toric"]["rate"] == "+8%"
