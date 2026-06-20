"""
Turno dos inimigos autoritativo (task 4, motor de combate engine-autoritativo).

Por que existe: a decisão de 19/06 ([[roadmap_combate_engine]]) é que o turno dos
    inimigos é da ENGINE — ela rola o ataque (d20 + bônus) vs a CA do jogador e
    aplica o dano, em vez de pedir `[DANO]` ao LLM (que errava). Esta função é o
    miolo: recebe os inimigos + a CA do jogador + um RNG e devolve o resultado
    mecânico de cada ataque. A aplicação no HP do jogador e a narração são de quem
    chama (task 7 no websocket).
Dependências: engine.combat.resolver, engine.combat.stats.
Armadilha: RNG é injetável (`rng`) — em teste passe um determinístico; em
    produção, `random.Random()`. Inimigo morto não ataca.

Exemplo:
    res = resolver_turno_inimigos(inimigos, player_ca=15, rng=random.Random(1))
    # → {"dano_total": 5, "ataques": [{"id": "g1", "acertou": True, "dano": 5, ...}]}
"""

import random
import re
from typing import Any

from engine.combat.resolver import resolver_ataque, resolver_dano
from engine.combat.stats import stats_inimigo

_RE_DADO = re.compile(r"(\d+)d(\d+)")


def rolar_dado(dado_str: str, rng: random.Random) -> int:
    """Rola 'NdM' com o RNG dado. Retorna 0 se a string não casar."""
    m = _RE_DADO.search(dado_str or "")
    if not m:
        return 0
    n, faces = int(m.group(1)), int(m.group(2))
    if n <= 0 or faces <= 0:
        return 0
    return sum(rng.randint(1, faces) for _ in range(n))


def resolver_turno_inimigos(
    inimigos_combate: dict[str, dict[str, Any]],
    player_ca: int,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Resolve o ataque de cada inimigo vivo contra a CA do jogador.

    Para cada inimigo vivo: stats (ficha SRD ou default) → rola d20 + atk vs CA →
    se acerta, rola o dano. Acumula `dano_total`. Não muta o estado — devolve só
    o resultado pra quem aplica (websocket).
    """
    rng = rng or random.Random()
    ataques: list[dict[str, Any]] = []
    dano_total = 0
    for iid, dados in inimigos_combate.items():
        if dados.get("estado") == "morto":
            continue
        stats = stats_inimigo(ficha=str(dados.get("ficha", "")), nome=str(dados.get("nome", iid)))
        d20 = rng.randint(1, 20)
        res = resolver_ataque(d20, stats.atk_bonus, player_ca)
        dano = 0
        if res.acertou:
            rolado = rolar_dado(stats.dano_dado, rng)
            dano = resolver_dano(rolado, stats.dano_bonus, critico=res.critico)
            dano_total += dano
        ataques.append({
            "id": iid,
            "nome": dados.get("nome", iid),
            "d20": d20,
            "acertou": res.acertou,
            "critico": res.critico,
            "dano": dano,
        })
    return {"dano_total": dano_total, "ataques": ataques}
