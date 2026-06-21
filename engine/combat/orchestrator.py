"""
Orquestração de um turno de combate — a cola entre os primitivos e o WebSocket.

Por que existe: resolver/stats/enemy_turn/turn_control/HP são primitivos puros e
    testados. Esta camada os SEQUENCIA num turno do jeito que a engine é autoridade
    (decisão 19/06): o jogador rola o ataque → a engine resolve vs a CA do alvo
    (somando o mod do jogador) → rola o dano → aplica no HP do inimigo; e o turno
    dos inimigos resolve contra a CA do jogador, aplicando o dano no PJ. O WS
    (task 7, validada no playtest) só chama estas funções no fluxo das mensagens —
    sem reimplementar a matemática. Quem extrai o alvo do texto e guarda o estado
    "aguardando rolagem" é o WS (acoplado ao formato do fluxo, que o playtest calibra).
Dependências: engine.combat.resolver, engine.combat.enemy_turn, WorkingMemory.
Armadilha: estas funções MUTAM a WorkingMemory (HP de inimigo e do jogador). Alvo
    inexistente ou morto é no-op seguro.

Exemplo:
    r = resolver_ataque_do_jogador(wm, "g1", d20=15)   # vs CA do g1, + mod do jogador
    if r and r.acertou:
        dano, estado = aplicar_dano_do_jogador(wm, "g1", dado_dano=5, critico=r.critico)
    res = executar_turno_inimigos(wm)                   # inimigos batem no PJ
"""

import random
from typing import Any

from engine.combat.enemy_turn import resolver_turno_inimigos
from engine.combat.resolver import ResultadoAtaque, resolver_ataque, resolver_dano


def resolver_ataque_do_jogador(wm: Any, alvo_id: str, d20: int) -> ResultadoAtaque | None:
    """Resolve o ataque do jogador (d20 + mod de ataque) vs a CA do alvo.

    Retorna o ResultadoAtaque, ou None se o alvo não existe ou já está morto.
    """
    alvo = wm.inimigos_combate.get(alvo_id)
    if not alvo or alvo.get("estado") == "morto":
        return None
    ca = int(alvo.get("ca", 12))  # default se o inimigo ainda não tem stats aplicados
    return resolver_ataque(d20, wm.mod_ataque(), ca)


def aplicar_dano_do_jogador(
    wm: Any, alvo_id: str, dado_dano: int, critico: bool = False
) -> tuple[int, str]:
    """Aplica o dano do jogador (dado + mod de dano) no HP do alvo.

    Retorna (dano_aplicado, novo_estado_narrativo). (0, "") se alvo inválido/morto.
    """
    alvo = wm.inimigos_combate.get(alvo_id)
    if not alvo or alvo.get("estado") == "morto":
        return 0, ""
    dano = resolver_dano(dado_dano, wm.mod_dano(), critico=critico)
    estado = wm.aplicar_dano_inimigo(alvo_id, dano)
    return dano, estado


def executar_turno_inimigos(wm: Any, rng: random.Random | None = None) -> dict[str, Any]:
    """Resolve o turno dos inimigos vs a CA do jogador e aplica o dano total no PJ.

    Retorna o resumo de `resolver_turno_inimigos` acrescido de `hp_jogador` (o HP
    do personagem depois do dano). O dano no PJ usa o clamp do PlayerCharacter.
    """
    res = resolver_turno_inimigos(wm.inimigos_combate, wm.ca, rng=rng)
    if res.get("dano_total", 0) > 0:
        wm.character.aplicar_dano(res["dano_total"])
    res["hp_jogador"] = wm.player_hp
    return res
