"""
Refinamento de fragmentos do VoxDM Schema v1.2 via Groq.

Por que existe: garante consistência e completude do schema após a conversão
    inicial — preenche campos obrigatórios ausentes, corrige IDs para kebab-case
    e remove ruído (strings vazias, campos null desnecessários).
Dependências: groq, tenacity, structlog
Armadilha: usar APÓS schema_converter.py, nunca em substituição. O refiner
    corrige problemas de qualidade, não faz conversão de texto bruto para JSON.

Exemplo:
    fragmento_sujo = {"npcs": [{"id": "Bjorn The Blacksmith", "name": "Bjorn"}]}
    fragmento_limpo = await refinar_fragmento(fragmento_sujo)
    # → {"npcs": [{"id": "bjorn-the-blacksmith", "name": "Bjorn"}]}
"""

import json
import re
from typing import Any

import structlog
from groq import (
    APIConnectionError,
    APITimeoutError,
    AsyncGroq,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """Você é um validador e refinador do VoxDM Schema v1.2.

Dado um fragmento JSON de schema de módulo RPG, corrija e retorne o fragmento melhorado.

CORREÇÕES OBRIGATÓRIAS:
1. IDs em kebab-case: "Bjorn Ferreiro" → "bjorn-ferreiro"
2. Remover campos com string vazia "", null ou lista vazia []
3. Garantir que `name` existe em toda entidade com `id`
4. `trust_level` em secrets: inteiro 0-3 (não string)
5. `edges`: garantir que `from`, `to` e `type` são strings não-vazias

RETORNE SOMENTE JSON VÁLIDO — sem markdown, sem explicação, sem backticks.
Se o fragmento já estiver correto, retorne-o idêntico."""


def _extrair_json_limpo(texto: str) -> str:
    """Remove formatação Markdown se o Groq retornar com backticks."""
    texto = texto.strip()
    # Remove blocos ```json ... ``` ou ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", texto)
    if match:
        return match.group(1).strip()
    return texto


def _log_retry(state: RetryCallState) -> None:
    log.warning(
        "groq_refiner.retry",
        tentativa=state.attempt_number,
        erro=str(state.outcome.exception()) if state.outcome else "desconhecido",
    )


@retry(
    retry=retry_if_exception_type(
        (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=_log_retry,
)
async def refinar_fragmento(fragmento: dict[str, Any]) -> dict[str, Any]:
    """
    Refina um fragmento de schema via Groq corrigindo IDs, ruído e campos obrigatórios.

    Args:
        fragmento: Fragmento do VoxDM Schema v1.2 (saída do schema_converter).

    Returns:
        Fragmento refinado e consistente.

    Raises:
        json.JSONDecodeError: Se o Groq retornar JSON inválido após 3 tentativas.
    """
    cliente = AsyncGroq(api_key=settings.GROQ_API_KEY)

    fragmento_str = json.dumps(fragmento, ensure_ascii=False, indent=2)

    log.info("groq_refiner.iniciando", entidades=list(fragmento.keys()))

    resposta = await cliente.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": fragmento_str},
        ],
        temperature=0.0,
        max_tokens=4096,
    )

    conteudo = resposta.choices[0].message.content or ""
    conteudo_limpo = _extrair_json_limpo(conteudo)

    try:
        resultado: dict[str, Any] = json.loads(conteudo_limpo)
    except json.JSONDecodeError as exc:
        log.error(
            "groq_refiner.json_invalido",
            erro=str(exc),
            resposta_bruta=conteudo[:300],
        )
        # Retorna fragmento original sem refinamento para não perder dados
        return fragmento

    log.info("groq_refiner.concluido", entidades=list(resultado.keys()))
    return resultado


async def refinar_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Refina o schema completo dividindo em fragmentos por seção.

    Processa cada chave de lista (npcs, locations, etc.) separadamente
    para respeitar o limite de tokens do Groq.

    Args:
        schema: Schema VoxDM v1.2 completo.

    Returns:
        Schema refinado e consistente.
    """
    # Chaves que contêm listas de entidades para refinar
    chaves_entidades = [
        "npcs", "companions", "entities", "locations",
        "factions", "quests", "items", "secrets",
    ]

    schema_refinado: dict[str, Any] = {**schema}

    for chave in chaves_entidades:
        if chave not in schema or not schema[chave]:
            continue

        fragmento = {chave: schema[chave]}
        log.info("groq_refiner.secao", chave=chave, total=len(schema[chave]))

        fragmento_refinado = await refinar_fragmento(fragmento)
        if chave in fragmento_refinado:
            schema_refinado[chave] = fragmento_refinado[chave]

    # Refinar edges separadamente (estrutura diferente)
    if schema.get("edges"):
        fragmento_edges = await refinar_fragmento({"edges": schema["edges"]})
        if "edges" in fragmento_edges:
            schema_refinado["edges"] = fragmento_edges["edges"]

    log.info("groq_refiner.schema_completo_refinado")
    return schema_refinado
