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

    Args:
        contexto: ContextoMontado produzido pelo context_builder.
        master_system_override: Substitui o master_system.md (útil em testes).

    Returns:
        Lista de dicts {role, content} prontos para o Groq/Ollama.
    """
    master_system = master_system_override or _carregar_master_system()

    # ── System message: prompt do mestre + contexto da cena ──────────────────
    secoes: list[str] = [master_system, ""]

    # Working memory — sempre completa (prioridade máxima)
    secoes.append(contexto.working_memory.para_texto())

    # Relações do grafo (NPCs presentes)
    if contexto.relacoes_grafo:
        secoes.append(_formatar_relacoes(contexto.relacoes_grafo))

    # Memória semântica (conteúdo do módulo)
    sem_texto = _formatar_chunks(contexto.chunks_semanticos, limite_chars=BUDGET_SEMANTICO * 4)
    if sem_texto:
        secoes.append(f"\n=== CONTEÚDO DO MÓDULO ===\n{sem_texto}")

    # Regras SRD relevantes
    regras_texto = _formatar_chunks(contexto.chunks_regras, limite_chars=600)
    if regras_texto:
        secoes.append(f"\n=== REGRAS RELEVANTES ===\n{regras_texto}")

    # Memória episódica (sessões anteriores)
    ep_texto = _formatar_chunks(contexto.chunks_episodicos, limite_chars=BUDGET_EPISODICO * 4)
    if ep_texto:
        secoes.append(f"\n=== SESSÕES ANTERIORES ===\n{ep_texto}")

    # Instruções de secrets (internas — não visíveis ao jogador)
    secrets_texto = _formatar_secrets(contexto.secrets_visiveis)
    if secrets_texto:
        secoes.append(f"\n{secrets_texto}")

    system_content = "\n".join(secoes)

    log.info(
        "prompt_montado",
        chars_system=len(system_content),
        chunks_semanticos=len(contexto.chunks_semanticos),
        chunks_episodicos=len(contexto.chunks_episodicos),
        secrets=len(contexto.secrets_visiveis),
    )

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": contexto.transcricao_atual},
    ]
