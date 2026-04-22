"""
Converte chunks de texto de PDF para o VoxDM Schema v1.2 via Groq.

Por que existe: Groq substitui Gemini (free tier extinto) na etapa de conversão
da pipeline de ingestão — recebe chunks brutos e devolve fragmentos de schema JSON.
Dependências: groq, tenacity, structlog

Schema v1.2 — mudanças em relação à v1.1:
  - NPCs/Companions: campos `honesty`, `disposition`, `political_allegiance`
  - Secrets: `lie_content`, `min_trust_level`, trigger_condition composto (AND/OR)
  - Locations: `state_variants` — descrição muda por condição de quest/evento
  - Factions: `reputation_thresholds` — define o que cada standing desbloqueia
  - Quests/stages: `on_complete` — efeitos encadeados entre entidades
  - Items: `owner`, `unlock_conditions`
  - Top-level `edges` — todas as relações entre entidades para o Neo4j

Armadilhas:
  - Groq retorna Markdown mesmo com instrução explícita →
    usar _extrair_json_limpo() SEMPRE antes de json.loads()
  - `edges` não usa `id` — deduplicação é por (from, to, type) em merge_schema_fragments()
  - `on_complete` em quests cria dependência entre entidades — o context_builder
    precisa resolver efeitos em ordem topológica, não em paralelo
  - `honesty` é traço estático do NPC; a decisão de mentir é dinâmica e fica
    no context_builder, não no schema

Exemplo:
    fragmentos = await convert_all_chunks(["Bjorn é o líder de Tharnvik..."])
    schema = merge_schema_fragments(fragmentos)
    # → {"npcs": [...], "edges": [...], "locations": [...]}
"""

import asyncio
import json
import re
from typing import Any

import structlog
from groq import (
    AsyncGroq,
    APIConnectionError,
    APITimeoutError,
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

logger = structlog.get_logger(__name__)

# Semáforo global — limita chamadas paralelas ao Groq (conservador para free tier)
_GROQ_SEMAPHORE = asyncio.Semaphore(5)

# =============================================================================
# SYSTEM PROMPT — VoxDM Schema v1.2
# =============================================================================
# ARMADILHA (prompt engineering): o Groq tende a "completar" campos opcionais
# com strings vazias ("") em vez de omiti-los. Isso infla o schema com ruído.
# A instrução "omita campos ausentes" precisa estar explícita e repetida.
# Se o ruído voltar em produção, adicionar uma etapa de limpeza pós-parse
# que remove strings vazias e listas vazias antes de salvar no Qdrant.
# =============================================================================
_SYSTEM_PROMPT = """Você é um conversor de texto para o VoxDM Schema v1.2.

Dado um trecho de texto de módulo de RPG, extraia APENAS as entidades presentes
e retorne um fragmento JSON parcial do schema.

REGRAS ABSOLUTAS:
- Retorne SOMENTE JSON válido — sem markdown, sem backticks, sem explicação
- Inclua APENAS as chaves presentes no texto — omita campos ausentes completamente
- IDs sempre em kebab-case: "bjorn-tharnsson", "vale-dos-ossos"
- Se o texto não contiver nenhuma entidade reconhecível, retorne: {}

ESTRUTURA DE REFERÊNCIA COMPLETA (use apenas o que o texto mencionar):

{
  "npcs": [
    {
      "id": "kebab-case",
      "name": "",
      "role": "",
      "personality": "",
      "speech_style": "",
      "knowledge": [],

      "honesty": 0.8,
      "disposition": "neutral",
      "political_allegiance": "id-da-faccao-ou-null",

      "_ext": {
        "race": "",
        "age": 0,
        "appearance": "",
        "motivation": ""
      }
    }
  ],

  "companions": [
    {
      "id": "kebab-case",
      "name": "",
      "companion_for": "id-do-npc-ou-jogador",
      "role": "",
      "personality": "",
      "speech_style": "",
      "knowledge": [],
      "honesty": 0.9,
      "disposition": "friendly",
      "political_allegiance": null,
      "_ext": {
        "race": "",
        "age": 0,
        "appearance": "",
        "motivation": "",
        "class_mechanic": ""
      }
    }
  ],

  "entities": [
    {
      "id": "kebab-case",
      "name": "",
      "type": "criatura|construto|espírito",
      "description": "",
      "abilities": []
    }
  ],

  "locations": [
    {
      "id": "kebab-case",
      "name": "",
      "description": "",
      "atmosphere": "",
      "connections": [],
      "npcs": [],

      "state_variants": [
        {
          "trigger_condition": {
            "operator": "SINGLE",
            "conditions": [
              {"type": "quest_stage", "target": "id-da-quest", "value": "id-do-stage"}
            ]
          },
          "description": "Descrição alternativa após o evento"
        }
      ]
    }
  ],

  "factions": [
    {
      "id": "kebab-case",
      "name": "",
      "goal": "",
      "members": [],

      "reputation_thresholds": {
        "hostile": -20,
        "neutral": 0,
        "friendly": 20,
        "allied": 50
      }
    }
  ],

  "items": [
    {
      "id": "kebab-case",
      "name": "",
      "description": "",
      "properties": [],
      "owner": "id-do-npc-ou-null",

      "unlock_conditions": {
        "operator": "SINGLE",
        "conditions": [
          {"type": "npc_trust", "target": "id-do-npc", "value": 2}
        ]
      }
    }
  ],

  "quests": [
    {
      "id": "kebab-case",
      "name": "",
      "description": "",
      "stages": [
        {
          "id": "kebab-case",
          "description": "",
          "on_complete": [
            {"effect": "activate_quest",            "target": "id-da-quest"},
            {"effect": "npc_disposition_change",    "target": "id-do-npc",    "value": "hostile"},
            {"effect": "location_state_change",     "target": "id-do-local",  "value": "id-do-state-variant"},
            {"effect": "faction_standing_change",   "target": "id-da-faccao", "value": 10},
            {"effect": "item_transfer",             "target": "id-do-item",   "value": "id-do-novo-dono"}
          ]
        }
      ]
    }
  ],

  "secrets": [
    {
      "id": "kebab-case",
      "content": "A verdade que o NPC guarda",
      "lie_content": "O que o NPC diz quando honesty < threshold ou political_allegiance protege o secret. null se ele simplesmente recusa.",
      "known_by": ["id-do-npc"],
      "min_trust_level": 2,

      "trigger_condition": {
        "operator": "OR",
        "conditions": [
          {"type": "npc_trust",        "target": "id-do-npc",    "value": 2},
          {"type": "item_used",        "target": "id-do-item",   "value": null},
          {"type": "faction_standing", "target": "id-da-faccao", "value": "friendly"},
          {"type": "quest_stage",      "target": "id-da-quest",  "value": "id-do-stage"},
          {"type": "player_action",    "target": "descricao-da-acao", "value": null},
          {"type": "npc_relationship", "source": "id-npc-a",    "target": "id-npc-b", "value": "hostile"},
          {"type": "location_visited", "target": "id-do-local", "value": null}
        ]
      }
    }
  ],

  "edges": [
    {
      "from": "id-da-entidade-origem",
      "to":   "id-da-entidade-destino",
      "type": "rival|ally|mentor|guard|member_of|located_in|owns|knows_secret",
      "weight": 0.8
    }
  ]
}

NOTAS SOBRE CAMPOS CRÍTICOS:

honesty (NPCs/Companions):
  0.0 = sempre mente | 0.5 = situacional | 1.0 = incapaz de mentir
  Use o contexto narrativo para inferir — não invente se não houver indício.

disposition:
  Valores válidos: "friendly" | "neutral" | "hostile" | "fearful" | "indifferent"

trigger_condition.operator:
  "SINGLE" → exatamente uma condição no array
  "AND"    → todas as condições precisam ser verdadeiras
  "OR"     → qualquer condição satisfaz

edges.weight:
  Positivo = relação positiva (aliança, lealdade)
  Negativo = relação negativa (rivalidade, ódio)
  0.0 = neutro ou desconhecido"""


# =============================================================================
# Funções auxiliares
# =============================================================================

def _extrair_json_limpo(texto: str) -> str:
    """Remove backticks e marcadores markdown antes do json.loads()."""
    texto = re.sub(r"```(?:json)?\s*", "", texto)
    texto = re.sub(r"```", "", texto)
    return texto.strip()


def _logar_tentativa(retry_state: RetryCallState) -> None:
    """Loga cada tentativa de retry com contexto estruturado."""
    logger.warning(
        "groq_retry",
        tentativa=retry_state.attempt_number,
        chunk_index=retry_state.kwargs.get("chunk_index", "?"),
        erro=str(retry_state.outcome.exception()) if retry_state.outcome else None,
    )


# =============================================================================
# Conversão de chunks
# =============================================================================

@retry(
    wait=wait_exponential(min=2, max=30),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(
        (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
    ),
    before_sleep=_logar_tentativa,
)
async def convert_chunk_to_schema(
    chunk: str,
    chunk_index: int,
    cliente: AsyncGroq,
) -> dict[str, Any]:
    """Converte um único chunk de texto para fragmento do VoxDM Schema v1.2.

    Args:
        chunk: Texto bruto extraído do PDF.
        chunk_index: Índice do chunk para logging e rastreabilidade.
        cliente: Instância compartilhada do AsyncGroq (aberta em convert_all_chunks).

    Returns:
        Dicionário com fragmento do schema. Retorna {} em caso de chunk vazio
        ou resposta não-parseável — nunca lança exceção para não interromper o pipeline.
    """
    log = logger.bind(chunk_index=chunk_index, chunk_len=len(chunk))

    # Guard — chunk vazio não gasta chamada ao Groq
    if not chunk or not chunk.strip():
        log.debug("chunk_vazio_ignorado")
        return {}

    log.info("convertendo_chunk")

    async with _GROQ_SEMAPHORE:
        resposta = await cliente.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Converta este trecho:\n\n{chunk}"},
            ],
            temperature=0.1,   # baixa para respostas determinísticas
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
        return {}


async def convert_all_chunks(chunks: list[str]) -> dict[str, Any]:
    """Converte todos os chunks em paralelo e consolida num schema único.

    Usa asyncio.gather com semáforo de 5 conexões simultâneas para
    respeitar o rate limit do Groq free tier.

    Args:
        chunks: Lista de strings extraídas do PDF pelo pdf_reader.py.

    Returns:
        Schema VoxDM v1.2 consolidado com todas as entidades encontradas.
    """
    logger.info("iniciando_conversao", total_chunks=len(chunks))

    # Cliente único compartilhado — async with garante fechamento das conexões
    async with AsyncGroq(api_key=settings.GROQ_API_KEY, timeout=60.0) as cliente:
        tarefas = [
            convert_chunk_to_schema(chunk=chunk, chunk_index=i, cliente=cliente)
            for i, chunk in enumerate(chunks)
        ]
        resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    # Separa resultados válidos de exceções não capturadas pelo retry
    fragmentos: list[dict[str, Any]] = []
    for i, r in enumerate(resultados):
        if isinstance(r, Exception):
            logger.error("chunk_excecao_nao_recuperada", chunk_index=i, erro=str(r))
        elif r:
            fragmentos.append(r)

    falhas: int = len(chunks) - len(fragmentos)
    schema_final: dict[str, Any] = merge_schema_fragments(fragmentos)

    logger.info(
        "conversao_concluida",
        total_chunks=len(chunks),
        fragmentos_validos=len(fragmentos),
        falhas=falhas,
        chaves_schema=list(schema_final.keys()),
    )
    return schema_final


# =============================================================================
# Consolidação de fragmentos
# =============================================================================

def merge_schema_fragments(fragments: list[dict[str, Any]]) -> dict[str, Any]:
    """Consolida lista de fragmentos num schema único, desduplicando por `id`.

    `edges` é tratado separadamente — não tem campo `id` próprio.
    Deduplicação de edges é por tupla (from, to, type).

    ARMADILHA: chunks vizinhos no PDF frequentemente descrevem o mesmo NPC
    em diferentes níveis de detalhe. A deduplicação por `id` mantém a PRIMEIRA
    ocorrência. Se o módulo tiver uma seção de "ficha resumida" antes do texto
    narrativo completo, garantir que o chunker coloque as fichas completas
    ANTES das resumidas na lista de entrada — ou implementar um merge por campo
    (deep merge) aqui no futuro como v1.3.

    Args:
        fragments: Lista de dicionários parciais do schema VoxDM v1.2.

    Returns:
        Schema único com listas desduplicadas por `id` (ou por from+to+type para edges).
    """
    # Chaves com listas de entidades identificadas por `id`
    chaves_lista: list[str] = [
        "npcs", "companions", "entities", "locations",
        "factions", "items", "quests", "secrets",
    ]

    merged: dict[str, Any] = {}
    ids_por_chave: dict[str, set[str]] = {}

    # Set separado para deduplicação de edges — chave composta (from, to, type)
    # ARMADILHA: o Groq pode gerar edges duplicadas com `weight` diferente para
    # o mesmo par de entidades (ex: "rival" com 0.6 e depois -0.8).
    # A deduplicação atual mantém a primeira — se isso gerar ruído nos grafos
    # do Neo4j, implementar estratégia de merge por média ou prioridade aqui.
    edges_vistos: set[tuple[str, str, str]] = set()

    for fragmento in fragments:
        for chave, valor in fragmento.items():

            # Tratamento especial para `edges` — sem campo `id`
            if chave == "edges":
                if not isinstance(valor, list):
                    continue
                if "edges" not in merged:
                    merged["edges"] = []
                for edge in valor:
                    chave_edge = (
                        edge.get("from", ""),
                        edge.get("to", ""),
                        edge.get("type", ""),
                    )
                    if all(chave_edge) and chave_edge not in edges_vistos:
                        merged["edges"].append(edge)
                        edges_vistos.add(chave_edge)
                    elif not all(chave_edge):
                        logger.warning(
                            "edge_incompleta_descartada",
                            edge=edge,
                        )
                continue

            if chave not in chaves_lista:
                # Chaves escalares (ex: module_name) — última escreve
                merged[chave] = valor
                continue

            if not isinstance(valor, list):
                continue

            if chave not in merged:
                merged[chave] = []
                ids_por_chave[chave] = set()

            for item in valor:
                item_id: str = item.get("id", "")
                if item_id and item_id not in ids_por_chave[chave]:
                    merged[chave].append(item)
                    ids_por_chave[chave].add(item_id)
                elif not item_id:
                    logger.warning(
                        "item_sem_id_descartado",
                        chave=chave,
                        item_preview=str(item)[:120],
                    )

    logger.info(
        "fragmentos_consolidados",
        total_fragmentos=len(fragments),
        entidades_por_chave={
            k: len(v) for k, v in merged.items() if isinstance(v, list)
        },
    )
    return merged
