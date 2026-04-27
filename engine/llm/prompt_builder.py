"""
Monta o prompt final para o LLM a partir do contexto pré-assembleado.

Por que existe: separa a lógica de formatação do prompt da lógica de busca,
    garantindo que o prompt_builder seja puro (sem I/O) e testável isoladamente.
Dependências: apenas stdlib — recebe dados já montados pelo context_builder
Armadilha: lie_content nunca deve chegar ao LLM como string vazia — se for None,
    passar instrução de evasão; se for str, passar como mentira direta.

Exemplo:
    msgs = montar_mensagens(contexto, master_system)
    # → [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Caminho do prompt do mestre — lido uma vez e cacheado
_MASTER_SYSTEM_PATH = Path(__file__).parent / "prompts" / "master_system.md"
_master_system_cache: str | None = None

# Budget de tokens por camada (aproximado — 1 token ≈ 4 chars)
BUDGET_WORKING   = 1600   # 40% — nunca cortado
BUDGET_EPISODICO = 1200   # 30%
BUDGET_SEMANTICO = 1200   # 30%
BUDGET_REGRAS    =  225   # combate, saves, condições de status — top 3 chunks SRD

# Lembrete de formato — posicionado ao fim do system prompt para garantir aderência.
# Repetir aqui compensa o fato de o contexto (lore, regras, secrets) ser injetado
# depois do master_system.md e "soterrar" a Regra Zero original.
_LEMBRETE_SAIDA = (
    "\n---\n"
    "[LEMBRETE DE SAÍDA — OBRIGATÓRIO]\n"
    "Responda em prosa falada. Proibido: markdown, asteriscos, listas, "
    "parênteses técnicos, travessões de diálogo, cabeçalhos, negrito, itálico.\n"
    "Use apenas vírgulas, reticências, dois-pontos e pontos finais.\n"
    "Máximo 2 a 3 frases curtas por resposta. "
    "Escreva como narrador humano falando em voz alta — não como texto impresso."
)


@dataclass
class SecretVisivel:
    """Secret que o context_builder decidiu que pode ser revelado (total ou parcialmente)."""
    npc_id: str
    content: str
    lie_content: str | None   # None → NPC esquiva; str → NPC mente com este texto
    revelar: bool             # True → content; False → lie_content ou evasão


@dataclass
class ContextoMontado:
    """Saída do context_builder — tudo que o prompt_builder precisa."""
    working_memory: WorkingMemory
    chunks_semanticos: list[dict[str, Any]]      # do voxdm_modules
    chunks_episodicos: list[dict[str, Any]]      # sessões anteriores
    chunks_regras: list[dict[str, Any]]          # do voxdm_rules (SRD)
    relacoes_grafo: list[dict[str, Any]]         # do Neo4j
    secrets_visiveis: list[SecretVisivel]
    transcricao_atual: str


def _carregar_master_system() -> str:
    """Carrega e cacheia o prompt do mestre em disco."""
    global _master_system_cache
    if _master_system_cache is None:
        if _MASTER_SYSTEM_PATH.exists():
            _master_system_cache = _MASTER_SYSTEM_PATH.read_text(encoding="utf-8")
        else:
            log.warning("master_system_ausente", path=str(_MASTER_SYSTEM_PATH))
            _master_system_cache = (
                "Você é VoxDM, um mestre de RPG de mesa narrando em português brasileiro. "
                "Seja imersivo, conciso e consistente com o contexto fornecido."
            )
    return _master_system_cache


def _formatar_chunks(chunks: list[dict[str, Any]], limite_chars: int) -> str:
    """Formata chunks como texto, respeitando limite de caracteres aproximado."""
    if not chunks:
        return ""
    partes: list[str] = []
    total = 0
    for chunk in chunks:
        texto = chunk.get("text", "")
        nome = chunk.get("source_name", chunk.get("source_id", ""))
        linha = f"[{nome}] {texto}"
        if total + len(linha) > limite_chars:
            break
        partes.append(linha)
        total += len(linha)
    return "\n\n".join(partes)


def _formatar_relacoes(relacoes: list[dict[str, Any]]) -> str:
    if not relacoes:
        return ""
    linhas = [f"  {r['tipo']}: {r.get('alvo_nome', r['alvo_id'])} (peso: {r['weight']:.1f})"
              for r in relacoes]
    return "Relações no grafo:\n" + "\n".join(linhas)


def _formatar_secrets(secrets: list[SecretVisivel]) -> str:
    """Formata secrets como instruções internas ao LLM — não visíveis ao jogador."""
    if not secrets:
        return ""
    partes: list[str] = ["[INSTRUÇÕES INTERNAS — NÃO REVELAR AO JOGADOR]"]
    for s in secrets:
        if s.revelar:
            partes.append(
                f"NPC {s.npc_id} pode revelar agora: \"{s.content}\""
            )
        elif s.lie_content:
            partes.append(
                f"NPC {s.npc_id} sabe a verdade mas vai mentir: \"{s.lie_content}\""
            )
        else:
            # lie_content None → evasão narrativa
            partes.append(
                f"NPC {s.npc_id} sabe algo mas deve desviar do assunto sem revelar."
            )
    return "\n".join(partes)


def montar_mensagens(
    contexto: ContextoMontado,
    master_system_override: str | None = None,
) -> list[dict[str, str]]:
    """
    Monta a lista de mensagens para o LLM a partir do contexto pré-montado.

    O histórico de diálogo é passado como pares user/assistant reais — não como
    texto no system prompt — para aproveitar o modo de chat nativo do modelo.

    Args:
        contexto: ContextoMontado produzido pelo context_builder.
        master_system_override: Substitui o master_system.md (útil em testes).

    Returns:
        Lista de dicts {role, content} prontos para o Groq/Ollama.
        Estrutura: [system, user?, assistant?, ..., user_atual]
    """
    master_system = master_system_override or _carregar_master_system()

    # ── System message: identidade + estado da cena (sem diálogo) ────────────
    secoes: list[str] = [master_system, ""]

    # Working memory sem diálogo — histórico vai como pares de mensagem abaixo
    secoes.append(contexto.working_memory.para_texto(incluir_dialogo=False))

    # Relações do grafo (NPCs presentes)
    if contexto.relacoes_grafo:
        secoes.append(_formatar_relacoes(contexto.relacoes_grafo))

    # Memória semântica (conteúdo do módulo)
    sem_texto = _formatar_chunks(contexto.chunks_semanticos, limite_chars=BUDGET_SEMANTICO * 4)
    if sem_texto:
        secoes.append(f"\n=== CONTEÚDO DO MÓDULO ===\n{sem_texto}")

    # Regras SRD relevantes (combate, saves, condições)
    regras_texto = _formatar_chunks(contexto.chunks_regras, limite_chars=BUDGET_REGRAS * 4)
    if regras_texto:
        secoes.append(f"\nREGRAS DE JOGO:\n{regras_texto}")

    # Memória episódica (sessões anteriores)
    ep_texto = _formatar_chunks(contexto.chunks_episodicos, limite_chars=BUDGET_EPISODICO * 4)
    if ep_texto:
        secoes.append(f"\n=== SESSÕES ANTERIORES ===\n{ep_texto}")

    # Instruções de secrets (internas — não visíveis ao jogador)
    secrets_texto = _formatar_secrets(contexto.secrets_visiveis)
    if secrets_texto:
        secoes.append(f"\n{secrets_texto}")

    system_content = "\n".join(secoes) + _LEMBRETE_SAIDA

    # ── Histórico de diálogo como pares user/assistant ────────────────────────
    # dialogo_recente[-1] é o turno atual do jogador (já registrado antes de montar).
    # Passamos [-1] como a mensagem final; os anteriores viram histórico real.
    turnos = contexto.working_memory.dialogo_recente
    historico = turnos[:-1] if turnos else []  # tudo exceto o turno atual

    mensagens: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    for turno in historico:
        role = "user" if turno.falante == "player" else "assistant"
        mensagens.append({"role": role, "content": turno.texto})

    # Turno atual — se dialogo_recente está vazio (chamada direta sem voice_runner)
    # usa transcricao_atual diretamente
    mensagens.append({"role": "user", "content": contexto.transcricao_atual})

    log.info(
        "prompt_montado",
        chars_system=len(system_content),
        turnos_historico=len(historico),
        chunks_semanticos=len(contexto.chunks_semanticos),
        chunks_episodicos=len(contexto.chunks_episodicos),
        secrets=len(contexto.secrets_visiveis),
    )

    return mensagens
