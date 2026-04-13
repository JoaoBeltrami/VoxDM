"""
Divide elementos do schema VoxDM v1.2 em chunks semânticos para o Qdrant.

Por que existe: o Qdrant armazena vetores de texto; descriptions longas precisam
    ser quebradas com overlap para não perder contexto nas bordas.
Dependências: nenhuma externa — só stdlib
Armadilha: chunks muito curtos (< 10 palavras) geram vetores ruidosos —
    elementos sem description são ignorados silenciosamente.

Exemplo:
    chunks = extrair_chunks(schema)
    # → [ChunkRecord(text="...", source_type="npc", source_id="bjorn", ...)]
"""

from typing import Any, TypedDict

import structlog

log = structlog.get_logger()

# Limite de palavras por chunk antes de dividir (~500 tokens)
MAX_PALAVRAS = 375
# Overlap em palavras entre chunks consecutivos
OVERLAP_PALAVRAS = 50
# Mínimo de palavras para valer um chunk
MIN_PALAVRAS = 10

# Campos de texto a extrair por categoria (em ordem de prioridade)
_CAMPOS_POR_CATEGORIA: dict[str, list[str]] = {
    "locations":   ["description", "atmosphere"],
    "npcs":        ["description", "backstory", "personality"],
    "companions":  ["description", "backstory", "personality"],
    "entities":    ["description"],
    "factions":    ["description", "goals"],
    "items":       ["description", "lore"],
    "artifacts":   ["description", "lore"],
    "quests":      ["description", "summary"],
    "secrets":     ["content", "description", "lie_content"],
}


class ChunkRecord(TypedDict):
    """Registro de um chunk pronto para embedding e upload ao Qdrant."""
    text: str
    source_type: str   # categoria normalizada: "npc", "location", etc.
    source_id: str
    source_name: str
    chunk_index: int
    campo: str         # qual campo do schema originou este chunk


def _normalizar_source_type(categoria: str) -> str:
    """Converte chave do schema (plural) para source_type (singular) do Qdrant."""
    mapa = {
        "locations": "location",
        "npcs": "npc",
        "companions": "companion",
        "entities": "entity",
        "factions": "faction",
        "items": "item",
        "artifacts": "artifact",
        "quests": "quest",
        "secrets": "secret",
    }
    return mapa.get(categoria, categoria)


def _dividir_em_chunks(
    texto: str,
    source_id: str,
    source_name: str,
    source_type: str,
    campo: str,
    offset_index: int = 0,
) -> list[ChunkRecord]:
    """
    Divide um texto em chunks com overlap.

    offset_index permite continuar a numeração quando um elemento tem
    múltiplos campos (description + atmosphere, por ex).
    """
    palavras = texto.split()

    if len(palavras) < MIN_PALAVRAS:
        return []

    if len(palavras) <= MAX_PALAVRAS:
        return [ChunkRecord(
            text=texto,
            source_type=source_type,
            source_id=source_id,
            source_name=source_name,
            chunk_index=offset_index,
            campo=campo,
        )]

    chunks: list[ChunkRecord] = []
    inicio = 0
    idx = offset_index

    while inicio < len(palavras):
        fim = min(inicio + MAX_PALAVRAS, len(palavras))
        chunks.append(ChunkRecord(
            text=" ".join(palavras[inicio:fim]),
            source_type=source_type,
            source_id=source_id,
            source_name=source_name,
            chunk_index=idx,
            campo=campo,
        ))
        if fim == len(palavras):
            break
        inicio = fim - OVERLAP_PALAVRAS
        idx += 1

    return chunks


def extrair_chunks(schema: dict[str, Any]) -> list[ChunkRecord]:
    """
    Percorre todas as categorias do schema e extrai chunks de todos os campos de texto.

    Retorna lista plana de ChunkRecord prontos para embedding.
    """
    todos: list[ChunkRecord] = []
    total_por_categoria: dict[str, int] = {}

    for categoria, campos in _CAMPOS_POR_CATEGORIA.items():
        elementos: list[dict[str, Any]] = schema.get(categoria, [])
        if not isinstance(elementos, list):
            continue

        source_type = _normalizar_source_type(categoria)
        chunks_categoria = 0

        for elem in elementos:
            if not isinstance(elem, dict):
                continue

            source_id: str = str(elem.get("id", "unknown"))
            source_name: str = str(elem.get("name", source_id))
            chunk_index_offset = 0

            for campo in campos:
                texto: Any = elem.get(campo)
                if not texto or not isinstance(texto, str):
                    continue

                novos_chunks = _dividir_em_chunks(
                    texto=texto.strip(),
                    source_id=source_id,
                    source_name=source_name,
                    source_type=source_type,
                    campo=campo,
                    offset_index=chunk_index_offset,
                )
                todos.extend(novos_chunks)
                chunks_categoria += len(novos_chunks)
                # Próximo campo do mesmo elemento continua a numeração
                chunk_index_offset += len(novos_chunks)

        if chunks_categoria:
            total_por_categoria[categoria] = chunks_categoria

    log.info(
        "chunks_extraidos",
        total=len(todos),
        por_categoria=total_por_categoria,
    )
    return todos
