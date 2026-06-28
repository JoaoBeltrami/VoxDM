"""
Testes do extractor de quest improvisada (engine/llm/extractor.py) — PLAY5-QUEST (16/06).

Garantem que missões que o Mestre improvisa fora do catálogo do módulo viram
estado rastreável (continuidade + quest log), sem depender do LLM emitir [Q:].
Cobrem também a persistência (dm_state) e a injeção no prompt. Mock do groq — sem rede.
"""

import pytest

from engine.llm.extractor import (
    _quest_reativa,
    _sanitizar_quests,
    aplicar_quests_extraidas,
    extrair_quests_cena,
)
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="quest-01",
    )


def _contexto(wm: WorkingMemory, transcricao: str = "e agora?"):
    """ContextoMontado mínimo com todos os campos obrigatórios."""
    from engine.llm.types import ContextoMontado

    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual=transcricao,
    )


class _FakeGroq:
    """groq.completar fake — devolve um JSON fixo."""

    def __init__(self, resposta: str) -> None:
        self._resposta = resposta

    async def completar(self, *args, **kwargs) -> str:
        return self._resposta


# ── NarrativeState.registrar_quest_improvisada / concluir ────────────────────────

def test_registrar_quest_improvisada():
    wm = _wm()
    assert wm.narrative.registrar_quest_improvisada(
        "achar-ferreiro", "Achar o ferreiro", "Encontrar Bram, sumido há 3 dias"
    )
    assert len(wm.quests_improvisadas) == 1
    q = wm.quests_improvisadas[0]
    assert q["id"] == "achar-ferreiro"
    assert q["titulo"] == "Achar o ferreiro"
    assert q["status"] == "ativa"
    # Nova missão entra na crônica
    assert any("Achar o ferreiro" in c for c in wm.narrative.cronica)


def test_registrar_quest_dedup():
    wm = _wm()
    assert wm.narrative.registrar_quest_improvisada("q1", "Q1", "obj")
    assert not wm.narrative.registrar_quest_improvisada("q1", "Q1 dup", "outro")
    assert len(wm.quests_improvisadas) == 1


def test_registrar_quest_id_vazio_rejeitado():
    wm = _wm()
    assert not wm.narrative.registrar_quest_improvisada("  ", "Sem id", "obj")
    assert wm.quests_improvisadas == []


def test_registrar_quest_cap_eviction():
    wm = _wm()
    for i in range(9):
        wm.narrative.registrar_quest_improvisada(f"q{i}", f"Q{i}", "obj")
    assert len(wm.quests_improvisadas) == 6  # cap _MAX_QUESTS_IMPROV
    # Eviction oldest: q0/q1/q2 saíram, q8 ficou
    ids = {q["id"] for q in wm.quests_improvisadas}
    assert "q0" not in ids
    assert "q8" in ids


def test_concluir_quest_improvisada():
    wm = _wm()
    wm.narrative.registrar_quest_improvisada("q1", "Q1", "obj")
    assert wm.narrative.concluir_quest_improvisada("q1")
    assert wm.quests_improvisadas[0]["status"] == "concluida"
    # Re-concluir não muda estado
    assert not wm.narrative.concluir_quest_improvisada("q1")
    assert any("cumprida" in c.lower() for c in wm.narrative.cronica)


def test_concluir_quest_inexistente():
    wm = _wm()
    assert not wm.narrative.concluir_quest_improvisada("fantasma")


# ── _sanitizar_quests ────────────────────────────────────────────────────────────

def test_sanitizar_quests_novas_valida():
    out = _sanitizar_quests(
        {"novas": [{"id": "Achar Ferreiro", "titulo": "Achar Ferreiro", "objetivo": "ir lá"}]},
        ids_abertos=set(),
    )
    assert out["novas"] == [
        {"id": "achar-ferreiro", "titulo": "Achar Ferreiro", "objetivo": "ir lá"}
    ]
    assert out["concluidas"] == []


def test_sanitizar_quests_nao_duplica_aberta():
    out = _sanitizar_quests(
        {"novas": [{"id": "q1", "titulo": "Q1", "objetivo": "x"}]},
        ids_abertos={"q1"},
    )
    assert out["novas"] == []  # já está aberta


def test_sanitizar_quests_concluidas_so_abertas():
    out = _sanitizar_quests(
        {"novas": [], "concluidas": ["q1", "fantasma"]},
        ids_abertos={"q1"},
    )
    assert out["concluidas"] == ["q1"]  # 'fantasma' não está aberta → rejeitado


def test_sanitizar_quests_cap_e_dedup():
    bruto = {"novas": [{"id": f"q{i}", "titulo": f"Q{i}", "objetivo": "o"} for i in range(5)]}
    out = _sanitizar_quests(bruto, ids_abertos=set())
    assert len(out["novas"]) == 3  # cap defensivo por turno


def test_sanitizar_quests_vazio():
    out = _sanitizar_quests({}, ids_abertos=set())
    assert out == {"novas": [], "concluidas": []}


# ── QUEST-SPAM (playtest 27/06): movimento/ação física momentânea ≠ missão ────

@pytest.mark.parametrize("qid,titulo", [
    ("subir-ao-andar-superior", "Subir ao andar superior"),
    ("continuar-no-corredor", "Continuar no corredor"),
    ("acender-fosforo", "Acender o fósforo"),
    ("hesita-um-segundo", "Hesita um segundo"),
    ("sentir-que-esta-escondendo-algo", "Sentir que está escondendo algo"),
    ("pegar-o-amuleto", "Pegar o amuleto"),
    ("abrir-a-porta", "Abrir a porta"),
])
def test_quest_momentanea_e_reativa(qid, titulo):
    assert _quest_reativa(qid, titulo) is True


@pytest.mark.parametrize("qid,titulo", [
    ("investigar-as-luzes-da-torre", "Investigar as luzes da torre"),
    ("encontrar-o-ferreiro-sumido", "Encontrar o ferreiro sumido"),
    ("descobrir-quem-matou-o-prefeito", "Descobrir quem matou o prefeito"),
    ("explorar-as-catacumbas", "Explorar as catacumbas"),
])
def test_quest_objetivo_real_nao_e_reativa(qid, titulo):
    # Verbos ambíguos (investigar/encontrar/descobrir/explorar) PODEM ser objetivo
    # real — não foram adicionados ao filtro, pra não matar missão legítima.
    assert _quest_reativa(qid, titulo) is False


def test_sanitizar_quests_filtra_momentaneas_preserva_objetivo():
    out = _sanitizar_quests(
        {"novas": [
            {"id": "subir-ao-andar-superior", "titulo": "Subir ao andar superior", "objetivo": "ir pra cima"},
            {"id": "acender-fosforo", "titulo": "Acender o fósforo", "objetivo": "iluminar"},
            {"id": "investigar-a-torre", "titulo": "Investigar a torre", "objetivo": "descobrir o que há lá"},
        ]},
        ids_abertos=set(),
    )
    ids = [q["id"] for q in out["novas"]]
    assert "subir-ao-andar-superior" not in ids
    assert "acender-fosforo" not in ids
    assert "investigar-a-torre" in ids  # objetivo real sobrevive


# ── aplicar_quests_extraidas ─────────────────────────────────────────────────────

def test_aplicar_registra_e_conclui():
    wm = _wm()
    wm.narrative.registrar_quest_improvisada("antiga", "Antiga", "obj")
    novas, concluidas = aplicar_quests_extraidas(
        wm,
        {
            "novas": [{"id": "nova", "titulo": "Nova", "objetivo": "fazer X"}],
            "concluidas": ["antiga"],
        },
    )
    assert novas == ["nova"]
    assert concluidas == ["antiga"]
    estados = {q["id"]: q["status"] for q in wm.quests_improvisadas}
    assert estados == {"antiga": "concluida", "nova": "ativa"}


def test_aplicar_vazio_noop():
    wm = _wm()
    novas, concluidas = aplicar_quests_extraidas(wm, {"novas": [], "concluidas": []})
    assert novas == []
    assert concluidas == []
    assert wm.quests_improvisadas == []


# ── extrair_quests_cena (mock groq) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extrair_quests_cena_parse():
    groq = _FakeGroq(
        '{"novas": [{"id": "achar-bram", "titulo": "Achar Bram", '
        '"objetivo": "encontrar o ferreiro sumido"}], "concluidas": []}'
    )
    out = await extrair_quests_cena(
        groq, "O velho pede que você encontre Bram, o ferreiro sumido.", []
    )
    assert out["novas"][0]["id"] == "achar-bram"
    assert out["concluidas"] == []


@pytest.mark.asyncio
async def test_extrair_quests_cena_narracao_vazia():
    groq = _FakeGroq('{"novas": [], "concluidas": []}')
    assert await extrair_quests_cena(groq, "   ", []) is None


@pytest.mark.asyncio
async def test_extrair_quests_cena_json_invalido():
    groq = _FakeGroq("não consigo ajudar com isso")
    assert await extrair_quests_cena(groq, "algo aconteceu", []) is None


@pytest.mark.asyncio
async def test_extrair_quests_cena_conclui_aberta():
    groq = _FakeGroq('{"novas": [], "concluidas": ["q1"]}')
    abertas = [{"id": "q1", "titulo": "Q1", "objetivo": "x", "status": "ativa"}]
    out = await extrair_quests_cena(groq, "Bram aparece, são e salvo.", abertas)
    assert out["concluidas"] == ["q1"]


# ── Persistência via dm_state (roundtrip) ────────────────────────────────────────

def test_quests_persistem_via_dm_state():
    from types import SimpleNamespace

    wm = _wm()
    wm.narrative.registrar_quest_improvisada("q1", "Q1", "obj1")
    wm.narrative.concluir_quest_improvisada("q1")
    wm.narrative.registrar_quest_improvisada("q2", "Q2", "obj2")
    dm_state = {"quests_improvisadas": [dict(q) for q in wm.quests_improvisadas]}

    wm2 = _wm()
    wm2.aplicar_character_state(SimpleNamespace(dm_state=dm_state))
    assert len(wm2.quests_improvisadas) == 2
    estados = {q["id"]: q["status"] for q in wm2.quests_improvisadas}
    assert estados == {"q1": "concluida", "q2": "ativa"}


def test_restauracao_nao_sobrescreve_ativas():
    from types import SimpleNamespace

    wm = _wm()
    wm.narrative.registrar_quest_improvisada("viva", "Viva", "obj")
    # dm_state tem outra quest, mas a memória ativa não está vazia → não restaura
    wm.aplicar_character_state(
        SimpleNamespace(dm_state={"quests_improvisadas": [
            {"id": "antiga", "titulo": "Antiga", "objetivo": "x", "status": "ativa"}
        ]})
    )
    ids = {q["id"] for q in wm.quests_improvisadas}
    assert ids == {"viva"}


# ── Injeção no prompt ────────────────────────────────────────────────────────────

def test_quest_ativa_entra_no_prompt():
    from engine.llm.prompt_builder import montar_mensagens

    wm = _wm()
    wm.narrative.registrar_quest_improvisada(
        "achar-bram", "Achar Bram", "encontrar o ferreiro sumido"
    )
    mensagens = montar_mensagens(_contexto(wm))
    system = "\n".join(m["content"] for m in mensagens if m["role"] == "system")
    assert "MISSÕES EM ANDAMENTO" in system
    assert "Achar Bram" in system


def test_quest_concluida_nao_entra_no_prompt():
    from engine.llm.prompt_builder import montar_mensagens

    wm = _wm()
    wm.narrative.registrar_quest_improvisada("feita", "Feita", "obj")
    wm.narrative.concluir_quest_improvisada("feita")
    mensagens = montar_mensagens(_contexto(wm))
    system = "\n".join(m["content"] for m in mensagens if m["role"] == "system")
    assert "MISSÕES EM ANDAMENTO" not in system
