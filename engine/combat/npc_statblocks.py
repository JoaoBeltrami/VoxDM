"""
Statblocks de combate pros NPCs FIXOS do módulo — análogo SRD + override no schema.

Por que existe: os NPCs do módulo (Bjorn, Runa, Halvard…) não tinham stat block —
    ao virar inimigos caíam no fallback CR genérico (~CA 12), e lutar contra o
    líder de Tharnvik era mecanicamente igual a lutar contra um capanga
    (nota do Beltrami no playtest 29/06; decisão "híbrido" em 02/07).
    O campo `combat` de cada NPC no JSON do módulo aponta um análogo SRD
    (`{"srd_analogo": "berserker"}`) e/ou sobrescreve campos individuais
    (`{"srd_analogo": "veteran", "ca": 18}`). O JSON é lido em runtime —
    NÃO precisa de re-ingest.
Dependências: config (DEFAULT_MODULE_PATH). Dados dos statblocks: SRD 5.1 (OGL).
Armadilha: o retorno é a FICHA EM TEXTO no formato que `engine/combat/stats.py:
    parse_ficha` e `engine/progression.py: xp_do_inimigo` parseiam ("CA N | PV N",
    "Ataques: … +N (NdM+K)", "(N XP)") — mudar o formato quebra CA/HP, o ataque
    do inimigo no enemy_turn E o XP de abate ao mesmo tempo.

Exemplo:
    ficha = resolver_ficha_npc("bjorn-tharnsson")
    # → "Berserker — CR 2 (450 XP). CA 13 | PV 67. Ataques: Machadão +5 (1d12+3)"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from config import settings

log = structlog.get_logger()

# ── Tabela estática de statblocks SRD 5.1 (OGL) ───────────────────────────────
# Mesmo padrão do engine/magic/spell_list.py: dados SRD em código, sem Qdrant.
# Campos: nome PT-BR (flavor da ficha), cr (exibição), xp, ca, hp, atk (bônus),
# dano ("NdM"), dano_bonus. Humanoides genéricos + o gigante do módulo.
STATBLOCKS_SRD: dict[str, dict[str, Any]] = {
    "commoner":       {"nome": "Plebeu",             "cr": "0",   "xp": 10,   "ca": 10, "hp": 4,   "atk": 2, "dano": "1d4",  "dano_bonus": 0},
    "noble":          {"nome": "Nobre",              "cr": "1/8", "xp": 25,   "ca": 15, "hp": 9,   "atk": 3, "dano": "1d8",  "dano_bonus": 1},
    "guard":          {"nome": "Guarda",             "cr": "1/8", "xp": 25,   "ca": 16, "hp": 11,  "atk": 3, "dano": "1d6",  "dano_bonus": 1},
    "bandit":         {"nome": "Bandido",            "cr": "1/8", "xp": 25,   "ca": 12, "hp": 11,  "atk": 3, "dano": "1d6",  "dano_bonus": 1},
    "acolyte":        {"nome": "Acólito",            "cr": "1/4", "xp": 50,   "ca": 10, "hp": 9,   "atk": 2, "dano": "1d4",  "dano_bonus": 0},
    "scout":          {"nome": "Batedor",            "cr": "1/2", "xp": 100,  "ca": 13, "hp": 16,  "atk": 4, "dano": "1d6",  "dano_bonus": 2},
    "thug":           {"nome": "Capanga",            "cr": "1/2", "xp": 100,  "ca": 11, "hp": 32,  "atk": 4, "dano": "1d6",  "dano_bonus": 2},
    "spy":            {"nome": "Espião",             "cr": "1",   "xp": 200,  "ca": 12, "hp": 27,  "atk": 4, "dano": "1d6",  "dano_bonus": 2},
    "priest":         {"nome": "Sacerdote",          "cr": "2",   "xp": 450,  "ca": 13, "hp": 27,  "atk": 2, "dano": "1d6",  "dano_bonus": 0},
    "cult-fanatic":   {"nome": "Fanático de Culto",  "cr": "2",   "xp": 450,  "ca": 13, "hp": 33,  "atk": 4, "dano": "1d4",  "dano_bonus": 2},
    "berserker":      {"nome": "Berserker",          "cr": "2",   "xp": 450,  "ca": 13, "hp": 67,  "atk": 5, "dano": "1d12", "dano_bonus": 3},
    "bandit-captain": {"nome": "Capitão Bandido",    "cr": "2",   "xp": 450,  "ca": 15, "hp": 65,  "atk": 5, "dano": "1d6",  "dano_bonus": 3},
    "veteran":        {"nome": "Veterano",           "cr": "3",   "xp": 700,  "ca": 17, "hp": 58,  "atk": 5, "dano": "1d8",  "dano_bonus": 3},
    "knight":         {"nome": "Cavaleiro",          "cr": "3",   "xp": 700,  "ca": 18, "hp": 52,  "atk": 5, "dano": "2d6",  "dano_bonus": 3},
    "hill-giant":     {"nome": "Gigante das Colinas", "cr": "5",  "xp": 1800, "ca": 13, "hp": 105, "atk": 8, "dano": "3d8",  "dano_bonus": 5},
}

# Campos numéricos/textuais que o `combat` do NPC pode sobrescrever no análogo.
_CAMPOS_OVERRIDE: tuple[str, ...] = ("nome", "cr", "xp", "ca", "hp", "atk", "dano", "dano_bonus")

# Cache do mapa npc_id → dict `combat` do módulo. Carregado 1x por processo —
# o JSON do módulo não muda mid-sessão (uvicorn --reload recarrega em dev).
_combat_map_cache: dict[str, dict[str, Any]] | None = None

# Ids que o módulo DECLARA mas para os quais não há bloco `combat` — Vyrmathax é
# o caso que deu nome ao bug. Preenchido no mesmo passe do mapa, e usado por
# `sem_ficha_autoral` pra avisar ALTO antes do fallback genérico entrar.
_SEM_FICHA: set[str] = set()


def _ficha_texto(campos: dict[str, Any]) -> str:
    """Formata os campos num texto parseável por parse_ficha + xp_do_inimigo."""
    bonus = int(campos.get("dano_bonus", 0) or 0)
    sufixo_bonus = f"+{bonus}" if bonus > 0 else ""
    return (
        f"{campos['nome']} — CR {campos['cr']} ({int(campos['xp'])} XP). "
        f"CA {int(campos['ca'])} | PV {int(campos['hp'])}. "
        f"Ataques: golpe +{int(campos['atk'])} ({campos['dano']}{sufixo_bonus})"
    )


def _carregar_combat_map() -> dict[str, dict[str, Any]]:
    """Mapa npc_id → campo `combat` lido do JSON do módulo (cache por processo)."""
    global _combat_map_cache
    if _combat_map_cache is not None:
        return _combat_map_cache
    caminho = Path(settings.DEFAULT_MODULE_PATH)
    if not caminho.is_absolute():
        _raiz = Path(__file__).parent.parent.parent
        caminho = _raiz / str(settings.DEFAULT_MODULE_PATH).lstrip("./")
    mapa: dict[str, dict[str, Any]] = {}
    try:
        with caminho.open(encoding="utf-8") as f:
            dados = json.load(f)
        # BESTIARIO-CR-ERRADO-1 (playtest 07/08): varria SÓ `npcs`. As `entities`
        # — que no schema v1.2 são justamente as criaturas não-humanoides com
        # papel narrativo, ou seja, os inimigos que MAIS importam — ficavam de
        # fora do mapa inteiro. Vyrmathax caiu no fallback genérico e recebeu
        # ficha de warlock; o Beltrami matou "uma lenda" com 9 de dano e achou
        # o combate fácil. Companions entram pelo mesmo motivo (aliado com
        # ficha errada erra na direção oposta).
        for secao in ("npcs", "entities", "companions"):
            for ent in dados.get(secao, []):
                combat = ent.get("combat")
                if isinstance(combat, dict) and ent.get("id"):
                    mapa[str(ent["id"])] = combat
                # O módulo CONHECE esta criatura mas não deu ficha de combate a
                # ela. Registrar aqui é o que permite avisar alto quando ela
                # entra em combate — ver `sem_ficha_autoral`.
                elif ent.get("id"):
                    _SEM_FICHA.add(str(ent["id"]))
    except Exception as e:
        # Módulo ausente/corrompido → NPCs caem no fallback CR genérico, jogo segue.
        log.warning("npc_statblocks_schema_falhou", erro=str(e)[:120])
    _combat_map_cache = mapa
    return mapa


def limpar_cache() -> None:
    """Descarta o cache do mapa `combat` (uso em testes)."""
    global _combat_map_cache
    _combat_map_cache = None
    _SEM_FICHA.clear()


def _id_canonico(npc_id: str) -> str:
    """Tira o sufixo de instância: `vyrmathax-1` → `vyrmathax`.

    BESTIARIO-CR-ERRADO-1: o combate numera instâncias (`goblin-1`, `goblin-2`)
    e o log do playtest mostrou `combate_inimigo_declarado id=vyrmathax-1`. O
    mapa é chaveado pelo id do MÓDULO, sem sufixo — então nenhum inimigo
    numerado achava a própria ficha autoral, nem os 17 NPCs que têm uma.
    """
    base = str(npc_id or "").strip()
    partes = base.rsplit("-", 1)
    return partes[0] if len(partes) == 2 and partes[1].isdigit() else base


def sem_ficha_autoral(npc_id: str) -> bool:
    """True quando o módulo conhece esta criatura mas NÃO deu ficha de combate.

    É o sinal de "a lenda vai virar capanga": quem chama deve avisar ALTO antes
    de cair no fallback genérico, em vez de deixar o CR errado passar calado.
    """
    _carregar_combat_map()
    return _id_canonico(npc_id) in _SEM_FICHA


def e_npc_fixo(npc_id: str) -> bool:
    """True se o id é um NPC FIXO do módulo (tem campo `combat` autoral).

    NPC-IDENTITY-CONFLATION-1 (rodada grimdark 18/07): identidade autoral é
    inviolável — usado pelo name-reveal pra recusar que um figurante "roube"
    a entrada canônica de um NPC do módulo, e pelo extractor pra não batizar
    um falante com o nome de um NPC fixo apenas MENCIONADO em fala.
    """
    return _id_canonico(npc_id) in _carregar_combat_map()


def resolver_ficha_npc(npc_id: str) -> str | None:
    """Ficha em texto do NPC fixo, ou None se o módulo não define `combat` pra ele.

    Resolução (decisão "híbrido", 02/07): base = análogo SRD (`srd_analogo`);
    qualquer campo explícito SOBRESCREVE o do análogo (Bjorn pode ter CA única
    mantendo o resto do berserker). `combat` só com overrides e sem análogo
    válido também funciona, desde que tenha o mínimo (ca+hp).

    O campo pode vir solto (`combat.ca`) ou aninhado (`combat.overrides.ca`) —
    as duas formas circulam no projeto e ambas funcionam.
    """
    combat = _carregar_combat_map().get(_id_canonico(npc_id))
    if not combat:
        return None
    base = dict(STATBLOCKS_SRD.get(str(combat.get("srd_analogo", "")).strip().lower(), {}))
    # Aceita as DUAS formas: campo solto no `combat` (como o código sempre leu) e
    # aninhado em `combat.overrides` (como o CLAUDE.md sempre documentou). A
    # divergência mordeu em silêncio ao escrever os vilões em 29/07 — o override
    # aninhado era ignorado sem warning, e a ficha saía com o análogo puro.
    # Aninhado vence: quem escreveu explicitamente `overrides` quis sobrescrever.
    aninhados = combat.get("overrides") or {}
    for campo in _CAMPOS_OVERRIDE:
        if campo in combat:
            base[campo] = combat[campo]
        if isinstance(aninhados, dict) and campo in aninhados:
            base[campo] = aninhados[campo]
    # Mínimo pra ficha fazer sentido mecânico: CA e HP. Sem eles (análogo
    # inválido e override incompleto), o NPC cai no fallback genérico.
    if "ca" not in base or "hp" not in base:
        log.warning("npc_statblock_incompleto", npc_id=npc_id)
        return None
    base.setdefault("nome", str(npc_id).replace("-", " ").title())
    base.setdefault("cr", "?")
    base.setdefault("xp", 25)
    base.setdefault("atk", 3)
    base.setdefault("dano", "1d6")
    base.setdefault("dano_bonus", 1)
    return _ficha_texto(base)
