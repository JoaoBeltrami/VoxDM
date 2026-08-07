"""
Diretor de Arco — avaliação determinística de finais de campanha.

Por que existe: a engine narrava turno/sessão bem, mas nenhuma história ENCERRAVA
    (ADR-002) — sem final, sem Momento de CONSEGUI. O Diretor observa o estado do
    arco (fronts, reputação de facção, quests, secrets, flags) e decide QUAL final
    de campanha disparou, SEM chamar LLM: a LLM só narra o clímax/epílogo que a
    engine entrega. Finais = DADO no módulo (schema `endings`); este é o avaliador
    genérico e AGNÓSTICO de história (serve qualquer módulo que declare `endings`).
Dependências: stdlib. Reusa a DSL de condição dos secrets ({operator, conditions}).
Armadilha: funções PURAS sobre um snapshot `EstadoArco` — sem I/O, sem async, sem
    WorkingMemory. O adapter que traduz o estado vivo (snapshot_de_wm) é passo
    seguinte; aqui é só a lógica, 100% testável por fixture.

Exemplo:
    est = EstadoArco(fronts={"guerra-das-vilas": 6}, faction_rep={"os-tharn": 55},
                     reputation_thresholds={"os-tharn": {"allied": 50}})
    fim = escolher_ending(modulo["endings"], est)   # -> dict do final vencedor | None
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class EstadoArco:
    """Snapshot RAM-barato do estado que os finais avaliam. Tudo default-vazio
    pra um teste declarar só o que importa."""

    fronts: dict[str, int] = field(default_factory=dict)              # id → filled
    faction_rep: dict[str, int] = field(default_factory=dict)         # id → standing
    quests_completas: set[str] = field(default_factory=set)
    secrets_revelados: set[str] = field(default_factory=set)
    flags: dict[str, Any] = field(default_factory=dict)
    # faction_id → {nome_threshold: valor} (do módulo; ex: {"allied": 50})
    reputation_thresholds: dict[str, dict[str, int]] = field(default_factory=dict)


def _cmp(atual: int, alvo: int, comparison: str) -> bool:
    if comparison == "at_most":
        return atual <= alvo
    if comparison == "below":
        return atual < alvo
    if comparison == "above":
        return atual > alvo
    return atual >= alvo  # at_least (padrão)


def _resolver_threshold(est: EstadoArco, faccao: str, valor: Any) -> int:
    """value pode ser um número OU um nome de threshold ('allied') do módulo."""
    if isinstance(valor, bool):  # bool é subclasse de int — barra antes
        return 0
    if isinstance(valor, (int, float)):
        return int(valor)
    return int(est.reputation_thresholds.get(faccao, {}).get(str(valor), 0))


def _avaliar_folha(cond: dict[str, Any], est: EstadoArco) -> bool:
    tipo: str = cond.get("type", "")
    alvo: str = cond.get("target", "")
    valor: Any = cond.get("value")
    comp: str = cond.get("comparison", "at_least")

    if tipo == "front_filled":
        return _cmp(est.fronts.get(alvo, 0), int(valor or 0), comp)
    if tipo == "faction_reputation":
        return _cmp(est.faction_rep.get(alvo, 0), _resolver_threshold(est, alvo, valor), comp)
    if tipo == "quest_completed":
        return alvo in est.quests_completas
    if tipo == "secret_revealed":
        return alvo in est.secrets_revelados
    if tipo == "flag":
        esperado = True if valor is None else valor
        atual = est.flags.get(alvo)
        # Porta fechada (decisão "c"): comparação BOOLEANA trata flag AUSENTE como
        # False — `flag paz-morta == false` precisa passar quando ninguém matou a
        # paz ainda (antes, None == False dava falso e o F2 nunca disparava).
        if isinstance(esperado, bool):
            return bool(atual) is esperado
        return atual == esperado

    log.warning("arco_leaf_desconhecida", tipo=tipo)
    return False  # tipo desconhecido → não satisfeita (seguro)


def avaliar_condicao(cond: dict[str, Any] | None, est: EstadoArco) -> bool:
    """Avalia condição simples (folha) ou composta (AND/OR, aninhável)."""
    if not cond:
        return False
    operador = cond.get("operator")
    if operador:
        filhos = cond.get("conditions", [])
        if operador == "AND":
            return all(avaliar_condicao(f, est) for f in filhos)
        if operador == "OR":
            return any(avaliar_condicao(f, est) for f in filhos)
        log.warning("arco_operador_desconhecido", operador=operador)
        return False
    return _avaliar_folha(cond, est)


def endings_disparados(endings: list[dict[str, Any]], est: EstadoArco) -> list[dict[str, Any]]:
    """Lista os finais cuja condição `when` está satisfeita (sem `when` → nunca)."""
    return [e for e in endings if avaliar_condicao(e.get("when"), est)]


def escolher_ending(endings: list[dict[str, Any]], est: EstadoArco) -> dict[str, Any] | None:
    """O final vencedor: maior `priority` entre os disparados. Desempate
    determinístico por id (desc). None se nenhum disparou."""
    disparados = endings_disparados(endings, est)
    if not disparados:
        return None
    vencedor = max(disparados, key=lambda e: (int(e.get("priority", 0)), str(e.get("id", ""))))
    log.info(
        "arco_ending_escolhido",
        ending=vencedor.get("id"),
        disparados=[e.get("id") for e in disparados],
    )
    return vencedor


def snapshot_de_wm(wm: Any, modulo: dict[str, Any] | None = None) -> EstadoArco:
    """Traduz o estado VIVO (WorkingMemory + módulo) → EstadoArco (o seam entre a
    engine e o avaliador puro). Duck-typed de propósito: lê `quests_completas` e
    `secrets_revelados` da WM SE existirem (passo 3 os adiciona) — enquanto não,
    ficam vazios e os finais que dependem deles (F2/F4) só não disparam ainda.

    Fronts: união de `narrative.fronts_latentes` (filled) e `narrative.relogios`
    (atual); o relógio ATIVO sobrescreve o latente (mesmo id).
    """
    narr = getattr(wm, "narrative", None)

    fronts: dict[str, int] = {}
    for fid, d in (getattr(narr, "fronts_latentes", {}) or {}).items():
        fronts[str(fid)] = int((d or {}).get("filled", 0))
    for fid, d in (getattr(narr, "relogios", {}) or {}).items():
        fronts[str(fid)] = int((d or {}).get("atual", 0))  # ativo vence latente

    thresholds: dict[str, dict[str, int]] = {}
    for f in (modulo or {}).get("factions", []):
        fid = f.get("id")
        rt = f.get("reputation_thresholds")
        if fid and isinstance(rt, dict):
            thresholds[str(fid)] = {str(k): int(v) for k, v in rt.items()}

    scene = getattr(wm, "scene", None)
    return EstadoArco(
        fronts=fronts,
        faction_rep=dict(getattr(wm, "faction_standings", {}) or {}),
        quests_completas=set(getattr(wm, "quests_completas", set()) or set()),
        secrets_revelados=set(getattr(scene, "secrets_revelados", set()) or set()),
        flags=dict(getattr(wm, "arc_flags", {}) or {}),
        reputation_thresholds=thresholds,
    )


_modulo_cache: dict[str, Any] | None = None


def carregar_modulo_arco() -> dict[str, Any]:
    """Módulo do arco (arc/endings/factions/fronts) — cache por processo."""
    global _modulo_cache
    if _modulo_cache is not None:
        return _modulo_cache
    import json
    from pathlib import Path

    from config import settings
    try:
        caminho = Path(settings.DEFAULT_MODULE_PATH)
        if not caminho.is_absolute():
            caminho = Path(__file__).parent.parent.parent / str(
                settings.DEFAULT_MODULE_PATH).lstrip("./")
        _modulo_cache = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception as e:  # módulo ausente/corrompido → arco desligado, jogo segue
        log.warning("arco_modulo_falhou", erro=str(e)[:120])
        _modulo_cache = {}
    return _modulo_cache


def limpar_cache_modulo() -> None:
    """Descarta o cache do módulo (uso em testes)."""
    global _modulo_cache
    _modulo_cache = None


def conduzir_arco(wm: Any, modulo: dict[str, Any] | None = None) -> str:
    """Máquina de estados do arco, chamada no PÓS-TURNO. Devolve a fase nova.

    normal → (final disparou) climax → (clímax narrado) epilogo → (epílogo
    narrado) concluida. O prompt do turno SEGUINTE lê a fase e injeta a diretiva
    — por isso a transição acontece aqui, depois da narração.
    `free_master` (Mestre Livre) desliga o arco inteiro.
    """
    mod = modulo if modulo is not None else carregar_modulo_arco()
    arc = mod.get("arc") or {}
    if not arc or arc.get("free_master"):
        return getattr(wm, "arc_fase", "normal")

    fase = str(getattr(wm, "arc_fase", "normal") or "normal")
    if fase == "climax":
        wm.arc_fase = "epilogo"
        log.info("arco_fase", de="climax", para="epilogo", ending=wm.arc_ending_id)
        return "epilogo"
    if fase == "epilogo":
        wm.arc_fase = "concluida"
        log.info("arco_campanha_concluida", ending=wm.arc_ending_id)
        return "concluida"
    if fase != "normal":
        return fase  # concluida — nada a fazer

    vencedor = escolher_ending(mod.get("endings", []), snapshot_de_wm(wm, mod))
    if vencedor:
        wm.arc_fase = "climax"
        wm.arc_ending_id = str(vencedor.get("id", ""))
        log.info("arco_final_disparou", ending=wm.arc_ending_id)
        return "climax"
    return "normal"


def diretiva_de_arco(wm: Any, modulo: dict[str, Any] | None = None) -> str:
    """Bloco a injetar no prompt conforme a fase do arco (vazio em 'normal' sem
    espinha armada). É a voz da engine dirigindo o desfecho — a LLM só narra."""
    mod = modulo if modulo is not None else carregar_modulo_arco()
    arc = mod.get("arc") or {}
    if not arc or arc.get("free_master"):
        return ""

    fase = str(getattr(wm, "arc_fase", "normal") or "normal")
    ending = next(
        (e for e in mod.get("endings", []) if e.get("id") == getattr(wm, "arc_ending_id", "")),
        None,
    )

    if fase == "climax" and ending:
        climax = ending.get("climax") or {}
        linhas = [
            "\n=== CLÍMAX DA CAMPANHA ===",
            f"A história chegou ao desfecho: {ending.get('name', '')}.",
            str(climax.get("directive", "")).strip(),
        ]
        beats = climax.get("beats") or []
        if beats:
            linhas.append("Beats a cumprir: " + " → ".join(str(b) for b in beats) + ".")
        branches = climax.get("branches") or []
        if branches:
            linhas.append(
                "ESCOLHA DO JOGADOR — apresente as portas e encene a que ele tomar: "
                + " | ".join(
                    f"{b.get('label') or b.get('choice_id')}" for b in branches
                ) + "."
            )
        linhas.append("Encene o clímax AGORA. Não adie, não abra subtrama nova.")
        return "\n".join(x for x in linhas if x)

    if fase == "epilogo" and ending:
        semente = str(ending.get("epilogue", "")).strip()
        if not semente:
            branches = (ending.get("climax") or {}).get("branches") or []
            semente = str((branches[0] if branches else {}).get("epilogue", "")).strip()
        return (
            "\n=== EPÍLOGO — ENCERRE A CAMPANHA ===\n"
            f"{semente}\n"
            "Narre o fecho em 3-5 frases: o que ficou do mundo, o que custou, e o "
            "que o personagem leva. Depois PARE — a campanha acabou."
        )

    if fase == "concluida":
        # ARCO-CONCLUIDO-SEM-SAIDA-1 (playtest 01/08): esta diretiva dizia
        # "A história terminou. Não reabra o arco; responda como epílogo/OOC" —
        # e era injetada em TODO turno, para sempre. O Beltrami jogou ~11 minutos
        # depois da conclusão e sentiu exatamente isso: "A DESGRAÇA DA CENA NÃO
        # PROSSEGUE SEM EU PEDIR". A engine estava mandando o Mestre não mover
        # o mundo, e ele obedecia.
        #
        # O arco fechado continua CANON (não reabre, não desfaz o desfecho) — o
        # que muda é que a CENA volta a correr. Fim de campanha é epílogo do
        # ARCO, não fim do mundo: o jogador ainda está lá dentro.
        nome_fim = ending.get("name", "") if ending else ""
        selo = f' em "{nome_fim}"' if nome_fim else ""
        return (
            "\n=== DEPOIS DO FIM (arco encerrado) ===\n"
            f"A campanha já se resolveu{selo} — isso é CANON: não reabra o arco, "
            "não desfaça o desfecho e não anuncie de novo que acabou.\n"
            "Mas o mundo NÃO parou, e o jogador continua dentro dele. Conduza a "
            "cena normalmente — com iniciativa própria, consequências e o peso do "
            "que aquele fim deixou para trás."
        )

    # normal — só a pressão de escalada quando a espinha está armada
    if espinha_armada(arc, snapshot_de_wm(wm, mod)):
        return (
            "\n=== A GUERRA SE APROXIMA DA CABEÇA ===\n"
            "A espinha da campanha está prestes a estourar. Aumente a pressão: "
            "sinais de que o desfecho é iminente, urgência nas facções, o mundo "
            "cobrando uma decisão. NÃO resolva ainda."
        )
    return ""


def espinha_armada(arc: dict[str, Any] | None, est: EstadoArco) -> bool:
    """True quando a espinha atingiu `escalation.arm_at` — o Diretor passa a
    dirigir a narração pro clímax. `free_master` desliga o arco inteiro."""
    if not arc or arc.get("free_master"):
        return False
    spine = str(arc.get("spine", ""))
    arm_at = int((arc.get("escalation") or {}).get("arm_at", 0))
    return est.fronts.get(spine, 0) >= arm_at > 0
