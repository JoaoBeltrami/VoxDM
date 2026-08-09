"""
Gera a tabela MECÂNICA de magias a partir do 5e-database (artefato de build).

Por que existe: ADR-007 decidiu que resolução de magia NUNCA pode depender de
    rede. A única fonte estruturada era o Qdrant, e `buscar_dados_magia` falha
    CALADA por design — uma Bola de Fogo que não resolve porque o Qdrant piscou é
    exatamente o modo de falha que custou o playtest de 07/08 (BESTIARIO-CR-
    ERRADO-1). Este script cospe `engine/magic/spell_mechanics.py`, versionado no
    repo, no mesmo padrão de STATBLOCKS_SRD.
Dependências: nenhuma (stdlib) — lê `srd_data/5e-SRD-Spells.json`, o mesmo
    arquivo que o `rules_loader.py` já usa pra indexar no Qdrant.
Armadilha: é ARTEFATO DE BUILD. Se o 5e-database mudar e ninguém rodar isto, a
    tabela envelhece em silêncio. O teste de cobertura
    (`tests/test_spell_mechanics.py`) é o que transforma esse silêncio em falha.

Exemplo:
    uv run python -m ingestor.gerar_tabela_magias
    # → engine/magic/spell_mechanics.py (319 magias)
"""

from __future__ import annotations

import json
from pathlib import Path
from pprint import pformat
from typing import Any

_RAIZ = Path(__file__).resolve().parents[1]
_FONTE = _RAIZ / "srd_data" / "5e-SRD-Spells.json"
_DESTINO = _RAIZ / "engine" / "magic" / "spell_mechanics.py"

# Tipos de resolução — vocabulário FECHADO, mesmo princípio da tabela de CD:
# valor desconhecido não vira categoria nova, cai em "nenhum".
ATAQUE: str = "ataque"
RESISTENCIA: str = "resistencia"
NENHUM: str = "nenhum"


def _tipo_resolucao(magia: dict[str, Any]) -> str:
    """Como esta magia é resolvida mecanicamente.

    Ordem importa: uma magia com `attack_type` é um ataque do CONJURADOR (ele
    rola), enquanto `dc` é uma resistência do ALVO (a engine rola). Nenhuma magia
    do SRD tem os dois, mas a ordem deixa a precedência explícita se aparecer.
    """
    if magia.get("attack_type"):
        return ATAQUE
    if magia.get("dc"):
        return RESISTENCIA
    return NENHUM


def _dano(magia: dict[str, Any]) -> dict[str, Any]:
    """Dado de dano por nível de slot (ou por nível de personagem, em truques)."""
    dmg = magia.get("damage") or {}
    por_slot = dmg.get("damage_at_slot_level") or {}
    # Truque não gasta slot: escala pelo nível do PERSONAGEM. Guardamos os dois
    # num campo só, com `escala_por` dizendo qual chave usar na hora de olhar.
    por_nivel_pj = dmg.get("damage_at_character_level") or {}
    if not por_slot and not por_nivel_pj:
        return {}
    return {
        "tipo": ((dmg.get("damage_type") or {}) or {}).get("name", "") or "",
        "por": {str(k): str(v) for k, v in (por_slot or por_nivel_pj).items()},
        "escala_por": "slot" if por_slot else "nivel_personagem",
    }


def extrair(magia: dict[str, Any]) -> dict[str, Any]:
    """Um registro da tabela mecânica. Só o que a ENGINE usa pra calcular."""
    dc = magia.get("dc") or {}
    cura = magia.get("heal_at_slot_level") or {}
    return {
        "nome_en": str(magia.get("name") or ""),
        "nivel": int(magia.get("level") or 0),
        "escola": ((magia.get("school") or {}) or {}).get("name", "") or "",
        "resolucao": _tipo_resolucao(magia),
        # Atributo da resistência ("DEX", "WIS"…) e o que acontece em sucesso
        # ("half" = metade do dano; "none" = nada). Vazio quando não há save.
        "save_atributo": ((dc.get("dc_type") or {}) or {}).get("name", "") or "",
        "save_sucesso": str(dc.get("dc_success") or ""),
        "dano": _dano(magia),
        "cura": {str(k): str(v) for k, v in cura.items()},
        "concentracao": bool(magia.get("concentration")),
    }


def _formatar(registros: dict[str, dict[str, Any]]) -> str:
    # `pprint`, não `json.dumps`: JSON escreve `false`/`null`, que não são Python
    # válido — o módulo gerado quebrava no import. pprint emite literal Python e
    # continua legível em diff, que é metade do valor de versionar o artefato.
    corpo = pformat(registros, indent=4, width=100, sort_dicts=True)
    return f'''"""
Tabela MECÂNICA de magias do SRD 5.1 — GERADO, não edite à mão.

Por que existe: ADR-007 — resolução de magia não pode depender de rede. Estes são
    os números que a ENGINE usa pra calcular; a descrição e a nuance continuam
    vindo do Qdrant, pro prompt.
Dependências: nenhuma (dado estático, mesmo padrão de STATBLOCKS_SRD).
Armadilha: gerado por `ingestor/gerar_tabela_magias.py` a partir de
    `srd_data/5e-SRD-Spells.json`. Editar aqui é perder a mudança na próxima
    geração — mexa na FONTE ou no gerador.

Exemplo:
    from engine.magic.spell_mechanics import MECANICA_MAGIA
    MECANICA_MAGIA["fireball"]["dano"]["por"]["3"]   # → "8d6"
"""

from typing import Any, Final

#: Chave = índice do SRD (kebab-case, ex. "fireball"). Vocabulário fechado de
#: `resolucao`: "ataque" | "resistencia" | "nenhum".
MECANICA_MAGIA: Final[dict[str, dict[str, Any]]] = {corpo}

#: Junção com a lista PT-BR (`spell_list.SpellEntry.nome_en`), em minúsculas.
#: Existe como DADO gerado pra que o casamento não vire regex em runtime.
POR_NOME_EN: Final[dict[str, str]] = {{
    dados["nome_en"].lower(): indice
    for indice, dados in MECANICA_MAGIA.items()
    if dados.get("nome_en")
}}
'''


def gerar() -> int:
    """Lê a fonte, escreve o módulo. Retorna quantas magias entraram."""
    magias = json.loads(_FONTE.read_text(encoding="utf-8"))
    registros = {
        str(m["index"]): extrair(m)
        for m in magias
        if m.get("index") and m.get("name")
    }
    _DESTINO.write_text(_formatar(registros), encoding="utf-8")
    return len(registros)


if __name__ == "__main__":  # pragma: no cover — entrypoint de build
    total = gerar()
    print(f"{_DESTINO.relative_to(_RAIZ)}: {total} magias")
