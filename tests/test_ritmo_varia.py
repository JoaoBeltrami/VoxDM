"""
TELL C: o fôlego e a forma de abertura variam — e variam por decisão da ENGINE.

Por que existe (RITMO-MORTO-1, 17/08): `_ritmo_do_turno` rotacionava
    curto/medio/longo lendo `wm.iteracoes` — campo que NÃO existe na
    WorkingMemory. `getattr(..., 0)` devolvia sempre 0, o índice era sempre 0, e
    TODO turno saía "medio" (80 palavras). A função escrita para matar o
    metrônomo era o metrônomo. Mesma falha do ABERTURA-SEMPRE-LIGADA-1, que foi
    consertada no MESMO arquivo em 07/08 sem que ninguém olhasse esta função.
    Medido na régua antes do fix: desvio de ritmo 0.96, e uma corrida inteira
    com as SEIS aberturas na mesma forma.
Dependências: nenhuma — as duas funções são puras.
Armadilha: não basta testar "existe rotação". O bug ANTIGO passaria num teste
    que só chamasse a função com um `wm` fabricado tendo `iteracoes` — porque aí
    o campo existe. O teste precisa usar uma WorkingMemory DE VERDADE, que é
    onde o campo não existe.

Exemplo:
    uv run pytest tests/test_ritmo_varia.py -q
"""

from engine.authority.brief import montar_brief
from engine.llm.prompt_builder import _abertura_do_turno, _ritmo_do_turno
from engine.memory.working_memory import WorkingMemory

_FALA = "Pergunto ao ferreiro sobre o contrato de ferro que os Kael querem fechar."


def _wm(turnos: int, com_npc: bool = True) -> WorkingMemory:
    wm = WorkingMemory(session_id="teste-ritmo")
    wm.narrative.turnos_total = turnos
    if com_npc:
        wm.npcs_presentes = ["ferreiro"]
    return wm


def test_o_folego_realmente_muda_ao_longo_da_sessao():
    """O bug era este: seis turnos, seis vezes "medio"."""
    ritmos = {_ritmo_do_turno(_wm(i), _FALA) for i in range(6)}

    assert ritmos == {"curto", "medio", "longo"}, (
        f"a rotação de fôlego não está viva: {ritmos}"
    )


def test_o_contador_usado_e_o_que_existe_de_verdade():
    """`WorkingMemory` não tem `iteracoes` — quem incrementa é `turnos_total`.

    Se alguém voltar a ler o campo morto, `turnos_total` deixa de mudar o
    resultado e este teste cai.
    """
    wm = WorkingMemory(session_id="teste-ritmo")
    assert not hasattr(wm, "iteracoes"), (
        "a WorkingMemory ganhou `iteracoes`? então revise quem lê o quê — este "
        "teste existe porque esse campo NÃO existia e era lido mesmo assim"
    )

    wm.npcs_presentes = ["ferreiro"]
    vistos = set()
    for i in range(3):
        wm.narrative.turnos_total = i
        vistos.add(_ritmo_do_turno(wm, _FALA))
    assert len(vistos) == 3, f"turnos_total não está movendo o fôlego: {vistos}"


def test_pergunta_curta_ainda_manda_calar():
    """Os sinais de contexto vêm ANTES da rotação e continuam valendo."""
    assert _ritmo_do_turno(_wm(2), "Quanto custa?") == "curto"
    assert _ritmo_do_turno(_wm(0), "Sim.") == "curto"


def test_abertura_varia_de_forma():
    formas = {_abertura_do_turno(_wm(i), "medio") for i in range(6)}
    assert len(formas) >= 2, f"a abertura não varia: {formas}"


def test_abertura_nunca_contradiz_o_folego():
    """"mundo" pede ambiente; o TOM "curto" proíbe ambiente.

    Mandar os dois no mesmo prompt é a falha de 26/07 (o ramo épico apagando o
    fôlego): o modelo lia "narre denso" e, logo abaixo, "máximo 30 palavras".
    """
    for i in range(40):
        assert _abertura_do_turno(_wm(i), "curto") != "mundo"


def test_abertura_nunca_pede_para_comecar_pelo_jogador():
    """Abrir com "Você <verbo>" é o TELL A — variar C às custas de A é troca ruim."""
    formas = {_abertura_do_turno(_wm(i), r) for i in range(40)
              for r in ("curto", "medio", "longo")}
    assert "voce" not in formas and "você" not in formas
    assert formas <= {"fala", "gesto", "mundo", ""}


def test_sem_npc_em_cena_ninguem_pode_falar():
    """Pedir abertura por FALA sem ninguém em cena obrigaria a inventar gente."""
    for i in range(10):
        assert _abertura_do_turno(_wm(i, com_npc=False), "medio") != "fala"


def test_o_brief_carrega_a_abertura_escolhida():
    wm = _wm(0)
    com = montar_brief(wm, _FALA, ritmo="medio", abertura="fala").to_prompt()
    sem = montar_brief(wm, _FALA, ritmo="medio", abertura="").to_prompt()

    assert "ABERTURA:" in com
    assert "ABERTURA:" not in sem, "abertura vazia não pode injetar linha"


def test_abertura_invalida_nao_vaza_para_o_prompt():
    """Vocabulário FECHADO, como o do TOM e o do [ALINHAMENTO]."""
    saida = montar_brief(_wm(0), _FALA, ritmo="medio", abertura="inventada").to_prompt()
    assert "ABERTURA:" not in saida
