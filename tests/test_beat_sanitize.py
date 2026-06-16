"""
Testes do sanitizador de narração do beat de inimigo (BEAT-MARKER-LEAK-1, 16/06).

Por que existe: o beat roda no 8B, que emite marcadores meio-formatados como prosa
    ("DANO: machadinha [6 - CA]. ... 14/20 HP."). strip_marcadores não pega isso
    (não é `[DANO: ...]` bem-formado) e o TTS lia em voz alta. Estes testes travam a
    higienização antes do TTS.
Dependências: pytest
Armadilha: o sanitizador NÃO pode comer narração legítima — só os vazamentos.

Exemplo:
    pytest tests/test_beat_sanitize.py -q
"""

from api.websocket import _sanitizar_texto_beat


def test_remove_dano_cru_e_hp_do_log_real():
    """Caso EXATO do playtest #6 (log 21:29:50)."""
    bruto = (
        "DANO: machadinha [6 - CA]. Shaw Lothon agora tem 14/20 HP.\n\n"
        "Na tensão do momento, o Homem prepara-se para outro ataque."
    )
    limpo = _sanitizar_texto_beat(bruto)
    assert "DANO" not in limpo
    assert "14/20" not in limpo
    assert "[" not in limpo and "]" not in limpo
    assert "Na tensão do momento, o Homem prepara-se para outro ataque." in limpo


def test_remove_colchete_orfao():
    limpo = _sanitizar_texto_beat("O golpe rasga o ombro dele [6 - CA] e ele recua.")
    assert "[" not in limpo and "]" not in limpo
    assert "O golpe rasga o ombro dele" in limpo
    assert "ele recua." in limpo


def test_remove_vazamento_hp_pv():
    limpo = _sanitizar_texto_beat("Ele te atinge e você fica com 8/20 PV. Sangue escorre.")
    assert "8/20" not in limpo
    assert "Sangue escorre." in limpo


def test_narracao_limpa_passa_intacta():
    """Sem vazamento, o texto não pode ser alterado."""
    bom = (
        "O Homem avança com a lâmina erguida, os olhos cheios de ódio. "
        "A madeira range sob os pés dele enquanto procura uma brecha."
    )
    assert _sanitizar_texto_beat(bom) == bom


def test_nao_come_numero_de_dano_narrativo_sem_keyword():
    """Número solto em narração (sem keyword/HP) não é vazamento — preservar."""
    txt = "Três passos o separam de você."
    assert _sanitizar_texto_beat(txt) == txt


def test_resultado_vazio_quando_so_havia_marcador():
    """Só vazamento → string vazia (o beat pula o turno em vez de falar lixo)."""
    assert _sanitizar_texto_beat("DANO: -6 machadinha") == ""
