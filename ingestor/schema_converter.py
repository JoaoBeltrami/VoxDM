"""
Converte chunks de texto de PDF para o VoxDM Schema v1.1 via Groq.

Por que existe: Groq substitui Gemini (free tier extinto) na etapa de conversão
da pipeline de ingestão — recebe chunks brutos e devolve fragmentos de schema JSON.
Dependências: groq, tenacity, structlog
Armadilha: Groq retorna texto Markdown às vezes mesmo com instrução explícita;
usar _extrair_json_limpo() antes de json.loads() para remover backticks.

Exemplo:
    fragmentos = await convert_all_chunks(["Bjorn é o líder de Tharnvik..."])
    schema = merge_schema_fragments(fragmentos)
    # → {"npcs": [{"id": "bjorn-tharnsson", ...}], "locations": [...]}
"""

import json
import re
from typing import Any

import structlog
from groq import AsyncGroq
from tenacity import (
    RetryCallState,
    retry,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

logger = structlog.get_logger(__name__)

# Prompt do sistema — instrui o modelo a retornar SOMENTE JSON válido
_SYSTEM_PROMPT = """Você é um conversor de texto para o VoxDM Schema v1.1.

Dado um trecho de texto de módulo de RPG, extraia APENAS as entidades presentes e retorne um fragmento JSON parcial do schema.

REGRAS ABSOLUTAS:
- Retorne SOMENTE JSON válido — sem markdown, sem backticks, sem explicação, sem comentários
- Inclua apenas as chaves que existem no texto fornecido (npcs, locations, companions, entities, factions, items, quests, secrets)
- IDs sempre em kebab-case: "bjorn-tharnsson", "barovia-village"
- Se o texto não contiver nenhuma entidade reconhecível, retorne: {}

ESTRUTURA DE REFERÊNCIA (use apenas o que o texto mencionar):
{
  "npcs": [{"id": "", "name": "", "role": "", "personality": "", "knowledge": [], "speech_style": "", "relationships": {}, "_ext": {"race": "", "age": 0, "appearance": "", "motivation": ""}}],
  "companions": [{"id": "", "name": "", "role": "", "personality": "", "knowledge": [], "speech_style": "", "relationships": {}, "_ext": {"race": "", "age": 0, "appearance": "", "motivation": "", "class_mechanic": ""}}],
  "entities": [{"id": "", "name": "", "type": "", "description": "", "abilities": [], "relationships": {}}],
  "locations": [{"id": "", "name": "", "description": "", "connections": [], "npcs": [], "atmosphere": ""}],
  "factions": [{"id": "", "name": "", "goal": "", "members": []}],
  "items": [{"id": "", "name": "", "description": "", "properties": []}],
  "quests": [{"id": "", "name": "", "description": "", "stages": []}],
  "secrets": [{"id": "", "content": "", "known_by": []}]
}"""


def _extrair_json_limpo(texto: str) -> str:
    """Remove backticks e marcadores markdown antes do json.loads()."""
    # Remove blocos ```json ... ``` ou ``` ... ```
    texto = re.sub(r"```(?:json)?\s*", "", texto)
    texto = re.sub(r"```", "", texto)
    return texto.strip()


def _logar_tentativa(retry_state: RetryCallState) -> None:
    """Loga cada tentativa de retry com contexto."""
    logger.warning(
        "groq_retry",
        tentativa=retry_state.attempt_number,
        chunk_index=retry_state.kwargs.get("chunk_index", "?"),
        erro=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )


@retry(
    wait=wait_exponential(min=2, max=30),
    stop=stop_after_attempt(5),
    before_sleep=_logar_tentativa,
)
async def convert_chunk_to_schema(chunk: str, chunk_index: int) -> dict[str, Any]:
    """Converte um único chunk de texto para fragmento do VoxDM Schema v1.1.

    Args:
        chunk: Texto bruto extraído do PDF.
        chunk_index: Índice do chunk para logging.

    Returns:
        Dicionário com fragmento do schema (pode ser {} se nada for encontrado).
    """
    log = logger.bind(chunk_index=chunk_index, chunk_len=len(chunk))
    log.info("convertendo_chunk")

    cliente = AsyncGroq(api_key=settings.GROQ_API_KEY)

    resposta = await cliente.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Converta este trecho:\n\n{chunk}"},
        ],
        temperature=0.1,  # baixa para respostas determinísticas
        max_tokens=4096,
    )

    conteudo_bruto: str = resposta.choices[0].message.content or "{}"
    conteudo_limpo: str = _extrair_json_limpo(conteudo_bruto)

    try:
        fragmento: dict[str, Any] = json.loads(conteudo_limpo)
        log.info("chunk_convertido", chaves=list(fragmento.keys()))
        return fragmento
    except json.JSONDecodeError as e:
        log.error(
            "json_invalido",
            erro=str(e),
            conteudo_raw=conteudo_bruto[:200],
        )
        # Pula o chunk e continua — não interrompe o pipeline
        return {}


async def convert_all_chunks(chunks: list[str]) -> dict[str, Any]:
    """Converte todos os chunks e consolida num schema único.

    Args:
        chunks: Lista de strings extraídas do PDF.

    Returns:
        Schema VoxDM v1.1 consolidado com todas as entidades encontradas.
    """
    logger.info("iniciando_conversao", total_chunks=len(chunks))

    fragmentos: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        fragmento = await convert_chunk_to_schema(chunk=chunk, chunk_index=i)
        if fragmento:
            fragmentos.append(fragmento)

    schema_final: dict[str, Any] = merge_schema_fragments(fragmentos)
    logger.info(
        "conversao_concluida",
        fragmentos_validos=len(fragmentos),
        chaves_schema=list(schema_final.keys()),
    )
    return schema_final


def merge_schema_fragments(fragments: list[dict[str, Any]]) -> dict[str, Any]:
    """Consolida lista de fragmentos num schema único, desduplicando por `id`.

    Args:
        fragments: Lista de dicionários parciais do schema VoxDM v1.1.

    Returns:
        Schema único com listas desduplicadas por `id`.
    """
    # Chaves do schema que contêm listas de entidades com `id`
    chaves_lista: list[str] = [
        "npcs", "companions", "entities", "locations",
        "factions", "items", "quests", "secrets",
    ]

    merged: dict[str, Any] = {}

    for fragmento in fragments:
        for chave, valor in fragmento.items():
            if chave not in chaves_lista:
                # Chaves escalares (ex: module) — última escreve
                merged[chave] = valor
                continue

            if not isinstance(valor, list):
                continue

            if chave not in merged:
                merged[chave] = []

            # Desduplicação por `id`
            ids_existentes: set[str] = {
                item.get("id", "") for item in merged[chave]
            }
            for item in valor:
                item_id: str = item.get("id", "")
                if item_id and item_id not in ids_existentes:
                    merged[chave].append(item)
                    ids_existentes.add(item_id)

    logger.info(
        "fragmentos_consolidados",
        total_fragmentos=len(fragments),
        entidades_por_chave={k: len(v) for k, v in merged.items() if isinstance(v, list)},
    )
    return merged
