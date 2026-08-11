"""
COMBATE-NAO-TERMINA-1 (playtest 11/08) — o fim da luta vira FATO pro modelo.

Por que existe: a engine encerrou o combate no golpe das 22:25:28
    (`combate_engine_resolveu ... fim=True`, e `sair_combate()` rodou), mas a
    instrução de narração daquele mesmo turno continuava dizendo "narre este
    turno de combate". O modelo não tinha COMO saber que a luta acabou — o
    histórico inteiro é de briga — e seguiu narrando combate até o jogador
    escrever "Desisto, vou morrer".
Dependências: nenhuma (lê o fonte).
Armadilha: estado que muda sem virar FATO para o modelo é estado que não existe
    do lado de lá. `em_combate=False` conserta o PRÓXIMO turno; o turno em que a
    luta acaba precisa dizer, em palavras, que acabou.

Exemplo:
    uv run pytest tests/test_fim_de_combate.py -q
"""

import ast
from pathlib import Path

_WS = (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")


def test_o_fim_de_combate_muda_a_instrucao_de_narracao():
    i = _WS.index('log.info(\n        "combate_engine_resolveu"')
    bloco = _WS[i:i + 2600]
    assert "O COMBATE ACABOU" in bloco, (
        "sem dizer que acabou, o modelo continua narrando luta — foi o loop de "
        "fala que fez o jogador desistir no playtest de 11/08"
    )


def test_a_instrucao_de_fim_proibe_continuar_a_luta():
    """Não basta anunciar o fim: o modelo precisa saber o que NÃO fazer."""
    i = _WS.index("O COMBATE ACABOU")
    bloco = _WS[i:i + 500]
    for proibido in ("iniciativa", "inimigo agindo"):
        assert proibido in bloco, proibido


def test_o_estado_tambem_sai_de_combate():
    """As duas metades: o estado fecha E o modelo é avisado."""
    i = _WS.index('log.info(\n        "combate_engine_resolveu"')
    assert "sair_combate()" in _WS[max(0, i - 700):i + 400]


def test_o_turno_normal_de_combate_nao_foi_alterado():
    """O caminho comum (luta continua) tem que seguir igual."""
    assert "Narre este turno de combate dando corpo às decisões da" in _WS


def test_o_fim_e_um_ramo_proprio_nao_uma_frase_concatenada():
    """Checa o CÓDIGO, não o texto: dois `return` distintos sob o mesmo `if`.

    Assertar sobre a string acusaria o comentário que explica a mudança — a
    armadilha que já apareceu cinco vezes neste projeto.
    """
    arvore = ast.parse(_WS)
    achou = False
    for no in ast.walk(arvore):
        if isinstance(no, ast.If) and isinstance(no.test, ast.Name) and no.test.id == "_fim":
            if any(isinstance(f, ast.Return) for f in no.body):
                achou = True
    assert achou, "o fim de combate precisa ter seu próprio return"
