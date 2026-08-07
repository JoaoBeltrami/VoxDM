"""
O prefixo cacheável do prompt não pode ser quebrado por fragmento condicional.

Por que existe (CACHE-PREFIXO-ORDEM / P2, 01/08): o cache de prefixo do Groq
    exige match EXATO do começo do prompt — na primeira divergência, tudo daí
    pra frente cai fora, mesmo sendo byte-idêntico. Até 01/08 o
    `abertura_personagem` e o `markers_lista` entravam ANTES do catálogo de
    quests e da cena estática; como o markers alterna em ~40% dos turnos, ele
    derrubava do cache os ~800 chars de quests + a cena estática inteira toda
    vez que ligava ou desligava.
    A linha de base veio do playtest de 01/08, medida pela telemetria que o P1
    instalou: o cache do gpt-oss EXISTE, tem piso de tamanho de prefixo, e
    oscilava entre 0% e 80% com prompt do MESMO tamanho — ~2 800 tokens já
    cacheados caindo fora em metade dos turnos.
Dependências: pytest — monta o prompt em memória, sem rede.
Armadilha: este arquivo existe pela mesma razão do engine/markers.py — impedir
    que o arranjo derive em silêncio quando alguém acrescentar fragmento novo.
    Se um teste daqui falhar, a pergunta certa é "esse fragmento é invariante?",
    não "como faço o teste passar?".
"""

import pytest

from engine.llm.prompt_builder import _montar_mensagens_brief
from engine.llm.types import ContextoMontado
from engine.memory.working_memory import WorkingMemory


def _wm(*, pacing: float, iteracoes: int, nome: str = "Klaus") -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("drevamor", "Mercado de Drevamor", "cache-01")
    wm.player_name = nome
    wm.pacing_nivel = pacing
    wm.narrative.turnos_total = iteracoes
    wm.iteracoes = iteracoes
    # Catálogo de quests: ~800 chars ESTÁVEIS por sessão. É a primeira vítima
    # quando um condicional oscila antes dele.
    wm.quests_modulo = (
        "=== MISSÕES DO MÓDULO (o próximo passo de cada uma) ===\n"
        "• o-reconhecimento [não iniciada] → próximo `receber-missao`: "
        "O líder da vila do jogador pede reconhecimento."
    )
    return wm


def _system(wm: WorkingMemory) -> str:
    ctx = ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[],
        chunks_episodicos=[],
        chunks_regras=[],
        relacoes_grafo=[],
        secrets_visiveis=[],
        transcricao_atual="sigo pela estrada",
    )
    return _montar_mensagens_brief(ctx)[0]["content"]


def _prefixo_comum(a: str, b: str) -> str:
    """O maior começo idêntico entre dois prompts — o que o cache aproveita."""
    limite = min(len(a), len(b))
    i = 0
    while i < limite and a[i] == b[i]:
        i += 1
    return a[:i]


# ── markers_lista: o fragmento que oscila em ~40% dos turnos ─────────────────

def test_alternar_markers_preserva_quests_e_cena_no_prefixo():
    """O ponto da sessão.

    Duas montagens que diferem SÓ no markers_lista (pacing alto vs baixo) têm
    que compartilhar master_system + catálogo de quests + cena estática
    INTEIROS. Antes desta ordem, o prefixo comum morria no primeiro condicional.
    """
    com = _system(_wm(pacing=9.0, iteracoes=10))      # cena dramática → markers entra
    sem = _system(_wm(pacing=1.0, iteracoes=10))      # cena calma → markers fora
    assert com != sem, "o cenário não exercita a alternância do markers"

    prefixo = _prefixo_comum(com, sem)
    assert "MISSÕES DO MÓDULO" in prefixo, (
        f"o catálogo de quests caiu fora do prefixo comum ({len(prefixo)} chars) — "
        "algum condicional voltou a entrar antes dele"
    )
    assert "o-reconhecimento" in prefixo, "o catálogo entrou cortado no prefixo"


def test_markers_aparece_depois_do_catalogo_de_quests():
    """A ordem propriamente dita, não só o efeito."""
    com = _system(_wm(pacing=9.0, iteracoes=10))
    assert com.index("MISSÕES DO MÓDULO") < com.index("[DANO:"), (
        "markers_lista voltou a entrar antes do catálogo de quests"
    )


# ── abertura_personagem: entra só no começo da sessão ────────────────────────

def test_alternar_abertura_preserva_quests_no_prefixo():
    """Mesma prova, alternando o outro condicional que vivia no topo."""
    inicio = _system(_wm(pacing=1.0, iteracoes=0))     # abertura entra
    depois = _system(_wm(pacing=1.0, iteracoes=10))    # abertura fora
    assert inicio != depois, "o cenário não exercita a alternância da abertura"

    prefixo = _prefixo_comum(inicio, depois)
    assert "MISSÕES DO MÓDULO" in prefixo, (
        f"a abertura voltou a quebrar o prefixo ({len(prefixo)} chars)"
    )


def test_personagem_sem_nome_tambem_recebe_abertura_sem_quebrar_prefixo():
    """Session Zero: `player_name` vazio é o outro gatilho da abertura."""
    anonimo = _system(_wm(pacing=1.0, iteracoes=10, nome=""))
    nomeado = _system(_wm(pacing=1.0, iteracoes=10))
    assert "MISSÕES DO MÓDULO" in _prefixo_comum(anonimo, nomeado)


# ── A regra geral, pra fragmento NOVO não furar a fila ───────────────────────

@pytest.mark.parametrize("pacing,iteracoes", [(9.0, 0), (9.0, 10), (1.0, 0), (1.0, 10)])
def test_nenhum_condicional_aparece_antes_do_ultimo_invariante(pacing, iteracoes):
    """Invariante estrutural: em QUALQUER combinação de gates, todo fragmento
    condicional vem depois do último invariante.

    É esta asserção que pega o fragmento novo que alguém acrescentar no topo
    por hábito — o erro que esta sessão veio corrigir.
    """
    sistema = _system(_wm(pacing=pacing, iteracoes=iteracoes))
    fim_invariante = sistema.index("MISSÕES DO MÓDULO")

    for marca, nome in (("[DANO:", "markers_lista"),):
        if marca in sistema:
            assert sistema.index(marca) > fim_invariante, (
                f"{nome} está antes do fim do prefixo invariante"
            )


def test_master_system_continua_sendo_a_primeira_coisa():
    """O maior bloco invariante (6,5k chars) tem que abrir o prompt — se ele
    sair do topo, não há prefixo cacheável nenhum."""
    sistema = _system(_wm(pacing=9.0, iteracoes=0))
    assert sistema.lstrip().startswith("# Você é VoxDM")


def test_prefixo_comum_cobre_o_master_system_inteiro():
    """Piso quantitativo: o prefixo compartilhado tem que ser pelo menos o
    master_system (o bloco que entra em 100% dos turnos)."""
    com = _system(_wm(pacing=9.0, iteracoes=10))
    sem = _system(_wm(pacing=1.0, iteracoes=10))
    from engine.llm.prompt_builder import _carregar_master_system

    assert len(_prefixo_comum(com, sem)) >= len(_carregar_master_system())


# ── PROMPT-ACIMA-DO-TETO (playtest 01/08) ────────────────────────────────────
#
# `chars_system` chegou a 18 442 num turno FORA de combate — 23% acima do teto
# de 15k. O guard de budget já existia e dispararia, mas dizia só o TOTAL, e
# total sem composição não decide nada: não dá pra saber o que cortar sem saber
# quem ocupa o quê. O que cortar é decisão do Beltrami; medir é da engine.

def test_composicao_soma_exatamente_o_prompt():
    """Aritmética da decomposição: os blocos somados dão o acumulado final."""
    from engine.llm.prompt_builder import composicao_do_prompt

    marcos = [("a", 100), ("b", 250), ("c", 250), ("d", 900)]
    comp = composicao_do_prompt(marcos)
    assert comp == {"a": 100, "b": 150, "c": 0, "d": 650}
    assert sum(comp.values()) == marcos[-1][1]


def test_bloco_que_nao_entrou_aparece_com_zero():
    """Gate False vira 0, não some da tabela — é assim que se vê o fragmento
    que nunca sai (ou o que nunca entra)."""
    from engine.llm.prompt_builder import composicao_do_prompt

    assert composicao_do_prompt([("x", 500), ("y", 500)])["y"] == 0


def test_composicao_vazia_nao_quebra():
    from engine.llm.prompt_builder import composicao_do_prompt

    assert composicao_do_prompt([]) == {}


def test_warning_de_budget_carrega_a_composicao():
    """Teste que amarra os dois lados: se alguém tirar o campo do warning, o
    total volta a ser inacionável e ninguém percebe até o próximo playtest."""
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    fonte = (raiz / "engine/llm/prompt_builder.py").read_text(encoding="utf-8")
    i = fonte.index('"prompt_excede_budget"')
    assert "composicao=" in fonte[i : i + 600], (
        "o warning de budget voltou a reportar só o total"
    )


# ── ENGINE-COMO-PERSONAGEM-1 (playtest 07/08) ────────────────────────────────
#
# Três queixas do Beltrami na MESMA sessão: "a LLM começou a narrar a engine",
# "ele começou a usar engine como termo quando deveria ser uma mecânica", "ele
# continua narrando a engine como se eu fosse ela".
#
# Causa-raiz: a linha "ENGINE: ..." era injetada no `texto_jogador` — chegava ao
# modelo com `role: user`. Do ponto de vista dele, o JOGADOR dizia "ENGINE:
# teste de Furtividade = 15 vs CD 15: SUCESSO". Virou até query de RAG.

def _system_com_fatos(fatos: list[str]) -> str:
    from engine.llm.types import ContextoMontado

    ctx = ContextoMontado(
        working_memory=_wm(pacing=1.0, iteracoes=10),
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[],
        transcricao_atual="ataco o carniçal",
        fatos_engine=fatos,
    )
    return _montar_mensagens_brief(ctx)[0]["content"]


def test_fato_da_engine_entra_no_system_nao_na_fala_do_jogador():
    from engine.llm.types import ContextoMontado

    fato = "ENGINE: teste de Furtividade — 13 no dado +2 (DES +2) = 15 vs CD 15: SUCESSO na trave."
    ctx = ContextoMontado(
        working_memory=_wm(pacing=1.0, iteracoes=10),
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[],
        transcricao_atual="me escondo atrás da carroça",
        fatos_engine=[fato],
    )
    msgs = _montar_mensagens_brief(ctx)

    assert "Furtividade" in msgs[0]["content"], "o fato não chegou ao system"
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"] == "me escondo atrás da carroça", (
        "a fala do jogador foi contaminada pelo fato da engine — o bug de 07/08"
    )


def test_palavra_ENGINE_nao_chega_ao_modelo():
    """"começou a usar engine como termo quando deveria ser uma mecânica"."""
    sistema = _system_com_fatos(["ENGINE: seu ataque ACERTOU o carniçal (19 vs CA 12)."])
    corpo = sistema.split("JÁ RESOLVIDO PELA ENGINE")[1]
    assert "ENGINE:" not in corpo, "o prefixo voltou a vazar pro modelo"
    assert "ACERTOU o carniçal" in corpo, "o fato em si sumiu junto com o prefixo"


def test_bloco_proibe_citar_numero_e_falar_com_a_engine():
    sistema = _system_com_fatos(["ENGINE: dano 9."])
    bloco = sistema.split("JÁ RESOLVIDO PELA ENGINE")[1]
    assert "NÃO é fala do jogador" in bloco
    assert "nunca se dirija à engine" in bloco


def test_sem_fatos_o_bloco_nao_aparece():
    """Turno comum não paga o custo do bloco."""
    assert "JÁ RESOLVIDO PELA ENGINE" not in _system_com_fatos([])


def test_fatos_entram_na_zona_dinamica_nao_no_prefixo_cacheavel():
    """Eles mudam a cada turno — no prefixo, derrubariam o cache inteiro."""
    sistema = _system_com_fatos(["ENGINE: dano 9."])
    assert sistema.index("MISSÕES DO MÓDULO") < sistema.index("JÁ RESOLVIDO PELA ENGINE")
# ── ABERTURA-SEMPRE-LIGADA-1 (achado pela telemetria de composição, 07/08) ────
#
# O gate lia `wm.iteracoes`, que NÃO existe na WorkingMemory (o contador vive em
# SessaoAtiva). `getattr` devolvia sempre 0, a condição era sempre True, e o
# fragmento entrou em 100% dos turnos desde 30/07 — inclusive no turno 36, onde
# a composição do warning finalmente mostrou `abertura_personagem: 464`.

def test_abertura_some_depois_do_comeco_da_sessao():
    """O gate agora lê um contador que EXISTE."""
    inicio = _system(_wm(pacing=1.0, iteracoes=0))
    depois = _system(_wm(pacing=1.0, iteracoes=10))
    from engine.llm.prompt_builder import _carregar_abertura_personagem

    abertura = _carregar_abertura_personagem()
    assert abertura, "fixture quebrou: abertura_personagem.md deveria existir"
    assert abertura in inicio, "a abertura tem que entrar no começo da sessão"
    assert abertura not in depois, (
        "a abertura voltou a entrar em turno avançado — o gate está lendo "
        "um campo que não existe de novo"
    )


def test_gate_da_abertura_le_campo_que_existe_de_verdade():
    """Teste que amarra os dois lados: se alguém trocar o contador por um nome
    que a WorkingMemory não tem, o getattr silencia e o bug volta."""
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", "gate-01")
    assert hasattr(wm.narrative, "turnos_total"), (
        "o contador que o gate usa sumiu da WorkingMemory"
    )
    assert not hasattr(wm, "iteracoes"), (
        "se `iteracoes` passou a existir na WM, revisar o gate — foi a ausência "
        "dela que fez a condição ser sempre verdadeira"
    )


def test_personagem_sem_nome_recebe_abertura_mesmo_em_turno_avancado():
    """Session Zero: o outro gatilho continua valendo independente do contador."""
    from engine.llm.prompt_builder import _carregar_abertura_personagem

    assert _carregar_abertura_personagem() in _system(_wm(pacing=1.0, iteracoes=30, nome=""))
