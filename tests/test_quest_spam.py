"""
Testes da barra anti-spam de quests improvisadas (QUEST-SPAM-1, playtest #6).

Por que existe: no playtest #6 o extractor (8B) virou CADA reação de conversa em
    "missão" — responder-o-homem, abordar-o-homem, acalmar-a-situacao,
    responder-taverneiro — poluindo a crônica. A barra determinística no
    _sanitizar_quests descarta reações imediatas; só objetivo perseguível passa.
Dependências: pytest
Armadilha: a barra NÃO pode descartar missão legítima (encontrar/investigar algo).

Exemplo:
    pytest tests/test_quest_spam.py -q
"""

import pytest

from engine.llm.extractor import _quest_reativa, _sanitizar_quests


@pytest.mark.parametrize("qid,titulo", [
    ("responder-o-homem", "Responder o Homem"),
    ("abordar-o-homem", "Abordar o Homem"),
    ("acalmar-a-situacao", "Acalmar a situação"),
    ("responder-taverneiro", "Responder o taverneiro"),
    ("cumprimentar-a-guarda", "Cumprimentar a guarda"),
    ("decidir-o-proximo-passo", "Decidir o próximo passo"),
])
def test_reativas_sao_descartadas(qid, titulo):
    assert _quest_reativa(qid, titulo) is True


@pytest.mark.parametrize("qid,titulo", [
    ("encontrar-o-ferreiro", "Encontrar o ferreiro sumido"),
    ("investigar-as-luzes-na-torre", "Investigar as luzes na torre"),
    ("recuperar-o-cajado", "Recuperar o Cajado de Valdrek"),
    ("escoltar-a-caravana", "Escoltar a caravana até Kaelmund"),
])
def test_objetivos_reais_passam(qid, titulo):
    assert _quest_reativa(qid, titulo) is False


def test_sanitizar_filtra_so_as_reativas():
    bruto = {
        "novas": [
            {"id": "responder-o-homem", "titulo": "Responder o Homem", "objetivo": "x"},
            {"id": "encontrar-o-ferreiro", "titulo": "Encontrar o ferreiro", "objetivo": "y"},
            {"id": "acalmar-a-situacao", "titulo": "Acalmar a situação", "objetivo": "z"},
        ],
        "concluidas": [],
    }
    out = _sanitizar_quests(bruto, set())
    ids = [q["id"] for q in out["novas"]]
    assert ids == ["encontrar-o-ferreiro"]


def test_sanitizar_preserva_dedup_e_ids_abertos():
    """A barra nova não pode quebrar o dedup/ids_abertos existente."""
    bruto = {
        "novas": [
            {"id": "encontrar-o-ferreiro", "titulo": "Encontrar", "objetivo": ""},
            {"id": "encontrar-o-ferreiro", "titulo": "dup", "objetivo": ""},
            {"id": "investigar-a-cripta", "titulo": "Investigar a cripta", "objetivo": ""},
        ],
        "concluidas": ["resgatar-mira"],
    }
    out = _sanitizar_quests(bruto, {"investigar-a-cripta", "resgatar-mira"})
    ids = [q["id"] for q in out["novas"]]
    assert ids == ["encontrar-o-ferreiro"]          # dedup + já-aberta filtrados
    assert out["concluidas"] == ["resgatar-mira"]   # concluída válida preservada
