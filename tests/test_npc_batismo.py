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
