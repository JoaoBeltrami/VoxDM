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
