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

def test_ollama_grim_indisponivel_sem_flag(monkeypatch):
    # Hermético: não depende do .env do dev (que pode ter GRIMDARK_ATIVO=true).
    # Com o kill-switch desligado, o provider grim nunca está disponível.
    monkeypatch.setattr("config.settings.GRIMDARK_ATIVO", False)
    from engine.llm.providers.ollama_grim import OllamaGrimProvider
    p = OllamaGrimProvider()
    assert p.disponivel is False


def test_ollama_grim_indisponivel_sem_modelo(monkeypatch):
    # Flag ligada mas sem modelo configurado → indisponível (guard do disponivel).
    monkeypatch.setattr("config.settings.GRIMDARK_ATIVO", True)
    monkeypatch.setattr("config.settings.OLLAMA_MODEL_GRIM", "")
    from engine.llm.providers.ollama_grim import OllamaGrimProvider
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


# ── GRIM-ROTA-1: cena sombria (keywords/reativa) roteia a cascata grim ─────────


def test_escolher_grim_por_cena_sombria_sem_perfil():
    """Gatilho (a)+(c) do roadmap: keywords de atrocidade OU escalação reativa
    roteiam NARRATIVE_GRIM mesmo com dm_profile normal — antes, só o perfil
    'sombrio' chegava na cascata com a garantia do ollama-grim."""
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo
    task = escolher_task_type_narrativo(
        em_combate=False,
        pacing_nivel=3.0,
        dm_profile="equilibrado",
        grimdark_ativo=True,
        cena_sombria=True,
    )
    assert task == TaskType.NARRATIVE_GRIM


def test_escolher_cena_sombria_sem_killswitch_nao_roteia_grim():
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo
    task = escolher_task_type_narrativo(
        em_combate=False,
        pacing_nivel=3.0,
        dm_profile="equilibrado",
        grimdark_ativo=False,
        cena_sombria=True,
    )
    assert task != TaskType.NARRATIVE_GRIM


def test_escolher_sem_cena_sombria_preserva_comportamento():
    """Default cena_sombria=False não muda nenhuma rota existente."""
    from engine.llm.tasks import TaskType, escolher_task_type_narrativo
    task = escolher_task_type_narrativo(
        em_combate=False,
        pacing_nivel=3.0,
        npc_na_cena=True,
        dm_profile="equilibrado",
        grimdark_ativo=True,
    )
    assert task == TaskType.NARRATIVE


# ── GRIM-REATIVA-1: escalação reativa gruda a cena ─────────────────────────────


def test_scene_state_tem_flag_reativa_default_false():
    from engine.state.scene import SceneState
    assert SceneState().cena_sombria_reativa is False


def test_mudanca_de_cena_limpa_flag_reativa():
    """Trocar de local ([CENA]) encerra a cena sombria — o massacre ficou
    pra trás; a nova cena começa limpa."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-grim")
    wm.scene.cena_sombria_reativa = True
    aplicar_pos_turno(wm, "Sigo para o porto.", "Vocês chegam. [CENA: porto|Porto|Noite]")
    assert wm.scene.cena_sombria_reativa is False


def test_mesmo_local_preserva_flag_reativa():
    """Turno sem troca de local mantém a escalação grudada."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-grim")
    wm.scene.cena_sombria_reativa = True
    aplicar_pos_turno(wm, "Continuo andando.", "A rua segue vazia e fria.")
    assert wm.scene.cena_sombria_reativa is True


@pytest.mark.asyncio
async def test_router_seta_ultima_chamada_amarelou_em_cena_sombria():
    """Provider amarela em cena sombria → flag do router liga (o websocket lê
    e gruda a cena). Outro provider completa e a flag PERSISTE (o sinal é
    'houve amarelada', não 'a chamada falhou')."""
    from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
    from engine.llm.router import LLMRouter
    from engine.llm.tasks import TaskType

    class _Amarela(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            raise LLMRetriable("filtrou", categoria="amarelada")
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            raise LLMRetriable("filtrou", categoria="amarelada")
            yield  # pragma: no cover

    class _Integro(BaseLLMProvider):
        nome = "gemini-flash"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            return "O sangue seca nas pedras do salão."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield "O sangue seca nas pedras."

    router = LLMRouter.__new__(LLMRouter)
    router._providers = {"groq-70b": _Amarela(), "gemini-flash": _Integro()}
    router._cena_sombria = True
    router._override_primario = None
    router.ultimo_provider_stream = None
    router.ultima_chamada_amarelou = False

    texto = await router.completar([{"role": "user", "content": "x"}], task=TaskType.NARRATIVE)
    assert "sangue" in texto
    assert router.ultima_chamada_amarelou is True


@pytest.mark.asyncio
async def test_router_flag_reseta_em_chamada_limpa():
    from engine.llm.providers.base import BaseLLMProvider
    from engine.llm.router import LLMRouter
    from engine.llm.tasks import TaskType

    class _Integro(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            return "A taverna está quieta."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield "A taverna está quieta."

    router = LLMRouter.__new__(LLMRouter)
    router._providers = {"groq-70b": _Integro()}
    router._cena_sombria = True
    router._override_primario = None
    router.ultimo_provider_stream = None
    router.ultima_chamada_amarelou = True  # sobra da chamada anterior

    await router.completar([{"role": "user", "content": "x"}], task=TaskType.NARRATIVE)
    assert router.ultima_chamada_amarelou is False


@pytest.mark.asyncio
async def test_router_fora_de_cena_sombria_nao_gruda():
    """Recusa fora de cena sombria (prompt malformado, etc.) NÃO liga a flag —
    escalação grim indevida degradaria qualidade de conversa normal."""
    from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
    from engine.llm.router import LLMRouter
    from engine.llm.tasks import TaskType

    class _Recusa(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            raise LLMRetriable("recusou", categoria="refusal")
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            raise LLMRetriable("recusou", categoria="refusal")
            yield  # pragma: no cover

    class _Integro(BaseLLMProvider):
        nome = "gemini-flash"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            return "Tudo bem."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield "Tudo bem."

    router = LLMRouter.__new__(LLMRouter)
    router._providers = {"groq-70b": _Recusa(), "gemini-flash": _Integro()}
    router._cena_sombria = False
    router._override_primario = None
    router.ultimo_provider_stream = None
    router.ultima_chamada_amarelou = False

    await router.completar([{"role": "user", "content": "x"}], task=TaskType.NARRATIVE)
    assert router.ultima_chamada_amarelou is False


def test_fragmento_injetado_com_flag_reativa(monkeypatch):
    """O fragmento grimdark acompanha a escalação reativa — cena grudada
    injeta o contrato mesmo sem keyword no turno atual."""
    monkeypatch.setattr("config.settings.GRIMDARK_ATIVO", True)
    from engine.llm.prompt_builder import montar_mensagens
    from engine.llm.types import ContextoMontado
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-grim")
    wm.scene.cena_sombria_reativa = True
    ctx = ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[],
        transcricao_atual="continuo olhando ao redor",  # sem keyword
    )
    system = montar_mensagens(ctx)[0]["content"]
    assert "ficção sombria" in system.lower() or "grimdark" in system.lower() or "eventos de jogo" in system.lower()


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


# ── GRIM-REFRAME-1 (Camada 5): reframe literário antes de escalar ─────────────


def _router_com(providers: dict, cena_sombria: bool = True):
    """Router mínimo com providers mockados (sem __init__ real — sem chaves)."""
    from engine.llm.router import LLMRouter

    router = LLMRouter.__new__(LLMRouter)
    router._providers = providers
    router._cena_sombria = cena_sombria
    router._override_primario = None
    router.ultimo_provider_stream = None
    router.ultima_chamada_amarelou = False
    return router


def test_aplicar_reframe_anexa_system_sem_mutar():
    from engine.llm.amarelada import REFRAME_LITERARIO, aplicar_reframe

    original = [{"role": "system", "content": "mestre"}, {"role": "user", "content": "x"}]
    novo = aplicar_reframe(original)
    assert len(original) == 2  # intocada
    assert len(novo) == 3
    assert novo[-1] == {"role": "system", "content": REFRAME_LITERARIO}


@pytest.mark.asyncio
async def test_reframe_destrava_o_mesmo_provider():
    """Provider cloud amarela na 1ª tentativa; com o reframe anexado, narra
    íntegro — o MESMO provider vence, sem descer a cascata."""
    from engine.llm.providers.base import BaseLLMProvider
    from engine.llm.tasks import TaskType

    class _AmarelaSemReframe(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        def __init__(self):
            self.chamadas: list[list[dict]] = []
        async def completar(self, mensagens, temperatura, max_tokens):
            self.chamadas.append(mensagens)
            if any("REENQUADRAMENTO" in m.get("content", "") for m in mensagens):
                return "A crônica registra: o salão foi tomado pelo aço."
            return "Prefiro não detalhar o que aconteceu."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield ""

    class _NuncaChamado(BaseLLMProvider):
        nome = "gemini-flash"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            raise AssertionError("cascata não devia ter descido — reframe destravou")
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield ""

    p = _AmarelaSemReframe()
    router = _router_com({"groq-70b": p, "gemini-flash": _NuncaChamado()})
    texto = await router.completar([{"role": "user", "content": "x"}], task=TaskType.NARRATIVE)
    assert "crônica" in texto
    assert len(p.chamadas) == 2  # original + reframed
    # A tentativa reframed recebeu a instrução extra; a original não.
    assert not any("REENQUADRAMENTO" in m.get("content", "") for m in p.chamadas[0])
    assert any("REENQUADRAMENTO" in m.get("content", "") for m in p.chamadas[1])


@pytest.mark.asyncio
async def test_reframe_so_uma_vez_por_chamada():
    """Provider amarela SEMPRE (com e sem reframe) → 2 tentativas no primário,
    depois a cascata desce normalmente (sem loop de reframes)."""
    from engine.llm.providers.base import BaseLLMProvider
    from engine.llm.tasks import TaskType

    class _AmarelaSempre(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        def __init__(self):
            self.n = 0
        async def completar(self, mensagens, temperatura, max_tokens):
            self.n += 1
            return "Prefiro não detalhar."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield ""

    class _Grim(BaseLLMProvider):
        nome = "ollama-grim"
        disponivel = True
        async def completar(self, mensagens, temperatura, max_tokens):
            return "O aço canta e o sangue corre."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield ""

    p = _AmarelaSempre()
    router = _router_com({"groq-70b": p, "ollama-grim": _Grim()})
    # NARRATIVE_GRIM: a única cascata que inclui o ollama-grim como garantia.
    texto = await router.completar(
        [{"role": "user", "content": "x"}], task=TaskType.NARRATIVE_GRIM
    )
    assert "aço" in texto
    assert p.n == 2  # original + 1 reframe, nunca 3
    assert router.ultima_chamada_amarelou is True


@pytest.mark.asyncio
async def test_reframe_nao_dispara_fora_de_cena_sombria():
    """Fora de cena sombria não há detecção de amarelada — a resposta com
    frase de fade passa direto (pode ser fala legítima de NPC)."""
    from engine.llm.providers.base import BaseLLMProvider
    from engine.llm.tasks import TaskType

    class _P(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        def __init__(self):
            self.n = 0
        async def completar(self, mensagens, temperatura, max_tokens):
            self.n += 1
            return "Prefiro não detalhar, diz o velho, desviando o olhar."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield ""

    p = _P()
    router = _router_com({"groq-70b": p}, cena_sombria=False)
    texto = await router.completar([{"role": "user", "content": "x"}], task=TaskType.NARRATIVE)
    assert "velho" in texto
    assert p.n == 1  # sem retry


@pytest.mark.asyncio
async def test_reframe_nao_reaplica_em_provider_ollama():
    """ollama-grim amarelar é sinal de modelo errado, não de filtro corporativo
    — reframe não se aplica a providers locais."""
    from engine.llm.providers.base import BaseLLMProvider
    from engine.llm.tasks import TaskType

    class _GrimAmarela(BaseLLMProvider):
        nome = "ollama-grim"
        disponivel = True
        def __init__(self):
            self.n = 0
        async def completar(self, mensagens, temperatura, max_tokens):
            self.n += 1
            return "Prefiro não detalhar."
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            yield ""

    p = _GrimAmarela()
    router = _router_com({"ollama-grim": p})
    with pytest.raises(RuntimeError):
        await router.completar(
            [{"role": "user", "content": "x"}], task=TaskType.NARRATIVE_GRIM
        )
    assert p.n == 1  # sem retry de reframe no local


@pytest.mark.asyncio
async def test_reframe_no_stream_pre_emissao():
    """Recusa pré-emissão no stream → retry reframed do mesmo provider emite."""
    from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
    from engine.llm.tasks import TaskType

    class _RecusaSemReframe(BaseLLMProvider):
        nome = "groq-70b"
        disponivel = True
        def __init__(self):
            self.chamadas: list[list[dict]] = []
        async def completar(self, mensagens, temperatura, max_tokens):
            return ""
        async def completar_stream(self, mensagens, temperatura, max_tokens):
            self.chamadas.append(mensagens)
            if not any("REENQUADRAMENTO" in m.get("content", "") for m in mensagens):
                raise LLMRetriable("recusou", categoria="refusal")
            yield "A crônica registra o massacre em detalhe."

    p = _RecusaSemReframe()
    router = _router_com({"groq-70b": p})
    tokens = [
        t async for t in router.completar_stream(
            [{"role": "user", "content": "x"}], task=TaskType.NARRATIVE
        )
    ]
    assert "crônica" in "".join(tokens)
    assert len(p.chamadas) == 2
    assert router.ultima_chamada_amarelou is True  # a recusa original grudou
