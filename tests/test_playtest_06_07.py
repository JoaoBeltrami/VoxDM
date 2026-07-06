"""
Testes dos fixes do playtest 06/07 (sess-0d8321eaf3b3, 46 turnos).

Cobre 4 achados de causa-raiz:
- STT-ECO-HOTWORDS-1: Whisper alucina o próprio vocabulário de hotwords em
  silêncio/ruído — a "fala" transcrita era literalmente o vocabulário injetado.
- NPC-DEDUP-CANONICO-1: dedup comparava só npcs_presentes atual, perdendo o
  histórico da sessão quando a re-inferência de cena substituía a lista; uma
  pessoa virou 7 entradas (grimbold → grimbol → tabernero → taverneiro → ...).
- ALVO-PRONOME-1: "vou atacar ele" com só 1 NPC na cena nunca virava
  combate_pendente — pronome descartado incondicionalmente.
- NPC-REVEAL-TELEMETRIA-1: npc_name_reveal_ambiguo sem contexto suficiente
  pra calibrar a heurística de âncora.

Dependências: pytest, pytest-asyncio.
"""

import pytest

from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import garantir_registro, registrar_npc


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test", **kw)


# ══ STT-ECO-HOTWORDS-1 ════════════════════════════════════════════════════════


def test_eco_hotwords_descarta_lista_de_termos_concatenada():
    """A transcrição real do playtest: eco quase-literal do vocabulário injetado."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Tharnvik, Kaelmund, Os Kael, Faccao de Kaelmund, Drevamor"
    texto = "Tharnvik, Faccao de Kaelmund, Os Kael, Faccao de Kaelmund,"
    assert _e_eco_de_hotwords(texto, hotwords) is True


def test_eco_hotwords_preserva_mencao_pontual_a_npc():
    """'ataco o Bjorn Tharnsson' tem overlap com hotwords mas SEM estrutura de
    lista (1 segmento, sem vírgula) — não pode ser descartada."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Bjorn Tharnsson, Kael, Drevamor"
    texto = "Eu ataco o Bjorn Tharnsson com minha espada!"
    assert _e_eco_de_hotwords(texto, hotwords) is False


def test_eco_hotwords_preserva_fala_natural_com_virgulas():
    """Fala real com vírgulas normais ('Bom, eu acho que...') não deve ter
    overlap suficiente com o vocabulário pra ser confundida com eco."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Tharnvik, Kaelmund, Drevamor"
    texto = "Bom, eu acho que devemos ir embora, não é seguro aqui."
    assert _e_eco_de_hotwords(texto, hotwords) is False


def test_eco_hotwords_sem_hotwords_nunca_descarta():
    from engine.voice.stt import _e_eco_de_hotwords

    assert _e_eco_de_hotwords("Tharnvik, Kaelmund, Drevamor", None) is False
    assert _e_eco_de_hotwords("Tharnvik, Kaelmund, Drevamor", "") is False


def test_eco_hotwords_texto_vazio_nunca_descarta():
    from engine.voice.stt import _e_eco_de_hotwords

    assert _e_eco_de_hotwords("", "Thor, Tharnvik, Drevamor") is False


def test_eco_hotwords_minoria_de_batidas_preserva():
    """Só 1 de 3 segmentos bate com hotwords — abaixo do limiar, preserva."""
    from engine.voice.stt import _e_eco_de_hotwords

    hotwords = "Thor, Tharnvik, Kaelmund"
    texto = "Eu quero ir, encontrar o Thor, e depois descansar um pouco"
    assert _e_eco_de_hotwords(texto, hotwords) is False


@pytest.mark.asyncio
async def test_transcrever_bytes_descarta_eco_e2e(monkeypatch):
    """Integração: transcrever_bytes retorna "" quando o modelo mockado devolve
    eco do hotwords injetado, em vez de propagar a alucinação pro jogo."""
    import engine.voice.stt as stt_mod

    class _Segmento:
        def __init__(self, text: str) -> None:
            self.text = text

    class _ModeloEco:
        def transcribe(self, *a, **kw):
            return [_Segmento("Tharnvik, Faccao de Kaelmund, Os Kael,")], None

    monkeypatch.setattr(stt_mod, "_obter_whisper", lambda: _ModeloEco())
    texto = await stt_mod.transcrever_bytes(
        b"audio-fake",
        hotwords_extra="Tharnvik, Faccao de Kaelmund, Os Kael, Drevamor",
    )
    assert texto == ""


@pytest.mark.asyncio
async def test_transcrever_bytes_preserva_fala_real_e2e(monkeypatch):
    import engine.voice.stt as stt_mod

    class _Segmento:
        def __init__(self, text: str) -> None:
            self.text = text

    class _ModeloReal:
        def transcribe(self, *a, **kw):
            return [_Segmento("Eu ataco o goblin com meu machado!")], None

    monkeypatch.setattr(stt_mod, "_obter_whisper", lambda: _ModeloReal())
    texto = await stt_mod.transcrever_bytes(
        b"audio-fake",
        hotwords_extra="Tharnvik, Faccao de Kaelmund, Drevamor",
    )
    assert texto == "Eu ataco o goblin com meu machado!"


# ══ NPC-DEDUP-CANONICO-1 ══════════════════════════════════════════════════════


def test_distancia_edicao_helper():
    from engine.llm.extractor import _distancia_edicao

    assert _distancia_edicao("grimbold", "grimbold") == 0
    assert _distancia_edicao("grimbol", "grimbold") == 1  # falta 1 letra
    assert _distancia_edicao("taverneiro", "taberneiro") == 1  # v↔b
    assert _distancia_edicao("tabernero", "taverneiro") == 2
    assert _distancia_edicao("aldric", "bjorn") == 5


def test_variante_proxima_pega_erro_de_grafia_curto():
    """'grimbol' (1 letra faltando) casa com 'grimbold' já registrado."""
    from engine.llm.extractor import _canonico, _variante_proxima

    mapa = {_canonico("grimbold"): "grimbold", _canonico("aldric"): "aldric"}
    assert _variante_proxima("grimbol", mapa) == "grimbold"


def test_variante_proxima_pega_troca_de_letra():
    """'taberneiro' (v→b) casa com 'taverneiro' já registrado."""
    from engine.llm.extractor import _canonico, _variante_proxima

    mapa = {_canonico("taverneiro"): "taverneiro"}
    assert _variante_proxima("taberneiro", mapa) == "taverneiro"
    assert _variante_proxima("tabernero", mapa) == "taverneiro"  # distância 2


def test_variante_proxima_nao_funde_nomes_curtos_distintos():
    """Nomes curtos (<8 chars) toleram só distância 1 — 'kael' vs 'kaia'
    (distância 2) não pode colapsar."""
    from engine.llm.extractor import _canonico, _variante_proxima

    mapa = {_canonico("kael"): "kael"}
    assert _variante_proxima("kaia", mapa) is None


def test_variante_proxima_nao_funde_nomes_genuinamente_diferentes():
    from engine.llm.extractor import _canonico, _variante_proxima

    mapa = {_canonico("aldric"): "aldric", _canonico("bjorn"): "bjorn"}
    assert _variante_proxima("kael", mapa) is None


def test_variante_proxima_ids_curtos_demais_nao_comparam():
    """Abaixo de 4 chars, distância 1-2 é ruído — nunca compara."""
    from engine.llm.extractor import _canonico, _variante_proxima

    mapa = {_canonico("kai"): "kai"}
    assert _variante_proxima("kal", mapa) is None


def test_dedup_contra_registro_mesmo_fora_de_npcs_presentes():
    """'grimbold' saiu de npcs_presentes (re-inferência de cena trocou a
    lista) mas segue no registro canônico da sessão — repetição EXATA não
    pode re-registrar do zero (log real: 22:22:58, 'grimbold' voltou junto
    com 'tabernero' porque tinha saído de presentes)."""
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    wm.npcs_presentes = ["aldric"]  # grimbold NÃO está mais presente
    garantir_registro(wm)
    registrar_npc(wm, "grimbold", "Grimbold")  # mas segue no registro (já visto)

    add = aplicar_npcs_extraidos(wm, [{"id": "grimbold", "nome": "Grimbold"}])
    assert add == []  # repetição exata contra o registro — não duplica


def test_dedup_variante_de_grafia_fora_de_npcs_presentes():
    """Combina os dois mecanismos: universo session-wide + distância de
    edição — 'grimbol' (typo) casa com 'grimbold' mesmo fora de presentes."""
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    wm.npcs_presentes = ["aldric"]
    garantir_registro(wm)
    registrar_npc(wm, "grimbold", "Grimbold")

    add = aplicar_npcs_extraidos(wm, [{"id": "grimbol", "nome": "Grimbol"}])
    assert add == []
    assert "grimbol" not in wm.npcs_presentes


@pytest.mark.parametrize("candidato", ["taberneiro", "tabernero"])
def test_dedup_variantes_de_grafia_do_taverneiro(candidato):
    """As variantes de GRAFIA reais do log (distância de edição ≤2) colapsam
    contra 'taverneiro' já registrado. 'homem-da-taberna' e
    'grimbold-o-taberneiro' são descrições DIFERENTES (distância >10), não
    erro de grafia — não colapsam por esta via (limitação conhecida; mitigada
    pela lista de 'conhecidos' mais ampla passada ao extractor LLM)."""
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    wm.npcs_presentes = []
    garantir_registro(wm)
    registrar_npc(wm, "taverneiro", "Taverneiro")

    add = aplicar_npcs_extraidos(wm, [{"id": candidato, "nome": candidato.title()}])
    assert add == [], f"'{candidato}' deveria colapsar contra 'taverneiro'"


def test_dedup_nomes_distintos_nao_colapsam_por_edicao():
    """Distância de edição não pode fundir NPCs genuinamente diferentes."""
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    wm.npcs_presentes = []
    garantir_registro(wm)
    registrar_npc(wm, "aldric", "Aldric")

    add = aplicar_npcs_extraidos(wm, [{"id": "bjorn", "nome": "Bjorn"}])
    assert add == ["bjorn"]


def test_dedup_step17b_marker_usa_registro_canonico_e_edicao():
    """O mesmo fix no caminho do marcador [NPC: id|nome] (turn_pipeline step 17b)."""
    from api.turn_pipeline import aplicar_pos_turno

    wm = _wm()
    wm.npcs_presentes = ["aldric"]  # grimbold não está mais presente
    garantir_registro(wm)
    registrar_npc(wm, "grimbold", "Grimbold")

    aplicar_pos_turno(wm, "", "O taverneiro acena. [NPC: grimbol|Grimbol]")
    assert "grimbol" not in wm.npcs_presentes


def test_sotao_taberna_porao_nao_viram_npc():
    """'sotão' (falado pelo JOGADOR, não é NPC) virou NPC no playtest 06/07."""
    from engine.llm.extractor import _e_entidade_invalida

    for termo in ("sotao", "taberna", "porao"):
        assert _e_entidade_invalida(termo, "drevamor", "Drevamor") is True, termo


# ══ ALVO-PRONOME-1 ════════════════════════════════════════════════════════════


def test_ataque_por_pronome_resolve_unico_npc_presente():
    """'vou atacar ele do nada' — sem artigo, o regex de nome nem roda; com
    SÓ 1 NPC na cena, resolve pro único candidato em vez de descartar."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grimbold"]
    garantir_registro(wm)
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Vou atacar ele do nada!", wm)
    assert alvo == "grimbold"
    assert "grimbold" in wm.inimigos_combate


def test_ataque_por_pronome_resolve_unico_inimigo_ja_registrado():
    """Sem NPC presente nomeado mas com 1 inimigo VIVO já em combate."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = []
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "ferido")
    alvo = extrair_alvo_ataque("Ataco ele de novo!", wm)
    assert alvo == "goblin-1"


def test_ataque_por_pronome_nele_tambem_resolve():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grimbold"]
    garantir_registro(wm)
    wm.entrar_combate()
    assert extrair_alvo_ataque("Eu ataco nele com tudo!", wm) == "grimbold"


def test_ataque_por_pronome_ambiguo_mantem_comportamento_antigo():
    """2+ NPCs presentes — pronome continua ambíguo, sem alvo (nunca adivinha)."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grimbold", "aldric"]
    garantir_registro(wm)
    wm.entrar_combate()
    assert extrair_alvo_ataque("Vou atacar ele do nada!", wm) is None


def test_ataque_por_pronome_sem_ninguem_mantem_comportamento_antigo():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = []
    wm.entrar_combate()
    assert extrair_alvo_ataque("Vou atacar ele do nada!", wm) is None


def test_ataque_com_nome_explicito_tem_precedencia_sobre_pronome():
    """Regressão: nome explícito (passo 1) continua tendo precedência — o
    fallback de pronome só entra quando NENHUM nome bate."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grimbold", "aldric"]
    garantir_registro(wm)
    wm.entrar_combate()
    assert extrair_alvo_ataque("Eu ataco o aldric!", wm) == "aldric"


def test_ataque_sem_pronome_de_ataque_nao_aciona_fallback():
    """Texto sem verbo+pronome de ataque (ex: fala social) não deve resolver
    um alvo só porque há 1 NPC presente — o fallback é condicionado ao
    padrão verbal, não dispara pra qualquer turno."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grimbold"]
    garantir_registro(wm)
    wm.entrar_combate()
    assert extrair_alvo_ataque("Eu confio nele.", wm) is None
