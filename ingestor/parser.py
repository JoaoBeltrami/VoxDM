"""
Valida a estrutura de um schema VoxDM v1.2 antes de ingeri-lo nos bancos.

Por que existe: detectar erros de estrutura cedo, antes de gastar chamadas de API
    e tempo de upload em dados malformados.
Dependências: nenhuma externa — só stdlib
Armadilha: validação é intencional mas não exaustiva — foca nos campos que quebram
    o pipeline downstream (id, name, edges). Campos opcionais são ignorados.

Exemplo:
    erros = validar_schema(schema_dict)
    # → [] se OK, ou ["npcs[2]: id ausente", "edges[0]: type ausente", ...]
"""

import re
from typing import Any

import structlog

log = structlog.get_logger()

# Padrão obrigatório para IDs: kebab-case
_PADRAO_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Categorias com elementos que precisam de id + name
_CATEGORIAS_ENTIDADES = [
    "locations", "npcs", "companions", "entities",
    "factions", "items", "artifacts", "quests", "secrets",
]

# Valores válidos para disposition
_DISPOSITIONS_VALIDOS = {"friendly", "neutral", "hostile", "fearful", "indifferent"}


def _validar_id(id_valor: str, contexto: str) -> list[str]:
    """Valida que um ID existe e segue kebab-case."""
    erros: list[str] = []
    if not id_valor:
        erros.append(f"{contexto}: id ausente ou vazio")
    elif not _PADRAO_ID.match(id_valor):
        erros.append(f"{contexto}: id '{id_valor}' não é kebab-case válido")
    return erros


def _validar_entidades(schema: dict[str, Any]) -> list[str]:
    """Valida todos os elementos de todas as categorias."""
    erros: list[str] = []

    for categoria in _CATEGORIAS_ENTIDADES:
        elementos: list[Any] = schema.get(categoria, [])
        if not isinstance(elementos, list):
            erros.append(f"{categoria}: esperado list, recebeu {type(elementos).__name__}")
            continue

        for i, elem in enumerate(elementos):
            if not isinstance(elem, dict):
                erros.append(f"{categoria}[{i}]: elemento não é dict")
                continue

            ctx = f"{categoria}[{i}]"

            # id obrigatório
            erros.extend(_validar_id(str(elem.get("id", "")), ctx))

            # name recomendado mas opcional — secrets usam apenas id + content
            if not elem.get("name") and categoria != "secrets":
                erros.append(f"{ctx}: name ausente ou vazio")

            # honesty: se presente, deve ser float 0.0-1.0
            if "honesty" in elem:
                h = elem["honesty"]
                if not isinstance(h, (int, float)) or not (0.0 <= float(h) <= 1.0):
                    erros.append(f"{ctx}: honesty '{h}' fora do range 0.0-1.0")

            # disposition: se presente, deve ser valor válido
            if "disposition" in elem:
                d = elem["disposition"]
                if d not in _DISPOSITIONS_VALIDOS:
                    erros.append(f"{ctx}: disposition '{d}' inválido — esperado {_DISPOSITIONS_VALIDOS}")

    return erros


def _validar_edges(schema: dict[str, Any]) -> list[str]:
    """Valida a lista de arestas top-level."""
    erros: list[str] = []
    edges: list[Any] = schema.get("edges", [])

    if not isinstance(edges, list):
        erros.append(f"edges: esperado list, recebeu {type(edges).__name__}")
        return erros

    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            erros.append(f"edges[{i}]: elemento não é dict")
            continue

        ctx = f"edges[{i}]"

        if not edge.get("from"):
            erros.append(f"{ctx}: campo 'from' ausente ou vazio")
        if not edge.get("to"):
            erros.append(f"{ctx}: campo 'to' ausente ou vazio")
        if not edge.get("type"):
            erros.append(f"{ctx}: campo 'type' ausente ou vazio")

        # weight: se presente, deve ser numérico
        if "weight" in edge:
            w = edge["weight"]
            if not isinstance(w, (int, float)):
                erros.append(f"{ctx}: weight '{w}' não é numérico")

    return erros


def _validar_module(schema: dict[str, Any]) -> list[str]:
    """Valida o bloco module (metadados do módulo)."""
    erros: list[str] = []
    module: Any = schema.get("module")

    if module is None:
        erros.append("module: bloco ausente")
        return erros

    if not isinstance(module, dict):
        erros.append(f"module: esperado dict, recebeu {type(module).__name__}")
        return erros

    erros.extend(_validar_id(str(module.get("id", "")), "module"))

    if not module.get("name"):
        erros.append("module: name ausente")

    return erros


def validar_schema(schema: dict[str, Any]) -> list[str]:
    """
    Valida um schema VoxDM v1.2 completo.

    Retorna lista de strings descrevendo cada erro encontrado.
    Lista vazia significa schema válido para ingestão.
    """
    if not isinstance(schema, dict):
        return [f"schema: esperado dict, recebeu {type(schema).__name__}"]

    erros: list[str] = []

    erros.extend(_validar_module(schema))
    erros.extend(_validar_entidades(schema))
    erros.extend(_validar_edges(schema))

    if erros:
        log.warning("schema_invalido", total_erros=len(erros), primeiros=erros[:5])
    else:
        total_nos = sum(
            len(schema.get(cat, []))
            for cat in _CATEGORIAS_ENTIDADES
        )
        log.info("schema_valido", nos=total_nos, edges=len(schema.get("edges", [])))

    return erros
