"""
Lookup de fichas (stat blocks) de monstro do SRD e enriquecimento do combate.

Por que existe: o Mestre improvisa HP/CA/ataques de inimigo sem dados reais. Este
    módulo busca a ficha compacta de um monstro na coleção voxdm_bestiary (indexada
    por ingest_rules.py) e a guarda no inimigo registrado, pra o prompt de combate
    narrar com consistência mecânica (gêmeo do engine/magic/spell_detector.py).
Dependências: engine/memory/qdrant_client
Armadilha: lookup é DETERMINÍSTICO por source_id (filtro exato), nunca fuzzy —
    evita injetar a ficha errada. Se o índice não existe na coleção, retorna None
    silenciosamente e o combate segue com narração improvisada (como hoje).

Exemplo:
    ficha = await buscar_ficha_monstro(srd_index="goblin")
    # → "Goblin — Pequeno humanoide, CR 1/4 (50 XP). CA 15 | PV 7 (2d6) ..."
    # → None se não indexado / Qdrant fora
"""

import re
import unicodedata
from typing import Any

import structlog

from config import settings
from engine.combat.stats import stats_inimigo

log = structlog.get_logger()

# Teto de lookups por turno — protege contra um turno declarando dezenas de
# inimigos novos (cada lookup é uma ida ao Qdrant). Os já cacheados não contam.
_MAX_LOOKUPS_POR_TURNO = 5

# BESTIARY-PERF-1 (teste ao vivo 09/06): cada lookup criava um QdrantMemoryClient
# NOVO, que recarregava o SentenceTransformer (~3s) — com 2 inimigos por turno de
# combate, +6s/turno só de reload (turnos de 13-14s nos logs). Singleton elimina.
_cliente_singleton: Any = None

# BESTIARY-SRD-1: cache negativo. O LLM emitiu o índice LITERAL "srd" (copiou o
# placeholder da doc do marker) e o lookup-miss repetia TODO turno. Misses entram
# aqui e não são re-consultados (a coleção não muda durante o jogo).
_indices_sem_ficha: set[str] = set()

# Índices que NUNCA são válidos — placeholders que o LLM copia da documentação.
_INDICES_INVALIDOS: frozenset[str] = frozenset({"srd", "id", "indice", "index", "none", "x"})


def _obter_cliente() -> Any:
    """Cliente Qdrant singleton (lazy) — evita reload do embedder por chamada."""
    global _cliente_singleton
    if _cliente_singleton is None:
        from engine.memory.qdrant_client import QdrantMemoryClient
        _cliente_singleton = QdrantMemoryClient()
    return _cliente_singleton


def _slugify(nome: str) -> str:
    """Converte nome livre em índice kebab-case candidato (ex: 'Goblin' → 'goblin')."""
    normalizado = unicodedata.normalize("NFD", nome.strip().lower())
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


async def buscar_ficha_monstro(srd_index: str = "", nome: str = "") -> str | None:
    """Busca a ficha compacta de um monstro na coleção voxdm_bestiary.

    Estratégia (determinística, sem fuzzy):
      1. Se `srd_index` fornecido, filtra por source_id exato.
      2. Senão, tenta slugify(nome) como índice (ex: "Goblin" → "goblin").
    Em ambos os casos é um match exato por source_id — se o índice não existe,
    retorna None (sem semântico, pra nunca injetar a ficha de outro monstro).

    Returns:
        O texto do stat block, ou None se não encontrado / erro de rede.
    """
    indice = (srd_index or "").strip().lower()
    # BESTIARY-SRD-1: índice placeholder ("srd" etc.) cai pro slug do nome,
    # que ainda pode bater num monstro real ("Goblin" → "goblin").
    if not indice or indice in _INDICES_INVALIDOS:
        indice = _slugify(nome)
    if not indice or indice in _INDICES_INVALIDOS:
        return None
    if indice in _indices_sem_ficha:
        return None
    try:
        cliente = _obter_cliente()
        # query é só pra gerar o vetor exigido pelo query_points; o filtro exato
        # por source_id é quem decide o resultado. score_threshold=0 → não filtra.
        resultados = await cliente.buscar(
            query=indice,
            colecao=settings.QDRANT_COLECAO_BESTIARY,
            top_k=1,
            filtro={"source_id": indice},
            score_threshold=0.0,
        )
        if not resultados:
            _indices_sem_ficha.add(indice)
            return None
        texto = str(resultados[0].get("text", "")).strip()
        if texto:
            log.info("bestiario_ficha_encontrada", indice=indice)
        else:
            _indices_sem_ficha.add(indice)
        return texto or None
    except Exception as exc:
        # Falha silenciosa — Qdrant fora, coleção ausente, etc. Combate segue.
        log.warning("bestiario_busca_falhou", indice=indice, erro=str(exc)[:120])
        return None


async def enriquecer_fichas_inimigos(working_mem: Any) -> int:
    """Carrega a ficha SRD dos inimigos em combate que ainda não a têm.

    Idempotente: pula inimigos mortos, os que já têm `ficha`, e os cujo índice
    (srd_index ou slug do nome) não bate em nenhum monstro indexado. Roda no
    websocket (contexto async) DEPOIS do pipeline pós-turno — a ficha fica
    disponível no prompt do turno seguinte. Falha de lookup é silenciosa.

    Returns:
        Quantas fichas novas foram carregadas (útil pra telemetria/testes).
    """
    if not getattr(working_mem, "em_combate", False):
        return 0
    carregadas = 0
    for iid, dados in working_mem.inimigos_combate.items():
        if dados.get("estado") == "morto":
            continue
        # 0. Statblock do MÓDULO (NPCs fixos — decisão "híbrido" 02/07): fonte
        #    prioritária, sem I/O. Bjorn/Runa/etc. ganham a ficha do análogo SRD
        #    (ou override) definida no campo `combat` do JSON do módulo — antes
        #    caíam no fallback CR genérico e o líder da vila lutava como capanga.
        if not dados.get("ficha"):
            from engine.combat.npc_statblocks import resolver_ficha_npc, sem_ficha_autoral
            ficha_modulo = resolver_ficha_npc(iid)
            if ficha_modulo:
                dados["ficha"] = ficha_modulo
                dados["ficha_fonte"] = "modulo"
                log.info("statblock_modulo_aplicado", id=iid)
            elif sem_ficha_autoral(iid):
                # BESTIARIO-CR-ERRADO-1 (playtest 07/08): o módulo CONHECE esta
                # criatura e não deu ficha a ela — daqui pra baixo ela vira um
                # genérico. Foi assim que Vyrmathax recebeu ficha de warlock e o
                # Beltrami matou "uma lenda" com 9 de dano, achando o combate
                # fácil. O fallback continua (o jogo não pode travar), mas agora
                # é ALTO: dá pra ver no log qual criatura precisa de statblock.
                log.warning(
                    "npc_do_modulo_sem_ficha_autoral",
                    id=iid,
                    nome=dados.get("nome", ""),
                    acao="escreva o bloco `combat` deste id no JSON do módulo",
                )
        # 1. Ficha SRD em texto (lookup Qdrant, com cap por turno).
        if not dados.get("ficha") and carregadas < _MAX_LOOKUPS_POR_TURNO:
            ficha = await buscar_ficha_monstro(
                srd_index=dados.get("srd_index", ""),
                nome=dados.get("nome", ""),
            )
            if ficha:
                dados["ficha"] = ficha
                dados["ficha_fonte"] = "bestiario"
                carregadas += 1
        # 1.5 Âncora no SRD estático — último elo antes do genérico. Grátis (sem
        #     I/O): casa o índice OU o nome PT-BR contra a tabela de 15 statblocks.
        #     Sem isto, um "Capanga" e um "Cavaleiro" tinham a MESMA ficha de
        #     lacaio CR 1/8, e o combate não conseguia doer nem quando devia.
        if not dados.get("ficha"):
            from engine.combat.npc_statblocks import ancorar_no_srd
            ficha_ancora = ancorar_no_srd(
                srd_index=str(dados.get("srd_index", "")),
                nome=str(dados.get("nome", "")),
            )
            if ficha_ancora:
                dados["ficha"] = ficha_ancora
                dados["ficha_fonte"] = "srd-ancora"
                log.info("statblock_srd_ancorado", id=iid, ficha=ficha_ancora[:60])
        # 2. Stats numéricos (CA/HP) — todo inimigo vivo sem CA recebe, da ficha
        #    SRD parseada ou do default por CR. Grátis (sem I/O), não conta no cap.
        #    Sem isto, o combate autoritativo (resolver/turno inimigo) não tem CA/HP
        #    pra trabalhar e a morte volta a depender de regex.
        if "ca" not in dados:
            stats = stats_inimigo(
                ficha=str(dados.get("ficha", "")),
                nome=str(dados.get("nome", iid)),
            )
            if not dados.get("ficha"):
                # Nenhum dos elos pegou: números inventados. Visível no estado
                # (o /debug e o CombatTracker leem daqui) e no log.
                dados["ficha_fonte"] = "generico"
                log.warning(
                    "statblock_generico_aplicado",
                    id=iid,
                    nome=dados.get("nome", ""),
                    ca=stats.ca,
                    hp=stats.hp_max,
                )
            working_mem.aplicar_stats_inimigo(iid, stats.ca, stats.hp_max)
    if carregadas:
        log.info("bestiario_fichas_carregadas", quantidade=carregadas)
    return carregadas
