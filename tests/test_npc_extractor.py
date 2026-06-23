"""
Testes do extractor de NPC (engine/llm/extractor.py) — PLAY5-NPC (13/06).

Garantem que NPCs improvisados pelo Mestre viram presença de fato, sem depender
do LLM emitir [NPC:]. Mock do groq — sem rede.
"""

import pytest

from engine.llm.extractor import (
    _canonico,
    _e_apelido_do_jogador,
    _kebab_id,
    _npc_fantasma,
    _sanitizar_npcs,
    aplicar_npcs_extraidos,
    extrair_npcs_cena,
)
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="npc-01",
    )


class _FakeGroq:
    """groq.completar fake — devolve um JSON fixo."""

    def __init__(self, resposta: str) -> None:
        self._resposta = resposta

    async def completar(self, *args, **kwargs) -> str:
        return self._resposta


# ── _sanitizar_npcs ──────────────────────────────────────────────────────────

def test_sanitizar_npcs_valido():
    out = _sanitizar_npcs({"npcs": [{"id": "Velho Mercador", "nome": "Velho Mercador"}]})
    assert out == [{"id": "velho-mercador", "nome": "Velho Mercador"}]


# PT-3 (playtest #7): fragmento de narração com verbo no fim vira "NPC presente".
@pytest.mark.parametrize("nid", [
    "velho-sorri", "figura-observa", "o-homem-ri", "guarda-grita",
    "sombra-recua", "anciao-murmurou",
])
def test_npc_fantasma_verbo_no_fim(nid):
    assert _npc_fantasma(nid) is True


@pytest.mark.parametrize("nid", [
    "velho-mercador", "aldric-drevasson", "mira", "garrek",
    "osmund-o-exilado", "maren-drevadottir",
])
def test_npc_real_nao_e_fantasma(nid):
    assert _npc_fantasma(nid) is False


def test_sanitizar_npcs_filtra_fragmento_de_narracao():
    """'o velho sorri' não vira NPC; 'Mira' (nome real) sobrevive."""
    bruto = {"npcs": [
        {"id": "velho-sorri", "nome": "Velho"},
        {"id": "mira", "nome": "Mira"},
        {"id": "figura-observa", "nome": "Figura"},
    ]}
    out = _sanitizar_npcs(bruto)
    assert [n["id"] for n in out] == ["mira"]


def test_sanitizar_npcs_dedup_e_cap():
    # sufixo de letra (não número) pra não colidir com o filtro de figurante numerado
    bruto = {"npcs": [{"id": f"npc-{chr(97 + i)}", "nome": f"N{i}"} for i in range(10)]
             + [{"id": "npc-a", "nome": "dup"}]}
    out = _sanitizar_npcs(bruto)
    assert len(out) == 4  # cap defensivo
    assert len({n["id"] for n in out}) == len(out)  # sem duplicata


def test_sanitizar_npcs_pula_invalido():
    out = _sanitizar_npcs({"npcs": [{"nome": "Sem id"}, "lixo", {"id": "  "}]})
    assert out == []


def test_sanitizar_npcs_vazio():
    assert _sanitizar_npcs({}) == []
    assert _sanitizar_npcs({"npcs": []}) == []


# ── NPC-DUP-1 / NPC-CITADO-2 (playtest #8) ──────────────────────────────────────

def test_kebab_id_translitera_acento():
    # 'Braço' não pode virar 'bra-o' (ç→dash) — transliterar p/ 'braco'
    assert _kebab_id("Gharen Braço de Ferro") == "gharen-braco-de-ferro"
    assert _kebab_id("Anção") == "ancao"


def test_canonico_colapsa_variantes_de_acento():
    # as duas variantes do MESMO NPC viram a mesma chave canônica
    assert _canonico("gharen-bra-o-de-ferro") == _canonico("gharen-brao-de-ferro")
    assert _canonico("gharen-braço-de-ferro") == _canonico("gharen-braco-de-ferro")


def test_aplicar_dedup_variante_de_acento():
    """NPC-DUP-1: 'Gharen Braço' não entra duas vezes por grafia diferente."""
    wm = _wm()
    aplicar_npcs_extraidos(wm, [{"id": "gharen-bra-o-de-ferro", "nome": "Gharen"}])
    add2 = aplicar_npcs_extraidos(wm, [{"id": "gharen-brao-de-ferro", "nome": "Gharen"}])
    assert add2 == []  # variante canônica já presente
    assert len(wm.npcs_presentes) == 1


def test_aplicar_dedup_epiteto_de_local():
    """NPC-DUP-2: 'Brennan' e 'Brennan Sem Vila' (alcunha do local) são o mesmo
    NPC — o epíteto anexado não pode duplicá-lo na cena."""
    wm = _wm()
    wm.npcs_presentes = ["brennan"]
    add = aplicar_npcs_extraidos(wm, [{"id": "brennan-sem-vila", "nome": "Brennan Sem Vila"}])
    assert add == []
    assert len(wm.npcs_presentes) == 1
    # caminho inverso: presente com alcunha, extrai nome curto
    wm2 = _wm()
    wm2.npcs_presentes = ["brennan-sem-vila"]
    add2 = aplicar_npcs_extraidos(wm2, [{"id": "brennan", "nome": "Brennan"}])
    assert add2 == []
    assert len(wm2.npcs_presentes) == 1


def test_aplicar_nao_funde_nomes_distintos():
    """A dedup por primeiro nome não pode fundir NPCs diferentes de um token."""
    wm = _wm()
    wm.npcs_presentes = ["aldric"]
    add = aplicar_npcs_extraidos(wm, [{"id": "aldrina", "nome": "Aldrina"}])
    assert add == ["aldrina"]
    assert len(wm.npcs_presentes) == 2


@pytest.mark.parametrize("nid", [
    "pessoa-1", "pessoa-2", "homem-1", "viajante-espalhado-1", "cavaleiro-solitario-1",
])
def test_npc_figurante_numerado_e_fantasma(nid):
    assert _npc_fantasma(nid) is True


def test_sanitizar_filtra_figurante_numerado():
    bruto = {"npcs": [
        {"id": "pessoa-1", "nome": "Pessoa"},
        {"id": "garrek", "nome": "Garrek"},
        {"id": "viajante-espalhado-1", "nome": "Viajante"},
    ]}
    out = _sanitizar_npcs(bruto)
    assert [n["id"] for n in out] == ["garrek"]


# ── aplicar_npcs_extraidos ──────────────────────────────────────────────────────

def test_aplicar_registra_novo_npc():
    wm = _wm()
    add = aplicar_npcs_extraidos(wm, [{"id": "garrek", "nome": "Garrek"}])
    assert add == ["garrek"]
    assert "garrek" in wm.npcs_presentes
    assert "garrek" in wm.scene.npcs_apresentados


def test_aplicar_pula_ja_presente():
    wm = _wm()
    wm.npcs_presentes = ["garrek"]
    add = aplicar_npcs_extraidos(wm, [{"id": "garrek", "nome": "Garrek"}])
    assert add == []  # já estava


def test_aplicar_pula_jogador():
    wm = _wm()
    wm.player_name = "Abaco Baco"
    add = aplicar_npcs_extraidos(wm, [{"id": "abaco-baco", "nome": "Abaco Baco"}])
    assert add == []
    assert "abaco-baco" not in wm.npcs_presentes


# ── extrair_npcs_cena (mock groq) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extrair_npcs_cena_parse():
    groq = _FakeGroq('{"npcs": [{"id": "mira", "nome": "Mira"}]}')
    out = await extrair_npcs_cena(groq, "Mira se aproxima do balcão.", [])
    assert out == [{"id": "mira", "nome": "Mira"}]


@pytest.mark.asyncio
async def test_extrair_npcs_cena_narracao_vazia():
    groq = _FakeGroq('{"npcs": []}')
    assert await extrair_npcs_cena(groq, "   ", []) is None


@pytest.mark.asyncio
async def test_extrair_npcs_cena_json_invalido():
    groq = _FakeGroq("desculpe, não consigo")
    assert await extrair_npcs_cena(groq, "algo aconteceu", []) is None


# ── _e_apelido_do_jogador (NPC-APELIDO) ─────────────────────────────────────────

@pytest.mark.parametrize("nome,narracao", [
    ("Ladrãozinho", "Ninguém te convidou, ladrãozinho."),
    ("forasteiro", "Você não é bem-vindo aqui, forasteiro."),
    ("Ladrãozinho", "Ladrãozinho, você acha que pode entrar assim?"),
    ("pequeno tolo", "Eu já te avisei, pequeno tolo."),
])
def test_apelido_do_jogador_vocativo(nome, narracao):
    # Alcunha dirigida ao jogador (2ª pessoa) — não é NPC.
    assert _e_apelido_do_jogador(nome, narracao) is True


@pytest.mark.parametrize("nome,narracao", [
    # NPC que AGE na cena é preservado mesmo com vocativo de 2ª pessoa por perto.
    ("Brennan", "Você é tolo, Brennan recua para as sombras."),
    ("Aldric", "Aldric disse que você deve ir embora."),
    # Sem vocativo de 2ª pessoa — NPC normal.
    ("Mira", "Mira se aproxima do balcão e observa a sala."),
    # Nome ausente da narração — não há como julgar, mantém.
    ("Vyrmathax", "O porto cheira a sal e peixe podre."),
])
def test_apelido_do_jogador_mantem_npc(nome, narracao):
    assert _e_apelido_do_jogador(nome, narracao) is False


def test_apelido_do_jogador_nome_curto_ignorado():
    # < 3 chars é ruidoso demais — nunca descarta por vocativo.
    assert _e_apelido_do_jogador("Ré", "Eu te vejo, ré.") is False


@pytest.mark.asyncio
async def test_extrair_npcs_cena_descarta_apelido_do_jogador():
    # O 8B extrai "Ladrãozinho" de um vocativo dirigido ao jogador → filtrado.
    groq = _FakeGroq('{"npcs": [{"id": "ladraozinho", "nome": "Ladrãozinho"}]}')
    out = await extrair_npcs_cena(groq, "Ninguém te convidou, ladrãozinho.", [])
    assert out == []


@pytest.mark.asyncio
async def test_extrair_npcs_cena_mantem_npc_real_com_vocativo():
    # NPC real que age na cena não é confundido com alcunha do jogador.
    groq = _FakeGroq('{"npcs": [{"id": "brennan", "nome": "Brennan"}]}')
    out = await extrair_npcs_cena(groq, "Você é tolo, Brennan recua para as sombras.", [])
    assert out == [{"id": "brennan", "nome": "Brennan"}]
