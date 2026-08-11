"""
Gera `engine/state/escolhas_iniciais.py` — as ESCOLHAS de equipamento do SRD.

Por que existe: pedido do Beltrami em 11/08 — oferecer as opções de equipamento
    do SRD tanto na criação por ficha quanto por voz. O equipamento FIXO já
    entrava (`equipamento_inicial.py`); o que faltava eram as escolhas, e é
    delas que vem TODO o equipamento do Guerreiro — a classe mais simples do
    jogo nascia de mãos abanando.
Dependências: `srd_data/5e-SRD-Classes.json` + `5e-SRD-Equipment.json`.
Armadilha: o formato de saída serve DOIS consumidores com necessidades opostas —
    a ficha precisa de itens para renderizar botões, e a VOZ precisa de uma frase
    curta para o Mestre ler. Por isso cada opção carrega `rotulo` (a frase) E
    `itens` (o efeito). Gerar só um dos dois obrigaria um dos caminhos a
    reconstruir o outro, e é assim que os dois divergem.

    Opção de CATEGORIA ("uma arma marcial à sua escolha") não vira lista de 18
    armas: ela sai com `categoria` preenchida e `itens` vazio. Despejar 18 nomes
    numa pergunta falada seria ilegível, e a ficha resolve melhor com um seletor.

Exemplo:
    uv run python ingestor/gerar_escolhas_iniciais.py
    # → engine/state/escolhas_iniciais.py: 12 classes, 39 escolhas
"""

import json
import pprint
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parents[1]
_CLASSES = _RAIZ / "srd_data" / "5e-SRD-Classes.json"
_DESTINO = _RAIZ / "engine" / "state" / "escolhas_iniciais.py"

# Os 29 itens que aparecem nas escolhas, traduzidos à mão. Mesma razão do
# gerador de equipamento fixo: tradução automática inventa termo, e o inventário
# é comparado por NOME — termo errado vira item que ninguém acha.
_PT: dict[str, str] = {
    "Arrow": "Flecha", "Burglar's Pack": "Mochila de gatuno",
    "Chain Mail": "Cota de malha", "Component pouch": "Bolsa de componentes",
    "Crossbow bolt": "Virote de besta", "Crossbow, light": "Besta leve",
    "Dagger": "Adaga", "Diplomat's Pack": "Mochila de diplomata",
    "Dungeoneer's Pack": "Mochila de masmorra",
    "Entertainer's Pack": "Mochila de artista",
    "Explorer's Pack": "Mochila de explorador", "Greataxe": "Machado grande",
    "Handaxe": "Machadinha", "Javelin": "Azagaia",
    "Leather Armor": "Armadura de couro", "Longbow": "Arco longo",
    "Longsword": "Espada longa", "Lute": "Alaúde", "Mace": "Maça",
    "Priest's Pack": "Mochila de sacerdote", "Quarterstaff": "Bordão",
    "Rapier": "Rapieira", "Scale Mail": "Cota de escamas",
    "Scholar's Pack": "Mochila de estudioso", "Scimitar": "Cimitarra",
    "Shield": "Escudo", "Shortbow": "Arco curto", "Shortsword": "Espada curta",
    "Warhammer": "Martelo de guerra",
}

# As 8 categorias, em frase que cabe numa pergunta falada.
_CATEGORIA_PT: dict[str, str] = {
    "Arcane Foci": "um foco arcano",
    "Druidic Foci": "um foco druídico",
    "Holy Symbols": "um símbolo sagrado",
    "Martial Melee Weapons": "uma arma marcial corpo a corpo",
    "Martial Weapons": "uma arma marcial",
    "Musical Instruments": "um instrumento musical",
    "Simple Melee Weapons": "uma arma simples corpo a corpo",
    "Simple Weapons": "uma arma simples",
}

_CLASSE_PT: dict[str, str] = {
    "barbarian": "Bárbaro", "bard": "Bardo", "cleric": "Clérigo",
    "druid": "Druida", "fighter": "Guerreiro", "monk": "Monge",
    "paladin": "Paladino", "ranger": "Ranger", "rogue": "Ladino",
    "sorcerer": "Feiticeiro", "warlock": "Bruxo", "wizard": "Mago",
}

_faltando: set[str] = set()


def _item(no: dict[str, Any]) -> dict[str, Any] | None:
    nome_en = str((no.get("of") or {}).get("name") or "")
    if not nome_en:
        return None
    if nome_en not in _PT:
        _faltando.add(nome_en)
        return None
    return {"nome": _PT[nome_en], "quantidade": int(no.get("count") or 1)}


def _categoria(no: dict[str, Any]) -> str:
    """Frase PT-BR da categoria, ou "" se o nó não for de categoria."""
    fonte = (no.get("choice") or {}).get("from") or no.get("from") or {}
    nome = str((fonte.get("equipment_category") or {}).get("name") or "")
    if not nome:
        return ""
    if nome not in _CATEGORIA_PT:
        _faltando.add(f"[categoria] {nome}")
        return ""
    return _CATEGORIA_PT[nome]


def _opcao(no: dict[str, Any]) -> dict[str, Any] | None:
    """Uma alternativa da escolha: `rotulo` (o que se fala) + `itens` (o efeito)."""
    tipo = str(no.get("option_type") or "")

    if tipo == "counted_reference":
        it = _item(no)
        if not it:
            return None
        rotulo = it["nome"] if it["quantidade"] == 1 else f"{it['nome']} ×{it['quantidade']}"
        return {"rotulo": rotulo, "itens": [it], "categoria": ""}

    if tipo == "multiple":
        itens = [x for x in (_item(i) for i in no.get("items", [])) if x]
        # Pacote com categoria dentro ("uma arma marcial e um escudo"): a parte
        # concreta vai em `itens`, a aberta em `categoria`.
        cat = next((c for c in (_categoria(i) for i in no.get("items", [])) if c), "")
        if not itens and not cat:
            return None
        partes = [i["nome"] if i["quantidade"] == 1 else f"{i['nome']} ×{i['quantidade']}"
                  for i in itens]
        if cat:
            partes.append(cat)
        return {"rotulo": ", ".join(partes), "itens": itens, "categoria": cat}

    if tipo == "choice":
        cat = _categoria(no)
        return {"rotulo": cat, "itens": [], "categoria": cat} if cat else None

    return None


def main() -> None:
    classes = json.loads(_CLASSES.read_text(encoding="utf-8"))
    tabela: dict[str, list[dict[str, Any]]] = {}
    total = 0

    for classe in classes:
        pt = _CLASSE_PT.get(str(classe.get("index") or ""))
        if not pt:
            continue
        escolhas: list[dict[str, Any]] = []
        for bruta in classe.get("starting_equipment_options") or []:
            fonte = bruta.get("from") or {}
            if fonte.get("option_set_type") == "options_array":
                opcoes = [o for o in (_opcao(x) for x in fonte.get("options", [])) if o]
            else:
                cat = _categoria(bruta)
                opcoes = [{"rotulo": cat, "itens": [], "categoria": cat}] if cat else []
            if not opcoes:
                continue
            escolhas.append({
                "escolher": int(bruta.get("choose") or 1),
                "opcoes": opcoes,
            })
            total += 1
        tabela[pt] = escolhas

    if _faltando:
        raise SystemExit(f"sem tradução: {sorted(_faltando)}")

    corpo = (
        '"""\nEscolhas de equipamento inicial por classe (SRD 5.1).\n\n'
        "GERADO por `ingestor/gerar_escolhas_iniciais.py` — NÃO editar à mão.\n\n"
        "Cada opção traz `rotulo` (a frase que o Mestre LÊ em voz alta e que a\n"
        "ficha mostra no botão) e `itens` (o efeito no inventário). Opção de\n"
        "CATEGORIA traz `categoria` preenchida e `itens` vazio: 'uma arma\n"
        "marcial' não vira uma lista de 18 nomes numa pergunta falada.\n"
        '"""\n\n'
        "from typing import Any\n\n"
        "ESCOLHAS_INICIAIS: dict[str, list[dict[str, Any]]] = "
        + pprint.pformat(tabela, width=100, sort_dicts=True)
        + "\n"
    )
    _DESTINO.write_text(corpo, encoding="utf-8")
    print(f"{_DESTINO.relative_to(_RAIZ)}: {len(tabela)} classes, {total} escolhas")


if __name__ == "__main__":
    main()
