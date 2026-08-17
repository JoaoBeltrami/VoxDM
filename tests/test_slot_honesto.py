"""
O nome do slot não pode mentir sobre o modelo que ele roda — nem depois da
próxima troca.

Por que existe (SLOT-MENTE-1, pedido do Beltrami em 01/08): o slot `groq-8b`
    rodava `openai/gpt-oss-20b` desde 25/07. O nome ficou pra trás na migração e
    ninguém percebeu, porque nada amarrava os dois. A conta veio AO VIVO, no
    diagnóstico do TOOL-FANTASMA-1: o log dizia `provider=groq-8b`, o Beltrami
    esperando, e foi preciso grepar tasks.py → router.py → config.py pra saber
    qual modelo tinha falhado.
    O pedido dele foi "refletindo sempre o modelo real, ATÉ QUANDO TROCARMOS" —
    ou seja, não adianta rebatizar de "groq-20b" hoje; tem que ser impossível
    mentir amanhã. Este arquivo é o mecanismo: disciplina não escala, teste sim.
Cobrança #2 (17/08/26): o mecanismo funcionou. O Groq desligou o
    `llama-3.3-70b-versatile` e, ao apontar `GROQ_MODEL` pro
    `openai/gpt-oss-120b`, o slot `groq-70b` passaria a mentir igualzinho ao
    `groq-8b` de julho. Este teste ficou VERMELHO na hora, antes de qualquer
    playtest, e o slot virou `groq-principal` — nome de papel. É a diferença
    entre descobrir agora e descobrir com o Beltrami esperando na frente do
    microfone.
Dependências: nenhuma — lê as constantes e o settings, sem tocar rede.
Armadilha: se um slot novo citar tamanho de modelo no nome ("groq-405b"), este
    teste passa a exigir que o settings realmente aponte pra um 405b. É de
    propósito. A saída barata é nomear pelo PAPEL (como `groq-leve`), não pelo
    tamanho.
"""

import re

from config import settings
from engine.llm.tasks import (
    ALIASES_SLOT,
    CASCATA_DEFAULT,
    PROV_GROQ_120B,
    PROV_GROQ_LEVE,
    PROV_GROQ_PRINCIPAL,
    modelo_do_slot,
)

# "70b", "120b", "8b" — o que um nome de slot promete sobre o tamanho do modelo.
_RE_TAMANHO = re.compile(r"\d+\s*b\b")

_SLOTS_GROQ = (PROV_GROQ_PRINCIPAL, PROV_GROQ_120B, PROV_GROQ_LEVE)


def test_nome_de_slot_que_promete_tamanho_cumpre_a_promessa():
    """A trava que o Beltrami pediu.

    Se o nome do slot cita um tamanho, o modelo configurado tem que ter esse
    mesmo tamanho. Trocar o modelo sem acertar o nome quebra AQUI, e não num
    playtest seis semanas depois.
    """
    for slot in _SLOTS_GROQ:
        modelo = modelo_do_slot(slot)
        assert modelo, f"{slot} não resolve pra modelo nenhum"
        prometido = _RE_TAMANHO.search(slot.replace("-", ""))
        if not prometido:
            continue  # nome de papel — nada a cumprir, e é o caminho recomendado
        tamanho = prometido.group(0).replace(" ", "")
        assert tamanho in modelo.replace("-", "").replace(".", ""), (
            f"o slot {slot!r} promete um {tamanho} mas roda {modelo!r} — "
            "renomeie pelo PAPEL (ex: groq-leve) ou acerte o modelo"
        )


def test_o_slot_leve_nao_promete_tamanho_nenhum():
    """Foi ele que mentiu por 7 dias. Nome de papel não envelhece na troca."""
    assert not _RE_TAMANHO.search(PROV_GROQ_LEVE.replace("-", ""))


def test_modelo_do_slot_vem_do_settings_nao_de_literal():
    """A fonte da verdade é a configuração — senão volta a divergir."""
    assert modelo_do_slot(PROV_GROQ_PRINCIPAL) == settings.GROQ_MODEL
    assert modelo_do_slot(PROV_GROQ_120B) == settings.GROQ_MODEL_MEIO
    assert modelo_do_slot(PROV_GROQ_LEVE) == settings.GROQ_MODEL_FALLBACK


def test_alias_legado_do_localstorage_continua_resolvendo():
    """Toggle salvo antes de 01/08 guarda "groq-8b". Quebrar isso deixa a
    preferência gravada apontando pra provider inexistente."""
    assert ALIASES_SLOT["groq-8b"] == PROV_GROQ_LEVE
    assert modelo_do_slot("groq-8b") == settings.GROQ_MODEL_FALLBACK


def test_alias_do_slot_renomeado_em_17_08_continua_resolvendo():
    """Mesma dívida, segunda parcela: quem escolheu "Groq grande" nas Opções
    antes de 17/08 tem "groq-70b" gravado no localStorage. O slot virou
    `groq-principal`; sem o alias, a preferência salva aponta pra um provider
    que não existe mais e o override é descartado em silêncio."""
    assert ALIASES_SLOT["groq-70b"] == PROV_GROQ_PRINCIPAL
    assert modelo_do_slot("groq-70b") == settings.GROQ_MODEL

    from engine.llm.groq_client import _BACKEND_PARA_PROVIDER

    assert _BACKEND_PARA_PROVIDER["groq-70b"] == PROV_GROQ_PRINCIPAL
    assert _BACKEND_PARA_PROVIDER["groq-principal"] == PROV_GROQ_PRINCIPAL


def test_toggle_do_frontend_aceita_o_nome_novo_e_o_antigo():
    from engine.llm.groq_client import _BACKEND_PARA_PROVIDER

    assert _BACKEND_PARA_PROVIDER["groq-leve"] == PROV_GROQ_LEVE
    assert _BACKEND_PARA_PROVIDER["groq-8b"] == PROV_GROQ_LEVE


def test_todo_slot_das_cascatas_existe_no_router():
    """Cascata citando nome errado é pulada em SILÊNCIO (armadilha no docstring
    de tasks.py). Depois de renomear um slot, isto é a rede."""
    from engine.llm.router import LLMRouter

    registrados = set(LLMRouter()._providers)
    citados = {p for casc in CASCATA_DEFAULT.values() for p in casc}
    assert citados <= registrados, f"slots citados e não registrados: {citados - registrados}"


def test_log_do_router_carrega_o_modelo_junto_do_provider():
    """O que custou o tempo de diagnóstico: `provider=groq-8b` sem o modelo.

    Amarra os dois lados por inspeção do fonte — barato e suficiente pra impedir
    que alguém tire o campo sem perceber.
    """
    from pathlib import Path

    fonte = (Path(__file__).resolve().parent.parent / "engine/llm/router.py").read_text(
        encoding="utf-8"
    )
    for evento in ("llm_provider_tentando_stream", "llm_provider_stream_ok"):
        i = fonte.index(evento)
        trecho = fonte[i : i + 200]
        assert "modelo=" in trecho, f"{evento} voltou a logar sem o modelo"
