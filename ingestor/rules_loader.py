"""
Carrega JSONs do SRD 5e (spells, conditions, classes, equipment) e normaliza
para ChunkRecord pronto para embedding na coleção voxdm_rules do Qdrant.

Por que existe: o pipeline principal (main.py) lida com módulos VoxDM (schema próprio);
    este loader lida com regras abertas do SRD 5e para que a engine responda a
    perguntas como "o que Fireball faz?" durante a sessão.
Dependências: json (stdlib), ingestor.chunker
Armadilha: os JSONs do 5e-database têm estrutura profundamente aninhada —
    as funções _normalizar_* extraem só o texto relevante para consulta em jogo;
    campos URL e índices internos são descartados.

Exemplo:
    chunks = carregar_regras(Path("srd/"))
    # → [ChunkRecord(text="Fireball (3rd level Evocation)...", source_type="spell", ...)]
"""

import json
from pathlib import Path
from typing import Any, Callable

import structlog

from ingestor.chunker import ChunkRecord, _dividir_em_chunks

log = structlog.get_logger()

SRD_DIR_DEFAULT = Path("srd")

_NIVEL_ORDINAL: dict[int, str] = {
    0: "cantrip",
    1: "1st level", 2: "2nd level", 3: "3rd level",
    4: "4th level", 5: "5th level", 6: "6th level",
    7: "7th level", 8: "8th level", 9: "9th level",
}


def _nomes(lista: list[dict[str, Any]]) -> str:
    """Extrai e une os 'name' de uma lista de referências aninhadas."""
    return ", ".join(x.get("name", "") for x in lista if x.get("name"))


def _normalizar_spell(spell: dict[str, Any]) -> str:
    nivel = _NIVEL_ORDINAL.get(spell.get("level", 0), "unknown level")
    escola = spell.get("school", {}).get("name", "")
    componentes = ", ".join(spell.get("components", []))
    material = spell.get("material", "")
    if material:
        componentes += f" ({material})"

    classes = _nomes(spell.get("classes", []))
    desc = " ".join(spell.get("desc", []))
    higher = " ".join(spell.get("higher_level", []))

    damage = spell.get("damage", {})
    damage_type = damage.get("damage_type", {}).get("name", "")
    damage_dice = ""
    if "damage_at_slot_level" in damage:
        base_slot = str(spell.get("level", 1))
        damage_dice = damage.get("damage_at_slot_level", {}).get(base_slot, "")
    elif "damage_at_character_level" in damage:
        levels = damage.get("damage_at_character_level", {})
        if levels:
            damage_dice = levels[min(levels.keys())]

    linhas: list[str] = [
        f"{spell['name']} ({nivel} {escola})",
        f"Casting time: {spell.get('casting_time', '')} | Range: {spell.get('range', '')} | "
        f"Duration: {spell.get('duration', '')} | Components: {componentes}",
    ]
    if damage_dice and damage_type:
        linhas.append(f"Damage: {damage_dice} {damage_type}")
    if classes:
        linhas.append(f"Classes: {classes}")
    linhas.append(desc)
    if higher:
        linhas.append(f"At higher levels: {higher}")

    return "\n".join(linha for linha in linhas if linha.strip())


def _normalizar_condition(cond: dict[str, Any]) -> str:
    desc = "\n".join(cond.get("desc", []))
    return f"{cond['name']} (condition)\n{desc}"


def _normalizar_class(cls: dict[str, Any]) -> str:
    saving_throws = _nomes(cls.get("saving_throws", []))
    proficiencies = _nomes(cls.get("proficiencies", []))
    subclasses = _nomes(cls.get("subclasses", []))

    skill_choices = ""
    for choice in cls.get("proficiency_choices", []):
        if choice.get("desc"):
            skill_choices = choice["desc"]
            break

    linhas: list[str] = [
        f"{cls['name']} (class)",
        f"Hit Die: d{cls.get('hit_die', '?')}",
        f"Saving Throws: {saving_throws}",
    ]
    if proficiencies:
        linhas.append(f"Proficiencies: {proficiencies}")
    if skill_choices:
        linhas.append(f"Skill choices: {skill_choices}")
    if subclasses:
        linhas.append(f"Subclasses: {subclasses}")

    return "\n".join(linha for linha in linhas if linha.strip())


def _normalizar_equipment(eq: dict[str, Any]) -> str:
    categoria = eq.get("equipment_category", {}).get("name", "")
    custo = eq.get("cost", {})
    custo_str = f"{custo.get('quantity', '')} {custo.get('unit', '')}".strip()
    peso = eq.get("weight", "")

    linhas: list[str] = [f"{eq['name']} ({categoria})"]

    info: list[str] = []
    if custo_str:
        info.append(f"Cost: {custo_str}")
    if peso:
        info.append(f"Weight: {peso} lb")
    if info:
        linhas.append(" | ".join(info))

    # Arma
    if eq.get("damage"):
        dmg = eq["damage"]
        dice = dmg.get("damage_dice", "")
        tipo = dmg.get("damage_type", {}).get("name", "")
        if dice or tipo:
            linhas.append(f"Damage: {dice} {tipo}".strip())

    # Armadura
    ac = eq.get("armor_class", {})
    if ac:
        base = ac.get("base", "")
        dex = " + Dex modifier" if ac.get("dex_bonus") else ""
        linhas.append(f"Armor Class: {base}{dex}")
        if eq.get("str_minimum", 0) > 0:
            linhas.append(f"Requires Strength: {eq['str_minimum']}")
        if eq.get("stealth_disadvantage"):
            linhas.append("Stealth: Disadvantage")

    # Propriedades (armas)
    props = _nomes(eq.get("properties", []))
    if props:
        linhas.append(f"Properties: {props}")

    # Alcance (armas de distância — 5ft = só corpo a corpo, não informativo)
    rng = eq.get("range", {})
    normal = rng.get("normal", 0)
    if normal and normal > 5:
        long_range = rng.get("long", "")
        linhas.append(f"Range: {normal}/{long_range} ft" if long_range else f"Range: {normal} ft")

    # Montaria / veículo
    speed = eq.get("speed", {})
    if speed:
        linhas.append(f"Speed: {speed.get('quantity', '')} {speed.get('unit', '')}")
    if eq.get("capacity"):
        linhas.append(f"Capacity: {eq['capacity']}")

    # Gear / ferramentas (tem desc[] genérico)
    desc_list = eq.get("desc", [])
    if desc_list:
        linhas.append(" ".join(desc_list))

    return "\n".join(linha for linha in linhas if linha.strip())


# Mapeamento: nome do arquivo → (source_type, função normalizadora)
_NORMALIZADORES: dict[str, tuple[str, Callable[[dict[str, Any]], str]]] = {
    "5e-SRD-Spells.json":     ("spell",     _normalizar_spell),
    "5e-SRD-Conditions.json": ("condition", _normalizar_condition),
    "5e-SRD-Classes.json":    ("class",     _normalizar_class),
    "5e-SRD-Equipment.json":  ("equipment", _normalizar_equipment),
}


def carregar_regras(srd_dir: Path = SRD_DIR_DEFAULT) -> list[ChunkRecord]:
    """
    Carrega todos os arquivos SRD do diretório e retorna lista plana de ChunkRecord.

    Args:
        srd_dir: Diretório com os arquivos 5e-SRD-*.json.

    Returns:
        Lista de ChunkRecord prontos para embedding e upsert no Qdrant.
    """
    todos: list[ChunkRecord] = []
    totais: dict[str, int] = {}

    for filename, (source_type, normalizar) in _NORMALIZADORES.items():
        caminho = srd_dir / filename
        if not caminho.exists():
            log.warning("rules_loader_arquivo_ausente", path=str(caminho))
            continue

        with caminho.open(encoding="utf-8") as f:
            entradas: list[dict[str, Any]] = json.load(f)

        count = 0
        for entrada in entradas:
            source_id: str = str(entrada.get("index", entrada.get("name", "unknown"))).lower()
            source_name: str = str(entrada.get("name", source_id))

            texto = normalizar(entrada).strip()
            if not texto:
                continue

            chunks = _dividir_em_chunks(
                texto=texto,
                source_id=source_id,
                source_name=source_name,
                source_type=source_type,
                campo="description",
            )
            todos.extend(chunks)
            count += len(chunks)

        totais[source_type] = count
        log.info(
            "rules_loader_categoria",
            tipo=source_type,
            entradas=len(entradas),
            chunks=count,
        )

    log.info("rules_loader_concluido", total=len(todos), por_tipo=totais)
    return todos
