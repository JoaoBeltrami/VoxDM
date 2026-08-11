"""
Gera `engine/state/equipamento_inicial.py` — o que cada classe começa carregando.

Por que existe: decisão do Beltrami em 11/08 — *"o jogador só deve conseguir
    utilizar itens que estão no seu inventário, então a criação de personagem
    deve oferecer as coisas básicas que estão no SRD"*. Sem isto, cobrar o
    inventário seria punição pura: o personagem nascia com a mochila VAZIA, e
    qualquer uso de item viraria recusa.
Dependências: `srd_data/5e-SRD-Classes.json`.
Armadilha: só o `starting_equipment` FIXO entra aqui. O SRD também tem
    `starting_equipment_options` ("escolha uma arma marcial"), e escolher pelo
    jogador seria decidir a build dele — isso é UI de criação, e portanto gosto
    do Beltrami. Fica declarado como pendência, não resolvido em silêncio.

Exemplo:
    uv run python ingestor/gerar_equipamento_inicial.py
    # → engine/state/equipamento_inicial.py: 12 classes
"""

import json
import pprint
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parents[1]
_FONTE = _RAIZ / "srd_data" / "5e-SRD-Classes.json"
_DESTINO = _RAIZ / "engine" / "state" / "equipamento_inicial.py"

# Os 11 itens fixos do SRD inteiro, traduzidos à mão. Lista pequena de propósito:
# tradução automática de nome de equipamento inventaria termo, e o inventário é
# comparado por NOME — um termo errado aqui vira item que ninguém acha.
_PT: dict[str, str] = {
    "Arrow": "Flecha",
    "Chain Mail": "Cota de malha",
    "Dagger": "Adaga",
    "Dart": "Dardo",
    "Explorer's Pack": "Mochila de explorador",
    "Javelin": "Azagaia",
    "Leather Armor": "Armadura de couro",
    "Longbow": "Arco longo",
    "Shield": "Escudo",
    "Spellbook": "Grimório",
    "Thieves' Tools": "Ferramentas de ladrão",
}

# Nome canônico da classe em PT-BR — o mesmo de `engine/chargen.py`.
_CLASSE_PT: dict[str, str] = {
    "barbarian": "Bárbaro", "bard": "Bardo", "cleric": "Clérigo",
    "druid": "Druida", "fighter": "Guerreiro", "monk": "Monge",
    "paladin": "Paladino", "ranger": "Ranger", "rogue": "Ladino",
    "sorcerer": "Feiticeiro", "warlock": "Bruxo", "wizard": "Mago",
}


def main() -> None:
    dados = json.loads(_FONTE.read_text(encoding="utf-8"))
    tabela: dict[str, list[dict[str, Any]]] = {}
    faltando: set[str] = set()

    for classe in dados:
        pt = _CLASSE_PT.get(str(classe.get("index") or ""))
        if not pt:
            continue
        itens: list[dict[str, Any]] = []
        for entrada in classe.get("starting_equipment") or []:
            nome_en = str((entrada.get("equipment") or {}).get("name") or "")
            if not nome_en:
                continue
            if nome_en not in _PT:
                faltando.add(nome_en)
                continue
            itens.append({
                "nome": _PT[nome_en],
                "quantidade": int(entrada.get("quantity") or 1),
            })
        tabela[pt] = itens

    if faltando:
        # Grita: item sem tradução some do inventário inicial, e some CALADO —
        # a classe nasceria mais pobre do que o SRD manda sem ninguém notar.
        raise SystemExit(f"itens sem tradução em _PT: {sorted(faltando)}")

    corpo = (
        '"""\nEquipamento inicial por classe (SRD 5.1).\n\n'
        "GERADO por `ingestor/gerar_equipamento_inicial.py` — NÃO editar à mão.\n"
        "Só o equipamento FIXO. As opções de escolha do SRD ('escolha uma arma\n"
        "marcial') NÃO entram: escolher pelo jogador seria decidir a build dele.\n"
        '"""\n\n'
        "from typing import Any\n\n"
        "EQUIPAMENTO_INICIAL: dict[str, list[dict[str, Any]]] = "
        + pprint.pformat(tabela, width=100, sort_dicts=True)
        + "\n"
    )
    _DESTINO.write_text(corpo, encoding="utf-8")
    print(f"{_DESTINO.relative_to(_RAIZ)}: {len(tabela)} classes")


if __name__ == "__main__":
    main()
