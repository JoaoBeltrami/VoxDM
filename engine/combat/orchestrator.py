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
from engine.combat.narration import (
    classificar_tier,
    linha_ataque_jogador,
    linha_dano_jogador,
    linha_turno_inimigos,
)
from engine.combat.resolver import ResultadoAtaque, resolver_ataque, resolver_dano

# Dado de arma genérico quando a engine rola o dano do jogador (v1 da task 7).
# O jogador rola o d20 do ATAQUE na UI (decisão travada 19/06); o dado de DANO
# é rolado pela engine aqui pra evitar um 3º round-trip de mensagem. d8 ≈ arma
# marcial média — calibrar com a arma real no playtest/frontend (task 9).
_DADO_ARMA_PADRAO = 8


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


def resolver_turno_ataque_jogador(
    wm: Any,
    alvo_id: str,
    d20: int,
    *,
    dado_arma: int = _DADO_ARMA_PADRAO,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """Resolve um turno de combate COMPLETO do jogador, engine-autoritativo (task 7).

    Sequência (o LLM NÃO decide nem rola, só narra o resultado):
      1. ataque do jogador: d20 (da UI) + mod vs a CA do alvo;
      2. se acerta, dano: a engine rola o dado da arma + mod (crit dobra o dado);
      3. consome a AÇÃO do jogador (action economy);
      4. turno dos inimigos: cada vivo rola vs a CA do jogador, dano aplicado no PJ;
      5. avança a rodada (renova ação/bônus/movimento).

    Devolve o CONTEXTO factual em linhas "ENGINE: ..." pro Mestre narrar, mais as
    flags dos beats. PURO de IO (só muta a WM + formata texto). `valido=False`
    quando o alvo não existe ou já está morto — o caller trata como alvo inválido
    (cai no fluxo antigo). RNG injetável pra teste determinístico.
    """
    rng = rng or random.Random()
    r = resolver_ataque_do_jogador(wm, alvo_id, d20)
    if r is None:
        return {"valido": False, "contexto": ""}

    alvo = wm.inimigos_combate.get(alvo_id, {})
    nome = str(alvo.get("nome") or alvo_id)
    linhas = [linha_ataque_jogador(nome, r)]

    dano = 0
    estado = str(alvo.get("estado", ""))
    if r.acertou:
        rolado = rng.randint(1, max(2, int(dado_arma)))
        dano, estado = aplicar_dano_do_jogador(wm, alvo_id, rolado, critico=r.critico)
        linhas.append(linha_dano_jogador(nome, dano, estado))

    # Action economy: a ação do jogador foi gasta nesta rodada.
    wm.usar_acao()

    # Turno dos inimigos (engine rola vs a CA do jogador e aplica o dano no PJ).
    res_inim = executar_turno_inimigos(wm, rng)
    linhas.append(linha_turno_inimigos(res_inim))

    # Nova rodada — renova ação/bônus/movimento.
    wm.avancar_rodada()

    # XP engine-first (decisão 01/07): abate paga XP determinístico AQUI —
    # antes de fim_combate, porque sair_combate() (no caller) limpa o dict e
    # o morto sumiria sem pagar. Dedup pela flag xp_concedido.
    from engine.progression import conceder_xp_abates_pendentes
    conceder_xp_abates_pendentes(wm)

    vivos = [d for d in wm.inimigos_combate.values() if d.get("estado") != "morto"]
    fim_combate = len(vivos) == 0
    # Task 8 do roadmap original ("prosa em camadas"): sinal explícito de tier
    # pro caller instruir o Mestre a variar densidade — épico só nos momentos-
    # chave (crítico, abate, fim de combate, inimigo critando no PJ), seco no
    # resto (não precisa mais inferir da prosa das linhas ENGINE).
    tier = classificar_tier(
        critico=r.critico,
        falha_critica=r.falha_critica,
        estado_alvo=estado,
        fim_combate=fim_combate,
        ataques_inimigos=res_inim.get("ataques"),
    )
    return {
        "valido": True,
        "contexto": "\n".join(linhas),
        "acertou": r.acertou,
        "critico": r.critico,
        "falha_critica": r.falha_critica,
        "estado_alvo": estado,
        "dano": dano,
        "dano_inimigos": int(res_inim.get("dano_total", 0)),
        "hp_jogador": wm.player_hp,
        "fim_combate": fim_combate,
        "tier": tier,
    }
