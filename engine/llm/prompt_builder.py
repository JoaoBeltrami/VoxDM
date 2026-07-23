"""
Monta o prompt final para o LLM a partir do contexto pré-assembleado.

Por que existe: separa a lógica de formatação do prompt da lógica de busca,
    garantindo que o prompt_builder seja puro (sem I/O) e testável isoladamente.
Dependências: apenas stdlib — recebe dados já montados pelo context_builder
Armadilha: lie_content nunca deve chegar ao LLM como string vazia — se for None,
    passar instrução de evasão; se for str, passar como mentira direta.

Exemplo:
    msgs = montar_mensagens(contexto, master_system)
    # → [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
"""

import re
from pathlib import Path
from typing import Any

import structlog

from config import settings
from engine.llm.amarelada import e_cena_sombria
from engine.llm.types import (
    RE_COMBATE as _RE_COMBATE,
)
from engine.llm.types import (
    RE_ROLAGEM as _RE_ROLAGEM,
)
from engine.llm.types import (
    ContextoMontado,
    SecretVisivel,
)
from engine.magic.spell_list import nivel_da_spell
from engine.memory.item_authority import nota_item_ausente

# Re-exportados para compatibilidade com importações existentes
__all__ = ["ContextoMontado", "SecretVisivel", "montar_mensagens", "invalidar_cache",
           "validar_master_system", "_RE_ROLAGEM", "_RE_COMBATE", "_LEMBRETE_SAIDA"]

log = structlog.get_logger()

# Caminhos dos prompts
_MASTER_SYSTEM_PATH = Path(__file__).parent / "prompts" / "master_system.md"
_DICE_PATH          = Path(__file__).parent / "prompts" / "dice.md"
_COMBAT_PATH        = Path(__file__).parent / "prompts" / "combat.md"
_SAVES_PATH         = Path(__file__).parent / "prompts" / "saves.md"
_QUESTS_PATH        = Path(__file__).parent / "prompts" / "quests.md"
_SOCIAL_PATH        = Path(__file__).parent / "prompts" / "social.md"
_RECAP_PATH         = Path(__file__).parent / "prompts" / "recap.md"
_INTRO_SYSTEM_PATH  = Path(__file__).parent / "prompts" / "intro_system.md"
_INTRO_FALLBACK_PATH = Path(__file__).parent / "prompts" / "intro_fallback.md"
_SESSION_ZERO_PATH  = Path(__file__).parent / "prompts" / "session_zero.md"
_DM_PROFILES_DIR    = Path(__file__).parent / "prompts" / "dm_profiles"
# Fragmentos condicionais (Frente B — gating contextual, 27/05)
# Injetados só quando a cena pede, não em todo turno. Economia: ~200-300
# tok/turno em exploração calma (~50% das sessões reais).
_FRAGMENTS_DIR      = Path(__file__).parent / "prompts" / "fragments"
_FRAG_VOZ_DUPLA     = _FRAGMENTS_DIR / "voz_dupla.md"
_FRAG_MARKERS_LISTA = _FRAGMENTS_DIR / "markers_lista.md"
# Canon do módulo ativo — guarda contra canon-break (teste #3: LLM improvisou o
# próprio Valdrek vivo e ele virou companion). Hardcoded enquanto o módulo é
# único; Schema v2 move isto para o JSON do módulo.
_FRAG_CANON         = _FRAGMENTS_DIR / "canon.md"
# Contrato de ficção sombria — injetado quando GRIMDARK_ATIVO e (dm_profile=="sombrio"
# ou cena contém keywords de atrocidade). ~900 chars, instrui o LLM a narrar sem
# fade-to-black/moralização. Ver engine/llm/amarelada.py para detecção de amarelada.
_FRAG_GRIMDARK      = _FRAGMENTS_DIR / "grimdark.md"

# Perfis válidos — alinhar com SessaoConfig.dm_profile e WorkingMemory.dm_profile
_DM_PROFILES_VALIDOS: frozenset[str] = frozenset({
    "rigoroso", "equilibrado", "tranquilo", "rule_of_cool", "sombrio",
})

# Tamanho mínimo aceitável para um prompt (em chars) — evita servir arquivo corrompido
_PROMPT_MIN_CHARS = 100

# MESTRE-MOVER-LOCAL (playtest 21/06): o Mestre esquece de emitir [CENA] quando
# o jogador viaja, e a engine acha que ninguém saiu do local inicial. Detecta
# DESLOCAMENTO EXPLÍCITO na fala do jogador (verbo de movimento + preposição de
# destino) pra injetar um lembrete de [CENA] nesse turno. Conservador: exige
# preposição de destino — "vou atacar"/"vamos lutar" (sem destino) NÃO casam.
_RE_VIAGEM = re.compile(
    # Verbo de movimento + preposição de DESTINO. Sem o "a" pelado (ambíguo com
    # "a"+infinitivo: "volto a perguntar") e excluindo "ao/à que" relativo
    # ("vou ao que interessa" não é viagem).
    r"\b(?:vou|vamos|sigo|seguimos|viajo|viajamos|parto|partimos|volto|voltamos|"
    r"retorno|retornamos)\s+(?:para|pra|at[ée]|aos?|às?|rumo|de\s+volta|"
    r"em\s+direção)\b(?!\s+que\b)"
    r"|\brumo\s+a[oô]?\b"
    # "me dirijo a/ao <lugar>" — o destino NÃO pode ser pronome ("me dirijo a
    # ele" = falar com alguém, não viajar).
    r"|\b(?:me\s+dirijo|nos\s+dirigimos)\s+(?:a|ao|à|aos|às|para|pra|at[ée])\s+"
    r"(?!ele\b|ela\b|eles\b|elas\b|voc[êe]\b|vc\b|mim\b|ti\b|si\b|n[óo]s\b)"
    r"|\b(?:entro|entramos|adentro|adentramos)\s+(?:n[oa]s?|em)\b"
    r"|\b(?:saio|sa[íi]mos)\s+d[oae]s?\b"
    r"|\b(?:atravesso|atravessamos|cruzo|cruzamos)\b"
    r"|\b(?:vou|vamos)\s+embora\b",
    re.IGNORECASE,
)

# COMPANION-NUDGE-1 (playtest 10/07, sess-cc69c30f7c4f): contratação de
# mercenário inequívoca (aperto de mão, "selando o acordo", LLM até emitiu
# [XP: +100] pelo marco) e [COMPANION_ADD] nunca veio — a instrução JÁ estava
# no prompt duas vezes (social.md + markers_lista.md), o modelo simplesmente
# não obedeceu. Mesmo padrão do nudge de [CENA]/[INIMIGO]: detecta a fala do
# JOGADOR fechando o recrutamento e reforça o marcador pontualmente nesse
# turno. Conservador — linguagem de FECHAMENTO de acordo, não negociação
# ainda em curso ("quanto você cobra?" não casa).
_RE_RECRUTAMENTO = re.compile(
    r"bem[- ]vind[oa]\s+a[oa]?\s*(?:bando|grupo|time|equipe|jornada)|"
    r"\b(?:anda|vem|venha|vamos)\s+comigo\b|"
    r"\b(?:(?:você|voce)\s+)?(?:est[áa]|fica)\s+contratad[oa]\b|"
    r"\beu\s+(?:te\s+|o\s+|a\s+)?contrato\b|"
    r"\bjunt[ae]-?se\s+a\s+mim\b|"
    r"\b(?:fechado|combinado|trato\s+feito)\b.{0,30}\b(?:moedas?|ouro|contrat)",
    re.IGNORECASE,
)

# Cache com hot reload por mtime — quando o arquivo .md muda, próxima leitura
# pega o novo conteúdo sem precisar reiniciar o servidor. Estrutura:
#   path -> (mtime_visto, conteudo_ou_string_vazia)
# string vazia em conteudo significa "arquivo ausente ou inválido" e tem TTL
# de mtime=0.0 — sempre re-tenta na próxima chamada.
_cache_prompts: dict[Path, tuple[float, str]] = {}


def _ler_prompt(path: Path) -> str | None:
    """Lê um prompt .md com cache invalidado por mtime.

    Permite editar prompts ao vivo (mestre veterano ajustando comportamento)
    sem reiniciar a API — próximo turno pega versão nova.

    Returns:
        str com conteúdo se OK, None se ausente ou muito curto.
    """
    try:
        if not path.exists():
            # Re-tenta a cada chamada (arquivo pode aparecer)
            return None
        mtime_atual = path.stat().st_mtime
        cached = _cache_prompts.get(path)
        if cached and cached[0] == mtime_atual:
            return cached[1] or None
        conteudo = path.read_text(encoding="utf-8")
        if len(conteudo) < _PROMPT_MIN_CHARS:
            log.warning("prompt_muito_curto", path=str(path), chars=len(conteudo))
            _cache_prompts[path] = (mtime_atual, "")
            return None
        if cached and cached[1] and cached[0] != mtime_atual:
            log.info("prompt_recarregado", path=path.name, mtime=mtime_atual)
        _cache_prompts[path] = (mtime_atual, conteudo)
        return conteudo
    except Exception as e:
        log.warning("prompt_leitura_falhou", path=str(path), erro=str(e))
        return None

# Budget de tokens por camada (aproximado — 1 token ≈ 4 chars)
BUDGET_WORKING   = 1600   # 40% — nunca cortado
BUDGET_EPISODICO = 1200   # 30%
BUDGET_SEMANTICO = 1200   # 30%
BUDGET_REGRAS    =  225   # combate, saves, condições de status — top 3 chunks SRD

# Lembrete de formato — posicionado ao fim do system prompt para reforçar aderência
# após os blocos de lore/regras que "enterram" a Regra Zero do master_system.
# Mantido curto para não inflar tokens: master_system já cobre as regras completas;
# aqui repetimos só os pontos ÚNICOS que ele não repete (2-4 frases, "comece direto").
_LEMBRETE_SAIDA = (
    "\n---\n"
    "[LEMBRETE] PT-BR falado — sem markdown, listas, asteriscos. "
    "2 a 4 frases, máximo 80 palavras — acima disso a fala é CORTADA no meio. "
    "Termine com ponto/!/? completo — nunca no meio de uma frase. "
    "Comece DIRETO na narração, sem prefácio."
)



# Fallback inline para master_system — usado se o .md sumir/corromper.
# Mantemos curto e auto-suficiente; nunca é o caminho normal.
_MASTER_SYSTEM_FALLBACK = (
    "Você é VoxDM, um mestre de RPG de mesa narrando em português brasileiro. "
    "Seja imersivo, conciso e consistente com o contexto fornecido. "
    "Nunca use markdown, asteriscos, listas ou parênteses técnicos. "
    "Máximo 80 palavras por resposta."
)


def _carregar_master_system() -> str:
    """Carrega prompt do mestre com hot reload — fallback inline se ausente."""
    return _ler_prompt(_MASTER_SYSTEM_PATH) or _MASTER_SYSTEM_FALLBACK


def _carregar_dice() -> str | None:
    """Guia de rolagem de dados — com hot reload. None se ausente."""
    return _ler_prompt(_DICE_PATH)


def _carregar_voz_dupla() -> str | None:
    """Fragmento de voz dupla Mestre vs NPC. Gated em montar_mensagens."""
    return _ler_prompt(_FRAG_VOZ_DUPLA)


def _carregar_markers_lista() -> str | None:
    """Fragmento com lista completa de marcadores. Gated em montar_mensagens."""
    return _ler_prompt(_FRAG_MARKERS_LISTA)


def _cena_dramatica(wm: Any) -> bool:
    """Heurística pra decidir se a cena tem ritmo dramático.

    Critérios — qualquer um basta:
      - em combate ativo (precisa dos markers de combate)
      - pacing >= 4.0 (ação acelerando ou clímax)
      - há cliffhanger pendente (cena guardada pra encerrar dramatico)
      - já há fios_soltos ou agenda_npcs ativos (o LLM precisa saber quais
        marcadores existem pra manter coerência)

    Quando False, a lista detalhada de marcadores é omitida. O master_system.md
    ainda menciona que marcadores existem e quais são os básicos — o LLM não
    perde a noção, só não recebe a tabela completa quando não precisa.
    """
    if getattr(wm, "em_combate", False):
        return True
    if getattr(wm, "pacing_nivel", 3.0) >= 4.0:
        return True
    if getattr(wm, "cliffhanger_pendente", ""):
        return True
    if getattr(wm, "fios_soltos", []):
        return True
    if getattr(wm, "agenda_npcs", {}):
        return True
    return False


def _carregar_combat() -> str | None:
    """Guia de combate — com hot reload. None se ausente."""
    return _ler_prompt(_COMBAT_PATH)


def _carregar_saves() -> str | None:
    """Guia de salvaguardas — com hot reload. None se ausente."""
    return _ler_prompt(_SAVES_PATH)


def _carregar_quests() -> str | None:
    """Instrução de sinalização de quest — com hot reload. None se ausente."""
    return _ler_prompt(_QUESTS_PATH)


def _carregar_social() -> str | None:
    """Camada social — injetada em cena social (NPCs presentes, fora de combate)."""
    return _ler_prompt(_SOCIAL_PATH)


def _tier_do_turno(wm: Any, transcricao: str) -> str:
    """"epico" nos momentos que pedem peso; "seco" no resto.

    TOM-CHAPADO-1 (auditoria 22/07): `montar_brief` aceita `tier`, mas o caminho
    de produção nunca o passava — TODO turno saía "TOM: turno comum, 1-3 frases".
    Clímax da campanha, epílogo e picos de tensão saíam secos como "ando até a
    porta". Sinais robustos e baratos: a fase do arco (autoridade da engine) e o
    pacing; a linha ENGINE de um crítico/abate também levanta o tom.
    """
    fase = getattr(wm, "arc_fase", "normal")
    # Clímax e epílogo pedem peso. "concluida" NÃO entra (verificação 23/07): a
    # campanha já acabou — a tela de fim entregou o Momento de CONSEGUI. Se o
    # jogador dispensa e segue jogando, todo turno pós-fim viraria "momento-chave"
    # pra sempre; o desfecho relaxa pro tom comum, como um denouement.
    if fase in ("climax", "epilogo"):
        return "epico"
    if float(getattr(wm, "pacing_nivel", 0) or 0) >= 7:
        return "epico"
    t = (transcricao or "").upper()
    if "ENGINE:" in t and ("NATURAL" in t or "ABATE" in t or "MORTO" in t):
        return "epico"
    return "seco"


def _blocos_de_cena(contexto: Any) -> list[str]:
    """Estado + protocolo + nudges que o rolling summary NÃO consegue codificar.

    NUDGES/COMBATE/MESMICE-BRIEF (auditoria 22/07): o caminho do brief (produção,
    BRIEF_ATIVO=True) nasceu enxuto demais e deixou de fora blocos que o caminho
    legado sempre teve. Um resumo de médio prazo carrega "o que aconteceu", mas
    não carrega CONTRA QUEM o jogador luta agora (CA/PV/ficha do inimigo), o
    PROTOCOLO de como rodar o combate (combat.md), a VOZ distinta de cada NPC
    (social.md + assinaturas) nem os empurrões pontuais de marcador ([CENA],
    [INIMIGO], [COMPANION], [ROLAGENS]). Sem isso: o Mestre narra a luta cego,
    todo NPC soa igual, e o mundo não muda quando o jogador viaja.

    Reusa os MESMOS carregadores do caminho legado — o conteúdo não pode divergir,
    só o gate. PURA sobre o contexto; não muta nada.
    """
    wm = contexto.working_memory
    transcricao = getattr(contexto, "transcricao_atual", "") or ""
    blocos: list[str] = []

    # Anti-repetição — as imagens sensoriais dos últimos turnos. GUARDA-REPETICAO
    # (auditoria 22/07): alimentada todo turno, nunca LIDA no brief. Lendo em vez
    # de ouvir, reabrir com "o frio cortante da noite" 5 vezes é gritante. O
    # resumo não codifica a imagem EXATA — por isso viaja verbatim (cap 4, ~160c).
    ambiente = list(getattr(wm, "ambiente_recente", []) or [])
    if ambiente:
        blocos.append(
            "\n=== AMBIENTAÇÃO JÁ DESCRITA (não repita estas imagens) ===\n"
            + "\n".join(f"• {a}" for a in ambiente)
        )

    em_combate = bool(getattr(wm, "em_combate", False))
    acao_combate = bool(_RE_COMBATE.search(transcricao))

    # ── Combate: protocolo (estático) + estado (dinâmico) ─────────────────────
    if em_combate or acao_combate:
        combat_texto = _carregar_combat()
        if combat_texto:
            blocos.append(f"\n{combat_texto}")
        saves_texto = _carregar_saves()
        if saves_texto:
            blocos.append(f"\n{saves_texto}")
    if em_combate:
        # Contra quem, quantos, feridos, ficha SRD, distância, rodada — o bloco
        # que o brief simplesmente não tinha (COMBATE-CEGO-BRIEF-1).
        estado_combate = wm.combat.to_prompt() if getattr(wm, "combat", None) else ""
        if estado_combate:
            blocos.append(f"\n=== {estado_combate}")

    # ── Social: camada + assinatura de voz por NPC ────────────────────────────
    npcs_presentes = list(getattr(wm, "npcs_presentes", []) or [])
    if not em_combate and npcs_presentes:
        social_texto = _carregar_social()
        if social_texto:
            blocos.append(f"\n{social_texto}")
        voz_dupla = _carregar_voz_dupla()
        if voz_dupla:
            blocos.append(f"\n{voz_dupla}")
        try:
            from engine.memory.working_memory import _id_para_nome as _id_nome_voz
            from engine.npc.identity import retrato_seed as _seed_identidade
            from engine.npc.persona import bloco_assinaturas

            def _seed_voz(nid: str) -> str:
                try:
                    return _seed_identidade(wm, nid)
                except Exception:
                    return nid

            bloco_voz_npc = bloco_assinaturas(npcs_presentes, _id_nome_voz, seed_de=_seed_voz)
            if bloco_voz_npc:
                blocos.append(bloco_voz_npc)
        except Exception as e:
            log.warning("brief_voz_npc_falhou", erro=str(e)[:80])

    # ── Nudges de marcador (mesmos do caminho legado) ─────────────────────────
    if _RE_VIAGEM.search(transcricao):
        blocos.append(
            "\n=== DESLOCAMENTO PEDIDO ===\n"
            "O jogador indicou ir a outro lugar. Se a narração SAIR do local atual, "
            "EMITA [CENA: local-id|Nome|hora] no fim da resposta — local de passagem "
            "(estrada, trilha, portão, floresta) TAMBÉM é cena nova: improvise um id "
            "kebab-case (ex.: [CENA: estrada-norte|Estrada ao Norte|noite]). Sem o "
            "marcador a engine não atualiza local, NPCs presentes, trilha nem imagem."
        )
    if em_combate and not getattr(wm, "inimigos_combate", None):
        blocos.append(
            "\n=== COMBATE SEM COMBATENTE REGISTRADO ===\n"
            "O combate está ativo mas NENHUM oponente foi registrado. EMITA "
            "[INIMIGO: id|Nome|indice-srd] pra cada oponente desta luta AGORA — "
            "sem isso a engine não resolve ataques, não aplica dano e não encerra "
            "o combate direito. Se a luta já se resolveu narrativamente (rendição, "
            "aperto de mãos, sparring encerrado), deixe a cena esfriar em paz."
        )
    if _RE_RECRUTAMENTO.search(transcricao):
        blocos.append(
            "\n=== RECRUTAMENTO SENDO FECHADO ===\n"
            "O jogador está fechando a contratação/aliança de um NPC nesta fala. "
            "Se o acordo for selado NESTA resposta, EMITA "
            "[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano] (tipo: hireling|"
            "familiar|animal|summon) — sem isso o aliado não aparece na ficha "
            "nem luta ao seu lado."
        )
    roll_vis = getattr(wm, "roll_visibility", "result_only")
    if roll_vis in ("open", "result_only") and (em_combate or _RE_ROLAGEM.search(transcricao)):
        blocos.append(
            "\n[ROLAGENS DO MESTRE] Sempre que o Mestre rolar um dado internamente "
            "(ataque de NPC, teste secreto, evento aleatório), escreva "
            "[Rolagem visível: dX=Y] ANTES da narração do resultado, onde X é o "
            "tipo do dado e Y é o valor (ex: [Rolagem visível: d20=14]). "
            "Limite: no máximo 1 por turno. Não inventar números — usar o dado sorteado."
        )

    return blocos


def _carregar_recap() -> str | None:
    """Instrução de recap de abertura (sessão continuada). None se ausente."""
    return _ler_prompt(_RECAP_PATH)


def _carregar_intro_system() -> str:
    """Prompt de abertura (intro_system.md) com hot reload via _ler_prompt.
    Fallback pro master_system se ausente — a abertura nunca fica sem persona."""
    return _ler_prompt(_INTRO_SYSTEM_PATH) or _carregar_master_system()


def _carregar_intro_fallback() -> str:
    """Texto de abertura de EMERGÊNCIA (LLM falhou na intro). Prosa pura — vai pro
    TTS direto, sem markdown. Compliant com intro_system (nada de 'bem-vindo'
    genérico). Fallback inline curto se o arquivo sumir."""
    return _ler_prompt(_INTRO_FALLBACK_PATH) or (
        "O ar à sua volta está parado, pesado de expectativa. "
        "Alguma coisa, em algum lugar, aguarda o seu próximo passo."
    )


def _carregar_dm_profile(profile: str) -> str | None:
    """Carrega overlay de personalidade do Mestre. None se inválido ou ausente.

    Equilibrado é o tom default já contido no master_system — o overlay
    apenas reforça; perfis distintos sobrescrevem o tom.
    """
    if profile not in _DM_PROFILES_VALIDOS:
        log.warning("dm_profile_invalido", profile=profile)
        return None
    return _ler_prompt(_DM_PROFILES_DIR / f"{profile}.md")


def invalidar_cache() -> None:
    """Invalida caches de prompts — útil em testes (força releitura)."""
    _cache_prompts.clear()


def validar_master_system() -> tuple[bool, str]:
    """
    Verifica se master_system.md existe e tem conteúdo mínimo.

    Returns:
        (ok, mensagem) — ok=True se válido, mensagem descreve o problema caso contrário.
    """
    if not _MASTER_SYSTEM_PATH.exists():
        return False, f"Arquivo ausente: {_MASTER_SYSTEM_PATH}"
    try:
        conteudo = _MASTER_SYSTEM_PATH.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Erro de leitura: {e}"
    if len(conteudo) < _PROMPT_MIN_CHARS:
        return False, f"Arquivo muito curto ({len(conteudo)} chars — mínimo {_PROMPT_MIN_CHARS})"
    return True, "ok"


def _formatar_chunks(
    chunks: list[dict[str, Any]],
    limite_chars: int,
    incluir_prefixo: bool = True,
) -> str:
    """Formata chunks como texto, respeitando limite de caracteres aproximado.

    Args:
        chunks: lista de chunks recuperados do Qdrant.
        limite_chars: budget aproximado em caracteres.
        incluir_prefixo: se True, prefixa cada chunk com [source_name].
            Para chunks de regras SRD, passar False — prefixo coloca o
            modelo em "modo de leitura de documento" em vez de narração.
    """
    if not chunks:
        return ""
    partes: list[str] = []
    total = 0
    for chunk in chunks:
        texto = chunk.get("text", "")
        if incluir_prefixo:
            nome = chunk.get("source_name", chunk.get("source_id", ""))
            linha = f"[{nome}] {texto}"
        else:
            linha = texto
        if total + len(linha) > limite_chars:
            break
        partes.append(linha)
        total += len(linha)
    return "\n\n".join(partes)


def _formatar_relacoes(relacoes: list[dict[str, Any]]) -> str:
    if not relacoes:
        return ""
    # Dedup ANTES do cap (B4 — dieta mecânica de tokens): relacoes_grafo concatena
    # os laços de até 4 entidades, e laços bidirecionais (A→ALIADO_DE→B aparece ao
    # consultar A e ao consultar B) + alvos compartilhados por NPCs distintos geram
    # linhas idênticas. Uma linha repetida não carrega informação nova pro LLM —
    # só gasta token e, pior, consome o cap de 10 empurrando laços ÚNICOS pra fora.
    # Dedup por (tipo, alvo) preservando a 1ª ocorrência → o cap passa a valer
    # sobre relações distintas. Não muda o significado: o LLM usa a existência do
    # laço, não a contagem.
    linhas: list[str] = []
    vistas: set[tuple[str, str]] = set()
    for r in relacoes:
        chave = (r["tipo"], r.get("alvo_nome", r["alvo_id"]))
        if chave in vistas:
            continue
        vistas.add(chave)
        linhas.append(f"  {chave[0]}: {chave[1]}")
        if len(linhas) >= 10:  # cap mantido (teste #3: 13 laços/turno inflavam)
            break
    return "Relações no grafo:\n" + "\n".join(linhas)


def _formatar_secrets(secrets: list[SecretVisivel]) -> str:
    """Formata secrets como instruções internas ao LLM — não visíveis ao jogador."""
    if not secrets:
        return ""
    partes: list[str] = ["[INSTRUÇÕES INTERNAS — NÃO REVELAR AO JOGADOR]"]
    for s in secrets:
        if s.revelar:
            partes.append(
                f"NPC {s.npc_id} pode revelar agora: \"{s.content}\""
            )
        elif s.lie_content:
            partes.append(
                f"NPC {s.npc_id} sabe a verdade mas vai mentir: \"{s.lie_content}\""
            )
        else:
            # lie_content None → evasão narrativa
            partes.append(
                f"NPC {s.npc_id} sabe algo mas deve desviar do assunto sem revelar."
            )
    return "\n".join(partes)


def _montar_mensagens_brief(
    contexto: ContextoMontado,
    master_system_override: str | None = None,
) -> list[dict[str, str]]:
    """Modo NarrationBrief (BRIEF_ATIVO=True) — o system enxuto da tese LLM-fino.

    Composição: persona (master_system) + contrato de markers (sempre — o LLM
    continua operando [DANO]/[CENA]/etc.) + overlay de perfil + grimdark (mesmas
    condições do modo normal — segurança de rota não é negociável) + regras SRD
    do turno (mecânica que a engine JÁ buscou pro casting) + o BRIEFING
    (engine/authority/brief.py, com rolling summary sempre incluso). O que o
    modo normal injeta e este NÃO: para_texto() completo, chunks de lore
    episódicos/semânticos, relações do grafo, social/combat/saves/dice.md,
    fios/agenda/cartas/pacing — a aposta é que o rolling + o brief carregam o
    contexto que importa. Validação = playtest com a flag ligada.
    """
    wm = contexto.working_memory
    master_system = master_system_override or _carregar_master_system()
    secoes: list[str] = [master_system, ""]

    markers = _carregar_markers_lista()
    if markers:
        secoes.append(markers)

    dm_profile_attr = getattr(wm, "dm_profile", "equilibrado")
    if dm_profile_attr not in ("equilibrado", "sombrio"):
        overlay = _carregar_dm_profile(dm_profile_attr)
        if overlay:
            secoes.append(overlay)

    if settings.GRIMDARK_ATIVO:
        _transcricao = getattr(contexto, "transcricao_atual", "") or ""
        _scene = getattr(wm, "scene", None)
        if (
            dm_profile_attr == "sombrio"
            or e_cena_sombria(_transcricao)
            or bool(getattr(_scene, "cena_sombria_reativa", False))
        ):
            grimdark_frag = _ler_prompt(_FRAG_GRIMDARK)
            if grimdark_frag and len(grimdark_frag) >= _PROMPT_MIN_CHARS:
                secoes.append(grimdark_frag)
                log.info("grimdark_fragmento_injetado", dm_profile=dm_profile_attr)

    # Regras SRD do turno (spell detector) — mecânica engine-fornecida, faz
    # parte dos "fatos que a engine entrega", não do dump cortado.
    if contexto.chunks_regras:
        regras = "\n".join(str(c.get("text", c)) for c in contexto.chunks_regras[:3])
        if regras.strip():
            secoes.append(f"\n=== MECÂNICA DO TURNO (SRD) ===\n{regras}")

    # Catálogo de quests + como sinalizar avanço. QUEST-DEADLOCK-1 (playtest
    # 21/07): este bloco não existia no caminho do brief, então o Mestre nunca
    # via um único id de quest — e sem id não há `[Q: ...]`, sem `[Q: ...]` não
    # há avanço, sem avanço a espinha da guerra não anda e a campanha não chega
    # a final nenhum. ~800 chars estáveis por sessão (prefixo cacheável).
    _quests_catalogo = getattr(wm, "quests_modulo", "")
    if _quests_catalogo:
        _quests_instrucao = _carregar_quests()
        secoes.append(
            f"\n{_quests_catalogo}"
            + (f"\n{_quests_instrucao}" if _quests_instrucao else "")
        )

    # Estado de combate, protocolo, voz de NPC e nudges — tudo que o rolling
    # summary não codifica (COMBATE-CEGO / MESMICE / NUDGES-MORTOS, auditoria
    # 22/07). Reusa os carregadores do caminho legado; gate espelhado.
    secoes.extend(_blocos_de_cena(contexto))

    from engine.authority.brief import montar_brief  # lazy — evita ciclo em import
    _tier = _tier_do_turno(wm, contexto.transcricao_atual or "")
    brief = montar_brief(wm, contexto.transcricao_atual or "", tier=_tier)
    secoes.append("\n" + brief.to_prompt())

    # DIRETOR DE ARCO (passo 4): a voz da engine dirigindo o desfecho — pressão
    # de escalada quando a espinha arma, diretiva de CLÍMAX quando um final
    # dispara, semente de EPÍLOGO pra encerrar. Vazio no fluxo normal; vale nos
    # DOIS caminhos (brief e legado). Falha silenciosa nunca derruba o turno.
    try:
        from engine.authority.arco import diretiva_de_arco
        _bloco_arco = diretiva_de_arco(contexto.working_memory)
        if _bloco_arco:
            secoes.append(_bloco_arco)
    except Exception as _e_arco:
        log.warning("arco_diretiva_falhou", erro=str(_e_arco)[:100])

    system_content = "\n".join(secoes) + _LEMBRETE_SAIDA
    turnos = wm.dialogo_recente
    historico = turnos[:-1] if turnos else []
    mensagens: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    for turno in historico:
        role = "user" if turno.falante == "player" else "assistant"
        mensagens.append({"role": role, "content": turno.texto})
    mensagens.append({"role": "user", "content": contexto.transcricao_atual})
    log.info(
        "prompt_brief",
        chars_system=len(system_content),
        turnos_historico=len(historico),
    )
    return mensagens


def montar_mensagens(
    contexto: ContextoMontado,
    master_system_override: str | None = None,
) -> list[dict[str, str]]:
    """
    Monta a lista de mensagens para o LLM a partir do contexto pré-montado.

    O histórico de diálogo é passado como pares user/assistant reais — não como
    texto no system prompt — para aproveitar o modo de chat nativo do modelo.

    Args:
        contexto: ContextoMontado produzido pelo context_builder.
        master_system_override: Substitui o master_system.md (útil em testes).

    Returns:
        Lista de dicts {role, content} prontos para o Groq/Ollama.
        Estrutura: [system, user?, assistant?, ..., user_atual]
    """
    # ── Session Zero (Ritual P3): entrevista de criação substitui TUDO ───────
    # Sem RAG, sem combate, sem markers — só o entrevistador + diálogo. O
    # [FICHA] no pipeline desliga o flag e o próximo turno volta ao normal.
    if getattr(contexto.working_memory, "session_zero_ativa", False):
        sz = _ler_prompt(_SESSION_ZERO_PATH)
        if sz:
            mensagens_sz: list[dict[str, str]] = [{"role": "system", "content": sz}]
            turnos_sz = contexto.working_memory.dialogo_recente
            for turno in (turnos_sz[:-1] if turnos_sz else []):
                role = "user" if turno.falante == "player" else "assistant"
                mensagens_sz.append({"role": role, "content": turno.texto})
            mensagens_sz.append({"role": "user", "content": contexto.transcricao_atual})
            log.info("prompt_session_zero", chars_system=len(sz), turnos=len(turnos_sz))
            return mensagens_sz
        # session_zero.md ausente/corrompido → degrada pro fluxo normal

    # ── NarrationBrief (kill-switch BRIEF_ATIVO, decisão 12/07) ──────────────
    # A aposta engine-first completa: em vez do dump do para_texto() + RAG +
    # fragmentos de cena, o system vira persona + contrato de markers + o
    # BRIEFING curto (fatos de cena + estado vital + evento de mundo + rolling
    # summary — orçamento travado em 01/07). Wirado atrás de flag DESLIGADA
    # (padrão grimdark): zero mudança até o Beltrami ligar no .env e validar a
    # qualidade narrativa ao vivo. Regras SRD (mecânica de magia que a engine
    # buscou) e grimdark (segurança de rota) acompanham o brief.
    if settings.BRIEF_ATIVO and contexto.working_memory is not None:
        return _montar_mensagens_brief(contexto, master_system_override)

    master_system = master_system_override or _carregar_master_system()

    # ── System message: identidade + estado da cena (sem diálogo) ────────────
    secoes: list[str] = [master_system, ""]

    # ── Frente B: fragmentos condicionais (27/05) ────────────────────────────
    # Voz dupla: injeta só quando o LLM já registrou voz de algum NPC. Em
    # sessões 100% narração de mob/exploração, economiza ~600 chars (~150 tok).
    wm = contexto.working_memory
    chars_voz_dupla = 0
    chars_markers = 0
    # TOKENS-21K: acumuladores pra decompor o antigo bucket "outros" (~10k chars
    # invisíveis no breakdown). social.md (~6k) era o maior culpado oculto.
    chars_canon = 0
    chars_saves = 0
    chars_social = 0
    chars_relacoes = 0
    chars_dice = 0
    chars_quests = 0
    chars_rolling = 0
    if getattr(wm, "npc_vozes", {}):
        voz_dupla = _carregar_voz_dupla()
        if voz_dupla:
            secoes.append(voz_dupla)
            chars_voz_dupla = len(voz_dupla)

    # Canon — duas camadas. (1) A REGRA genérica (canon.md): mortos continuam
    # mortos, segredos saem por conquista, canon não muda pra agradar o jogador.
    # (2) Os FATOS específicos deste módulo (Schema v2 `canon`, data-driven via
    # context_builder) — ex: "Valdrek está morto há gerações". Sem isto o LLM
    # "ressuscita" figuras canônicas (teste #3). A regra é engine-wide; os fatos
    # são do autor do módulo.
    canon = _ler_prompt(_FRAG_CANON)
    if canon:
        secoes.append(canon)
        chars_canon += len(canon)
    fatos_canon = getattr(contexto, "canon_modulo", [])
    if fatos_canon:
        linhas_canon = "\n".join(f"• {f}" for f in fatos_canon)
        _bloco_canon = f"\nFATOS CANÔNICOS DESTE MUNDO (imutáveis):\n{linhas_canon}"
        secoes.append(_bloco_canon)
        chars_canon += len(_bloco_canon)

    # Markers list: injeta só quando a cena tem ritmo dramático (em combate,
    # pacing alto, cliffhanger, fios ou agendas ativos). Em exploração calma
    # o master_system já menciona que markers existem — a tabela completa
    # custaria ~1500 chars (~380 tok) sem necessidade real.
    if _cena_dramatica(wm):
        markers = _carregar_markers_lista()
        if markers:
            secoes.append(markers)
            chars_markers = len(markers)

    # Overlay de perfil do DM — sobrepõe o tom default quando perfil != equilibrado.
    # "equilibrado" é o tom JÁ contido em master_system.md — injetar overlay é
    # ~150 tokens/turno de redundância (6k tokens em sessão de 40 turnos).
    # Pulamos quando perfil é o default.
    dm_profile_attr = getattr(contexto.working_memory, "dm_profile", "equilibrado")
    if dm_profile_attr not in ("equilibrado", "sombrio"):
        overlay = _carregar_dm_profile(dm_profile_attr)
        if overlay:
            secoes.append(overlay)
            log.info("dm_profile_aplicado", profile=dm_profile_attr)

    # Contrato de ficção sombria — injetado quando kill-switch ativo E
    # (dm_profile="sombrio" OU keywords de atrocidade na transcrição atual OU
    # escalação reativa grudada na cena — GRIM-REATIVA-1: o LLM já amarelou
    # nesta cena, então o fragmento acompanha a rota grim até a cena mudar).
    # Posicionado APÓS o overlay de perfil pra ter prioridade de instrução.
    # "sombrio" não tem overlay de dm_profiles/ — ele só usa este fragmento.
    if settings.GRIMDARK_ATIVO:
        _transcricao = getattr(contexto, "transcricao_atual", "") or ""
        _scene = getattr(contexto.working_memory, "scene", None)
        _usa_grimdark = (
            dm_profile_attr == "sombrio"
            or e_cena_sombria(_transcricao)
            or bool(getattr(_scene, "cena_sombria_reativa", False))
        )
        if _usa_grimdark:
            grimdark_frag = _ler_prompt(_FRAG_GRIMDARK)
            if grimdark_frag and len(grimdark_frag) >= _PROMPT_MIN_CHARS:
                secoes.append(grimdark_frag)
                log.info("grimdark_fragmento_injetado", dm_profile=dm_profile_attr)

    # ── Camada de combate — parte do PREFIXO ESTÁTICO (cache-friendly) ────────
    # combat.md + saves.md são INSTRUÇÕES de comportamento ("como rodar combate"),
    # não estado dinâmico. Por isso vivem aqui, junto da persona/markers, e não
    # depois do RAG/working-memory. Isso (a) agrupa todo o conteúdo estático num
    # prefixo contíguo — cacheável por prefixo durante uma sequência de turnos de
    # combate (o maior dreno de tokens do projeto) — e (b) deixa o estado dinâmico
    # (inimigos, HP, fichas) na posição de recência, logo antes do diálogo.
    # _combat_md_presente é computado aqui pois o bloco de REGRAS SRD abaixo
    # também depende dele (regras só entram fora de combate).
    _em_combate_ativo = contexto.working_memory.em_combate
    _acao_combate = bool(_RE_COMBATE.search(contexto.transcricao_atual))
    _combat_md_presente = _em_combate_ativo or _acao_combate
    chars_combat = 0
    if _combat_md_presente:
        combat_texto = _carregar_combat()
        if combat_texto:
            secoes.append(f"\n{combat_texto}")
            chars_combat = len(combat_texto)
            log.info(
                "combat_md_injetado",
                em_combate=_em_combate_ativo,
                acao_detectada=_acao_combate,
                chars_combat=chars_combat,
                transcricao=contexto.transcricao_atual[:60],
            )
        saves_texto = _carregar_saves()
        if saves_texto:
            _bloco_saves = f"\n{saves_texto}"
            secoes.append(_bloco_saves)
            chars_saves = len(_bloco_saves)

    # Camada social — cena de conversa/barganha/interrogatório (NPCs presentes,
    # fora de combate). Parte do prefixo estático (cache-friendly), igual combat.md.
    # Mutuamente exclusiva com combat.md (esta exige NÃO-combate), então nunca soma
    # ao prompt de combate nem ao seu teto de budget. Resolve drift #61 (social.md
    # existia mas nunca era carregado).
    if (not _em_combate_ativo) and bool(getattr(wm, "npcs_presentes", [])):
        social_texto = _carregar_social()
        if social_texto:
            _bloco_social = f"\n{social_texto}"
            secoes.append(_bloco_social)
            chars_social = len(_bloco_social)

        # Assinatura de voz por NPC (mestre veterano — NPCs distintos). Determinística
        # pela SEED de identidade (id original de criação — NPC-IDENTIDADE 05/07:
        # rename via name-reveal não troca a personalidade), injetada só fora de
        # combate e quando há NPC presente. Mantém o ferreiro ≠ bruxa entre sessões.
        # Import local espelha o _id_para_nome lazy abaixo (evita ciclo de import).
        from engine.memory.working_memory import _id_para_nome as _id_nome_voz
        from engine.npc.identity import retrato_seed as _seed_identidade
        from engine.npc.persona import bloco_assinaturas

        def _seed_voz(nid: str) -> str:
            try:
                return _seed_identidade(wm, nid)
            except Exception:
                return nid  # stub de teste sem scene.npc_registro

        bloco_voz_npc = bloco_assinaturas(
            getattr(wm, "npcs_presentes", []), _id_nome_voz, seed_de=_seed_voz
        )
        if bloco_voz_npc:
            secoes.append(bloco_voz_npc)

    # Working memory sem diálogo — histórico vai como pares de mensagem abaixo.
    # Subclasse injetada separadamente para não inflar para_texto() com campo raro.
    wm_texto = contexto.working_memory.para_texto(incluir_dialogo=False)
    player_subclass = getattr(contexto.working_memory, "player_subclass", "")
    if player_subclass:
        # Insere "Subclasse: X" logo após a linha "Personagem: ..." no para_texto()
        wm_texto = wm_texto.replace(
            "\nLocal:",
            f"\nSubclasse: {player_subclass}\nLocal:",
            1,
        )
    secoes.append(wm_texto)

    # PT-6 (playtest #7): autoridade de item — INFORMA (não proíbe) quando o
    # jogador cita usar um consumível que não está no inventário. Por turno
    # (depende da transcrição), fica na seção dinâmica. Detecção conservadora.
    _nota_item = nota_item_ausente(
        contexto.transcricao_atual, getattr(wm, "player_inventory", [])
    )
    if _nota_item:
        secoes.append(f"\n[NOTA DA ENGINE] {_nota_item}")

    # Relações do grafo (NPCs presentes)
    if contexto.relacoes_grafo:
        _bloco_rel = _formatar_relacoes(contexto.relacoes_grafo)
        secoes.append(_bloco_rel)
        chars_relacoes = len(_bloco_rel)

    # Memória semântica (conteúdo do módulo)
    sem_texto = _formatar_chunks(contexto.chunks_semanticos, limite_chars=BUDGET_SEMANTICO * 4)
    if sem_texto:
        secoes.append(f"\n=== CONTEÚDO DO MÓDULO ===\n{sem_texto}")

    # Regras SRD relevantes (saves, condições, checks fora de combate).
    # _combat_md_presente já foi computado no bloco de combate (prefixo estático).
    # combat.md já cobre os modificadores relevantes — injetar regras SRD
    # simultaneamente duplica conteúdo e estoura o budget do Groq.
    # Prefixo [source_name] removido — chunks puros mantêm o modelo em modo
    # de narração em vez de "modo de leitura de documento".
    regras_texto = ""
    if not _combat_md_presente:
        regras_texto = _formatar_chunks(
            contexto.chunks_regras,
            limite_chars=BUDGET_REGRAS * 4,
            incluir_prefixo=False,
        )
        if regras_texto:
            secoes.append(f"\nREGRAS DE JOGO:\n{regras_texto}")

    # Guia de rolagem de dados — injetado apenas quando o jogador rola um dado
    # E NÃO está em combate: combat.md (já injetado) cobre as 3 camadas de dados
    # em combate, então somar dice.md por cima é redundante e estoura o budget de
    # combate (~580 chars de duplicata — teste 13/06: prompt_excede_budget em
    # TODO turno de combate com [Rolagem]). Fora de combate, dice.md é o único guia.
    if _RE_ROLAGEM.search(contexto.transcricao_atual) and not _em_combate_ativo:
        dice_texto = _carregar_dice()
        if dice_texto:
            _bloco_dice = f"\n{dice_texto}"
            secoes.append(_bloco_dice)
            chars_dice = len(_bloco_dice)
            log.info("dice_md_injetado", transcricao=contexto.transcricao_atual[:60])

    # Instrução de progressão de quests — injetada apenas quando o módulo define quests
    if getattr(contexto.working_memory, "quests_modulo", ""):
        quests_texto = _carregar_quests()
        if quests_texto:
            _bloco_quests = f"\n{quests_texto}"
            secoes.append(_bloco_quests)
            chars_quests = len(_bloco_quests)

    # ── Features de Mestre Veterano ──────────────────────────────────────────

    # Pacing meter — lido aqui pra ficar disponível em decisões de gating
    # antes do bloco que injeta a instrução de pacing em si.
    pacing = getattr(contexto.working_memory, "pacing_nivel", 3.0)

    # Feat 1: Fios Soltos — tópicos narrativos em aberto, para o mestre não esquecer
    fios = getattr(contexto.working_memory, "fios_soltos", [])
    if fios:
        lista_fios = "\n".join(f"• {f}" for f in fios)
        secoes.append(
            f"\n=== FIOS NARRATIVOS EM ABERTO ===\n{lista_fios}\n"
            "Trate-os como oportunidades — mencione ou aprofunde 1 por turno se a cena permitir."
        )

    # PLAY5-QUEST: missões improvisadas pelo Mestre (fora do catálogo). Sem este
    # bloco o Mestre "esquece" objetivos que ele mesmo deu e o jogador fica sem
    # rumo. Só as ativas entram no prompt (concluídas vivem só no quest log).
    qimprov = getattr(contexto.working_memory, "quests_improvisadas", [])
    ativas = [q for q in qimprov if q.get("status") != "concluida"]
    if ativas:
        lista_q = "\n".join(
            f"• {q.get('titulo', '')}" + (f": {q.get('objetivo', '')}" if q.get("objetivo") else "")
            for q in ativas
        )
        secoes.append(
            f"\n=== MISSÕES EM ANDAMENTO ===\n{lista_q}\n"
            "São objetivos que você deu ao jogador. Mantenha-os vivos — referencie, "
            "avance ou complique conforme a cena pedir. Não os deixe sumir."
        )

    # Feat 2: Cliffhanger — encerramento dramático planejado
    cliffhanger = getattr(contexto.working_memory, "cliffhanger_pendente", "")
    if cliffhanger:
        secoes.append(
            f"\n=== CLIFFHANGER GUARDADO ===\n{cliffhanger}\n"
            "Quando o jogador indicar que quer encerrar a sessão (\"parar\", \"sair\", \"por hoje é\"), "
            "narre esta cena dramática como última linha antes de encerrar."
        )

    # Feat 3: Agenda Paralela dos NPCs — motivações em background.
    # Filtra só NPCs presentes na cena atual — agendas de NPCs ausentes
    # custam tokens sem influenciar a narração imediata (eles voltam ao prompt
    # quando o jogador entrar no local deles).
    agenda = getattr(contexto.working_memory, "agenda_npcs", {})
    if agenda:
        presentes = set(getattr(contexto.working_memory, "npcs_presentes", []) or [])
        if presentes:
            agenda_relevante = {k: v for k, v in agenda.items() if k in presentes}
        else:
            # Sem npcs_presentes definidos — preserva comportamento anterior (tudo)
            agenda_relevante = agenda
        if agenda_relevante:
            items = "\n".join(f"• {npc}: {plano}" for npc, plano in agenda_relevante.items())
            secoes.append(
                f"\n=== AGENDA DOS NPCs (background) ===\n{items}\n"
                "Estes planos correm em paralelo à ação do jogador. Deixe transparecer através "
                "de comportamento, não de monólogo — sem revelar diretamente."
            )

    # Feat 4: Cartas de Improviso — elementos prontos para usar.
    # Cartas servem pra acender uma cena ou complicar exploração calma. Em
    # combate denso (pacing alto) viram ruído — o LLM já tem urgência de
    # mecânica e narrativa pra resolver sem precisar de improviso.
    cartas = getattr(contexto.working_memory, "cartas_improviso", [])
    if cartas and not _em_combate_ativo and pacing < 6.0:
        lista_cartas = "\n".join(f"• {c}" for c in cartas)
        secoes.append(
            f"\n=== CARTAS DE IMPROVISO (use 1 se a cena pedir) ===\n{lista_cartas}"
        )

    # Feat 5: Pacing Meter — ajusta densidade narrativa
    # Thresholds calibrados para o pacing_nivel real da WorkingMemory:
    #   - padrão: 3.0; exploração: +0.2/turno; combate: +1.5/turno
    #   - 3+ turnos calmos: -0.3/turno; pós-combate: -0.5/turno
    # BAIXO era ≤1.5, tornando-o virtualmente inatingível (30+ turnos calmos).
    # Corrigido para ≤2.5: 3 turnos calmos após combate já o ativam (3.0 → 2.5→2.2→1.9).
    if pacing >= 8.0:
        secoes.append(
            "\n[PACING: CLÍMAX] — Tensão máxima. Frases curtas, urgentes. "
            "Sem pausas descritivas longas. Cada palavra conta."
        )
    elif pacing >= 6.0:
        secoes.append(
            "\n[PACING: ALTO] — Ação acelerada. Descrições vívidas mas rápidas. "
            "Não deixe o ritmo cair."
        )
    elif pacing <= 2.5:
        secoes.append(
            "\n[PACING: BAIXO] — Momento de respiro. Ambiente, detalhes sensoriais, "
            "personagens com textura. Pode haver silêncio significativo."
        )
        # Reincorporação (mestre veterano #2): a calmaria é a hora de PUXAR um fio
        # de volta — o mundo lembra e se conecta. Só dispara em lull real (pacing
        # baixo) E com fio em aberto; custo-zero quando não há o que reincorporar.
        if fios:
            secoes.append(
                "\n[REINCORPORAR] — O ritmo esfriou: use a calmaria pra puxar de volta "
                "UM fio em aberto (acima). Um NPC o menciona, um detalhe o ressuscita, "
                "uma consequência aparece. Reincorporar dá direção sem forçar ação."
            )

    # Mundo Vivo — Relógios de Ameaça: o mundo anda sem o jogador. Invisíveis
    # pra ele; o LLM usa pra dosar presságios e urgência. Irrupção é one-shot.
    narrative = getattr(contexto.working_memory, "narrative", None)
    if narrative is not None:
        # Ritual de mesa — modo episódio: pós-clímax com ritmo assentado, o
        # mestre propõe encerrar UMA vez (one-shot consumido aqui).
        if getattr(contexto.working_memory, "modo_episodio", False) and narrative.momento_de_fecho():
            secoes.append(
                "\n=== MOMENTO DE FECHO (modo episódio) ===\n"
                "O clímax passou e o ritmo assentou — ponto clássico de encerrar. "
                "Proponha ao jogador, na voz do mestre, encerrar o episódio aqui; "
                "plante o gancho do próximo ([CLIFFHANGER: texto]). Se ele aceitar, "
                "narre um epílogo de 2-3 frases. Se recusar, siga o jogo sem insistir."
            )
        irrompido = narrative.consumir_relogio_irrompido()
        if irrompido:
            secoes.append(
                f"\n=== RELÓGIO ESTOUROU: {irrompido} ===\n"
                "A ameaça se concretiza AGORA — irrompa o evento nesta cena "
                "(chegada, ataque, notícia, consequência visível). Sem adiar."
            )
        if narrative.relogios:
            linhas_rel = "\n".join(
                f"• {r['nome']}: {'▓' * r['atual']}{'░' * (r['max'] - r['atual'])} {r['atual']}/{r['max']}"
                for r in narrative.relogios.values()
            )
            secoes.append(
                f"\n=== RELÓGIOS DE AMEAÇA (invisíveis ao jogador) ===\n{linhas_rel}\n"
                "Avançam com o tempo (engine). Use [RELOGIO_AVANCA: id] quando o "
                "jogador ignora a ameaça ou ela ganha força. Semeie presságios "
                "proporcionais ao preenchimento — quase cheio = sinais urgentes."
            )
            # Presságio (mestre veterano #3): relógio quase cheio → telegrafar
            # CONCRETO. O veterano mostra a fumaça antes do fogo. ≥70% e ainda não
            # estourado (estouro tem o caminho próprio acima). Token-light: só
            # quando há ameaça realmente iminente.
            _quase = [
                r for r in narrative.relogios.values()
                if r.get("max", 0) > 0 and r.get("atual", 0) < r["max"]
                and r["atual"] / r["max"] >= 0.7
            ]
            if _quase:
                _mais = max(_quase, key=lambda r: r["atual"] / r["max"])
                secoes.append(
                    f"\n[PRESSÁGIO] — '{_mais['nome']}' está quase no limite. Plante "
                    "NESTA cena um sinal CONCRETO de que a ameaça se aproxima: um "
                    "presságio, um mensageiro ofegante, um tremor, um silêncio errado, "
                    "algo que deveria estar ali e não está. Telegrafe sem revelar o relógio."
                )

        # PLAY5-FRONTS — ameaças latentes (fronts autorais ainda não introduzidos).
        # Diferente dos relógios ativos: o jogador NÃO as vê e elas não andam até
        # serem estabelecidas na cena. O LLM as semeia e, quando a narrativa
        # justifica, ativa via [RELOGIO: id|...] (vira relógio visível e correndo).
        if getattr(narrative, "fronts_latentes", None):
            linhas_lat = "\n".join(
                f"• [{fid}] {f['nome']}" for fid, f in narrative.fronts_latentes.items()
            )
            secoes.append(
                f"\n=== AMEAÇAS LATENTES (o jogador AINDA não as conhece) ===\n{linhas_lat}\n"
                "Forças que o autor plantou no mundo, mas que o jogador ainda não "
                "viu. NÃO as anuncie como ameaça pronta nem como contagem — semeie "
                "presságios sutis (rumores, sinais, tensão de fundo). Quando a cena "
                "ESTABELECER a ameaça de verdade, emita [RELOGIO: id|nome|segmentos] "
                "com o id entre colchetes para torná-la um relógio ativo e visível."
            )

        # Mundo Vivo P2 — NPC toma a iniciativa (one-shot da engine). O NPC
        # deixa de ser estátua reativa: a agenda dele vira movimento na cena.
        ini = narrative.consumir_iniciativa_npc()
        if ini is not None:
            from engine.memory.working_memory import _id_para_nome
            _npc_id, _plano, _presente = ini
            _nome = _id_para_nome(_npc_id)
            if _presente:
                secoes.append(
                    f"\n=== INICIATIVA DE NPC (NESTE turno) ===\n"
                    f'{_nome} age por vontade própria, movido pela agenda dele: "{_plano}". '
                    "Ele toma a iniciativa — aborda o jogador, interrompe, faz o movimento. "
                    "Não espere o jogador puxar."
                )
            else:
                secoes.append(
                    f"\n=== SINAL DE NPC (NESTE turno) ===\n"
                    f'Um sinal de {_nome} chega à cena agora — mensageiro, bilhete, rumor, '
                    f'som à distância — ligado à agenda dele: "{_plano}". '
                    "Encene o sinal, não o NPC em pessoa."
                )

        # Ritual P2 — perfil do jogador (gated: fora de combate + amostra ≥10
        # turnos + estilo realmente dominante). O mestre te conhece.
        if not getattr(contexto.working_memory, "em_combate", False):
            dom = narrative.estilo_dominante()
            if dom is not None:
                _cat, _n, _total = dom
                _rotulo = {
                    "combate": "resolver na lâmina",
                    "social": "resolver na conversa",
                    "exploracao": "explorar e investigar antes de agir",
                }[_cat]
                secoes.append(
                    f"\n=== PERFIL DO JOGADOR (meta) ===\n"
                    f"Nos últimos {_total} turnos, ele tende a {_rotulo} ({_n}/{_total}). "
                    "Prepare cenas que recompensem esse estilo — e de vez em quando o "
                    "desafie com o oposto. Pode comentar isso com leveza, como mestre "
                    "de mesa faz."
                )

    # Mundo Vivo P2 — ecos: retorno a local conhecido (one-shot). O local
    # LEMBRA do jogador; consequências viram reação concreta na cena.
    scene_state = getattr(contexto.working_memory, "scene", None)
    if scene_state is not None and scene_state.consumir_retorno_local():
        _eco_conseq = "; ".join(
            getattr(contexto.working_memory, "log_consequencias", [])
        ) or "nenhuma registrada — improvise um eco menor (alguém o reconhece)"
        _local_nome = getattr(contexto.working_memory, "location_nome", "") or "este local"
        secoes.append(
            f"\n=== RETORNO A LOCAL CONHECIDO ===\n"
            f"O jogador JÁ esteve em {_local_nome}. O local LEMBRA da passagem dele — "
            "mostre pelo menos UM eco concreto: NPC reage à visita anterior, marca que "
            f"ele deixou, boato sobre o que fez. Consequências registradas: {_eco_conseq}."
        )

    # Pilar Perigo — cicatrizes permanentes: NPCs notam e reagem a elas.
    cicatrizes = getattr(contexto.working_memory, "cicatrizes", [])
    if cicatrizes:
        lista_cic = "; ".join(cicatrizes)
        secoes.append(
            f"\n=== CICATRIZES DO PERSONAGEM ===\n{lista_cic}\n"
            "Marcas permanentes de quase-morte. NPCs atentos notam e reagem "
            "(respeito, medo, curiosidade) — referencie quando fizer sentido."
        )

    # Pilar Perigo — protocolo de 0 PV conforme a política de morte da sessão.
    # Injetado SÓ quando o jogador está caído: instrução de maior prioridade.
    if getattr(contexto.working_memory, "player_hp", 1) <= 0:
        if getattr(contexto.working_memory, "death_policy", "narrativo") == "mortal":
            secoes.append(
                "\n=== O PERSONAGEM ESTÁ A 0 PV — PROTOCOLO MORTAL ===\n"
                "Conduza salvaguardas contra a morte: peça d20 ao jogador "
                "(10+ = sucesso; 3 sucessos estabiliza, 3 falhas = MORTE REAL). "
                "Narre com peso e finalidade — sem milagre barato. Inimigos podem "
                "ignorá-lo caído ou tentar executá-lo (1 falha automática por golpe)."
            )
        else:
            secoes.append(
                "\n=== O PERSONAGEM CAIU A 0 PV — DERROTA COM CUSTO ===\n"
                "NÃO o mate. Narre a derrota com custo CONCRETO: captura, perda de "
                "item ([PERDEU: item]), resgate por aliado com dívida, ou cicatriz "
                "permanente ([CICATRIZ: texto]). Aplique [CURA: +1] ao retomar a "
                "consciência e mova a história adiante — derrota também é enredo."
            )

    # Repetition Guard — fatos âncora: o que JÁ foi narrado nesta sessão.
    # Injetado para evitar que o LLM re-narre descobertas do início da sessão
    # em ~40-50 turnos (sintoma clássico de janela de contexto curta).
    fatos_ancora = getattr(contexto.working_memory, "fatos_ancora", [])
    if fatos_ancora:
        lista_ancora = "\n".join(f"• {f}" for f in fatos_ancora)
        secoes.append(
            f"\n=== FATOS ESTABELECIDOS (não repetir narrativa já dita) ===\n{lista_ancora}\n"
            "Estes fatos já foram narrados. Não repita — avance a história."
        )

    # Repetition Guard SENSORIAL (REPETICAO-FRIO) — imagens de clima/ambiente já
    # usadas. O Mestre tende a reabrir todo turno com a MESMA imagem ("frio
    # cortante da noite"). Listamos as recentes pra ele variar ou omitir.
    ambiente_recente = getattr(contexto.working_memory, "ambiente_recente", [])
    if ambiente_recente:
        lista_amb = "\n".join(f"• {a}" for a in ambiente_recente)
        secoes.append(
            f"\n=== AMBIENTAÇÃO JÁ DESCRITA (não repita estas imagens) ===\n{lista_amb}\n"
            "Você já usou estas imagens de clima/sensação. Estabeleça o ambiente "
            "UMA vez — não reabra o turno com a mesma frase. Ser sensorial não é "
            "repetir a mesma imagem: varie a descrição ou apenas avance a cena."
        )

    # MESTRE-MOVER-LOCAL — nudge de [CENA]. Quando o jogador declara deslocamento
    # explícito, lembra o LLM de marcar a troca de cena se a narração chegar a um
    # local novo. Não muda estado (sem risco de teleporte falso) — só reforça a
    # emissão do marcador, que o LLM costuma esquecer.
    # SEM gate de combate (fix playtest 01/07, sess-7893f3bdbd28): "Eu entro na
    # casa" aconteceu com em_combate=True (combate-conversa que não encerrava) e
    # o nudge foi suprimido → [CENA] nunca veio → a engine achou que o jogador
    # nunca saiu da estrada e a cena "voltou pro local inicial" sem sentido. O
    # pressuposto "mudança de cena mid-combate é rara" foi refutado ao vivo;
    # ~230 chars é barato perto de perder a troca de cena.
    if _RE_VIAGEM.search(contexto.transcricao_atual or ""):
        # CENA-TRANSITO-1 (validações 16-18/07, 3/3 corridas): o nudge disparava
        # mas o Mestre NÃO emitia [CENA] quando o destino era local de PASSAGEM
        # (estrada, trilha) — não é location do módulo, e a instrução sugeria
        # local "de verdade"; o elenco da taverna seguia "presente" na estrada.
        # Texto afiado: trânsito CONTA como cena nova, improvise o id.
        secoes.append(
            "\n=== DESLOCAMENTO PEDIDO ===\n"
            "O jogador indicou ir a outro lugar. Se a narração SAIR do local atual, "
            "EMITA [CENA: local-id|Nome|hora] no fim da resposta — local de passagem "
            "(estrada, trilha, portão, floresta) TAMBÉM é cena nova: improvise um id "
            "kebab-case (ex.: [CENA: estrada-norte|Estrada ao Norte|noite]). Sem o "
            "marcador a engine não atualiza local, NPCs presentes, trilha nem imagem."
        )
        log.info("nudge_cena_injetado", transcricao=(contexto.transcricao_atual or "")[:60])

    # COMBATE-SEM-REGISTRO (playtest 05/07, sess-95a7c47468c5): um sparring
    # abriu em_combate mas NENHUM [INIMIGO] foi emitido a luta inteira — sem
    # combatente registrado o turno de inimigo da engine nunca roda, o dano
    # narrado nunca vira [DANO] aplicado (HP ficou 24/24 a sessão toda) e o
    # combate só morre pelo timeout de fantasma (6+ turnos de zumbi). Mesmo
    # padrão do nudge de [CENA]: não muda estado, só cobra o marcador. Custo
    # ~300 chars SÓ neste estado anômalo (combate ativo + zero registrados).
    _wm_nudge = contexto.working_memory
    if (
        _wm_nudge is not None
        and getattr(_wm_nudge, "em_combate", False)
        and not getattr(_wm_nudge, "inimigos_combate", None)
    ):
        secoes.append(
            "\n=== COMBATE SEM COMBATENTE REGISTRADO ===\n"
            "O combate está ativo mas NENHUM oponente foi registrado. EMITA "
            "[INIMIGO: id|Nome|indice-srd] pra cada oponente desta luta AGORA — "
            "sem isso a engine não resolve ataques, não aplica dano e não encerra "
            "o combate direito. Se a luta já se resolveu narrativamente (rendição, "
            "aperto de mãos, sparring encerrado), deixe a cena esfriar em paz."
        )
        log.info("nudge_inimigo_injetado")

    # COMPANION-NUDGE-1 (playtest 10/07): reforço pontual quando o jogador
    # fecha um recrutamento nesta fala — mesmo padrão do nudge de [INIMIGO].
    if _RE_RECRUTAMENTO.search(contexto.transcricao_atual or ""):
        secoes.append(
            "\n=== RECRUTAMENTO SENDO FECHADO ===\n"
            "O jogador está fechando a contratação/aliança de um NPC nesta fala. "
            "Se o acordo for selado NESTA resposta, EMITA "
            "[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano] (tipo: hireling|"
            "familiar|animal|summon) — sem isso o aliado não aparece na ficha "
            "nem luta ao seu lado."
        )
        log.info("nudge_companion_injetado")

    # Fase 5.7: instrução de visibilidade de rolagens do mestre.
    # "open" / "result_only" → LLM insere [Rolagem visível: dX=Y] ANTES de narrar
    #   qualquer rolagem interna (ataque de NPC, teste secreto, evento aleatório).
    # "narrated" → sem marker, número nunca aparece (roll behind the screen).
    #
    # Gated: só injeta quando há chance real do Mestre rolar — em combate ativo
    # ou quando o turno do jogador trouxe rolagem (chip de dado). Fora disso,
    # ~480 chars desperdiçados todo turno em cena social/exploração calma.
    roll_vis = getattr(contexto.working_memory, "roll_visibility", "result_only")
    if roll_vis in ("open", "result_only") and (
        _em_combate_ativo or _RE_ROLAGEM.search(contexto.transcricao_atual)
    ):
        secoes.append(
            "\n[ROLAGENS DO MESTRE] Sempre que o Mestre rolar um dado internamente "
            "(ataque de NPC, teste secreto, evento aleatório), escreva "
            "[Rolagem visível: dX=Y] ANTES da narração do resultado, onde X é o "
            "tipo do dado e Y é o valor (ex: [Rolagem visível: d20=14]). "
            "Limite: no máximo 1 por turno. Não inventar números — usar o dado sorteado."
        )

    # Magias conhecidas do personagem — restrição de repertório mágico.
    # Injetadas ANTES dos chunks episódicos para ter peso maior no system prompt.
    spells_conhecidas = getattr(contexto, "spells_conhecidas", [])
    if spells_conhecidas:
        # Agrupa por nível usando lookup estático (sem I/O)
        classe_attr = getattr(contexto.working_memory, "player_class", "")
        truques: list[str] = []
        por_nivel: dict[int, list[str]] = {}
        for nome in spells_conhecidas:
            nivel = nivel_da_spell(nome, classe_attr)
            if nivel == 0:
                truques.append(nome)
            elif nivel is not None:
                por_nivel.setdefault(nivel, []).append(nome)
            else:
                # Magia não encontrada na lista estática — ainda assim incluir
                por_nivel.setdefault(99, []).append(nome)
        linhas: list[str] = []
        if truques:
            linhas.append(f"Truques: {', '.join(truques)}")
        for nivel_k in sorted(k for k in por_nivel if k != 99):
            linhas.append(f"Nível {nivel_k}: {', '.join(por_nivel[nivel_k])}")
        if 99 in por_nivel:
            linhas.append(f"Outras: {', '.join(por_nivel[99])}")
        secoes.append(
            "\n=== MAGIAS CONHECIDAS DO PERSONAGEM ===\n"
            + "\n".join(linhas)
            + "\nO personagem SOMENTE conhece as magias acima. "
            "Se tentar conjurar outra, narre educadamente que não a domina."
        )
        log.info("spells_conhecidas_injetadas", total=len(spells_conhecidas))

    # Memória episódica (sessões anteriores)
    ep_texto = _formatar_chunks(contexto.chunks_episodicos, limite_chars=BUDGET_EPISODICO * 4)
    if ep_texto:
        secoes.append(f"\n=== SESSÕES ANTERIORES ===\n{ep_texto}")

    # Instruções de secrets (internas — não visíveis ao jogador)
    secrets_texto = _formatar_secrets(contexto.secrets_visiveis)
    if secrets_texto:
        secoes.append(f"\n{secrets_texto}")

    # Rolling summary — resumo contínuo da sessão como memória interna do
    # mestre. PROSA pura, sem === nem colchetes: rótulos de código disparam
    # "modo leitura de código" no LLM e degradam a narração.
    if settings.ROLLING_SUMMARY_ATIVO:
        _resumo_rolling = getattr(contexto.working_memory, "resumo_rolling", "")
        if _resumo_rolling:
            _bloco_rolling = (
                "\nVocê se lembra de tudo o que já aconteceu nesta sessão:\n"
                + _resumo_rolling
            )
            secoes.append(_bloco_rolling)
            chars_rolling = len(_bloco_rolling)

    # DIRETOR DE ARCO (passo 4): a voz da engine dirigindo o desfecho — pressão
    # de escalada quando a espinha arma, diretiva de CLÍMAX quando um final
    # dispara, semente de EPÍLOGO pra encerrar. Vazio no fluxo normal; vale nos
    # DOIS caminhos (brief e legado). Falha silenciosa nunca derruba o turno.
    try:
        from engine.authority.arco import diretiva_de_arco
        _bloco_arco = diretiva_de_arco(contexto.working_memory)
        if _bloco_arco:
            secoes.append(_bloco_arco)
    except Exception as _e_arco:
        log.warning("arco_diretiva_falhou", erro=str(_e_arco)[:100])

    system_content = "\n".join(secoes) + _LEMBRETE_SAIDA

    # Breakdown de chars por componente — diagnóstico de prompt inflado.
    # Útil pra calibrar quais blocos têm peso desproporcional em sessão real.
    # 1 token ≈ 4 chars; valores em chars são mais legíveis em log.
    chars_breakdown = {
        "master": len(master_system),
        "voz_dupla_frag": chars_voz_dupla,
        "markers_frag": chars_markers,
        "wm": len(wm_texto),
        "regras_srd": len(regras_texto),
        "combat_md": chars_combat,
        "semantica": len(sem_texto),
        "episodica": len(ep_texto),
        # TOKENS-21K: ex-"outros" agora decomposto. social.md era ~6k oculto;
        # relações do grafo (3 NPCs repetidos) e rolling summary são os outros pesos.
        "social_md": chars_social,
        "saves_md": chars_saves,
        "dice_md": chars_dice,
        "quests_md": chars_quests,
        "canon": chars_canon,
        "relacoes_grafo": chars_relacoes,
        "rolling_summary": chars_rolling,
        "lembrete_saida": len(_LEMBRETE_SAIDA),
    }
    # "outros" = resíduo após a decomposição acima — agora majoritariamente os
    # blocos inline dos Pilares (relógios, ameaças latentes, iniciativa NPC, perfil
    # do jogador, ecos, fios/cliffhanger/âncora, cartas, magias) + newlines do join.
    chars_breakdown["outros"] = max(
        0, len(system_content) - sum(chars_breakdown.values())
    )

    # Guard de budget — loga warning quando o system prompt excede o teto.
    # Target: ≤ 20 000 chars (≈ 5 700 tokens) para caber em 70B com respostas de
    # 400 tokens dentro de 6 000 TPM. Acima disso, o turn cascateia para 8B.
    # Não trunca — só observa para diagnóstico e eventual ajuste de prompts.
    _BUDGET_SYSTEM_CHARS = 20_000
    if len(system_content) > _BUDGET_SYSTEM_CHARS:
        log.warning(
            "prompt_excede_budget",
            chars=len(system_content),
            excesso=len(system_content) - _BUDGET_SYSTEM_CHARS,
            em_combate=getattr(contexto.working_memory, "em_combate", False),
            transcricao=contexto.transcricao_atual[:60],
        )

    # ── Histórico de diálogo como pares user/assistant ────────────────────────
    # dialogo_recente[-1] é o turno atual do jogador (já registrado antes de montar).
    # Passamos [-1] como a mensagem final; os anteriores viram histórico real.
    turnos = contexto.working_memory.dialogo_recente
    historico = turnos[:-1] if turnos else []  # tudo exceto o turno atual

    mensagens: list[dict[str, str]] = [{"role": "system", "content": system_content}]

    for turno in historico:
        role = "user" if turno.falante == "player" else "assistant"
        mensagens.append({"role": role, "content": turno.texto})

    # Turno atual — se dialogo_recente está vazio (chamada direta sem voice_runner)
    # usa transcricao_atual diretamente
    mensagens.append({"role": "user", "content": contexto.transcricao_atual})

    log.info(
        "prompt_montado",
        chars_system=len(system_content),
        chars_breakdown=chars_breakdown,
        turnos_historico=len(historico),
        chunks_semanticos=len(contexto.chunks_semanticos),
        chunks_episodicos=len(contexto.chunks_episodicos),
        secrets=len(contexto.secrets_visiveis),
    )

    return mensagens
