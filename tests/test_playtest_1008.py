"""
Os itens que o playtest de 10/08 comprou — economia, arma e morte.

Por que existe: a sessão `sess-e2221414ef32` terminou com o jogador morto e uma
    lista de queixas que são todas a mesma família — a engine sabia menos sobre a
    rodada do que o jogador esperava. Não conseguiu usar magia de ação bônus, o
    Mestre pediu Força a um Ranger de arco, e morrer não teve regra nenhuma.
Dependências: nenhuma (tudo função pura + estado).
Armadilha: `finesse` não é "usa Destreza", é "escolhe o melhor" — e cair a 0 PV
    não é morrer, é cair. Os dois erros são simplificações que parecem certas e
    punem metade das fichas.

Exemplo:
    uv run pytest tests/test_playtest_1008.py -q
"""

import random

from engine.combat.arma import (
    atributo_do_ataque,
    dado_de_dano,
    identificar_arma,
)
from engine.combat.morte import (
    estado_de_morte,
    falha_por_golpe,
    precisa_rolar_save,
    rolar_save_de_morte,
)
from engine.magic.economia import custo_de_acao, gastar_recurso_da_magia
from engine.memory.working_memory import WorkingMemory


def _ranger() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class="Ranger", player_level=3,
    )
    wm.player_name = "Sylas"
    wm.character.dex_score = 16   # +3
    wm.character.str_score = 10   # +0
    return wm


# ══ ACAO-BONUS-INEXISTENTE-1 ═════════════════════════════════════════════════


def test_marca_do_cacador_custa_bonus_nao_acao():
    """A frase literal do playtest: *"como ação bônus, eu vou utilizar a marca
    do caçador nele e em seguida ataco"*."""
    assert custo_de_acao("Marca do Caçador") == "bonus"
    assert custo_de_acao("Bola de Fogo") == "acao"


def test_conjurar_de_bonus_deixa_a_acao_livre_pra_atacar():
    """O "e em seguida ataco" precisa continuar possível."""
    wm = _ranger()
    wm.entrar_combate()
    recurso, gastou = gastar_recurso_da_magia(wm, "Marca do Caçador")
    assert (recurso, gastou) == ("bonus", True)
    assert wm.bonus_usada is True
    assert wm.acao_usada is False
    assert wm.pode_agir() is True, "atacar depois da magia de bônus é a regra"


def test_conjurar_de_acao_consome_a_acao():
    wm = _ranger()
    wm.entrar_combate()
    assert gastar_recurso_da_magia(wm, "Bola de Fogo") == ("acao", True)
    assert wm.pode_agir() is False


def test_duas_magias_de_bonus_na_mesma_rodada_nao_passam():
    wm = _ranger()
    wm.entrar_combate()
    assert gastar_recurso_da_magia(wm, "Marca do Caçador")[1] is True
    assert gastar_recurso_da_magia(wm, "Marca do Caçador")[1] is False


def test_magia_desconhecida_cobra_o_recurso_mais_CARO():
    """Errar pra baixo daria uma ação de graça, que ninguém percebe."""
    assert custo_de_acao("Punho Sideral de Valdrek") == "acao"


def test_fora_de_combate_nao_ha_economia_pra_gastar():
    wm = _ranger()
    assert gastar_recurso_da_magia(wm, "Marca do Caçador") == ("bonus", False)


# ══ MOD-ARMA-1 ═══════════════════════════════════════════════════════════════


def test_arco_ataca_por_destreza():
    """*"Pedindo ataque com Força que seria com Destreza"* — o caso literal."""
    wm = _ranger()
    idx, _ = identificar_arma("ataco o bandido com meu arco longo")
    assert idx == "longbow"
    assert atributo_do_ataque(wm, idx) == ("DES", 5)   # +3 DES, +2 prof


def test_arma_pesada_ataca_por_forca():
    wm = _ranger()
    idx, _ = identificar_arma("ergo a espada grande e ataco")
    assert atributo_do_ataque(wm, idx) == ("FOR", 2)   # +0 FOR, +2 prof


def test_finesse_escolhe_o_MELHOR_nao_a_destreza():
    """Fixar finesse em DES puniria o ladino forte tanto quanto fixar em FOR
    punia o arqueiro. A rapieira é o caso canônico."""
    wm = _ranger()
    idx, _ = identificar_arma("saco a rapieira")
    assert atributo_do_ataque(wm, idx) == ("DES", 5)
    wm.character.str_score = 18   # +4, agora a Força é melhor
    assert atributo_do_ataque(wm, idx) == ("FOR", 6)


def test_o_dado_de_dano_vem_da_arma():
    assert dado_de_dano(identificar_arma("com o arco longo")[0]) == 8
    assert dado_de_dano(identificar_arma("com a adaga")[0]) == 4
    assert dado_de_dano(identificar_arma("com a espada grande")[0]) == 6   # 2d6


def test_termo_longo_vence_o_curto():
    """"espada longa" não pode ser capturado pelo "espada" de outra arma."""
    assert identificar_arma("ataco com a espada longa")[0] == "longsword"
    assert identificar_arma("ataco com a espada grande")[0] == "greatsword"


def test_sem_arma_reconhecida_volta_ao_comportamento_antigo():
    """Não regredir o Bruxo que ataca por Carisma (playtest 29/06)."""
    wm = _ranger()
    wm.character.cha_score = 20   # +5
    assert identificar_arma("eu ataco o guarda") == ("", "")
    assert atributo_do_ataque(wm, "") == ("CAR", 7)


def test_a_arma_pode_vir_do_inventario():
    wm = _ranger()
    idx, _ = identificar_arma("ataco o guarda", ["Arco longo", "Corda de cânhamo"])
    assert idx == "longbow"
    assert atributo_do_ataque(wm, idx)[0] == "DES"


# ══ MORTE-SEM-DESFECHO-1 ═════════════════════════════════════════════════════


def test_zero_pv_e_cair_nao_morrer():
    wm = _ranger()
    wm.player_hp = 0
    assert estado_de_morte(wm) == "caido"
    assert precisa_rolar_save(wm) is True


def test_tres_falhas_matam():
    wm = _ranger()
    wm.player_hp = 0
    for d in (5, 5, 5):
        rolar_save_de_morte(wm, d)
    assert estado_de_morte(wm) == "morto"


def test_tres_sucessos_estabilizam():
    wm = _ranger()
    wm.player_hp = 0
    for d in (12, 12, 12):
        rolar_save_de_morte(wm, d)
    assert estado_de_morte(wm) == "estavel"
    assert precisa_rolar_save(wm) is False, "estável não rola mais"


def test_nat_20_devolve_um_pv():
    wm = _ranger()
    wm.player_hp = 0
    wm.death_saves_failures = 2
    r = rolar_save_de_morte(wm, 20)
    assert r["resultado"] == "critico"
    assert wm.player_hp == 1
    assert estado_de_morte(wm) == "de_pe"
    assert wm.death_saves_failures == 0


def test_nat_1_conta_duas_falhas():
    wm = _ranger()
    wm.player_hp = 0
    rolar_save_de_morte(wm, 1)
    assert wm.death_saves_failures == 2


def test_golpe_em_caido_e_falha_automatica():
    """*"Se o inimigo finalizar o jogador é morte mesmo"* — decisão do Beltrami."""
    wm = _ranger()
    wm.player_hp = 0
    falha_por_golpe(wm, critico=False)
    assert wm.death_saves_failures == 1
    falha_por_golpe(wm, critico=True)     # crítico vale DUAS
    assert estado_de_morte(wm) == "morto"


def test_dois_golpes_de_um_inimigo_adjacente_nao_bastam_sem_critico():
    """A regra é dura, não instantânea: 3 falhas continuam sendo 3."""
    wm = _ranger()
    wm.player_hp = 0
    falha_por_golpe(wm)
    falha_por_golpe(wm)
    assert estado_de_morte(wm) == "caido"
    falha_por_golpe(wm)
    assert estado_de_morte(wm) == "morto"


def test_golpe_tira_a_estabilidade():
    """Estável não é imune — é só sem contador correndo."""
    wm = _ranger()
    wm.player_hp = 0
    for d in (12, 12, 12):
        rolar_save_de_morte(wm, d)
    assert estado_de_morte(wm) == "estavel"
    falha_por_golpe(wm)
    assert estado_de_morte(wm) == "caido"
    assert wm.death_saves_stable is False


def test_quem_esta_de_pe_nao_rola_save():
    wm = _ranger()
    assert precisa_rolar_save(wm) is False
    assert rolar_save_de_morte(wm, 5)["resultado"] == "nao_aplicavel"
    assert wm.death_saves_failures == 0


def test_inimigo_nao_causa_DANO_em_quem_ja_caiu():
    """O dano vira falha de morte — senão o HP negativo viraria estado sem regra."""
    from engine.combat.orchestrator import executar_turno_inimigos

    wm = _ranger()
    wm.entrar_combate()
    wm.registrar_inimigo("guarda", "Guarda")
    wm.player_hp = 0
    res = executar_turno_inimigos(wm, random.Random(4))
    assert res["dano_total"] == 0
    assert wm.player_hp == 0
    assert "falhas_de_morte" in res
