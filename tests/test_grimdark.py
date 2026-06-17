"""
Testes da fundação grimdark — Camadas 1-3 do roadmap anti-amarelada.

Cobre: e_amarelada, e_cena_sombria, OllamaGrimProvider.disponivel,
TaskType.NARRATIVE_GRIM, cascata, escolher_task_type_narrativo,
injeção do fragmento grimdark.md, schemas e working_memory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ── e_amarelada ────────────────────────────────────────────────────────────────

def test_e_amarelada_fade_to_black():
    from engine.llm.amarelada import e_amarelada
    assert e_amarelada("Prefiro não detalhar o massacre.") is True


def test_e_amarelada_moralizacao():
    from engine.llm.amarelada import e_amarelada
    assert e_amarelada("É importante lembrar que violência tem consequências.") is True


def test_e_amarelada_texto_normal():
    from engine.llm.amarelada import e_amarelada
    assert e_amarelada("O goblin avança com a lança.") is False


def test_e_amarelada_case_insensitive():
    from engine.llm.amarelada import e_amarelada
    assert e_amarelada("PREFIRO NÃO DETALHAR") is True


def test_e_amarelada_deixo_imaginacao():
    from engine.llm.amarelada import e_amarelada
    assert e_amarelada("Deixo à imaginação os detalhes.") is True


def test_e_amarelada_aviso_conteudo():
    from engine.llm.amarelada import e_amarelada
    assert e_amarelada("Aviso de conteúdo: cena de violência.") is True


# ── e_cena_sombria ─────────────────────────────────────────────────────────────

def test_e_cena_sombria_tortura():
    from engine.llm.amarelada import e_cena_sombria
    assert e_cena_sombria("Quero torturar o prisioneiro.") is True


def test_e_cena_sombria_chacina():
    from engine.llm.amarelada import e_cena_sombria
    assert e_cena_sombria("Organizamos uma chacina na aldeia.") is True


def test_e_cena_sombria_combate_normal():
    from engine.llm.amarelada import e_cena_sombria
    assert e_cena_sombria("Ataco o goblin com minha espada.") is False


def test_e_cena_sombria_massacre_com_alvo():
    from engine.llm.amarelada import e_cena_sombria
    assert e_cena_sombria("Vamos cometer um massacre de aldeões.") is True


# ── OllamaGrimProvider ─────────────────────────────────────────────────────────

def test_ollama_grim_indisponivel_por_padrao():
    from engine.llm.providers.ollama_grim import OllamaGrimProvider
    # GRIMDARK_ATIVO=False (default)
    p = OllamaGrimProvider()
    assert p.disponivel is False


def test_ollama_grim_disponivel_com_flag(monkeypatch):
    monkeypatch.setattr("config.settings.GRIMDARK_ATIVO", True)
    monkeypatch.setattr("config.settings.OLLAMA_MODEL_GRIM", "dolphin-mistral")
    from engine.llm.providers.ollama_grim import OllamaGrimProvider
    p = OllamaGrimProvider()
    assert p.disponivel is True


def test_ollama_grim_nome():
    from engine.llm.providers.ollama_grim import OllamaGrimProvider
    p = OllamaGrimProvider()
    assert p.nome == "ollama-grim"


def test_ollama_grim_keep_alive():
    from engine.llm.providers.ollama_grim import OllamaGrimProvider
    p = OllamaGrimProvider()
    assert p._keep_alive == "5m"


# ── TaskType.NARRATIVE_GRIM ────────────────────────────────────────────────────

def test_narrative_grim_existe():
    from engine.llm.tasks import TaskType
    assert TaskType.NARRATIVE_GRIM == "narrative_grim"


def test_cascata_grim_exclui_8b():
    from engine.llm.tasks import CASCATA_DEFAULT, PROV_GROQ_8B, TaskType
    cascata = CASCATA_DEFAULT[TaskType.NARRATIVE_GRIM]
    assert PROV_GROQ_8B not in cascata


def test_cascata_grim_tem_ollama_grim():
    from engine.llm.tasks import CASCATA_DEFAULT, PROV_OLLAMA_GRIM, TaskType
    cascata = CASCATA_DEFAULT[TaskType.NARRATIVE_GRIM]
    assert PROV_OLLAMA_GRIM in cascata


def test_cascata_grim_ordem():
    from engine.llm.tasks import CASCATA_DEFAULT, PROV_GEMINI, PROV_GROQ_70B, PROV_OLLAMA_GRIM, TaskType
    cascata = CASCATA_DEFAULT[TaskType.NARRATIVE_GRIM]
    assert cascata[0] == PROV_GROQ_70B
    assert cascata[1] == PROV_GEMINI
    assert cascata[2] == PROV_OLLAMA_GRIM


# ── escolher_task_type_narrativo ────────────────────────────────────────────────

def test_escolher_grim_com_perfil_e_flag():
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo
    task = escolher_task_type_narrativo(
        em_combate=False,
        pacing_nivel=3.0,
        dm_profile="sombrio",
        grimdark_ativo=True,
    )
    assert task == TaskType.NARRATIVE_GRIM


def test_escolher_grim_sem_flag_retorna_normal():
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo
    task = escolher_task_type_narrativo(
        em_combate=False,
        pacing_nivel=3.0,
        dm_profile="sombrio",
        grimdark_ativo=False,
    )
    assert task != TaskType.NARRATIVE_GRIM


def test_escolher_grim_tem_prioridade_sobre_climax():
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo
    task = escolher_task_type_narrativo(
        em_combate=True,
        pacing_nivel=9.0,  # normalmente seria CLIMAX
        cliffhanger_pendente=True,
        dm_profile="sombrio",
        grimdark_ativo=True,
    )
    assert task == TaskType.NARRATIVE_GRIM


# ── Fragmento grimdark.md ──────────────────────────────────────────────────────

def test_grimdark_md_existe():
    frag = Path("engine/llm/prompts/fragments/grimdark.md")
    assert frag.exists(), "grimdark.md não encontrado"


def test_grimdark_md_tamanho_minimo():
    frag = Path("engine/llm/prompts/fragments/grimdark.md")
    conteudo = frag.read_text(encoding="utf-8")
    assert len(conteudo) >= 100, "grimdark.md muito curto"


def test_grimdark_md_tem_proibicao_fade():
    frag = Path("engine/llm/prompts/fragments/grimdark.md")
    conteudo = frag.read_text(encoding="utf-8").lower()
    assert "prefiro não detalhar" in conteudo or "fade" in conteudo or "deixo à imaginação" in conteudo


def test_grimdark_md_tem_autorizacao_violencia():
    frag = Path("engine/llm/prompts/fragments/grimdark.md")
    conteudo = frag.read_text(encoding="utf-8").lower()
    # Deve mencionar que violência/horror é permitida como ficção
    assert any(kw in conteudo for kw in ("violência", "fantasia", "narrar", "autor"))


# ── Schemas — dm_profile aceita sombrio ────────────────────────────────────────

def test_sessao_config_aceita_sombrio():
    from api.models.schemas import SessaoConfig
    cfg = SessaoConfig(
        player_name="Teste",
        player_class="Guerreiro",
        player_race="Humano",
        player_background="Soldado",
        dm_profile="sombrio",
    )
    assert cfg.dm_profile == "sombrio"


def test_sessao_config_rejeita_perfil_invalido():
    from pydantic import ValidationError

    from api.models.schemas import SessaoConfig
    with pytest.raises(ValidationError):
        SessaoConfig(
            player_name="Teste",
            player_class="Guerreiro",
            player_race="Humano",
            player_background="Soldado",
            dm_profile="malvado_demo",
        )


# ── WorkingMemory — dm_profile="sombrio" aceito ────────────────────────────────

def test_working_memory_aceita_sombrio():
    from engine.memory.working_memory import WorkingMemory
    wm = WorkingMemory.nova_sessao(
        session_id="test-123",
        player_name="Teste",
        player_class="Guerreiro",
        player_race="Humano",
        player_background="Soldado",
        location_id="taverna",
        location_nome="Taverna",
        dm_profile="sombrio",
    )
    assert wm.dm_profile == "sombrio"


def test_working_memory_perfil_invalido_cai_para_default():
    from engine.memory.working_memory import WorkingMemory
    wm = WorkingMemory.nova_sessao(
        session_id="test-456",
        player_name="Teste",
        player_class="Guerreiro",
        player_race="Humano",
        player_background="Soldado",
        location_id="taverna",
        location_nome="Taverna",
        dm_profile="perfil_ficticio",
    )
    assert wm.dm_profile == "equilibrado"


# ── GroqClient expõe router ────────────────────────────────────────────────────

def test_groq_client_expoe_router():
    from engine.llm.groq_client import GroqClient
    from engine.llm.router import LLMRouter
    client = GroqClient()
    assert isinstance(client.router, LLMRouter)


def test_set_cena_sombria_propaga_para_providers():
    from engine.llm.groq_client import GroqClient
    client = GroqClient()
    # Não deve lançar exceção
    client.router.set_cena_sombria(True)
    client.router.set_cena_sombria(False)
