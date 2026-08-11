"""
Pontas soltas ligadas na varredura de 11/08 — e as duplicações que sobraram.

Por que existe: a varredura achou 69 funções públicas de `engine/` sem uso fora
    do próprio módulo. A maioria é helper legítimo, mas três eram FEATURE
    DORMENTE — código escrito, testado e nunca plugado, a mesma classe do
    `avaliar_acao_jogador` (escrito em 19/06, sem call-site até 09/08):
      1. `buscar_afeto_npc` — a engine GRAVAVA afeto/medo/respeito/rancor no
         Neo4j desde sempre e nunca lia de volta. Dava pra atacar um NPC, voltar
         na sessão seguinte, e ser recebido como um estranho simpático.
      2. `para_exibicao` — o inventário estruturado sabia quantidade e arma
         equipada, e o prompt seguia recebendo a lista plana.
      3. Duas listas de "o que é consumível" que discordavam entre si.
Dependências: nenhuma (tudo puro).
Armadilha: o rótulo de afeto NUNCA carrega número. Toda a autoridade social do
    projeto é discreta por decisão (02/07) — o toast de relação não mostra
    pontos, e o dossiê não pode mostrar "rancor: 4".

Exemplo:
    uv run pytest tests/test_pontas_soltas.py -q
"""

import re

from engine.memory.item_authority import _ITENS_CONSUMIVEIS
from engine.memory.working_memory import WorkingMemory
from engine.npc.afeto import aplicar_afeto, rotulo_de_afeto
from engine.state.inventario import RADICAIS_CONSUMIVEL, classificar_tipo


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")


# ══ AFETO-NUNCA-LIDO-1 ═══════════════════════════════════════════════════════


def test_o_afeto_vira_frase_nao_numero():
    """Autoridade social é discreta por decisão — nada de "rancor: 4"."""
    for entrada in ({"rancor": 4}, {"medo": 6}, {"afeto": 3}, {"respeito": 9}):
        rotulo = rotulo_de_afeto(entrada)
        assert rotulo, entrada
        assert not re.search(r"\d", rotulo), f"{rotulo!r} carrega número"


def test_eixo_forte_ganha_frase_mais_dura():
    assert rotulo_de_afeto({"rancor": 2}) != rotulo_de_afeto({"rancor": 6})
    assert rotulo_de_afeto({"afeto": 2}) != rotulo_de_afeto({"afeto": 6})


def test_um_ato_isolado_nao_muda_a_descricao_do_npc():
    """Abaixo do limiar é ruído — senão o Mestre narra reviravolta a cada turno."""
    assert rotulo_de_afeto({"afeto": 1}) == ""
    assert rotulo_de_afeto({"rancor": 1, "medo": 1}) == ""


def test_rancor_manda_em_respeito():
    """Um NPC que te admira e te odeia age pelo ódio."""
    assert rotulo_de_afeto({"respeito": 8, "rancor": 3}) == rotulo_de_afeto({"rancor": 3})


def test_afeto_vazio_ou_invalido_nao_explode():
    assert rotulo_de_afeto(None) == ""
    assert rotulo_de_afeto({}) == ""
    assert rotulo_de_afeto({"rancor": "muito"}) == ""


def test_o_rotulo_chega_ao_prompt_junto_do_dossie():
    """É o pagamento da ponta solta: o Mestre passa a SABER que o NPC te odeia."""
    wm = _wm()
    wm.scene.npcs_presentes = ["gorvoth"]
    wm.scene.npcs_apresentados = {"gorvoth"}
    wm.scene.npc_registro["gorvoth"] = {"nome": "Gorvoth", "tracos": ["fala pouco"]}
    aplicar_afeto(wm, "gorvoth", {"rancor": 6})
    texto = wm.scene.to_prompt()
    assert "te odeia abertamente" in texto
    assert "fala pouco" in texto, "o afeto não pode expulsar a personalidade"


def test_afeto_sobrescreve_ao_contrario_do_dossie():
    """Personalidade é quem o NPC É (1º encontro vence); afeto é como ele ESTÁ."""
    wm = _wm()
    wm.scene.npc_registro["gorvoth"] = {"nome": "Gorvoth"}
    aplicar_afeto(wm, "gorvoth", {"rancor": 6})
    aplicar_afeto(wm, "gorvoth", {"afeto": 6})
    assert wm.scene.npc_registro["gorvoth"]["afeto_rotulo"] == "é leal a você"


def test_afeto_que_zerou_some_do_registro():
    wm = _wm()
    wm.scene.npc_registro["gorvoth"] = {"nome": "Gorvoth"}
    aplicar_afeto(wm, "gorvoth", {"rancor": 6})
    aplicar_afeto(wm, "gorvoth", {"rancor": 0})
    assert "afeto_rotulo" not in wm.scene.npc_registro["gorvoth"]


def test_o_leitor_de_afeto_tem_call_site_em_producao():
    """A prova contra a feature dormente: existir e ser testado não basta."""
    from pathlib import Path

    fonte = (Path(__file__).resolve().parents[1] / "engine/memory/context_builder.py")
    texto = fonte.read_text(encoding="utf-8")
    assert "buscar_afeto_npc" in texto
    assert "aplicar_afeto(" in texto


# ══ INVENTARIO no prompt ═════════════════════════════════════════════════════


def test_o_prompt_mostra_quantidade_e_arma_equipada():
    wm = _wm()
    wm.player_inventory = ["Arco longo", "Poção de Cura", "Poção de Cura"]
    wm.character.equipar_item("Arco longo")
    linha = next(
        l for l in wm.character.to_prompt().splitlines() if l.startswith("Inventário:")
    )
    assert "[equipado]" in linha
    assert "(×2)" in linha


def test_a_checagem_de_posse_continua_com_nome_plano():
    """A vista decorada é só pro prompt — decorar a de checagem quebraria tudo."""
    wm = _wm()
    wm.player_inventory = ["Poção de Cura", "Poção de Cura"]
    assert "Poção de Cura" in wm.player_inventory


# ══ CONSUMIVEL-DUPLICADO-1 ═══════════════════════════════════════════════════


def test_existe_UMA_lista_canonica_de_consumivel():
    """As duas discordavam: "frasco"/"ração" só numa, "tônico"/"kit de cura" só
    na outra — item que a ficha chamava de consumível e a autoridade não
    reconhecia na hora de beber."""
    faltando = [r for r in RADICAIS_CONSUMIVEL if r not in _ITENS_CONSUMIVEIS]
    assert not faltando, f"a autoridade não deriva da canônica: {faltando}"


def test_os_radicais_que_faltavam_nos_dois_lados_agora_valem():
    for nome in ("Frasco de óleo", "Ração de viagem", "Tônico élfico",
                 "Kit de cura", "Bálsamo de ervas"):
        assert classificar_tipo(nome) == "consumivel", nome


def test_a_lista_da_autoridade_mantem_as_formas_acentuadas():
    """Só ela compara contra a fala CRUA do jogador, que vem com acento."""
    assert "poção" in _ITENS_CONSUMIVEIS
    assert "antídoto" in _ITENS_CONSUMIVEIS


# ══ QDRANT-NO-CAMINHO-DA-MAGIA-1 ═════════════════════════════════════════════


def test_o_bloco_mecanico_sai_da_tabela_local_e_em_portugues():
    from engine.magic.resolucao import bloco_mecanico_local

    wm = WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class="Mago", player_level=5,
    )
    wm.character.int_score = 18
    d = bloco_mecanico_local("Bola de Fogo", wm)
    assert d["nivel"] == 3
    assert d["escola"] == "Evocação"
    assert "pés" in d["alcance"], d["alcance"]
    assert "fogo" in d["dano"], d["dano"]
    # A CD é a REAL do conjurador (8 + prof 3 + INT 4), coisa que a versão do
    # Qdrant nunca teve: ela transcrevia um número de texto.
    assert "CD 15" in d["cd_save"], d["cd_save"]


def test_sem_personagem_a_CD_e_omitida_em_vez_de_inventada():
    from engine.magic.resolucao import bloco_mecanico_local

    d = bloco_mecanico_local("Bola de Fogo")
    assert not re.search(r"\d", d["cd_save"]), d["cd_save"]


def test_o_websocket_nao_chama_mais_o_qdrant_pra_montar_o_bloco():
    """Checa o CÓDIGO via AST, não o texto.

    A primeira versão deste teste fazia `assert "await buscar_dados_magia(" not
    in fonte` — e falhou no COMENTÁRIO que explica a mudança, porque ele cita a
    chamada antiga pra dizer o que saiu. É a QUINTA vez que esta armadilha
    aparece no projeto, e a quinta está registrada no CLAUDE.md desde hoje de
    manhã. O texto do arquivo não é o comportamento dele.
    """
    import ast
    from pathlib import Path

    arvore = ast.parse(
        (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")
    )
    chamadas = {
        no.func.id
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert "bloco_mecanico_local" in chamadas
    assert "buscar_dados_magia" not in chamadas, (
        "rede no caminho do número da magia contraria o ADR-007"
    )
