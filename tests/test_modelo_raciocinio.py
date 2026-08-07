"""
Modelos de RACIOCÍNIO (openai/gpt-oss) não podem devolver narração vazia.

Por que existe (auditoria 24/07): `llama-3.1-8b-instant` — o fallback da cascata
    — DESLIGA em 16/08/2026. O substituto oficial `openai/gpt-oss-20b` gasta
    tokens num campo `reasoning` ANTES do `content`: medido, com max_tokens=120
    e esforço default, 447 chars foram pro raciocínio e o content voltou VAZIO
    (finish=length). O projeto tem chamadas em 120 — inclusive o gerador de
    dossiê de NPC, que sustenta a Camada 1-B. Migrar sem tratar isso quebraria a
    narração de forma intermitente e silenciosa (só quando o 70B falhasse).
Dependências: nenhuma — inspeciona os kwargs do provider, sem chamar a API.
Armadilha: é a MESMA classe do gemini-2.5-flash "full" já documentada no
    CLAUDE.md. Todo modelo novo de raciocínio precisa entrar em _RACIOCINIO_LOW.
"""

from types import SimpleNamespace

from config import settings
from engine.llm.providers.groq import GroqProvider


def test_gpt_oss_recebe_reasoning_effort_low():
    p = GroqProvider(nome="teste", modelo="openai/gpt-oss-20b")
    assert p._extras() == {"reasoning_effort": "low"}


def test_gpt_oss_120b_tambem():
    p = GroqProvider(nome="teste", modelo="openai/gpt-oss-120b")
    assert p._extras().get("reasoning_effort") == "low"


def test_modelo_comum_nao_recebe_kwarg_extra():
    """llama/qwen não aceitam reasoning_effort — mandar quebraria a chamada."""
    for modelo in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        assert GroqProvider(nome="teste", modelo=modelo)._extras() == {}


def test_fallback_configurado_nao_e_o_modelo_que_desliga():
    """llama-3.1-8b-instant desliga em 16/08/2026 — não pode ser o fallback."""
    assert settings.GROQ_MODEL_FALLBACK != "llama-3.1-8b-instant"


def test_fallback_de_raciocinio_tem_tratamento():
    """Se o fallback for um modelo de raciocínio, o provider PRECISA tratá-lo —
    senão o content volta vazio nas chamadas de max_tokens baixo."""
    p = GroqProvider(nome="fallback", modelo=settings.GROQ_MODEL_FALLBACK)
    if "gpt-oss" in settings.GROQ_MODEL_FALLBACK:
        assert p._extras().get("reasoning_effort") == "low"


# ── FREE-TIER-TPD (auditoria 24/07) ──────────────────────────────────────────
#
# No free tier do Groq o limite que morde não é o TPM — é o TPD. Medido:
#   llama-3.3-70b   100K TPD → ~19-27 turnos/dia (3,6k tok em exploração,
#                              5,2k em combate/social) = MENOS que uma sessão
#   gpt-oss-120b    200K TPD → ~38-55 turnos/dia (o dobro)
# Ou seja: o primário estoura no MEIO de toda partida (aconteceu ao vivo durante
# a própria auditoria: 429 em llama-3.3-70b). Sem um degrau grande no meio, a
# queda ia direto pro modelo pequeno e a segunda metade da sessão perdia
# qualidade sem ninguém perceber.

def test_cascata_narrativa_tem_amortecedor_entre_70b_e_8b():
    from engine.llm.tasks import CASCATA_DEFAULT, PROV_GROQ_8B, PROV_GROQ_70B, PROV_GROQ_120B, TaskType

    casc = CASCATA_DEFAULT[TaskType.NARRATIVE]
    assert casc.index(PROV_GROQ_70B) < casc.index(PROV_GROQ_120B) < casc.index(PROV_GROQ_8B), (
        f"o degrau de TPD tem que ficar ENTRE o 70B e o 8B: {casc}"
    )


def test_climax_cai_no_degrau_grande_antes_do_gemini():
    from engine.llm.tasks import CASCATA_DEFAULT, PROV_GEMINI, PROV_GROQ_120B, TaskType

    casc = CASCATA_DEFAULT[TaskType.NARRATIVE_CLIMAX]
    assert casc.index(PROV_GROQ_120B) < casc.index(PROV_GEMINI)


def test_light_nao_paga_o_modelo_grande():
    """LIGHT existe pra POUPAR cota — não pode escalar pro 120B."""
    from engine.llm.tasks import CASCATA_DEFAULT, PROV_GROQ_120B, TaskType

    assert PROV_GROQ_120B not in CASCATA_DEFAULT[TaskType.NARRATIVE_LIGHT]


def test_degrau_do_meio_esta_registrado_no_router():
    from engine.llm.router import LLMRouter
    from engine.llm.tasks import PROV_GROQ_120B

    r = LLMRouter()
    assert PROV_GROQ_120B in r._providers
    assert "gpt-oss-120b" in r._providers[PROV_GROQ_120B]._modelo


# ── LIGHT-MORTO-1 (auditoria 22/07, priorizado 25/07 pelo achado de TPD) ─────
#
# `NARRATIVE_LIGHT` existe pra POUPAR a cota do 70B em turno de filler. Ela
# nunca disparava depois do 1º NPC entrar em cena, porque o sinal era
# `bool(npcs_presentes)` — qualquer NPC, inclusive os que o Neo4j infere no
# local e com quem o jogador nunca falou. Numa vila povoada, TODO turno virava
# 70B. Com 100K TPD (19-27 turnos/dia), isso é queimar o recurso mais escasso
# do projeto em travessia.

def _wm_com_npcs(presentes, apresentados=()):
    from engine.memory.working_memory import WorkingMemory
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmünd", "s")
    wm.npcs_presentes = list(presentes)
    wm.scene.npcs_apresentados = set(apresentados)
    return wm


def test_npc_so_de_fundo_nao_e_cena_social():
    """Atravessar uma vila povoada não é diálogo — libera o LIGHT."""
    from api.websocket import _cena_social

    wm = _wm_com_npcs(["taverneiro", "ferreiro", "guarda"])  # ninguém apresentado
    assert _cena_social(wm) is False


def test_npc_apresentado_e_cena_social():
    """A regra 2 continua valendo onde ela nasceu: diálogo vai pro 70B."""
    from api.websocket import _cena_social

    wm = _wm_com_npcs(["taverneiro", "ferreiro"], apresentados=["taverneiro"])
    assert _cena_social(wm) is True


def test_cena_vazia_nao_e_social():
    from api.websocket import _cena_social

    assert _cena_social(_wm_com_npcs([])) is False


def test_apresentado_que_saiu_da_cena_nao_conta():
    """npcs_apresentados é cumulativo da SESSÃO — quem ficou pra trás não
    transforma a estrada num salão de baile."""
    from api.websocket import _cena_social

    wm = _wm_com_npcs([], apresentados=["taverneiro"])
    assert _cena_social(wm) is False


def test_filler_com_npc_de_fundo_escolhe_light():
    """O efeito final: o turno de travessia volta a poupar o 70B."""
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo

    task = escolher_task_type_narrativo(
        em_combate=False, pacing_nivel=1.0, turnos_sem_tensao=3,
        npc_na_cena=False,           # agora que o sinal é preciso
    )
    assert task is TaskType.NARRATIVE_LIGHT


# ── TOOL-FANTASMA-1 (playtest 01/08) ─────────────────────────────────────────
#
# Turno 1 da sessão morreu assim:
#
#   llm_provider_tentando_stream provider=groq-8b task=narrative_light
#   HTTP Request: POST .../chat/completions "HTTP/1.1 200 OK"
#   error ws_groq_falhou erro='Tool choice is none, but model called a tool'
#
# O `openai/gpt-oss-20b` chamou uma ferramenta que ninguém ofereceu. O 400 não é
# quota nem rede, então caía no `raise` do except APIError, subia inteiro e
# MATAVA o turno — Gemini e 70B, que rodam o mesmo prompt sem problema, nunca
# eram tentados. É falha DO MODELO: fallback-able por definição.
#
# Não reproduzido em 12 chamadas com o mesmo prompt (6 no 20b, 6 no 120b): é
# intermitente. Frequência baixa não muda o desenho — turno morto é turno morto.

import httpx
import pytest
from groq import APIError

from engine.llm.providers.base import LLMRetriable
from engine.llm.providers.groq import _e_falha_do_modelo

_MSG_REAL = "Tool choice is none, but model called a tool"


def _api_error(msg: str) -> APIError:
    return APIError(msg, httpx.Request("POST", "https://api.groq.com"), body=None)


def test_detecta_a_mensagem_exata_do_playtest():
    assert _e_falha_do_modelo(_api_error(_MSG_REAL)) is True


def test_nao_captura_400_legitimo():
    """Classificação larga demais mascararia bug NOSSO como falha do provider."""
    for msg in (
        "Invalid value for 'messages': expected an array",
        "model `foo` does not exist",
        "maximum context length exceeded",
    ):
        assert _e_falha_do_modelo(_api_error(msg)) is False


class _StreamQueQuebra:
    """Stream que emite N tokens e então levanta APIError — como o Groq faz."""

    def __init__(self, tokens: list[str], erro: APIError):
        self._tokens, self._erro = tokens, erro

    def __aiter__(self):
        async def _gen():
            for t in self._tokens:
                yield SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=t))]
                )
            raise self._erro
        return _gen()


def _provider_que_quebra(tokens: list[str]) -> GroqProvider:
    p = GroqProvider(nome="teste", modelo="openai/gpt-oss-20b")

    class _Completions:
        async def create(self, **_):
            return _StreamQueQuebra(tokens, _api_error(_MSG_REAL))

    p._get_client = lambda: SimpleNamespace(  # type: ignore[method-assign]
        chat=SimpleNamespace(completions=_Completions())
    )
    return p


@pytest.mark.asyncio
async def test_stream_vira_retriable_antes_de_emitir():
    """Pré-emissão: tem que virar LLMRetriable pro router cascatear."""
    p = _provider_que_quebra([])  # quebra sem emitir nada, como no playtest
    with pytest.raises(LLMRetriable) as exc:
        async for _ in p.completar_stream([{"role": "user", "content": "oi"}], 0.7, 100):
            pass
    assert exc.value.categoria == "modelo"


@pytest.mark.asyncio
async def test_stream_pos_emissao_propaga_sem_cascatear():
    """Depois do 1º token, trocar de modelo quebraria a frase no meio."""
    tokens = ["A taverna está cheia. " * 10]  # passa do _BUFFER_RECUSA
    p = _provider_que_quebra(tokens)
    with pytest.raises(APIError):
        async for _ in p.completar_stream([{"role": "user", "content": "oi"}], 0.7, 100):
            pass


def test_categoria_modelo_nao_e_amarelada_nem_cooldown():
    """Não é filtro de conteúdo (não escala grimdark) nem quota (não penaliza).

    Surto estocástico não pode tirar o provider de circulação por 75s — isso
    empurraria o turno seguinte pro 70B e queimaria o recurso mais escasso.
    """
    from engine.llm.router import _CATEGORIAS_AMARELADA

    assert "modelo" not in _CATEGORIAS_AMARELADA
