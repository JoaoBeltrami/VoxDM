"""
Testes do extractor de NPC (engine/llm/extractor.py) — PLAY5-NPC (13/06).

Garantem que NPCs improvisados pelo Mestre viram presença de fato, sem depender
do LLM emitir [NPC:]. Mock do groq — sem rede.
"""

import pytest

from engine.llm.extractor import (
    _canonico,
    _capar_npcs_presentes,
    _chave_conjunto,
    _e_apelido_do_jogador,
    _e_entidade_invalida,
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


# ── NPC-DUP-3 (playtest 03/07, sess-6a851e0fa7f1): tokens reordenados ─────────

def test_chave_conjunto_colapsa_reordenacao():
    """As duas grafias do monge da taverna de Kaelmünd viram a MESMA chave:
    conjunto ordenado de tokens, sem os estruturais (da/de/o...)."""
    assert _chave_conjunto("taverna-kaelmund-monge") == "kaelmund-monge-taverna"
    assert (
        _chave_conjunto("monge-da-taverna-kaelmund")
        == _chave_conjunto("taverna-kaelmund-monge")
    )


def test_chave_conjunto_ignora_tokens_estruturais():
    """'monge-da-taverna' e 'monge-taverna' são o mesmo NPC — artigo/preposição
    não distingue pessoa."""
    assert _chave_conjunto("monge-da-taverna") == _chave_conjunto("monge-taverna")


def test_chave_conjunto_nao_colapsa_nomes_distintos():
    """Conjuntos de tokens diferentes = NPCs diferentes — a chave secundária não
    pode fundir gente distinta."""
    assert _chave_conjunto("aldric-drevasson") != _chave_conjunto("dalla-drevadottir")
    assert (
        _chave_conjunto("guarda-do-portao-norte")
        != _chave_conjunto("guarda-da-torre-sul")
    )


def test_aplicar_dedup_tokens_reordenados():
    """NPC-DUP-3: o mesmo NPC descritivo com os tokens reordenados não entra
    duas vezes na cena ('taverna-kaelmund-monge' ↔ 'monge-da-taverna-kaelmund')."""
    wm = _wm()
    wm.npcs_presentes = ["taverna-kaelmund-monge"]
    add = aplicar_npcs_extraidos(
        wm, [{"id": "monge-da-taverna-kaelmund", "nome": "Monge da Taverna"}]
    )
    assert add == []
    assert len(wm.npcs_presentes) == 1
    # caminho inverso: presente com preposição, candidato reordenado sem ela
    wm2 = _wm()
    wm2.npcs_presentes = ["monge-da-taverna-kaelmund"]
    add2 = aplicar_npcs_extraidos(
        wm2, [{"id": "taverna-kaelmund-monge", "nome": "Monge"}]
    )
    assert add2 == []
    assert len(wm2.npcs_presentes) == 1


def test_aplicar_dedup_reordenado_so_com_estrutural():
    """Reordenação + estrutural: 'taverna-do-monge' e 'monge-da-taverna' têm
    chaves primárias diferentes ('taverna' vs 'monge') — só a secundária pega."""
    wm = _wm()
    wm.npcs_presentes = ["taverna-do-monge"]
    add = aplicar_npcs_extraidos(wm, [{"id": "monge-da-taverna", "nome": "Monge"}])
    assert add == []
    assert len(wm.npcs_presentes) == 1


def test_aplicar_nao_funde_papeis_distintos_de_mesmo_tipo():
    """NPCs que COMPARTILHAM um token de papel ('guarda') mas são pessoas
    distintas coexistem — a chave-conjunto usa frozenset estrutural pequeno de
    propósito (não _PALAVRAS_COMUNS inteiro, que descartaria 'guarda' e fundiria
    os dois). Nota: 'guarda-do-portao-norte' × 'guarda-da-torre-sul' já colapsam
    ANTES da chave secundária, pela regra do epíteto (mesmo 1º token) — por isso
    o par aqui tem primeiros tokens distintos."""
    wm = _wm()
    wm.npcs_presentes = ["capitao-da-guarda-norte"]
    add = aplicar_npcs_extraidos(
        wm, [{"id": "guarda-da-torre-sul", "nome": "Guarda da Torre Sul"}]
    )
    assert add == ["guarda-da-torre-sul"]
    assert len(wm.npcs_presentes) == 2


def test_aplicar_nomes_proprios_distintos_coexistem():
    """Regressão: a chave secundária não pode fundir nomes próprios distintos."""
    wm = _wm()
    wm.npcs_presentes = ["aldric-drevasson"]
    add = aplicar_npcs_extraidos(
        wm, [{"id": "maren-drevadottir", "nome": "Maren Drevadottir"}]
    )
    assert add == ["maren-drevadottir"]
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
    # Regressão: "<Nome>, <aposto>, te <verbo>" — Nome é SUJEITO, "te" é objeto.
    # Antes virava falso-apelido e dropava o NPC (achado no hardening adversarial).
    ("Gareth", "Gareth, o ferreiro, te entrega a espada."),
    ("Aldric", "Aldric, o velho guarda, te observa em silêncio."),
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


# ── _e_entidade_invalida + cap (PLAYTEST 24/06 — flood de NPC-lixo) ──────────

@pytest.mark.parametrize("nid", [
    "drevamor",              # o LOCAL atual
    "adeusa-da-magia",       # "a deusa" colado → divindade
    "deusa-da-guerra",
    "clerigo-desconhecido",  # figurante anônimo
    "figura-encapuzada",
    # NPC-LIXO (playtest 27/06): DESCRITORES sem nome próprio que o 8B registrou
    # como NPC presente. "velho-mercador" era a decisão de produto pendente (PT-3);
    # o Beltrami decidiu rejeitar descritores. Objetos ("barril") também.
    "velho-mercador",
    "homem-esguio",
    "mulher-fragil",
    "homem-de-capuz",
    "sombra-contorcida",
    "recem-chegado",
    "pequena-bruxa",
    "sussurro-da-esquerda",
    "guarda-noturno",
    "velho-amigo",
    "barril",                # objeto, id de 1 token só
    "ela",                   # PRONOME (playtest 29/06: "ela" virou NPC e entrou no combate)
    "ele",
    "voce",
    # META/OOC (playtest 03/07): "guia-do-jogo" registrado como NPC — gerou
    # timeout de Neo4j TODO turno pelo resto da sessão (não existe no grafo).
    "guia-do-jogo",
    # PAPÉIS GENÉRICOS DE COMBATE (colateral 04/07): "oponente" vazou pra
    # npcs_presentes — _npc_fantasma só barra o sufixo numérico ("oponente-1").
    "oponente",
    "inimigo",
    "adversario",
    "atacante-encapuzado",
])
def test_entidade_invalida_rejeita_lixo(nid):
    assert _e_entidade_invalida(nid, "drevamor", "Drevamor") is True


@pytest.mark.parametrize("nid", [
    "aldric-drevasson",
    "maren-drevadottir",
    "osmund-o-exilado",
    "gharen-braco-de-ferro",  # nome próprio + descritor → preserva
    "historiador",            # papel legítimo do módulo, id de 1 token
    # Regressão (hardening adversarial 24/06): NÃO podem ser rejeitados — "deus"
    # como substring pegava nomes próprios; "divino/divina" são epítetos de pessoa.
    "amadeus",
    "deusdedit-o-velho",
    "aldric-o-divino",
    "divina-cantora",
])
def test_entidade_invalida_preserva_npc_real(nid):
    assert _e_entidade_invalida(nid, "drevamor", "Drevamor") is False


# ── NPC-LOCAL-2 (playtest 05/07): OUTRO local do módulo também não é NPC ─────


def test_entidade_invalida_rejeita_outro_local_do_modulo():
    """Cena atual é 'drevamor'; 'kaelmund' é OUTRO local do módulo (citado de
    passagem) — não é a location_id/nome da cena, mas segue sendo um local."""
    from engine.llm import extractor as extractor_mod

    original = extractor_mod._LOCATIONS_MODULO
    extractor_mod._LOCATIONS_MODULO = None  # força rebuild do cache
    try:
        assert _e_entidade_invalida("kaelmund", "drevamor", "Drevamor") is True
    finally:
        extractor_mod._LOCATIONS_MODULO = original


def test_aplicar_descarta_outro_local_do_modulo():
    from engine.llm import extractor as extractor_mod

    original = extractor_mod._LOCATIONS_MODULO
    extractor_mod._LOCATIONS_MODULO = None
    try:
        wm = _wm()  # location_id="drevamor"
        extraidos = [
            {"id": "kaelmund", "nome": "Kaelmund"},         # outro local do módulo
            {"id": "aldric-drevasson", "nome": "Aldric"},   # real
        ]
        add = aplicar_npcs_extraidos(wm, extraidos)
        assert add == ["aldric-drevasson"]
        assert "kaelmund" not in wm.npcs_presentes
    finally:
        extractor_mod._LOCATIONS_MODULO = original


def test_locations_canonicas_modulo_falha_silenciosa_com_path_invalido(monkeypatch):
    """Módulo ausente/corrompido → set vazio, filtro cai pro comportamento
    de antes (só a cena atual) sem lançar."""
    from config import settings as cfg_settings
    from engine.llm import extractor as extractor_mod

    original_cache = extractor_mod._LOCATIONS_MODULO
    original_path = cfg_settings.DEFAULT_MODULE_PATH
    extractor_mod._LOCATIONS_MODULO = None
    cfg_settings.DEFAULT_MODULE_PATH = "modulo/inexistente.json"
    try:
        assert extractor_mod._locations_canonicas_modulo() == set()
    finally:
        extractor_mod._LOCATIONS_MODULO = original_cache
        cfg_settings.DEFAULT_MODULE_PATH = original_path


def test_aplicar_descarta_local_e_divindade():
    wm = _wm()  # location_id="drevamor"
    extraidos = [
        {"id": "drevamor", "nome": "Drevamor"},        # local
        {"id": "adeusa-da-magia", "nome": "A Deusa"},   # divindade
        {"id": "aldric-drevasson", "nome": "Aldric"},   # real
    ]
    add = aplicar_npcs_extraidos(wm, extraidos)
    assert add == ["aldric-drevasson"]
    assert "drevamor" not in wm.npcs_presentes
    assert "adeusa-da-magia" not in wm.npcs_presentes


class _WMCap:
    """WM mínima pra testar o cap sem montar WorkingMemory inteira."""
    class _Scene:
        npcs_apresentados = {"aldric-drevasson", "maren-drevadottir"}
    def __init__(self, pres):
        self.scene = self._Scene()
        self.npcs_presentes = list(pres)


def test_cap_npcs_presentes_evicta_background_preserva_apresentados():
    pres = ["aldric-drevasson", "maren-drevadottir", "velho-mercador",
            "mistra", "tharnvik", "kaelmund", "dreva", "estrano", "x", "y"]
    wm = _WMCap(pres)
    _capar_npcs_presentes(wm)
    assert len(wm.npcs_presentes) == 8
    # NPCs que o jogador conheceu nunca são evictados
    assert "aldric-drevasson" in wm.npcs_presentes
    assert "maren-drevadottir" in wm.npcs_presentes


def test_cap_nao_mexe_abaixo_do_teto():
    pres = ["aldric-drevasson", "maren-drevadottir"]
    wm = _WMCap(pres)
    _capar_npcs_presentes(wm)
    assert wm.npcs_presentes == pres


# ── F6 (PLAYTEST 24/06): conhecer NPC popula a crônica (sessão social) ───────

def test_conhecer_npc_registra_na_cronica():
    wm = _wm()
    aplicar_npcs_extraidos(wm, [{"id": "garrek", "nome": "Garrek"}])
    assert any("Garrek" in e for e in wm.narrative.cronica)
    assert any("🤝" in e for e in wm.narrative.cronica)


def test_conhecer_npc_nao_duplica_lixo_filtrado():
    # entidade inválida (o local) não vira NPC NEM entra na crônica
    wm = _wm()  # location_id="drevamor"
    aplicar_npcs_extraidos(wm, [{"id": "drevamor", "nome": "Drevamor"}])
    assert not any("Drevamor" in e for e in wm.narrative.cronica)


# ── NPC-SÍMILE + vocativo-final (playtest 05/07, sess-95a7c47468c5) ───────────
# "o amuleto pulsa... quase como um guia silencioso" virou NPC 'guia-silencioso';
# "Muito bem, marinheiro." (Mestre chamando o JOGADOR) virou NPC 'marinheiro'.


def test_simile_descarta_comparacao():
    from engine.llm.extractor import _e_mencao_simile

    narr = "O amuleto pulsa com um calor suave, quase como um guia silencioso."
    assert _e_mencao_simile("guia silencioso", narr) is True


def test_simile_preserva_mencao_real_mesmo_com_comparacao():
    from engine.llm.extractor import _e_mencao_simile

    # 1ª menção é símile, 2ª é o personagem de verdade — preserva.
    narr = (
        "Ele luta feito um berserker enfurecido. Mais tarde, o berserker "
        "do norte cruza os braços e cospe no chão."
    )
    assert _e_mencao_simile("berserker", narr) is False


def test_simile_nome_ausente_da_narracao_nao_e_simile():
    from engine.llm.extractor import _e_mencao_simile

    assert _e_mencao_simile("guia silencioso", "A noite cai sobre as dunas.") is False


def test_vocativo_final_em_fala_descarta_apelido():
    from engine.llm.extractor import _e_apelido_do_jogador

    assert _e_apelido_do_jogador("marinheiro", 'Ele sorri. "Muito bem, marinheiro."') is True
    assert _e_apelido_do_jogador("marinheiro", '"E aí, marinheiro?" Ele te encara.') is True


def test_vocativo_final_apresentacao_preserva_name_reveal():
    from engine.llm.extractor import _e_apelido_do_jogador

    # "Sou eu, Kael." é NAME-REVEAL de NPC, não vocativo ao jogador.
    assert _e_apelido_do_jogador("kael", 'A figura abaixa o capuz. "Sou eu, Kael."') is False
    assert _e_apelido_do_jogador("kael", '"Este é meu irmão, Kael." Ele aponta.') is False


def test_vocativo_final_aposto_fora_de_aspas_preserva():
    from engine.llm.extractor import _e_apelido_do_jogador

    # Aposto de narração (sem aspas) não é vocativo.
    assert _e_apelido_do_jogador("meridok", "Ele cumprimenta o capitão, Meridok.") is False


def test_vocativo_final_nome_que_age_preserva():
    from engine.llm.extractor import _e_apelido_do_jogador

    # A guarda de sujeito-3ª-pessoa tem precedência: NPC que AGE nunca é dropado.
    assert (
        _e_apelido_do_jogador("aldric", '"Cuidado, Aldric." Aldric saca a espada e recua.')
        is False
    )
