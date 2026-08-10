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
from engine.combat.morte import estado_de_morte, falha_por_golpe, linha_de_morte
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


def resolver_ataque_do_jogador(
    wm: Any, alvo_id: str, d20: int, *, mod_ataque: int | None = None
) -> ResultadoAtaque | None:
    """Resolve o ataque do jogador (d20 + mod de ataque) vs a CA do alvo.

    Retorna o ResultadoAtaque, ou None se o alvo não existe ou já está morto.

    MOD-ARMA-1 (10/08): `mod_ataque` permite ao caller passar o modificador
    derivado da ARMA (arco → DES, espada grande → FOR, finesse → o melhor). Sem
    ele o comportamento é o antigo — `wm.mod_ataque()`, o melhor atributo de
    todos — que acerta o número por acidente mas não sabe NOMEAR o atributo, e
    era por isso que o Mestre pedia Força a um Ranger de arco.
    """
    alvo = wm.inimigos_combate.get(alvo_id)
    if not alvo or alvo.get("estado") == "morto":
        return None
    ca = int(alvo.get("ca", 12))  # default se o inimigo ainda não tem stats aplicados
    mod = wm.mod_ataque() if mod_ataque is None else int(mod_ataque)
    return resolver_ataque(d20, mod, ca)


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
    res = resolver_turno_inimigos(
        wm.inimigos_combate, wm.ca, rng=rng, ordem=ordem_de_iniciativa(wm),
    )
    # MORTE-SEM-DESFECHO-1 (10/08, pedido do Beltrami: *"se o inimigo finalizar o
    # jogador é morte mesmo"*). Golpe que acerta quem JÁ está a 0 PV não tira HP —
    # não há HP pra tirar — e sim uma falha automática no teste de morte (duas se
    # for crítico). Sem isto, estar caído ao lado de um inimigo seria mais seguro
    # que estar de pé, e a regra que o SRD usa pra fechar a luta não existiria.
    if estado_de_morte(wm) in ("caido", "estavel"):
        golpes = [a for a in (res.get("ataques") or []) if a.get("acertou")]
        res["falhas_de_morte"] = [
            falha_por_golpe(wm, critico=bool(a.get("critico"))) for a in golpes
        ]
        res["dano_total"] = 0   # o dano não se aplica a quem já caiu
        res["hp_jogador"] = wm.player_hp
        res["estado_morte"] = estado_de_morte(wm)
        return res
    if res.get("dano_total", 0) > 0:
        wm.character.aplicar_dano(res["dano_total"])
    res["hp_jogador"] = wm.player_hp
    res["estado_morte"] = estado_de_morte(wm)
    return res


def ordem_de_iniciativa(wm: Any) -> list[str]:
    """Ids dos inimigos na ordem de iniciativa (maior primeiro).

    COMBATE-SEM-RODADA-1: até 07/08 ninguém consultava `iniciativa_cache` na
    hora de resolver — a barra exibia uma ordem e a engine executava a de
    inserção no dict. Lista vazia quando não há cache (o caller cai no
    comportamento antigo, que continua determinístico).
    """
    cache = getattr(wm, "iniciativa_cache", None) or {}
    if not cache:
        return []
    # Mesmo desempate de `calcular_ordem_iniciativa`: -iniciativa, depois id.
    return sorted(
        (i for i in wm.inimigos_combate if i in cache),
        key=lambda i: (-int(cache[i]), i),
    )


def _fim_de_combate(wm: Any) -> bool:
    """True quando não sobrou inimigo vivo."""
    return not [d for d in wm.inimigos_combate.values() if d.get("estado") != "morto"]


def resolver_turno_inimigos_adiado(
    wm: Any, rng: random.Random | None = None
) -> dict[str, Any]:
    """A SEGUNDA metade da rodada: os inimigos agem, e só então a rodada fecha.

    Existe por causa do TURNO-COLAPSADO-1 — ver o comentário em
    `resolver_turno_ataque_jogador`. Chamada pelo beat, que entrega isto como uma
    mensagem SEPARADA do Mestre. A engine continua sendo a autoridade sobre os
    números; o que mudou é que a entrega deixou de ser um bloco só.

    Idempotente por turno: sem inimigo vivo (o jogador matou o último), não faz
    nada e não avança rodada — o combate acabou no golpe dele.
    """
    rng = rng or random.Random()
    if not getattr(wm, "em_combate", False) or _fim_de_combate(wm):
        return {"valido": False, "contexto": "", "dano_total": 0}

    res = executar_turno_inimigos(wm, rng)

    # A rodada fecha AQUI, não no golpe do jogador: ela é a volta completa da
    # ordem, e a ordem só deu a volta depois que os inimigos agiram.
    if getattr(wm, "iniciativa_cache", None) and hasattr(wm, "avancar_turno_e_rodada"):
        for _ in range(len(wm.inimigos_combate) + 1):
            if wm.avancar_turno_e_rodada():
                break
    else:
        wm.avancar_rodada()

    # As falhas de morte entram no contexto junto do turno: o Mestre precisa
    # narrar a lâmina descendo sobre quem já caiu, e precisa saber a contagem.
    _linhas = [linha_turno_inimigos(res)]
    _nome = str(getattr(wm, "player_name", "") or "")
    _linhas += [linha_de_morte(f, _nome) for f in (res.get("falhas_de_morte") or [])]

    return {
        "valido": True,
        "contexto": "\n".join(x for x in _linhas if x),
        "dano_total": int(res.get("dano_total", 0)),
        "ataques": res.get("ataques"),
        "falhas_de_morte": res.get("falhas_de_morte") or [],
        "estado_morte": res.get("estado_morte") or estado_de_morte(wm),
        "hp_jogador": wm.player_hp,
        "fim_combate": _fim_de_combate(wm),
    }


def resolver_turno_ataque_jogador(
    wm: Any,
    alvo_id: str,
    d20: int,
    *,
    dado_arma: int = _DADO_ARMA_PADRAO,
    mod_ataque: int | None = None,
    rng: random.Random | None = None,
    adiar_inimigos: bool = False,
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
    # MOD-ARMA-1: `mod_ataque` e `dado_arma` vêm da ARMA quando o caller
    # conseguiu identificá-la na declaração do jogador; None/padrão preservam o
    # comportamento antigo pra quem ataca sem nomear nada.
    r = resolver_ataque_do_jogador(wm, alvo_id, d20, mod_ataque=mod_ataque)
    if r is None:
        return {"valido": False, "contexto": ""}

    # COMBATE-SEM-RODADA-1: rola iniciativa AQUI, no começo da primeira troca
    # resolvida — é idempotente e sem I/O. Antes, quem populava era o pipeline
    # pós-turno, então a primeira troca do combate acontecia sem ordem nenhuma.
    if hasattr(wm, "popular_iniciativa"):
        wm.popular_iniciativa(rng=rng)

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

    # TURNO-COLAPSADO-1 (playtest 09/08): "tomei dano no meu ataque em vez da LLM
    # tomar o turno dela", "só o player age". O turno INTEIRO dos inimigos rodava
    # aqui dentro, na mesma chamada — o log mostra `dano=6 dano_inimigos=7` numa
    # linha só. A rodada virou unidade de tempo no estado (COMBATE-SEM-RODADA-1),
    # mas a ENTREGA continuou colapsada: o jogador não joga o estado interno, ele
    # joga a sequência de mensagens, e nela nada tinha mudado.
    #
    # Com `adiar_inimigos`, esta função resolve só a METADE do jogador e o turno
    # dos inimigos vai pro beat (`_beat_turno_inimigo`), que já existe e já é uma
    # SEGUNDA mensagem do Mestre — ele só estava desligado no caminho
    # engine-autoritativo, justamente pra não dobrar o dano (BEAT-DUPLO-1).
    #
    # ⚠️ Quem decide adiar é o CALLER, e só depois de saber que o beat vai mesmo
    # rodar. Adiar sem beat = inimigo que nunca age, que é pior que o colapso.
    if adiar_inimigos:
        return {
            "valido": True,
            "contexto": "\n".join(linhas),
            "acertou": r.acertou,
            "critico": r.critico,
            "falha_critica": r.falha_critica,
            "estado_alvo": estado,
            "dano": dano,
            "inimigos_adiados": True,
            "dano_inimigos": 0,
            "hp_jogador": wm.player_hp,
            "fim_combate": _fim_de_combate(wm),
            "tier": classificar_tier(
                critico=r.critico,
                falha_critica=r.falha_critica,
                estado_alvo=estado,
                fim_combate=_fim_de_combate(wm),
                ataques_inimigos=None,
            ),
        }

    # Turno dos inimigos (engine rola vs a CA do jogador e aplica o dano no PJ).
    res_inim = executar_turno_inimigos(wm, rng)
    linhas.append(linha_turno_inimigos(res_inim))

    # COMBATE-SEM-RODADA-1 (07/08): a rodada era incrementada aqui porque "o
    # jogador agiu" — e era essa a queixa literal do playtest ("um turno de
    # combate tem vários turnos com o mestre"). Agora a troca completa (jogador
    # + todos os inimigos) É a volta da ordem, então o cursor dá a volta e a
    # rodada vem como CONSEQUÊNCIA do wrap. `avancar_turno_e_rodada` renova
    # ação/bônus/movimento no True.
    if getattr(wm, "iniciativa_cache", None) and hasattr(wm, "avancar_turno_e_rodada"):
        # +1 = o jogador. O teto é defensivo: sem ele, um cache corrompido
        # (cursor fora de faixa) faria isto girar sem nunca dar a volta.
        for _ in range(len(wm.inimigos_combate) + 1):
            if wm.avancar_turno_e_rodada():
                break
    else:
        # Sem iniciativa não existe "volta da ordem" — mantém o comportamento
        # antigo pra que a rodada NUNCA congele. Foi assim que este caminho
        # apareceu num teste: `_wm_combate` nunca rolava iniciativa.
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
