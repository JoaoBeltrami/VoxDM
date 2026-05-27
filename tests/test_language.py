"""Testes do detector de idioma — engine/voice/language.py.

Por que existe: bug TTS-LANG-1 (26/05) — sentenças que começam com marcadores
técnicos `[Rolagem: d20 = 18]` eram detectadas como EN porque `d20` é neutro
e nada mais batia em PT-BR. TTS pronunciava errado palavras curtas.
"""

import pytest

from engine.voice.language import Idioma, detectar_idioma


# ── Casos básicos ────────────────────────────────────────────────────────────


def test_texto_ptbr_simples():
    assert detectar_idioma("Você está em uma sala escura") == Idioma.PTBR


def test_texto_en_simples():
    # Frase sem colisões com artigos/contrações PT-BR ("a", "o", "no", etc.)
    assert detectar_idioma("Where did you go yesterday") == Idioma.EN


def test_texto_en_misto_quando_compartilha_articulo_curto():
    # "a" em EN colide com artigo PT-BR — fica MISTO. Comportamento histórico
    # aceito (TTS escolhe voz PT-BR como fallback, narração soa OK).
    assert detectar_idioma("You are in a dark room") == Idioma.MISTO


def test_texto_vazio():
    assert detectar_idioma("") == Idioma.PTBR
    assert detectar_idioma("   ") == Idioma.PTBR


def test_texto_misto_dnd():
    # PT-BR com termo D&D em inglês ainda é PT-BR
    assert detectar_idioma("Eu lanço Fireball no goblin") == Idioma.PTBR


# ── Fix TTS-LANG-1: marcadores não enviesam ──────────────────────────────────


def test_apenas_marcador_e_ptbr():
    # Sentença que é só marker — sem texto narrativo. PT-BR default
    # (TTS usa voz PT, pronúncia padrão pra números).
    assert detectar_idioma("[Rolagem: d20 = 18]") == Idioma.PTBR


def test_marcador_no_inicio_de_frase_ptbr():
    # Frase real com marker no início — PT-BR domina o resto.
    texto = "[Rolagem: d20 = 14] Tóric te golpeia com força."
    assert detectar_idioma(texto) == Idioma.PTBR


def test_multiplos_marcadores_em_ptbr():
    texto = "[XP: +50 vitória] Você sente o peso da experiência. [FIO: vingança pendente]"
    assert detectar_idioma(texto) == Idioma.PTBR


def test_marcador_com_pontuacao_dentro():
    # Bracket pode conter qualquer caractere — regex tira tudo entre [ e ]
    texto = "[Rolagem visível: d20 = 8] Você falha de raspão."
    assert detectar_idioma(texto) == Idioma.PTBR


def test_marcador_em_texto_en():
    # Inglês com marker continua não-PTBR. "the" não bate; resultado real: EN ou MISTO
    # dependendo de outras palavras. Aceitamos qualquer não-PTBR.
    resultado = detectar_idioma("[XP: +50] Where did you go yesterday")
    assert resultado in (Idioma.EN, Idioma.MISTO)
