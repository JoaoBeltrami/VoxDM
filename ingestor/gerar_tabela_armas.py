"""
Gera `engine/combat/weapon_table.py` — arma → atributo de ataque e dado de dano.

Por que existe: no playtest de 10/08 o Mestre pediu *"ataque com Força"* para um
    Ranger que atacava por Destreza. A ficha do projeto não tinha conceito de arma
    NENHUM — `mod_ataque` devolvia `max()` de todos os atributos, o que acerta o
    número por acidente e não permite NOMEAR o atributo. Sem nome, quem anuncia é
    o modelo, por vibe.
Dependências: `srd_data/5e-SRD-Equipment.json` (mesmo padrão do gerador de magias).
Armadilha: `json.dumps` NÃO serve para gerar módulo Python — escreve `false`/`null`
    e o artefato quebra no import. Usar `pprint.pformat`. (Mordeu no gerador de
    magias em 09/08.)

Exemplo:
    uv run python ingestor/gerar_tabela_armas.py
    # → engine/combat/weapon_table.py: 37 armas
"""

import json
import pprint
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parents[1]
_FONTE = _RAIZ / "srd_data" / "5e-SRD-Equipment.json"
_DESTINO = _RAIZ / "engine" / "combat" / "weapon_table.py"

# Nome PT-BR das armas que o jogador realmente fala na mesa. O SRD é em inglês e
# a transcrição de voz chega em português — sem esta ponte a tabela é inútil no
# único idioma em que o jogo é jogado. Só as comuns; o resto casa pelo nome EN.
_PT: dict[str, tuple[str, ...]] = {
    "longbow": ("arco longo", "arco"),
    "shortbow": ("arco curto",),
    # BESTA-SEM-NOME-1 (17/08): estas três chaves eram "light-crossbow",
    # "heavy-crossbow" e "hand-crossbow" — e o índice do SRD é "crossbow-light",
    # "crossbow-heavy", "crossbow-hand". `_PT.get(idx, ())` devolvia vazio e as
    # três bestas ficaram SEM nome em português na tabela, caladas, desde que o
    # gerador nasceu. "Besta leve" é equipamento inicial de Clérigo, Bruxo e
    # Guerreiro: o jogador dizia "atiro com a besta" e a engine não achava a arma.
    # Mesma família do `utilizar` que não conjurava e do `clerigo` sem acento.
    "crossbow-light": ("besta leve", "besta"),
    "crossbow-heavy": ("besta pesada",),
    "crossbow-hand": ("besta de mão",),
    "dagger": ("adaga", "punhal"),
    "rapier": ("rapieira", "florete"),
    "shortsword": ("espada curta",),
    "longsword": ("espada longa", "espada"),
    "greatsword": ("espada grande", "montante"),
    "scimitar": ("cimitarra",),
    "handaxe": ("machadinha",),
    "battleaxe": ("machado de batalha", "machado"),
    "greataxe": ("machado grande",),
    "warhammer": ("martelo de guerra", "martelo"),
    "mace": ("maça",),
    "quarterstaff": ("bordão", "cajado"),
    "spear": ("lança",),
    "javelin": ("azagaia",),
    "club": ("clava", "porrete"),
    "sling": ("funda",),
    "whip": ("chicote",),
    "trident": ("tridente",),
    "glaive": ("glaive",),
    "halberd": ("alabarda",),
    "pike": ("pique",),
    "sickle": ("foice",),
    "flail": ("mangual",),
    # NOME-EM-INGLES-1 (17/08): estas nove nunca tiveram ponte e apareciam em
    # INGLÊS na ficha assim que o seletor de arma passou a listá-las — "Blowgun"
    # e "Morningstar" no meio de uma ficha em português. Pior que feio: sem nome
    # PT, `identificar_arma` não casa a fala do jogador ("jogo a rede nele") e a
    # arma não existe para a engine.
    "blowgun": ("zarabatana",),
    "dart": ("dardo",),
    "greatclub": ("clava grande",),
    "lance": ("lança montada", "lança de cavalaria"),
    "light-hammer": ("martelo leve",),
    "maul": ("malho", "marreta"),
    "morningstar": ("estrela matinal",),
    "net": ("rede",),
    "war-pick": ("picareta de guerra", "picareta"),
}


def _atributo(arma: dict[str, Any]) -> str:
    """"DES" | "FOR" | "MELHOR" — o vocabulário é FECHADO.

    Regra do SRD: arma à distância usa Destreza; corpo a corpo usa Força; e
    `finesse` deixa o jogador ESCOLHER, que é o "MELHOR" — não é um atributo, é
    uma licença, e tratá-lo como atributo fixo puniria metade das fichas.
    """
    props = {p.get("index") for p in (arma.get("properties") or [])}
    if "finesse" in props:
        return "MELHOR"
    if str(arma.get("weapon_range") or "").lower() == "ranged":
        return "DES"
    return "FOR"


def _dado(arma: dict[str, Any]) -> str:
    return str(((arma.get("damage") or {}).get("damage_dice")) or "1d4")


def _categoria(arma: dict[str, Any]) -> str:
    """"simples" | "marcial" — o vocabulário é FECHADO, como o de `_atributo`.

    Por que existe (P18 frente A, 17/08): as escolhas de equipamento do SRD dizem
    "uma arma marcial" e deixam o jogador nomear qual. Sem esta classificação, a
    ficha só podia oferecer um campo de texto livre — e texto livre num campo que
    vira NOME DE ITEM é como o inventário ganha "espada" que nenhuma tabela acha
    depois. Com ela, a ficha oferece exatamente as armas válidas.

    Fonte é o `weapon_category` do SRD (Simple/Martial), não uma lista à mão: a
    lista à mão é a duplicação que este projeto já pagou caro várias vezes.
    """
    return "marcial" if str(arma.get("weapon_category") or "").lower() == "martial" else "simples"


def main() -> None:
    dados = json.loads(_FONTE.read_text(encoding="utf-8"))
    armas = [
        e for e in dados
        if (e.get("equipment_category") or {}).get("index") == "weapon"
    ]
    tabela: dict[str, dict[str, Any]] = {}
    for a in armas:
        idx = str(a.get("index") or "")
        tabela[idx] = {
            "nome_en": str(a.get("name") or ""),
            "atributo": _atributo(a),
            "categoria": _categoria(a),
            "dado": _dado(a),
            "distancia": str(a.get("weapon_range") or "").lower() == "ranged",
            "nomes_pt": list(_PT.get(idx, ())),
        }
    corpo = (
        '"""\nArma → atributo de ataque e dado de dano (SRD 5.1).\n\n'
        "GERADO por `ingestor/gerar_tabela_armas.py` — NÃO editar à mão.\n"
        "Existe porque a ficha não tinha conceito de arma, e sem ele o Mestre\n"
        "anunciava o atributo do ataque por vibe (playtest 10/08: pediu Força a\n"
        "um Ranger de arco).\n\n"
        "`categoria` (simples/marcial) entrou em 17/08 para a ficha poder OFERECER\n"
        "as armas válidas de uma escolha do SRD em vez de pedir texto livre.\n"
        '"""\n\n'
        "from typing import Any\n\n"
        "ARMAS: dict[str, dict[str, Any]] = "
        + pprint.pformat(tabela, width=100, sort_dicts=True)
        + "\n"
    )
    _DESTINO.write_text(corpo, encoding="utf-8")
    print(f"{_DESTINO.relative_to(_RAIZ)}: {len(tabela)} armas")


if __name__ == "__main__":
    main()
