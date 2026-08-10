"""
ATRIBUTOS-DO-INIMIGO (09/08) — ficha melhor passa a valer alguma coisa.

Por que existe: `StatsInimigo` não tinha atributo nenhum. A consequência era
    invisível e grande: o inimigo rolava d20 PURO na iniciativa e nas
    salvaguardas, então uma dragoa CR 17 agia na mesma velocidade de um goblin e
    resistia a uma Bola de Fogo exatamente igual. Dar ficha melhor não mudava
    nada, porque a engine não tinha onde ler.
Dependências: nenhuma (parse puro; RNG injetável).
Armadilha: os atributos precisam ser emitidos por `_ficha_texto` no MESMO
    formato que o bestiário do Qdrant usa ("FOR 26 (+8)"), porque é esse formato
    que `parse_atributos` lê. Emitir diferente faz a engine ignorar em silêncio a
    ficha autoral — que é a classe de bug do BESTIARIO-CR-ERRADO-1.

Exemplo:
    uv run pytest tests/test_atributos_do_inimigo.py -q
"""

import random

from engine.combat.npc_statblocks import (
    STATBLOCKS_SRD,
    ancorar_no_srd,
    limpar_cache,
    resolver_ficha_npc,
    sem_ficha_autoral,
)
from engine.combat.stats import parse_atributos, stats_inimigo
from engine.memory.working_memory import WorkingMemory

_FICHA_QDRANT = (
    "Dragão — CR 17 (18000 XP). CA 19 | PV 256. "
    "FOR 27 (+8) DES 10 (+0) CON 25 (+7) INT 16 (+3) SAB 13 (+1) CAR 21 (+5). "
    "Ataques: mordida +14 (2d10+8)"
)


# ── O parse ──────────────────────────────────────────────────────────────────


def test_le_os_modificadores_da_ficha():
    mods = parse_atributos(_FICHA_QDRANT)
    assert mods == {"for": 8, "des": 0, "con": 7, "int": 3, "sab": 1, "car": 5}


def test_le_modificador_negativo():
    assert parse_atributos("Ogro — CA 11 | PV 59. DES 8 (-1) INT 5 (-3).")["des"] == -1


def test_ficha_sem_atributos_devolve_vazio():
    """Não é erro — é criatura improvisada. Somar zero é honesto."""
    assert parse_atributos("Vulto — CA 12 | PV 9. Ataques: golpe +3 (1d6+1)") == {}
    assert stats_inimigo(ficha="Vulto — CA 12 | PV 9.").mod("des") == 0


def test_atributo_desconhecido_e_zero():
    assert stats_inimigo(ficha=_FICHA_QDRANT).mod("inexistente") == 0


# ── A ficha autoral emite o formato que o parse lê ───────────────────────────


def test_round_trip_da_ficha_estatica():
    """O teste que amarra os dois lados: `_ficha_texto` escreve, `parse_atributos`
    lê. Se o formato divergir, a engine ignora a ficha EM SILÊNCIO."""
    ficha = ancorar_no_srd(srd_index="adult-red-dragon")
    st = stats_inimigo(ficha=ficha)
    assert st.ca == 19 and st.hp_max == 256
    assert st.mod("for") == 8
    assert st.mod("con") == 7


def test_todo_statblock_com_mods_faz_round_trip():
    for chave, campos in STATBLOCKS_SRD.items():
        if not campos.get("mods"):
            continue
        st = stats_inimigo(ficha=ancorar_no_srd(srd_index=chave))
        for attr, esperado in campos["mods"].items():
            assert st.mod(attr) == esperado, f"{chave}.{attr}"


# ── Vyrmathax deixa de ser um lacaio ─────────────────────────────────────────


def test_vyrmathax_tem_ficha_autoral_agora():
    """O inimigo que deu nome ao bug: pegava ficha de warlock e valia 25 XP."""
    limpar_cache()
    ficha = resolver_ficha_npc("vyrmathax")
    assert ficha, "Vyrmathax voltou a ficar sem bloco `combat` no módulo"
    assert not sem_ficha_autoral("vyrmathax")

    st = stats_inimigo(ficha=ficha)
    assert st.ca >= 18 and st.hp_max >= 200
    from engine.progression import xp_do_inimigo
    assert xp_do_inimigo({"ficha": ficha}) == 18_000


def test_a_lenda_nao_e_mais_igual_ao_capanga():
    limpar_cache()
    lenda = stats_inimigo(ficha=resolver_ficha_npc("vyrmathax") or "")
    capanga = stats_inimigo(ficha=ancorar_no_srd(srd_index="thug"))
    assert lenda.hp_max > capanga.hp_max * 5
    assert lenda.atk_bonus > capanga.atk_bonus


# ── Iniciativa passa a usar DES ──────────────────────────────────────────────


def test_iniciativa_soma_a_destreza_do_inimigo():
    """Mesma semente, DES diferente → iniciativa diferente. É a prova de que a
    ficha entrou na conta."""
    def _rolar(ficha: str) -> int:
        wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
        wm.entrar_combate()
        wm.registrar_inimigo("m", "Monstro")
        wm.inimigos_combate["m"]["ficha"] = ficha
        wm.popular_iniciativa(rng=random.Random(7))
        return wm.iniciativa_cache["m"]

    agil = _rolar("Ágil — CA 15 | PV 20. DES 18 (+4).")
    lento = _rolar("Lento — CA 15 | PV 20. DES 6 (-2).")
    assert agil - lento == 6


def test_inimigo_sem_ficha_continua_rolando_puro():
    """Nada regride: sem atributo, o comportamento é o de antes."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("m", "Monstro")
    wm.popular_iniciativa(rng=random.Random(7))
    assert 1 <= wm.iniciativa_cache["m"] <= 20


# ── Salvaguarda passa a usar o atributo certo ────────────────────────────────


def test_resistencia_usa_o_atributo_que_a_magia_exige():
    """Bola de Fogo é save de DES: um alvo com DES alta resiste mais."""
    from engine.magic.salvaguarda import resolver_resistencia

    def _resistiu(ficha: str, semente: int) -> bool:
        wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
        wm.player_class = "mago"
        wm.player_level = 5
        wm.entrar_combate()
        wm.registrar_inimigo("m", "Monstro")
        wm.aplicar_stats_inimigo("m", ca=15, hp_max=200)
        wm.inimigos_combate["m"]["ficha"] = ficha
        r = resolver_resistencia(
            wm, "Bola de Fogo", "m", nome_en="Fireball",
            nivel_slot=3, rng=random.Random(semente),
        )
        return bool(r and r["resistiu"])

    agil = "Ágil — CA 15 | PV 200. DES 20 (+5)."
    lento = "Lento — CA 15 | PV 200. DES 6 (-2)."
    vitorias_ageis = sum(_resistiu(agil, s) for s in range(60))
    vitorias_lentos = sum(_resistiu(lento, s) for s in range(60))
    assert vitorias_ageis > vitorias_lentos
