"""
Store global de sessões ativas — estado compartilhado entre rotas REST e WebSocket.

Por que existe: ContextBuilder e GroqClient são criados uma vez por sessão e
    reutilizados em todos os turnos, evitando cold start de conexões TCP/TLS a cada request.
Dependências: engine/memory, engine/llm
Armadilha: dict em memória sem TTL — sessões inativas não são limpas automaticamente.
    Para produção, migrar para Redis com TTL de ~4h por sessão inativa.
    MAX_SESSOES protege contra vazamento de memória em demos ao vivo.

Exemplo:
    from api.state import sessions, SessaoAtiva, MAX_SESSOES
    sessions["sess-01"] = SessaoAtiva(session_id="sess-01", working_mem=wm, ...)
    sessao = sessions.get("sess-01")
"""

import time
from dataclasses import dataclass, field

import structlog

_log = structlog.get_logger()

from engine.llm.groq_client import GroqClient
from engine.memory.context_builder import ContextBuilder
from engine.memory.working_memory import WorkingMemory
from engine.voice.voice_manager import VoiceManager

# Limite de sessões simultâneas — evita vazamento de memória em demos
MAX_SESSOES: int = 50

# TTL de inatividade: sessões idle por mais deste tempo são removidas automaticamente
SESSION_TTL_SECONDS: int = 4 * 3600  # 4 horas


@dataclass
class SessaoAtiva:
    """Contêiner de estado para uma sessão de jogo em andamento."""

    session_id: str
    working_mem: WorkingMemory
    context_builder: ContextBuilder
    groq: GroqClient
    voice_manager: VoiceManager
    # Email do dono da sessão — vem do JWT do Cloudflare Access (ou DEV_USER em
    # debug). Toda checagem de autorização em rotas que aceitam session_id deve
    # comparar com este campo. Vazio = legado pré-auth (não deve ocorrer pós-4.6).
    owner_email: str = ""
    iteracoes: int = 0
    criada_em: float = field(default_factory=time.time)
    ultima_atividade: float = field(default_factory=time.time)
    resumo_anterior: str = ""  # Resumo da sessão anterior para recap narrativo na abertura
    ultimo_turno: dict = field(default_factory=dict)  # Snapshot do último turno para /debug/ultimo-turno
    # Catálogo de quests carregado do módulo — quest_id → [stage_ids válidos]
    # Usado pelo quest_detector para validar sinais [Q:...] do LLM
    quest_catalog: dict[str, list[str]] = field(default_factory=dict)
    # Efeitos on_complete por stage — quest_id → stage_id → [effect_dicts]
    # Usado pelo quest_detector para aplicar recompensas após avanço de quest
    quest_efeitos: dict[str, dict[str, list[dict]]] = field(default_factory=dict)
    # Cache de magias conhecidas — lista de nomes PT-BR selecionados na criação.
    # Inicializado em api/routes/session.py no POST /start e imutável por turno.
    # Injetado em ContextoMontado.spells_conhecidas antes de montar_mensagens().
    spells_conhecidas: list[str] = field(default_factory=list)
    # Identidade restaurada de sessão anterior — preenchido por iniciar_sessao()
    # quando session_anterior_id é fornecido e CharacterState tem personagem_config.
    # Retornado ao frontend via SessaoInfo.personagem_restaurado para que a tela
    # de "Carregar Sessão" não exija re-preenchimento do CharacterForm.
    personagem_restaurado: dict | None = None
    # Última frase de "thinking audio" enviada — evita repetição imediata.
    # Passada como `exceto` ao pegar_random() no próximo turno.
    ultima_frase_thinking: str = ""
    # Cadência do thinking audio (PLAYTEST 24/06: tocava TODO turno porque a
    # latência > limiar sempre). > 0 = pula este disparo e decrementa.
    thinking_cooldown: int = 0
    # Chave da última imagem de cena enviada ao frontend — "{location}|{combate}".
    # Evita reenviar a mesma URL quando o estado de cena não mudou.
    ultima_imagem_chave: str = ""
    # Imersão P4: retratos de NPC já enviados (1× por npc_id por sessão).
    retratos_enviados: set[str] = field(default_factory=set)
    # CRIT-1: spell slot pending — guarda (nome_magia, nivel) detectado no texto
    # do jogador. O decremento ACONTECE só após o LLM narrar o cast com sucesso
    # (no fim do pipeline). Se o turno falhar, o slot não é perdido.
    spell_pending: tuple[str, int] | None = None

    # Task 7 (combate engine-autoritativo): alvo do ataque declarado, aguardando
    # a rolagem d20 do jogador. {"tipo": "ataque", "alvo": npc_id}. Setado quando
    # o jogador declara "ataco o X" em combate; consumido quando o [Rolagem:] chega
    # e a engine resolve. Inerte quando COMBATE_ENGINE_ATIVO=False.
    combate_pendente: dict | None = None

    # Dashboard admin: histórico de turnos para gráficos (max 50, rolling).
    # Cada entry: {turno, pacing, hp, hp_max, em_combate, provider, task_type,
    #              latencia_ms, erros}. Populado em websocket.py após cada fim.
    historico_turnos: list[dict] = field(default_factory=list)
    # Último task_type narrativo usado — exibido no monitor sem precisar do turno.
    task_type_ultimo: str = ""


# Store global — keyed by session_id (kebab-case)
sessions: dict[str, SessaoAtiva] = {}


def limpar_sessoes_inativas() -> list[str]:
    """Remove sessões onde ultima_atividade excedeu SESSION_TTL_SECONDS. Thread-safe p/ asyncio."""
    agora = time.time()
    encerradas = [
        sid for sid, s in list(sessions.items())
        if agora - s.ultima_atividade > SESSION_TTL_SECONDS
    ]
    for sid in encerradas:
        del sessions[sid]
    if encerradas:
        _log.info("sessoes_inativas_removidas", ids=encerradas, total=len(encerradas))
    return encerradas
