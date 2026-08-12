"""
FEATURE-DEPENDE-DO-LLM-1 (playtest 11/08) — a engine vê a Fúria sendo usada.

Por que existe: o jogador disse *"vou aproveitar pra usar Fúria e usar Reckless
    Attack"* e o evento `feature_gasta` aparece ZERO vezes na sessão inteira.
    Gastar feature dependia de o LLM emitir `[FEATURE_GASTA: rage]`, e ele não
    emitiu — o Bárbaro terminou a luta com as três fúrias intactas depois de usar
    duas. Recurso que só some quando o modelo lembra é decoração.
Dependências: nenhuma (função pura + estado).
Armadilha: o marcador CONTINUA existindo e continua certo — ele responde "o que
    aconteceu", não "quanto". A detecção SOMA a ele, e por isso precisa de guard
    contra cobrança DUPLA: o jogador declara na fala, o Mestre narra e emite o
    marcador, e sem o guard a fúria sumiria em dobro.

Exemplo:
    uv run pytest tests/test_feature_uso.py -q
"""

import ast
from pathlib import Path

from engine.memory.working_memory import WorkingMemory
from engine.state.feature_uso import (
    detectar_feature,
    detectar_features,
    gastar_feature,
    linha_de_feature,
    pode_usar,
)


def _barbaro() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class="Bárbaro", player_level=3,
    )


# ══ Detecção ═════════════════════════════════════════════════════════════════


def test_a_fala_literal_do_playtest_detecta_AS_DUAS_features():
    """"usar Fúria E usar Reckless Attack" — duas num fôlego. Devolver uma
    cobraria metade do que ele fez."""
    wm = _barbaro()
    achadas = detectar_features(
        "Eu vou aproveitar pra usar Fúria e usar Reckless Attack e eu parto pra cima",
        wm.class_features,
    )
    assert achadas == ["rage", "reckless-attack"]


def test_entende_apelido_em_portugues_e_em_ingles():
    """A mesa brasileira fala metade em inglês — ele disse os dois na mesma frase."""
    wm = _barbaro()
    assert detectar_feature("entro em raiva", wm.class_features) == "rage"
    assert detectar_feature("vou usar reckless", wm.class_features) == "reckless-attack"
    assert detectar_feature("ativo o ataque imprudente", wm.class_features) == "reckless-attack"


def test_exige_verbo_de_uso():
    """Sem isso, "a fúria dele era lendária" gastaria um recurso."""
    wm = _barbaro()
    assert detectar_features("a fúria dele era lendária", wm.class_features) == []


def test_estado_continuo_NAO_e_ativacao():
    """"enquanto eu tô em fúria" descreve uma fúria JÁ ativa — cobrar ali seria
    gastar o recurso duas vezes pela mesma ativação."""
    wm = _barbaro()
    assert detectar_features("ataco enquanto eu tô em fúria", wm.class_features) == []


def test_feature_de_outra_classe_nao_e_detectada():
    """O Bárbaro não tem Action Surge — a ficha é a lista, igual à magia."""
    wm = _barbaro()
    assert detectar_features("uso action surge", wm.class_features) == []


# ══ Gasto ════════════════════════════════════════════════════════════════════


def test_furia_gasta_ate_esgotar():
    wm = _barbaro()
    f = wm.class_features
    assert [gastar_feature(f, "rage")["restantes"] for _ in range(3)] == [2, 1, 0]
    esgotada = gastar_feature(f, "rage")
    assert esgotada["gastou"] is False and esgotada["esgotada"] is True
    assert pode_usar(f, "rage") is False


def test_feature_ilimitada_nao_gasta_e_isso_e_CERTO():
    """Reckless Attack é "sempre que quiser" no SRD. `gastou=False` ali é a
    resposta correta, não uma falha — e o Mestre ainda recebe o fato."""
    wm = _barbaro()
    fato = gastar_feature(wm.class_features, "reckless-attack")
    assert fato["gastou"] is False
    assert fato["restantes"] == -1
    assert "ilimitado" in linha_de_feature(fato)


def test_a_linha_avisa_quando_nao_ha_mais_usos():
    wm = _barbaro()
    for _ in range(3):
        gastar_feature(wm.class_features, "rage")
    assert "NÃO está disponível" in linha_de_feature(gastar_feature(wm.class_features, "rage"))


# ══ O guard de cobrança dupla ════════════════════════════════════════════════


def test_o_websocket_registra_o_que_cobrou_no_turno():
    _ws = (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")
    assert "detectar_features(" in _ws
    assert "features_gastas_no_turno.add(" in _ws
    assert "features_gastas_no_turno.clear()" in _ws, (
        "sem limpar por turno, o guard vira permanente e o marcador nunca mais cobra"
    )


def test_o_marcador_pula_o_que_a_fala_ja_cobrou():
    """Checa o CÓDIGO via AST: o `continue` tem que estar sob o `if` do guard."""
    fonte = (Path(__file__).resolve().parents[1] / "api/turn_pipeline.py")
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))
    achou = False
    for no in ast.walk(arvore):
        if isinstance(no, ast.If) and "features_gastas_no_turno" in ast.dump(no.test):
            achou = any(isinstance(f, ast.Continue) for f in no.body)
    assert achou, "o marcador precisa PULAR a feature já cobrada na fala"


def test_o_campo_do_guard_nasce_vazio_e_nao_persiste():
    wm = _barbaro()
    assert wm.features_gastas_no_turno == set()
