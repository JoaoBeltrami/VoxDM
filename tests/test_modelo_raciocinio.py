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
