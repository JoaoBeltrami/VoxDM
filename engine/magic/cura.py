"""
Cura por MAGIA resolvida pela engine — o último "quanto" que estava com o LLM.

Por que existe: `[CURA: +N]` é emitido pelo MODELO e aplicado direto no HP
    (api/turn_pipeline.py). Ou seja, quanto uma magia cura era decidido pelo LLM
    — a mesma classe do bug da poção de 01/08 ("não fui curado pela minha
    poção"), que foi consertado para ITEM e nunca para MAGIA. ADR-007, decisão 7.
Dependências: engine.magic.spell_mechanics (tabela local), engine.magic.
    salvaguarda (atributo de conjuração), engine.combat.enemy_turn.rolar_dado.
Armadilha: `[CURA:]` NÃO morre. Ele sobrevive para cura NÃO-mecânica — uma erva,
    um NPC que socorre, um descanso improvisado. A origem decide o dono, igual ao
    "conceder × consumir item": veio da ficha, é tabela; veio da ficção, é do
    Mestre. Quem cuida de não somar duas vezes é o caller.

Exemplo:
    r = resolver_cura_de_magia(wm, "Curar Ferimentos", nome_en="Cure Wounds")
    r["contexto"]   # → "ENGINE: Curar Ferimentos restaura 7 PV..."
"""

from __future__ import annotations

import random
import re
from typing import Any

from engine.combat.enemy_turn import rolar_dado
from engine.magic.resolucao import mecanica_da_magia
from engine.magic.salvaguarda import atributo_de_conjuracao

# "1d8 + MOD" — o SRD escreve o modificador de conjuração como literal `MOD`.
_RE_CURA_DADO = re.compile(r"(\d+d\d+)(?:\s*\+\s*MOD)?", re.IGNORECASE)


def _formula_de_cura(mecanica: dict[str, Any], nivel_slot: int) -> str:
    """A string de cura para este slot ("1d8 + MOD"). "" quando a magia não cura.

    Algumas magias trazem uma fórmula única; outras, uma por nível de slot
    (`Oração de Cura` começa no 2). Slot abaixo do mínimo cai no menor degrau —
    é o mesmo tratamento que o dano recebe.
    """
    cura = mecanica.get("cura") or {}
    if not cura:
        return ""
    niveis = sorted(int(k) for k in cura if str(k).isdigit())
    if not niveis:
        return ""
    alvo = max(niveis[0], min(int(nivel_slot or niveis[0]), niveis[-1]))
    return str(cura.get(str(alvo), ""))


def resolver_cura_de_magia(
    wm: Any,
    nome_pt: str,
    *,
    nome_en: str = "",
    nivel_slot: int = 0,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Rola e aplica a cura de uma magia no PRÓPRIO jogador. None se não cura.

    O `+ MOD` do SRD é o modificador do atributo de CONJURAÇÃO da classe — não o
    melhor atributo. Um clérigo cura por Sabedoria mesmo com Carisma alto, pelo
    mesmo motivo que a CD de magia usa o atributo da classe (passo 4).

    Respeita o teto de HP (quem clampa é `PlayerCharacter.aplicar_cura`) e
    registra o evento vital, pra que a cura apareça na tela como já aparece o
    dano — a engine sabendo e o jogador não é o bug que originou tudo isto.
    """
    mecanica = mecanica_da_magia(nome_pt, nome_en)
    if not mecanica:
        return None
    formula = _formula_de_cura(mecanica, nivel_slot or int(mecanica.get("nivel", 0) or 0))
    if not formula:
        return None

    m = _RE_CURA_DADO.search(formula)
    if not m:
        return None

    rng = rng or random.Random()
    attr = atributo_de_conjuracao(getattr(wm, "player_class", ""))
    mod = int(getattr(wm.character, f"mod_{attr}", 0) or 0)
    rolado = rolar_dado(m.group(1), rng)
    # O modificador só entra quando a fórmula do SRD pede ("+ MOD"). Magia de
    # cura em área costuma não somar, e somar por hábito inflaria a cura.
    total = rolado + (mod if "MOD" in formula.upper() else 0)
    total = max(0, total)

    antes = int(wm.player_hp)
    depois = wm.character.aplicar_cura(total)
    curado = max(0, int(depois) - antes)
    wm.character.registrar_evento_vital(
        "cura", curado, nome_pt, int(depois), int(wm.player_hp_max)
    )

    if curado <= 0:
        contexto = (
            f"ENGINE: {nome_pt} é conjurada, mas o alvo já está com PV cheio. "
            "Narre o gesto sem inventar efeito."
        )
    else:
        contexto = (
            f"ENGINE: {nome_pt} restaura {curado} PV. "
            "Narre o alívio, não o número."
        )

    return {
        "valido": True,
        "magia": nome_pt,
        "rolado": rolado,
        "modificador": mod if "MOD" in formula.upper() else 0,
        "curado": curado,
        "hp": int(depois),
        "contexto": contexto,
    }
