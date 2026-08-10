"""
Qual recurso da rodada uma magia custa — ação, ação bônus ou reação.

Por que existe: o playtest de 10/08 pediu *"como ação bônus, eu vou utilizar a
    marca do caçador nele e em seguida ataco"* — a sequência mais banal de um
    Ranger. A engine cobrava AÇÃO de toda magia, então marcar o alvo consumia o
    turno e o ataque seguinte não acontecia. O estado já tinha `bonus_usada` e
    `usar_bonus()` desde sempre; ninguém nunca os chamou.
Dependências: nenhuma (lê a tabela mecânica local, que é dado estático).
Armadilha: rótulo desconhecido cai em "acao" de propósito — é o custo mais CARO,
    e portanto o seguro. Errar para baixo daria ao jogador uma ação de graça toda
    rodada, que é justamente o tipo de vantagem silenciosa que ninguém percebe.

Exemplo:
    custo_de_acao("Marca do Caçador")
    # → "bonus"
    gastar_recurso_da_magia(wm, "Marca do Caçador")
    # → ("bonus", True)   e wm.bonus_usada vira True, a ação segue livre
"""

from typing import Any, Literal

from engine.magic.resolucao import mecanica_da_magia

Recurso = Literal["acao", "bonus", "reacao", "longo"]

# Fora de combate não há rodada, então não há o que gastar. A lista existe pra
# deixar explícito que "longo" (ritual de 10 minutos) NÃO é uma ação de combate:
# cobrar a ação por ele seria tão errado quanto cobrar bônus por Bola de Fogo.
_GASTAVEIS_EM_COMBATE: frozenset[str] = frozenset({"acao", "bonus"})


def custo_de_acao(nome_pt: str, nome_en: str = "") -> Recurso:
    """O recurso que esta magia consome numa rodada de combate.

    Devolve "acao" quando a magia é desconhecida — o custo mais caro é o
    palpite seguro (ver Armadilha no topo).
    """
    mecanica = mecanica_da_magia(nome_pt, nome_en) or {}
    bruto = str(mecanica.get("tempo_conjuracao") or "acao")
    return bruto if bruto in ("acao", "bonus", "reacao", "longo") else "acao"  # type: ignore[return-value]


def gastar_recurso_da_magia(
    wm: Any, nome_pt: str, nome_en: str = ""
) -> tuple[Recurso, bool]:
    """Cobra da economia da rodada o recurso certo. Devolve (recurso, gastou).

    `gastou=False` significa "não havia o que cobrar" — ou porque a luta não
    começou, ou porque o recurso JÁ tinha sido usado nesta rodada. O caller
    decide se isso vira recusa; esta função não julga, só contabiliza.
    """
    recurso = custo_de_acao(nome_pt, nome_en)
    if not getattr(wm, "em_combate", False):
        return recurso, False
    if recurso not in _GASTAVEIS_EM_COMBATE:
        return recurso, False
    if recurso == "bonus":
        return recurso, bool(wm.usar_bonus())
    return recurso, bool(wm.usar_acao())
