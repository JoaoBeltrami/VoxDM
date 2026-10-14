"""
Envelope de save — WorkingMemory ⇄ JSON versionado, sem perder tipo nenhum.

Por que existe: o save de campanha precisa fotografar o estado inteiro da
    sessão (personagem, party, cena, narrativa, combate, inventário, uso de
    feature) e devolvê-lo IGUAL. JSON perde tipo: set vira lista, chave int vira
    string (`spell_slots` é chaveado por int — e `decrementar_slot` falha CALADO
    com chave string), dataclass aninhada vira dict. Este codec marca cada tipo
    que o JSON não tem e o reconstrói na volta.
Dependências: nenhuma externa — stdlib.
Armadilha: o envelope guarda PONTEIROS para a memória (session_id + dono), nunca
    o conteúdo do Qdrant/Neo4j copiado dentro. Copiar a memória para dentro do
    save duplicaria narrativa fora do isolamento por dono.
Armadilha: decodificar só instancia dataclasses de módulos `engine.*`. O save é
    arquivo em disco, e um arquivo adulterado não pode virar import arbitrário.
Armadilha: campo que existe no save mas não na classe atual é IGNORADO (com
    log); campo novo na classe que o save antigo não tem fica no default. É
    assim que um save sobrevive a uma mudança de código que não mexeu no formato.

Exemplo:
    env = montar_envelope(wm, owner_email="a@x.com", session_id="sess-1", campanha_id="c1")
    wm2 = restaurar_working_memory(env)
    assert wm2 == wm
"""

from __future__ import annotations

import dataclasses
import importlib
import time
from enum import Enum
from typing import Any

import structlog

from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Versão do FORMATO do envelope. Suba quando a forma mudar de um jeito que o
# leitor antigo não entenda, e escreva o migrador em `_MIGRADORES`.
SCHEMA_VERSION: int = 1

_TAG = "__t"


class SaveIncompativel(ValueError):
    """Envelope em versão que este código não sabe ler — a mensagem diz o que fazer."""


def _codificar(valor: Any) -> Any:
    """Valor Python → estrutura JSON-segura com marcas de tipo."""
    if valor is None or isinstance(valor, bool | int | float | str):
        return valor
    if isinstance(valor, Enum):
        cls = type(valor)
        return {_TAG: "enum", "c": f"{cls.__module__}:{cls.__qualname__}", "v": _codificar(valor.value)}
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        cls = type(valor)
        return {
            _TAG: "dc",
            "c": f"{cls.__module__}:{cls.__qualname__}",
            "f": {
                f.name: _codificar(getattr(valor, f.name))
                for f in dataclasses.fields(valor)
                if f.init
            },
        }
    if isinstance(valor, list):
        return [_codificar(v) for v in valor]
    if isinstance(valor, tuple):
        return {_TAG: "tuple", "v": [_codificar(v) for v in valor]}
    if isinstance(valor, set | frozenset):
        itens = [_codificar(v) for v in valor]
        # ordem estável — dois saves do mesmo estado dão o mesmo arquivo
        itens.sort(key=repr)
        return {_TAG: "frozenset" if isinstance(valor, frozenset) else "set", "v": itens}
    if isinstance(valor, dict):
        if all(isinstance(k, str) for k in valor) and _TAG not in valor:
            return {k: _codificar(v) for k, v in valor.items()}
        return {_TAG: "dict", "v": [[_codificar(k), _codificar(v)] for k, v in valor.items()]}
    raise TypeError(
        f"tipo {type(valor).__name__} não é serializável num save — "
        "se ele é ESTADO, ensine o codec; se é infraestrutura (lock, cliente), "
        "ele não pertence à WorkingMemory"
    )


def _classe(caminho: str) -> type:
    modulo, _, nome = caminho.partition(":")
    if not modulo.startswith("engine."):
        raise SaveIncompativel(f"save referencia classe fora da engine: {caminho}")
    obj: Any = importlib.import_module(modulo)
    for parte in nome.split("."):
        obj = getattr(obj, parte)
    if not isinstance(obj, type):
        raise SaveIncompativel(f"'{caminho}' não é uma classe")
    return obj


def _decodificar(valor: Any) -> Any:
    """Inverso de `_codificar`."""
    if isinstance(valor, list):
        return [_decodificar(v) for v in valor]
    if not isinstance(valor, dict):
        return valor
    tag = valor.get(_TAG)
    if tag is None:
        return {k: _decodificar(v) for k, v in valor.items()}
    if tag == "tuple":
        return tuple(_decodificar(v) for v in valor["v"])
    if tag == "set":
        return {_decodificar(v) for v in valor["v"]}
    if tag == "frozenset":
        return frozenset(_decodificar(v) for v in valor["v"])
    if tag == "dict":
        return {_decodificar(k): _decodificar(v) for k, v in valor["v"]}
    if tag == "enum":
        return _classe(valor["c"])(_decodificar(valor["v"]))
    if tag == "dc":
        cls = _classe(valor["c"])
        if not dataclasses.is_dataclass(cls):
            raise SaveIncompativel(f"'{valor['c']}' não é dataclass")
        conhecidos = {f.name for f in dataclasses.fields(cls) if f.init}
        campos = valor["f"]
        sobrando = set(campos) - conhecidos
        if sobrando:
            log.warning("save_campo_desconhecido_ignorado", classe=valor["c"], campos=sorted(sobrando))
        return cls(**{k: _decodificar(v) for k, v in campos.items() if k in conhecidos})
    raise SaveIncompativel(f"marca de tipo desconhecida no save: {tag!r}")


def montar_envelope(
    wm: WorkingMemory,
    *,
    owner_email: str,
    session_id: str,
    campanha_id: str,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fotografa a WorkingMemory num envelope versionado.

    `personagens` é LISTA de propósito: a campanha comporta N personagens; a
    engine hoje roda um por sessão, então a lista tem um item.
    """
    return {
        "schema_version": SCHEMA_VERSION,
        "criado_em": time.time(),
        "campanha_id": campanha_id,
        # Ponteiros para a memória — o conteúdo dela NÃO vem junto.
        "memoria": {"session_id": session_id, "owner_email": owner_email},
        "personagens": [{
            "nome": wm.player_name,
            "classe": wm.player_class,
            "nivel": wm.player_level,
            "estado": _codificar(wm),
        }],
        "extras": _codificar(extras or {}),
    }


# versão antiga → função que devolve o envelope na versão seguinte
_MIGRADORES: dict[int, Any] = {}


def _atualizar(envelope: dict[str, Any]) -> dict[str, Any]:
    versao = envelope.get("schema_version")
    if not isinstance(versao, int):
        raise SaveIncompativel(
            "save sem schema_version — não é um envelope do VoxDM ou está corrompido"
        )
    if versao > SCHEMA_VERSION:
        raise SaveIncompativel(
            f"save na versão {versao}, este código lê até {SCHEMA_VERSION}: "
            "atualize o VoxDM (git pull) antes de carregar este save"
        )
    while versao < SCHEMA_VERSION:
        migrar = _MIGRADORES.get(versao)
        if migrar is None:
            raise SaveIncompativel(
                f"save na versão {versao} e não há migrador para {versao + 1} — "
                "carregue-o numa versão do VoxDM da época ou escreva o migrador "
                "em engine/persistence/save_envelope.py"
            )
        envelope = migrar(envelope)
        versao = envelope["schema_version"]
    return envelope


def restaurar_working_memory(envelope: dict[str, Any], indice: int = 0) -> WorkingMemory:
    """Reconstrói a WorkingMemory do personagem `indice` do envelope."""
    envelope = _atualizar(envelope)
    try:
        bruto = envelope["personagens"][indice]["estado"]
    except (KeyError, IndexError, TypeError) as e:
        raise SaveIncompativel(f"save sem o personagem {indice}: {e}") from e
    wm = _decodificar(bruto)
    if not isinstance(wm, WorkingMemory):
        raise SaveIncompativel("o estado do save não é uma WorkingMemory")
    return wm


def resumo_manifesto(envelope: dict[str, Any]) -> dict[str, Any]:
    """Metadado do save — o que dá pra mostrar sem abrir o conteúdo."""
    return {
        "schema_version": envelope.get("schema_version"),
        "personagens": [
            {"nome": p.get("nome", ""), "classe": p.get("classe", ""), "nivel": p.get("nivel", 0)}
            for p in envelope.get("personagens", [])
        ],
    }
