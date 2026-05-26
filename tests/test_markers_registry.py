"""Testes da tabela canônica de marcadores em engine/markers.py.

Por que existe: refactor D4 (26/05) centralizou nomes de markers numa
tupla única. Esta suite garante que:
1. Todos os nomes da tabela são stripados pelo RE_STRIP_MARCADORES.
2. Caso especial "Rolagem visível" segue stripado (não está na tabela).
3. Marcadores fora da tabela não são stripados (não-falso-positivo).
4. Imports legados (_RE_MESTRE_VET em quest_detector) continuam funcionando.
"""

import pytest

from engine.markers import NOMES_MARCADORES, RE_STRIP_MARCADORES


@pytest.mark.parametrize("nome", NOMES_MARCADORES)
def test_cada_nome_canonico_e_stripado(nome: str):
    """Cada nome da tabela deve casar no regex de strip — com :, com =, ou seco."""
    for sufixo in (":", "=", ""):
        texto = f"narração [{nome}{sufixo} qualquer coisa]"
        limpo = RE_STRIP_MARCADORES.sub("", texto).strip()
        assert limpo == "narração", f"falha em [{nome}{sufixo} ...] → '{limpo}'"


def test_rolagem_visivel_caso_especial():
    texto = "atinge o orc [Rolagem visível: d20=18] em cheio"
    limpo = RE_STRIP_MARCADORES.sub("", texto).strip()
    # Strip pode deixar espaço duplo entre palavras — normaliza pra checar conteúdo
    limpo = " ".join(limpo.split())
    assert limpo == "atinge o orc em cheio"


def test_marker_inventado_nao_e_stripado():
    """Markers fora da tabela não devem ser removidos — protege contra
    strip excessivo se LLM emitir [FOO: ...] por engano."""
    texto = "narração [MARCADORDESCONHECIDO: x] e mais"
    assert RE_STRIP_MARCADORES.sub("", texto) == texto


def test_case_insensitive():
    """Strip deve casar independente de capitalização."""
    for variante in ("[fio: x]", "[Fio: x]", "[FIO: x]", "[fIo: x]"):
        assert RE_STRIP_MARCADORES.sub("", variante) == ""


def test_multiplos_markers_na_mesma_linha():
    texto = "[FIO: a] entre [XP: +10] e [ANCORA: c] texto"
    limpo = " ".join(RE_STRIP_MARCADORES.sub("", texto).split())
    assert limpo == "entre e texto"


def test_compat_re_mestre_vet():
    """Re-export _RE_MESTRE_VET em quest_detector ainda funciona."""
    from engine.memory.quest_detector import _RE_MESTRE_VET
    assert _RE_MESTRE_VET is RE_STRIP_MARCADORES
