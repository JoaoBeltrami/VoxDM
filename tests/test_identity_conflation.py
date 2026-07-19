"""Testes do NPC-IDENTITY-CONFLATION-1 — identidade autoral inviolável (18/07).

Por que existe: na rodada grimdark (sess-a074414ce508) o extractor batizou o
guarda do portão de `bjorn-tharnsson` (a fala dele só MENCIONAVA Bjorn) e o
name-reveal "Roric" MIGROU a entrada — o Bjorn verdadeiro sumiu do registro e
Roric herdou a retrato_seed dele. Dois guardas novos:
  1. `revelar_nome` FORKA quando o id-origem é NPC fixo do módulo (entrada
     autoral intacta; nome revelado nasce como NPC novo com seed própria);
  2. extractor descarta NPC fixo cujo nome só aparece DENTRO de aspas na
     narração (mencionado ≠ presente).

Dependências: pytest; módulo `modulo_teste_v1.2.json` (bjorn-tharnsson tem
campo `combat` — é NPC fixo).
Armadilha: `e_npc_fixo` usa cache por processo do combat map — testes que
mexem no módulo precisam de `limpar_cache()`.
"""

from engine.combat.npc_statblocks import e_npc_fixo
from engine.llm.extractor import (
    _npc_fixo_apenas_citado_em_fala,
    aplicar_npcs_extraidos,
)
from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import registrar_npc, resolver_npc, retrato_seed, revelar_nome


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        "acampamento-sem-vila", "Acampamento dos Sem-Vila", "sess-test"
    )


# ── Sanidade do helper ───────────────────────────────────────────────────────


def test_bjorn_e_npc_fixo_do_modulo():
    assert e_npc_fixo("bjorn-tharnsson") is True
    assert e_npc_fixo("guarda-qualquer") is False
    assert e_npc_fixo("") is False


# ── revelar_nome: fork em vez de migração (caso real da rodada grimdark) ─────


def test_reveal_sobre_npc_fixo_forka_sem_apagar_o_original():
    wm = _wm()
    registrar_npc(wm, "bjorn-tharnsson", "Bjorn Tharnsson")
    wm.npcs_presentes.append("bjorn-tharnsson")

    novo = revelar_nome(wm, "bjorn-tharnsson", "Roric")

    assert novo == "roric"
    reg = wm.scene.npc_registro
    # Entrada autoral INTACTA — o Bjorn continua existindo
    assert "bjorn-tharnsson" in reg
    assert reg["bjorn-tharnsson"]["nome"] == "Bjorn Tharnsson"
    # Roric nasce como NPC NOVO com rosto PRÓPRIO (não herda a seed do Bjorn)
    assert "roric" in reg
    assert retrato_seed(wm, "roric") == "roric"
    # Sem alias — "bjorn-tharnsson" continua resolvendo pra ele mesmo
    assert resolver_npc(wm, "bjorn-tharnsson") == "bjorn-tharnsson"
    # O falante revelado entra em presença
    assert "roric" in wm.npcs_presentes


def test_reveal_sobre_npc_fixo_morto_preserva_flag_do_original():
    wm = _wm()
    registrar_npc(wm, "bjorn-tharnsson", "Bjorn Tharnsson")
    wm.scene.npc_registro["bjorn-tharnsson"]["morto"] = True

    revelar_nome(wm, "bjorn-tharnsson", "Roric")

    assert wm.scene.npc_registro["bjorn-tharnsson"].get("morto") is True
    # O fork NÃO carrega a morte do original — é outra pessoa
    assert not wm.scene.npc_registro["roric"].get("morto")


def test_reveal_de_npc_comum_segue_migrando_normal():
    """Regressão: o fluxo clássico (monge-da-taverna → Kael) não muda."""
    wm = _wm()
    registrar_npc(wm, "monge-da-taverna", "Monge da Taverna")

    novo = revelar_nome(wm, "monge-da-taverna", "Kael")

    assert novo == "kael"
    reg = wm.scene.npc_registro
    assert "monge-da-taverna" not in reg          # migrou
    assert reg["kael"]["retrato_seed"] == "monge-da-taverna"  # rosto preservado
    assert resolver_npc(wm, "monge-da-taverna") == "kael"     # alias segue


# ── Extractor: fixo citado só em fala não entra em presença ──────────────────

_NARRACAO_MENCAO = (
    'Um homem barbudo se levanta, encarando você. "Negócios, é? '
    'Com Bjorn Tharnsson?" A fogueira estala atrás dele.'
)

_NARRACAO_PRESENCA = (
    "Bjorn Tharnsson ergue os olhos de um mapa desdobrado sobre a mesa. "
    '"Trabalho sujo, é?"'
)


def test_helper_detecta_mencao_apenas_em_fala():
    assert _npc_fixo_apenas_citado_em_fala(
        "bjorn-tharnsson", "Bjorn Tharnsson", _NARRACAO_MENCAO
    ) is True


def test_helper_libera_quando_aparece_fora_de_fala():
    assert _npc_fixo_apenas_citado_em_fala(
        "bjorn-tharnsson", "Bjorn Tharnsson", _NARRACAO_PRESENCA
    ) is False


def test_helper_ignora_npc_comum():
    assert _npc_fixo_apenas_citado_em_fala(
        "gryff", "Gryff", '"Sou Gryff, um mercador."'
    ) is False


def test_extractor_descarta_fixo_citado_e_mantem_presente_real():
    wm = _wm()
    adicionados = aplicar_npcs_extraidos(
        wm,
        [
            {"id": "bjorn-tharnsson", "nome": "Bjorn Tharnsson"},
            {"id": "guarda-barbudo", "nome": "Guarda Barbudo"},
        ],
        narracao=_NARRACAO_MENCAO,
    )
    assert "bjorn-tharnsson" not in wm.npcs_presentes
    assert "guarda-barbudo" in wm.npcs_presentes
    assert adicionados == ["guarda-barbudo"]


def test_extractor_registra_fixo_quando_presente_de_verdade():
    wm = _wm()
    aplicar_npcs_extraidos(
        wm,
        [{"id": "bjorn-tharnsson", "nome": "Bjorn Tharnsson"}],
        narracao=_NARRACAO_PRESENCA,
    )
    assert "bjorn-tharnsson" in wm.npcs_presentes
