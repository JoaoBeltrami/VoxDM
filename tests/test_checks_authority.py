"""
Testes da autoridade de teste de perícia (engine/authority/checks.py).

Por que existe: CHECK-BONUS-1 (playtest 21/07) — "os pedidos de check
melhoraram, alguns não aplicaram o bônus". A soma era feita pela LLM a pedido
do prompt; aqui ela passa a ser da engine.
Dependências: nenhuma — tudo puro sobre a WorkingMemory.
Armadilha: sem perícia identificada NÃO se inventa modificador. Um bônus errado
    com cara de autoridade é pior que nenhum.
"""

from engine.authority.checks import bonus_de_check, resolver_check
from engine.memory.working_memory import WorkingMemory


def _sylas() -> WorkingMemory:
    """O personagem do playtest: Tiefling Ladino nv3, DES 17, CAR 17."""
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmünd", "sess-check")
    wm.dex_score = 17          # +3
    wm.cha_score = 17          # +3
    wm.str_score = 7           # -2
    wm.wis_score = 13          # +1
    wm.player_level = 3        # → prof_bonus +2 (derivado do nível)
    wm.skill_profs = ["Furtividade", "Enganação", "Acrobacia", "Atuação"]
    wm.save_profs = ["DES", "INT"]
    return wm


def test_pericia_com_proficiencia_soma_atributo_e_bonus():
    total, detalhe = bonus_de_check(_sylas(), "Furtividade")
    assert total == 5                      # DES +3 + prof +2
    assert "DES +3" in detalhe and "proficiência +2" in detalhe


def test_pericia_sem_proficiencia_soma_so_o_atributo():
    total, detalhe = bonus_de_check(_sylas(), "Persuasão")
    assert total == 3                      # CAR +3, sem prof
    assert "proficiência" not in detalhe


def test_modificador_negativo_e_respeitado():
    total, _ = bonus_de_check(_sylas(), "Atletismo")
    assert total == -2                     # FOR 7


def test_salvaguarda_usa_save_profs_nao_skill_profs():
    com_prof, _ = bonus_de_check(_sylas(), "Destreza")
    sem_prof, _ = bonus_de_check(_sylas(), "Sabedoria")
    assert com_prof == 5                   # DES +3 + prof (DES em save_profs)
    assert sem_prof == 1                   # SAB 13 → +1, sem prof


def test_nome_desconhecido_nao_inventa_bonus():
    assert bonus_de_check(_sylas(), "Malabarismo Interpretativo") is None
    assert bonus_de_check(_sylas(), "") is None


def test_linha_engine_traz_o_total_pronto():
    linha = resolver_check(_sylas(), 5, "Furtividade")
    assert linha.startswith("ENGINE:")
    assert "Furtividade" in linha
    assert "= 10" in linha                 # 5 + 5
    assert "sem recalcular" in linha


def test_critico_e_falha_natural_ficam_visiveis():
    assert "20 NATURAL" in resolver_check(_sylas(), 20, "Persuasão")
    assert "1 NATURAL" in resolver_check(_sylas(), 1, "Persuasão")
    assert "NATURAL" not in resolver_check(_sylas(), 12, "Persuasão")


def test_dado_invalido_ou_pericia_desconhecida_nao_resolve():
    assert resolver_check(_sylas(), 0, "Persuasão") is None
    assert resolver_check(_sylas(), 21, "Persuasão") is None
    assert resolver_check(_sylas(), 12, "Coisa Nenhuma") is None


def test_o_caminho_do_playtest_ponta_a_ponta():
    """Mestre pede Persuasão, jogador clica no d20 da toolbar: a engine
    intercepta o dado cru e devolve o total somado."""
    from api.turn_pipeline import extrair_d20_jogador
    from engine.combat.intent import eh_teste_pericia

    fala_mestre = "O taverneiro cruza os braços. Role um teste de Persuasão."
    texto_jogador = "[Rolagem: d20 = 13]"

    pericia = eh_teste_pericia(fala_mestre)
    bruto = extrair_d20_jogador(texto_jogador)
    assert pericia == "Persuasão" and bruto == 13

    linha = resolver_check(_sylas(), bruto, pericia)
    assert "= 16" in linha                 # 13 + 3 (CAR), sem proficiência


def test_pedido_de_ataque_nao_vira_teste_de_pericia():
    """Guarda existente do intent: ataque não passa por aqui."""
    from engine.combat.intent import eh_teste_pericia

    assert eh_teste_pericia("Faça sua rolagem de ataque contra o goblin.") is None
