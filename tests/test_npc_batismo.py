"""
Testes do batismo de NPC (NPC-SEM-BATISMO-2, playtest 21/07).

Por que existe: depois de 23 turnos o registro da sessão tinha
    `tavern-eiro → "homem gordo e simpático"`, `pessoa-andar-superior`,
    `homem-urgente`, `velho-moinheiro`. O fix de julho ensinou o Mestre a
    inventar nome QUANDO PERGUNTADO — quem nunca é interrogado morre sem nome.
    E o brief imprimia o id kebab ("Em cena: tavern eiro"), reinjetando o
    descritor como se fosse gente a cada turno.
Dependências: nenhuma — funções puras sobre a WorkingMemory.
Armadilha: `parece_nome_proprio` é heurística. Erra pro lado seguro — cobrar
    nome de quem já tem custa uma linha no prompt; deixar passar custa a sessão.
"""

from engine.authority.brief import montar_brief
from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import (
    garantir_registro,
    parece_nome_proprio,
    precisa_de_batismo,
    registrar_npc,
)


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("kaelmund", "Kaelmünd", "sess-batismo")


# ── A heurística ─────────────────────────────────────────────────────────────

def test_nomes_de_gente_passam():
    for nome in ("Bjorn", "Bjorn Tharnsson", "Runa", "Aldric Drevasson", "Gorvoth"):
        assert parece_nome_proprio(nome), nome


def test_descritores_do_playtest_nao_passam():
    for nome in (
        "homem gordo e simpático",   # o que estava no campo `nome` de tavern-eiro
        "Homem Urgente",
        "Velho Moinheiro",
        "Pessoa Andar Superior",
        "Tavern Eiro",
        "",
    ):
        assert not parece_nome_proprio(nome), nome


# ── A cobrança ───────────────────────────────────────────────────────────────

def test_figurante_de_um_turno_nao_e_cobrado():
    wm = _wm()
    wm.npcs_presentes = ["homem-urgente"]
    garantir_registro(wm)                       # 1º turno em cena
    assert precisa_de_batismo(wm) == []


def test_quem_reaparece_sem_nome_e_cobrado():
    wm = _wm()
    wm.npcs_presentes = ["tavern-eiro"]
    registrar_npc(wm, "tavern-eiro", "homem gordo e simpático")
    garantir_registro(wm)
    garantir_registro(wm)                       # 2º turno em cena
    pendentes = precisa_de_batismo(wm)
    assert pendentes and pendentes[0][0] == "tavern-eiro"


def test_quem_ja_tem_nome_nunca_e_cobrado():
    wm = _wm()
    wm.npcs_presentes = ["bjorn-tharnsson"]
    registrar_npc(wm, "bjorn-tharnsson", "Bjorn")
    for _ in range(5):
        garantir_registro(wm)
    assert precisa_de_batismo(wm) == []


def test_quem_saiu_de_cena_nao_e_cobrado():
    wm = _wm()
    wm.npcs_presentes = ["velho-moinheiro"]
    for _ in range(3):
        garantir_registro(wm)
    wm.npcs_presentes = []                      # o jogador foi embora do moinho
    assert precisa_de_batismo(wm) == []


# ── O que chega no prompt ────────────────────────────────────────────────────

def test_brief_mostra_nome_legivel_e_nao_o_id_kebab():
    wm = _wm()
    wm.npcs_presentes = ["bjorn-tharnsson"]
    registrar_npc(wm, "bjorn-tharnsson", "Bjorn")
    wm.scene.npcs_apresentados = {"bjorn-tharnsson"}
    texto = montar_brief(wm, "Olho ao redor").to_prompt()
    assert "Bjorn" in texto
    assert "bjorn tharnsson" not in texto.lower()


def test_brief_cobra_o_batismo_de_um_por_vez():
    """Batizar a taverna inteira num turno soa a chamada de classe."""
    wm = _wm()
    wm.npcs_presentes = ["tavern-eiro", "homem-urgente", "sorveteiro"]
    registrar_npc(wm, "tavern-eiro", "homem gordo e simpático")
    garantir_registro(wm)
    garantir_registro(wm)
    texto = montar_brief(wm, "Peço uma cerveja").to_prompt()
    assert texto.count("BATIZE:") == 1
    assert "[NPC: " in texto                    # com o formato do marcador junto


def test_cena_sem_pendencia_nao_ganha_linha_de_batismo():
    wm = _wm()
    wm.npcs_presentes = []
    assert "BATIZE:" not in montar_brief(wm, "Sigo pela estrada").to_prompt()


# ── NPC-PRESENCA-NOMEADA (regra do Beltrami, 21/07) ──────────────────────────
#
# "NPCs só deveriam aparecer como presentes se forem nomeados formalmente; se
# não, apenas personagens que já se esperam revelação ganham retrato com nome
# placeholder até o reveal." Figurante é cenário, não elenco.

def test_figurante_descritivo_nao_ganha_cadeira_na_cena():
    from engine.npc.identity import npcs_visiveis

    wm = _wm()
    wm.npcs_presentes = ["tavern-eiro", "sorveteiro", "pessoa-andar-superior"]
    registrar_npc(wm, "tavern-eiro", "homem gordo e simpático")
    wm.scene.npcs_apresentados = set(wm.npcs_presentes)
    assert npcs_visiveis(wm) == []


def test_npc_nomeado_ganha_cadeira():
    from engine.npc.identity import npcs_visiveis

    wm = _wm()
    wm.npcs_presentes = ["gorvoth"]
    registrar_npc(wm, "gorvoth", "Gorvoth")
    wm.scene.npcs_apresentados = {"gorvoth"}
    assert npcs_visiveis(wm) == ["gorvoth"]


def test_npc_autoral_do_modulo_segura_a_cadeira_mesmo_sem_reveal():
    """Quem o módulo escreveu tem revelação prevista — o lugar é dele."""
    from engine.combat.npc_statblocks import e_npc_fixo
    from engine.npc.identity import npcs_visiveis

    wm = _wm()
    fixo = next(
        (n for n in ("bjorn-tharnsson", "runa", "aldric-drevasson") if e_npc_fixo(n)),
        None,
    )
    if fixo is None:
        import pytest
        pytest.skip("módulo sem NPC fixo com bloco combat")
    wm.npcs_presentes = [fixo]
    wm.scene.npcs_apresentados = {fixo}
    assert npcs_visiveis(wm) == [fixo]


def test_quem_nao_foi_apresentado_nao_aparece_mesmo_com_nome():
    """Mencionado numa fala != em cena — a guarda antiga continua valendo."""
    from engine.npc.identity import npcs_visiveis

    wm = _wm()
    wm.npcs_presentes = ["gorvoth"]
    registrar_npc(wm, "gorvoth", "Gorvoth")
    wm.scene.npcs_apresentados = set()
    assert npcs_visiveis(wm) == []


def test_batismo_promove_o_figurante_a_elenco():
    """O laço se fecha: sem nome não tem cadeira; o brief cobra o nome; com
    nome, a cadeira aparece."""
    from engine.npc.identity import npcs_visiveis

    wm = _wm()
    wm.npcs_presentes = ["tavern-eiro"]
    registrar_npc(wm, "tavern-eiro", "homem gordo e simpático")
    wm.scene.npcs_apresentados = {"tavern-eiro"}
    garantir_registro(wm)
    garantir_registro(wm)

    assert npcs_visiveis(wm) == []
    assert "BATIZE:" in montar_brief(wm, "Peço uma cerveja").to_prompt()

    registrar_npc(wm, "tavern-eiro", "Halvard")   # o Mestre batizou: [NPC: tavern-eiro|Halvard]
    assert npcs_visiveis(wm) == ["tavern-eiro"]
    assert "BATIZE:" not in montar_brief(wm, "Peço outra").to_prompt()


def test_nome_de_uma_palavra_derivado_do_id_nao_conta_como_batismo():
    """O caso que expôs a falha da heurística de string: "Sorveteiro" e
    "Gorvoth" são estruturalmente idênticos — uma palavra, capitalizada. O que
    separa os dois é QUEM nomeou. Só o ato do Mestre batiza."""
    from engine.npc.identity import npcs_visiveis

    wm = _wm()
    wm.npcs_presentes = ["sorveteiro", "gorvoth"]
    registrar_npc(wm, "sorveteiro")                 # derivado do id, sem ato
    registrar_npc(wm, "gorvoth", "Gorvoth")         # o Mestre nomeou
    wm.scene.npcs_apresentados = {"sorveteiro", "gorvoth"}
    assert npcs_visiveis(wm) == ["gorvoth"]


def test_reveal_de_nome_da_cadeira_ao_anonimo():
    """'Aquele é... Gorvoth' — o reveal É o batismo."""
    from engine.npc.identity import npcs_visiveis, revelar_nome

    wm = _wm()
    wm.npcs_presentes = ["encapuzado"]
    registrar_npc(wm, "encapuzado")
    wm.scene.npcs_apresentados = {"encapuzado"}
    assert npcs_visiveis(wm) == []

    novo = revelar_nome(wm, "encapuzado", "Gorvoth")
    wm.scene.npcs_apresentados.add(novo)
    assert npcs_visiveis(wm) == [novo]
