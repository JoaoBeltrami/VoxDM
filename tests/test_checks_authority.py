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


# ── CHECK-SEM-DC-1 (playtest 01/08) ──────────────────────────────────────────
#
# O Beltrami reclamou TRÊS vezes na mesma sessão: "bom pedido de check, mas sem
# DC". A engine somava certo e entregava "= 18. Este é o resultado FINAL; narre
# o desfecho" — sem dizer contra o quê o 18 valia. Quem decidia se passou era o
# modelo, por vibe. Mostrar a conta sem mostrar o alvo é metade do problema.

def test_cd_padrao_e_o_medio_do_srd():
    from engine.authority.checks import CD_PADRAO, cd_de_dificuldade

    assert CD_PADRAO == 15
    assert cd_de_dificuldade(None) == 15
    assert cd_de_dificuldade("") == 15


def test_tabela_de_cd_segue_o_srd():
    from engine.authority.checks import cd_de_dificuldade

    assert cd_de_dificuldade("trivial") == 5
    assert cd_de_dificuldade("facil") == 10
    assert cd_de_dificuldade("media") == 15
    assert cd_de_dificuldade("dificil") == 20
    assert cd_de_dificuldade("muito_dificil") == 25
    assert cd_de_dificuldade("quase_impossivel") == 30


def test_rotulo_aceita_acento_espaco_e_sinonimo():
    """O rótulo chega de texto, não de enum — tolera a forma humana."""
    from engine.authority.checks import cd_de_dificuldade

    assert cd_de_dificuldade("Difícil") == 20
    assert cd_de_dificuldade("muito difícil") == 25
    assert cd_de_dificuldade("MÉDIO") == 15


def test_rotulo_desconhecido_cai_no_padrao_sem_inventar():
    """Vocabulário FECHADO, como o do [ALINHAMENTO]: desconhecido não vira CD
    novo — cai no padrão em silêncio."""
    from engine.authority.checks import cd_de_dificuldade

    assert cd_de_dificuldade("impossivelmente_dificil") == 15
    assert cd_de_dificuldade("42") == 15


def test_linha_engine_da_o_VEREDITO_nao_so_o_total():
    """O coração do fix: a engine decide SE passou, não só quanto deu."""
    linha = resolver_check(_sylas(), 5, "Furtividade")      # 5+5 = 10 vs CD 15
    assert "vs CD 15" in linha
    assert "FALHA por 5" in linha
    assert "SUCESSO" not in linha

    linha2 = resolver_check(_sylas(), 15, "Furtividade")    # 15+5 = 20 vs CD 15
    assert "SUCESSO por 5" in linha2


def test_empate_com_a_cd_e_sucesso():
    """No SRD, total >= CD passa. Empate é vitória — e merece nome próprio."""
    linha = resolver_check(_sylas(), 10, "Furtividade")     # 10+5 = 15 vs CD 15
    assert "SUCESSO na trave" in linha


def test_dificuldade_muda_o_veredito_do_mesmo_dado():
    """O mesmo total passa num teste fácil e falha num difícil — que é o ponto
    inteiro de existir CD."""
    assert "SUCESSO" in resolver_check(_sylas(), 10, "Furtividade", "facil")
    assert "FALHA" in resolver_check(_sylas(), 10, "Furtividade", "dificil")


def test_natural_20_nao_inverte_veredito_de_pericia():
    """SRD: teste de perícia não tem sucesso automático. O natural colore a
    narração, a CD decide. (Se um dia virar rule-of-cool, é decisão do Beltrami.)"""
    linha = resolver_check(_sylas(), 20, "Furtividade", "quase_impossivel")  # 25 vs 30
    assert "20 NATURAL" in linha
    assert "FALHA por 5" in linha


def test_prompt_descreve_o_MESMO_formato_que_a_engine_emite():
    """Teste que amarra os dois lados — a armadilha nº1 do projeto.

    `master_system.md` documenta pro Mestre o formato da linha "ENGINE:". Se a
    engine passa a emitir veredito e o prompt segue descrevendo só o total, o
    Mestre continua achando que a decisão é dele — o fix vira decoração. Já
    mordeu 4 vezes em 2 dias (LEMBRETE no TTS, voz_dupla, TOM do benchmark).
    """
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    md = (raiz / "engine/llm/prompts/master_system.md").read_text(encoding="utf-8")

    assert "vs CD" in md, "o prompt não menciona a CD que a engine passou a emitir"

    # Cada linha carrega UM veredito; o prompt precisa descrever os dois.
    sucesso = resolver_check(_sylas(), 15, "Furtividade")        # 20 vs 15
    falha = resolver_check(_sylas(), 5, "Furtividade")           # 10 vs 15
    assert "SUCESSO" in sucesso and "FALHA" in falha

    for token in ("vs CD", "SUCESSO", "FALHA"):
        assert token in md, (
            f"{token!r} sai da engine mas não está no master_system.md — "
            "prompt e código derivaram"
        )


def test_detalhar_check_leva_a_cd_pro_jogador():
    """CHECK-INVISIVEL-1 mostrou a conta; sem a CD junto, a conta não diz nada."""
    from engine.authority.checks import detalhar_check

    d = detalhar_check(_sylas(), 10, "Furtividade")         # 15 vs 15
    assert d["cd"] == 15
    assert d["sucesso"] is True
    assert d["margem"] == 0

    d2 = detalhar_check(_sylas(), 2, "Furtividade", "dificil")   # 7 vs 20
    assert d2["cd"] == 20 and d2["sucesso"] is False and d2["margem"] == -13


def test_pedido_de_ataque_nao_vira_teste_de_pericia():
    """Guarda existente do intent: ataque não passa por aqui."""
    from engine.combat.intent import eh_teste_pericia

    assert eh_teste_pericia("Faça sua rolagem de ataque contra o goblin.") is None
