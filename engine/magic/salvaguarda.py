"""
Resolve a RESISTÊNCIA a uma magia: quem rola é o ALVO, e quem rola é a engine.

Por que existe: é o inverso do ataque de magia (P16 passo 3). Ali o jogador rola
    o d20 na UI porque o ataque é dele; aqui quem resiste é o inimigo, então a
    rolagem é da engine. ADR-007, decisão 3.
Dependências: engine.combat.enemy_turn.rolar_dado, engine.combat.resolver
    (matemática já testada — esta camada não reimplementa),
    engine.magic.spell_mechanics (tabela local, sem rede).
Armadilha: `StatsInimigo` NÃO tem atributos — não há DES nem CON para somar na
    resistência. O inimigo rola d20 PURO, que é a mesma decisão já travada na
    iniciativa ("inimigo sem DES rola puro"). Inventar um modificador seria
    número sem lastro no SRD, e o projeto já pagou caro por isso.

Exemplo:
    r = resolver_resistencia(wm, "Bola de Fogo", "goblin-1", nome_en="Fireball")
    r["contexto"]   # → "ENGINE: Goblin resiste a Bola de Fogo (CD 13) — metade..."
"""

from __future__ import annotations

import random
from typing import Any

from engine.combat.enemy_turn import rolar_dado
from engine.magic.resolucao import _TIPO_DANO_PT, _dado_de_dano, mecanica_da_magia

# Atributo de conjuração por classe (SRD 5.1). Não existia no repo — a CD de
# magia depende dele, e derivar do "melhor modificador" (como `mod_ataque` faz)
# seria errado aqui: um clérigo com CAR alto teria CD de Carisma.
_ATRIBUTO_CONJURACAO: dict[str, str] = {
    "mago": "int", "artifice": "int", "artífice": "int",
    "clerigo": "sab", "clérigo": "sab", "druida": "sab", "ranger": "sab",
    "patrulheiro": "sab",
    "bardo": "car", "feiticeiro": "car", "bruxo": "car", "paladino": "car",
}
_ATRIBUTO_PADRAO = "sab"

# Metade do dano em sucesso, quando a magia diz "half" (SRD).
_SUCESSO_METADE = "half"


def atributo_de_conjuracao(classe: str) -> str:
    """'sab' | 'int' | 'car' pela classe. Cai no padrão quando desconhecida."""
    return _ATRIBUTO_CONJURACAO.get(str(classe or "").strip().lower(), _ATRIBUTO_PADRAO)


def cd_de_magia(wm: Any) -> int:
    """CD da magia do jogador: 8 + proficiência + mod do atributo de conjuração."""
    c = wm.character
    attr = atributo_de_conjuracao(getattr(wm, "player_class", ""))
    mod = int(getattr(c, f"mod_{attr}", 0) or 0)
    return 8 + int(c.prof_bonus) + mod


def resolver_resistencia(
    wm: Any,
    nome_pt: str,
    alvo_id: str,
    *,
    nome_en: str = "",
    nivel_slot: int = 0,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Resolve uma magia de RESISTÊNCIA contra um inimigo. None se não se aplica.

    O alvo rola d20 puro contra a CD do conjurador. Passou: metade do dano se a
    magia diz "half", nada se diz "none". Falhou: dano cheio.

    Devolve None (sem levantar) quando a magia não está na tabela, não é de
    resistência, ou o alvo não existe/morreu — o turno segue no fluxo antigo.
    """
    mecanica = mecanica_da_magia(nome_pt, nome_en)
    if not mecanica or mecanica.get("resolucao") != "resistencia":
        return None
    alvo = (getattr(wm, "inimigos_combate", {}) or {}).get(alvo_id)
    if not alvo or alvo.get("estado") == "morto":
        return None

    rng = rng or random.Random()
    cd = cd_de_magia(wm)
    # d20 PURO: o inimigo não tem atributos na ficha (ver armadilha no topo).
    d20 = rng.randint(1, 20)
    resistiu = d20 >= cd

    dado = _dado_de_dano(
        mecanica,
        nivel_pj=int(getattr(wm, "player_level", 1) or 1),
        nivel_slot=int(nivel_slot or mecanica.get("nivel", 0) or 0),
    )
    bruto = rolar_dado(dado, rng) if dado else 0
    meia_em_sucesso = str(mecanica.get("save_sucesso") or "").lower() == _SUCESSO_METADE

    if resistiu:
        dano = bruto // 2 if meia_em_sucesso else 0
    else:
        dano = bruto

    estado = str(alvo.get("estado", ""))
    if dano > 0:
        estado = wm.aplicar_dano_inimigo(alvo_id, dano)

    nome_alvo = str(alvo.get("nome") or alvo_id)
    atributo = str(mecanica.get("save_atributo") or "").upper()
    if resistiu:
        cauda = (
            f"aguenta metade — {dano} de dano" if meia_em_sucesso and dano
            else "escapa sem dano"
        )
        contexto = (
            f"ENGINE: {nome_alvo} RESISTE a {nome_pt} (salvaguarda de {atributo}) "
            f"e {cauda}. Narre o esquivo, não a rolagem."
        )
    else:
        tipo = _TIPO_DANO_PT.get(
            str((mecanica.get("dano") or {}).get("tipo") or "").lower(), ""
        )
        contexto = (
            f"ENGINE: {nome_alvo} FALHA a salvaguarda de {atributo} contra "
            f"{nome_pt} — {dano} de dano{(' ' + tipo) if tipo else ''}. "
            "Narre o efeito, não o número."
        )

    return {
        "valido": True,
        "magia": nome_pt,
        "alvo": alvo_id,
        "resistiu": resistiu,
        "cd": cd,
        "d20_alvo": d20,
        "dano": dano,
        "estado_alvo": estado,
        "contexto": contexto,
    }
