"""
Regressão do crash de serialização do combate (playtest 27/06).

Quando o bestiário ACHA uma ficha real e aplica stats numéricos (ca/hp_max/
hp_atual INT) no inimigo, o payload `fim` (MensagemWS.inimigos_combate) tipado
como dict[str, str] estourava ValidationError → WS fechava → loop infinito de
reconexão (inimigo "capuz"=cultist com ca=12, hp=9). O tipo agora aceita o mix.
"""

from api.models.schemas import MensagemWS


def test_inimigo_com_stats_int_serializa_sem_erro():
    # Espelha exatamente o estado que crashou: bestiário aplicou cultist (int).
    msg = MensagemWS(
        tipo="fim",
        em_combate=True,
        inimigos_combate={
            "capuz": {
                "nome": "Homem de Capuz",
                "estado": "intacto",
                "hp_rel": "",
                "ca": 12,        # int — vinha do bestiário
                "hp_max": 9,     # int
                "hp_atual": 9,   # int
            }
        },
    )
    dump = msg.model_dump()
    assert dump["inimigos_combate"]["capuz"]["ca"] == 12
    assert dump["inimigos_combate"]["capuz"]["hp_atual"] == 9
    # round-trip JSON (é o que o websocket faz no send) não pode quebrar
    assert "capuz" in msg.model_dump_json()


def test_inimigo_so_com_campos_str_continua_valido():
    # Inimigo declarado sem bestiário (só nome/estado) — formato antigo, ainda ok.
    msg = MensagemWS(
        tipo="fim",
        em_combate=True,
        inimigos_combate={"goblin": {"nome": "Goblin", "estado": "ferido", "hp_rel": "metade"}},
    )
    assert msg.inimigos_combate["goblin"]["estado"] == "ferido"
