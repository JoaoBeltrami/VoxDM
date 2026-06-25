"""
Testes do anti-repetição do clima no prompt de cena (FRIO-DREVAMOR-1).

Por que existe: o clima estático do local (weather="frio" fixo) era injetado como
"Clima: frio" em TODO turno via SceneState.to_prompt(), re-primando o clichê que o
master_system.md proíbe — no playtest #6 o Mestre dizia "o frio de Drevamor" a cada
resposta. O fix surfaça o clima UMA vez (ao chegar no local ou quando o clima muda
de fato) e o suprime nos turnos seguintes; a Hora (que muda) permanece sempre.

Armadilha: to_prompt() pode rodar mais de uma vez por turno (prompt + rolling
summary); por isso a chave é idempotente por "local|clima" — repetir a chamada no
mesmo local/clima não re-mostra o clima.
"""

from engine.state.scene import SceneState


def _cena(weather: str = "frio") -> SceneState:
    return SceneState(
        location_id="drevamor",
        location_nome="Drevamor",
        time_of_day="Noite",
        weather=weather,
    )


def test_clima_aparece_na_primeira_vez():
    cena = _cena("frio")
    p = cena.to_prompt()
    assert "Clima: frio" in p
    assert "Hora: Noite" in p


def test_clima_some_no_segundo_turno_mesmo_local():
    cena = _cena("frio")
    cena.to_prompt()                 # 1º turno — clima estabelecido
    p2 = cena.to_prompt()            # 2º turno — não re-prima
    assert "Clima: frio" not in p2
    assert "Hora: Noite" in p2       # hora permanece sempre


def test_clima_reaparece_quando_clima_muda():
    cena = _cena("frio")
    cena.to_prompt()                 # estabelece "frio"
    cena.weather = "tempestade"      # clima mudou de fato
    p = cena.to_prompt()
    assert "Clima: tempestade" in p  # mudança real volta ao prompt


def test_clima_reaparece_ao_trocar_de_local():
    cena = _cena("frio")
    cena.to_prompt()                 # estabelece frio em drevamor
    cena.location_id = "vila-quente"
    cena.weather = "frio"            # mesmo clima, OUTRO local → re-mostra
    p = cena.to_prompt()
    assert "Clima: frio" in p


def test_clima_vazio_nunca_quebra():
    cena = _cena("")
    p = cena.to_prompt()
    assert "Clima:" not in p         # sem clima, sem linha de clima
    assert "Hora: Noite" in p


def test_chamada_repetida_no_mesmo_turno_e_idempotente():
    """Rolling summary + prompt no mesmo turno não devem divergir absurdamente:
    a 2ª chamada (mesma chave local|clima) já não re-mostra o clima."""
    cena = _cena("frio")
    p1 = cena.to_prompt()
    p2 = cena.to_prompt()
    assert "Clima: frio" in p1
    assert "Clima: frio" not in p2   # idempotente por local|clima
