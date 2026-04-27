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
# knowledge é lista → normalizado para string em _extrair_texto_campo()
_CAMPOS_POR_CATEGORIA: dict[str, list[str]] = {
    "locations":   ["description", "atmosphere"],
    "npcs":        ["description", "backstory", "personality", "speech_style", "knowledge"],
    "companions":  ["description", "backstory", "personality", "speech_style", "knowledge"],
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


def _limpar_role(role: str, locais_ids: set[str]) -> str:
    """Remove termos de localização do role para não poluir queries geográficas.

    Strip tanto o ID completo (ex: 'gargantas-vulcanicas') quanto palavras
    individuais longas (ex: 'gargantas') para cobrir roles como 'comandante-guarda-gargantas'.
    """
    termos: set[str] = set()
    for local_id in locais_ids:
        termos.add(local_id)
        for palavra in local_id.split("-"):
            if len(palavra) > 4:  # evitar strip de palavras curtas como "de", "da"
                termos.add(palavra)
    for termo in termos:
        role = role.replace(f"-{termo}", "").replace(termo, "")
    # Remover preposições soltas no final após o strip ("lider de" → "lider")
    role = role.strip("-").replace("-", " ").strip()
    palavras = role.split()
    preposicoes = {"de", "da", "do", "dos", "das", "em", "na", "no"}
    while palavras and palavras[-1] in preposicoes:
        palavras.pop()
    return " ".join(palavras)


def _construir_prefixo(
    elem: dict[str, Any],
    source_name: str,
    source_id: str,
    categoria: str,
    locais_ids: set[str],
) -> str:
    """
    Gera prefixo em linguagem natural com identidade do elemento.

    Inclui role e tipo para que o embedding do chunk corresponda a queries
    como "quem é X?" e "o que é X?" sem depender só do nome.
    Remove IDs de localização dos roles de NPCs/companions para evitar
    que queries geográficas retornem personagens.
    """
    if categoria in ("companions", "npcs"):
        role_raw = elem.get("role", "")
        companion_for = elem.get("companion_for", "")
        all_locais = locais_ids | ({companion_for} if companion_for else set())
        role_clean = _limpar_role(role_raw, all_locais)
        tipo = "companion" if categoria == "companions" else "NPC"
        base = f"{source_name} é um {tipo}"
        if role_clean:
            base += f", papel de {role_clean}"
        return base + ". "
    elif categoria == "locations":
        return f"{source_name} é uma localização na região. "
    elif categoria == "factions":
        return f"{source_name} é uma facção. "
    elif categoria == "items":
        return f"{source_name} é um item. "
    elif categoria == "artifacts":
        return f"{source_name} é um artefato. "
    elif categoria == "quests":
        return f"{source_name} é uma quest. "
    elif categoria == "secrets":
        return f"Segredo ({source_id}): "
    elif categoria == "entities":
        tipo = elem.get("type", "entidade")
        return f"{source_name} é uma {tipo}. "
    else:
        return f"{source_name} ({source_id}). "


def _extrair_texto_campo(elem: dict[str, Any], campo: str) -> str | None:
    """
    Extrai e normaliza o valor de um campo para string embedável.

    Trata os casos especiais:
    - knowledge: lista de strings → joined com "; "
    - _ext.appearance: campo aninhado em _ext
    - strings normais: retorna diretamente
    """
    if campo == "knowledge":
        val = elem.get("knowledge")
        if isinstance(val, list):
            itens = [str(v).strip() for v in val if v]
            return "; ".join(itens) if itens else None
        if isinstance(val, str):
            return val.strip() or None
        return None

    if campo == "_ext_appearance":
        ext = elem.get("_ext")
        if isinstance(ext, dict):
            ap = ext.get("appearance", "")
            return str(ap).strip() or None
        return None

    val = elem.get(campo)
    if not val or not isinstance(val, str):
        return None
    return val.strip() or None


def extrair_chunks(schema: dict[str, Any]) -> list[ChunkRecord]:
    """
    Percorre todas as categorias do schema e extrai chunks de todos os campos de texto.

    Inclui knowledge (lista → string), _ext.appearance e campos texto normais.
    Retorna lista plana de ChunkRecord prontos para embedding.
    """
    todos: list[ChunkRecord] = []
    total_por_categoria: dict[str, int] = {}

    # IDs de localização para strip dos roles de NPCs/companions
    locais_ids: set[str] = {
        str(loc.get("id", ""))
        for loc in schema.get("locations", [])
        if isinstance(loc, dict) and loc.get("id")
    }

    # Campos extras implícitos para NPCs e companions (não declarados em _CAMPOS_POR_CATEGORIA
    # para manter retrocompatibilidade — injetados por categoria aqui)
    _CAMPOS_EXTRAS: dict[str, list[str]] = {
        "npcs":       ["_ext_appearance"],
        "companions": ["_ext_appearance"],
    }

    for categoria, campos in _CAMPOS_POR_CATEGORIA.items():
        elementos: list[dict[str, Any]] = schema.get(categoria, [])
        if not isinstance(elementos, list):
            continue

        source_type = _normalizar_source_type(categoria)
        chunks_categoria = 0
        campos_efetivos = campos + _CAMPOS_EXTRAS.get(categoria, [])

        for elem in elementos:
            if not isinstance(elem, dict):
                continue

            source_id: str = str(elem.get("id", "unknown"))
            source_name: str = str(elem.get("name", source_id))
            chunk_index_offset = 0

            for campo in campos_efetivos:
                texto = _extrair_texto_campo(elem, campo)
                if not texto:
                    continue

                # Prefixo enriquecido: nome + role/tipo para reforçar retrieval por identidade
                prefixo = _construir_prefixo(elem, source_name, source_id, categoria, locais_ids)

                # Para knowledge, o prefixo indica explicitamente que é conhecimento do NPC
                if campo == "knowledge":
                    prefixo = f"{source_name} sabe: "

                novos_chunks = _dividir_em_chunks(
                    texto=prefixo + texto,
                    source_id=source_id,
                    source_name=source_name,
                    source_type=source_type,
                    campo=campo,
                    offset_index=chunk_index_offset,
                )
                todos.extend(novos_chunks)
                chunks_categoria += len(novos_chunks)
                chunk_index_offset += len(novos_chunks)

        if chunks_categoria:
            total_por_categoria[categoria] = chunks_categoria

    log.info(
        "chunks_extraidos",
        total=len(todos),
        por_categoria=total_por_categoria,
    )
    return todos
