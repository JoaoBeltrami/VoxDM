"""
Autoridade social — atos do jogador mudam relações DETERMINISTICAMENTE.

Por que existe: playtest 01/07 (sess-7893f3bdbd28) — o jogador duelou e
    subjugou a família Tharnsson inteira e o trust de Runa ficou parado em 0 a
    sessão toda ("a relação com a Runa, mesmo eu sendo legal, não entendi").
    Mesma doença do [XP:]: o marcador [AFETO] é opcional e o LLM não o emite —
    feature dormente. Mesma cura (decisão Beltrami 02/07): eventos que a engine
    JÁ detecta mudam a relação sem depender do LLM. Decisões travadas: toast
    discreto com motivo (sem números); intensidade FORTE (alvo despenca +
    aliados presentes caem junto via grafo); recuperação por atos positivos
    (companion/cura) + [AFETO] do LLM segue vivo pra nuance de diálogo.
Dependências: nenhuma (funções puras — mutam a WM recebida, sem I/O).
Armadilha: o afeto Neo4j NÃO é aplicado aqui (I/O) — cada EventoRelacao carrega
    os deltas em `afeto` e o CALLER (websocket) dispara `atualizar_afeto_npc`
    fire-and-forget. Esquecer isso = relação muda na sessão mas não persiste.

Exemplo:
    eventos = abalar_relacoes_por_ataque(wm, "bjorn-tharnsson", ["runa-tharnsdottir"])
    # → trust de bjorn vira 0 e de runa cai 2 na WM; eventos carregam
    #   os toasts ("Bjorn não esquecerá este ataque") e os deltas de afeto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

# Recuperação é mais lenta que a queda (decisão 02/07): atacar derruba o alvo
# pro fundo; virar aliado sobe só +1. Rancor/medo persistem no grafo entre
# sessões — a vila lembra.
_AFETO_ATAQUE_ALVO: dict[str, int] = {"rancor": 3, "medo": 2}
_AFETO_ATAQUE_ALIADO: dict[str, int] = {"rancor": 2, "medo": 1}
_AFETO_COMPANION: dict[str, int] = {"afeto": 2}
_AFETO_CURA: dict[str, int] = {"afeto": 1}


@dataclass(frozen=True)
class EventoRelacao:
    """Mudança de relação decidida pela engine — pro toast e pro afeto Neo4j."""

    npc_id: str
    nome: str
    direcao: str                    # "down" | "up"
    motivo: str                     # frase curta do toast (sem números)
    afeto: dict[str, int] = field(default_factory=dict)  # campo→delta (Neo4j)


def _nome_de(wm: Any, npc_id: str) -> str:
    """Nome de exibição: do inimigo registrado, do companion, ou do id."""
    dados = wm.inimigos_combate.get(npc_id) or {}
    nome = dados.get("nome") or (wm.companions.get(npc_id) or {}).get("nome")
    return str(nome or str(npc_id).replace("-", " ").title())


def abalar_relacoes_por_ataque(
    wm: Any, alvo_id: str, aliados: list[str] | None = None
) -> list[EventoRelacao]:
    """Atacar um NPC derruba a relação dele E dos aliados presentes (grafo).

    Intensidade FORTE (decisão 02/07): trust do alvo vai a 0; aliados caem -2.
    Dedup por combate: a flag `relacao_abalada` no dict do inimigo garante que
    5 golpes no mesmo alvo não re-derrubam nem re-emitem toast — a flag morre
    junto com `inimigos_combate` quando o combate encerra.
    """
    eventos: list[EventoRelacao] = []

    dados_alvo = wm.inimigos_combate.get(alvo_id)
    if dados_alvo is not None and not dados_alvo.get("relacao_abalada"):
        dados_alvo["relacao_abalada"] = True
        trust_atual = int(wm.trust_levels.get(alvo_id, 0))
        if trust_atual > 0:
            wm.atualizar_trust(alvo_id, -trust_atual)  # despenca pro fundo
        eventos.append(EventoRelacao(
            npc_id=alvo_id,
            nome=_nome_de(wm, alvo_id),
            direcao="down",
            motivo=f"{_nome_de(wm, alvo_id)} não esquecerá este ataque",
            afeto=dict(_AFETO_ATAQUE_ALVO),
        ))

    for aid in aliados or []:
        dados_aliado = wm.inimigos_combate.get(aid)
        if dados_aliado is None or dados_aliado.get("relacao_abalada"):
            continue
        dados_aliado["relacao_abalada"] = True
        wm.atualizar_trust(aid, -2)
        eventos.append(EventoRelacao(
            npc_id=aid,
            nome=_nome_de(wm, aid),
            direcao="down",
            motivo=f"{_nome_de(wm, aid)} viu o que você fez",
            afeto=dict(_AFETO_ATAQUE_ALIADO),
        ))

    if eventos:
        log.info(
            "relacoes_abaladas_por_ataque",
            alvo=alvo_id, afetados=[e.npc_id for e in eventos],
        )
    return eventos


def melhorar_relacao_companion(wm: Any, npc_id: str, nome: str) -> EventoRelacao:
    """NPC que se junta à jornada ([COMPANION_ADD]) passa a confiar mais.

    Recuperação lenta de propósito: +1 de trust (o cap [0,3] é do
    atualizar_trust), +2 de afeto persistente.
    """
    wm.atualizar_trust(npc_id, +1)
    log.info("relacao_melhorada_companion", npc_id=npc_id)
    return EventoRelacao(
        npc_id=npc_id,
        nome=nome or _nome_de(wm, npc_id),
        direcao="up",
        motivo=f"{nome or _nome_de(wm, npc_id)} agora caminha ao seu lado",
        afeto=dict(_AFETO_COMPANION),
    )


def registrar_cura_companion(npc_id: str) -> EventoRelacao:
    """Curar um companion sobe o afeto persistente — SEM toast (micro-evento;
    toast a cada poção viraria spam). O caller só aplica o afeto Neo4j."""
    return EventoRelacao(
        npc_id=npc_id, nome="", direcao="up", motivo="",
        afeto=dict(_AFETO_CURA),
    )
