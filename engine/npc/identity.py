"""
Registro canônico de identidade de NPC — uma chave por pessoa, para sempre.

Por que existe: 3 playtests seguidos (01-05/07) com a MESMA raiz — cada NPC
    tinha N chaves independentes espalhadas (presença, trust, inimigo, voz,
    retrato). Name-reveal criava um NPC NOVO em vez de renomear ("kael" nasceu
    duplicado do monge); atacar "o monge" gravava trust numa 3ª chave curta que
    nenhum outro sistema lia; o retrato mudava de rosto quando o id mudava.
    Este módulo é a fonte única: todo id "falado"/derivado resolve pra UMA
    chave canônica, e o rename preserva a seed do retrato (decisão 05/07:
    "nome vence, retrato preservado").
Dependências: nenhuma externa — funções puras sobre a WorkingMemory (os dados
    vivem em SceneState.npc_registro/npc_aliases, serializados via dm_state).
Armadilha: NÃO importar engine.llm.extractor aqui (o extractor importa este
    módulo — ciclo). Os helpers de normalização são locais de propósito.

Exemplo:
    canonico = registrar_npc(wm, "monge-da-taverna", "Monge da Taverna")
    novo = revelar_nome(wm, "monge-da-taverna", "Kael")
    # → "kael"; retrato_seed(wm, "kael") == "monge-da-taverna" (rosto estável)
    resolver_falado(wm, "monge")  # → "kael" (via alias do id antigo)
"""

import re
import unicodedata
from typing import Any

import structlog

log = structlog.get_logger()

# Neutro da escala de trust 0-3 (Schema v1.2) — o snapshot usa default 1.
_TRUST_NEUTRO = 1

# Tokens estruturais ignorados no match de subconjunto (resolver_falado).
_ESTRUTURAIS = frozenset({
    "o", "a", "os", "as", "de", "da", "do", "das", "dos", "e", "em",
    "no", "na", "nos", "nas", "um", "uma", "ao", "aos",
})

# Janela de APRESENTAÇÃO — o NPC declara o próprio nome OU um terceiro revela
# o nome dele ("Aquele é... Gorvoth", resposta a "qual é o nome dele?").
# Mesmo vocabulário da guarda de name-reveal do extractor
# (_e_apelido_do_jogador), aqui na direção oposta: detectar o reveal pra
# RENOMEAR em vez de criar NPC novo.
# NAME-REVEAL-DUP-1 (playtest 10/07): "aquele é"/"aquela é" (revelação em 3ª
# pessoa distal — alguém aponta e nomeia outro NPC) faltava; só "este é"/
# "esta é" (proximal, tipo apresentar quem chegou) estava coberto.
_RE_APRESENTACAO = (
    r"\b(?:sou(?:\s+eu)?|me\s+chamo|meu\s+nome\s+e|se\s+chama|chamam[\s-]?me|"
    r"pode(?:m)?\s+me\s+chamar\s+de|este\s+e|esta\s+e|aquele\s+e|aquela\s+e|"
    r"apresento)\b"
)


def _translit(texto: str) -> str:
    """Acentos → ASCII (espelho local do helper do extractor — sem ciclo)."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalizar_reveal(texto: str) -> str:
    """_translit + lower + colapsa reticências.

    NAME-REVEAL-DUP-1 (playtest 10/07): "Aquele é... Gorvoth" nunca casava —
    "..." é PAUSA dramática dentro da MESMA fala em PT-BR, não fim de frase,
    mas a janela `[^.!?\\n]` do reveal trata qualquer "." como fronteira e
    nunca atravessava a reticência. Compartilhado por `_pos_reveal` e
    `alvo_do_reveal` pra manter as posições consistentes entre as duas.
    """
    return re.sub(r"\.{2,}", " ", _translit(texto).lower())


def _kebab(texto: str) -> str:
    """Nome → id kebab-case ASCII estável (espelho local, mesma regra)."""
    return re.sub(r"[^a-z0-9-]+", "-", _translit(texto).lower())[:48].strip("-")


def _tokens_uteis(nid: str) -> set[str]:
    """Tokens não-estruturais de um id, transliterados."""
    return {
        t for t in re.split(r"[\s-]+", _translit(str(nid)).lower())
        if t and t not in _ESTRUTURAIS
    }


def _registro(wm: Any) -> dict[str, dict]:
    return wm.scene.npc_registro


def _aliases(wm: Any) -> dict[str, str]:
    return wm.scene.npc_aliases


# ── API pública ───────────────────────────────────────────────────────────────


def resolver_npc(wm: Any, npc_id: str) -> str:
    """Id (possivelmente antigo/alias) → chave canônica. Identidade se desconhecido."""
    return _aliases(wm).get(npc_id, npc_id)


def registrar_npc(wm: Any, npc_id: str, nome: str | None = None) -> str:
    """Garante a entrada canônica de um NPC. Idempotente; retorna a chave canônica.

    A retrato_seed nasce = id de criação e NUNCA muda depois (nem no rename) —
    é ela que mantém o mesmo rosto Pollinations pra sempre.
    """
    canonico = resolver_npc(wm, npc_id)
    entrada = _registro(wm).get(canonico)
    if entrada is None:
        _registro(wm)[canonico] = {
            "nome": (nome or canonico.replace("-", " ").title()).strip()[:60],
            "retrato_seed": canonico,
        }
    elif nome and not entrada.get("nome"):
        entrada["nome"] = nome.strip()[:60]
    return canonico


def garantir_registro(wm: Any) -> None:
    """Backfill: todo NPC em npcs_presentes ganha entrada canônica.

    Cobre os NPCs do módulo (que entram via inferência Neo4j, sem passar pelos
    call-sites de registro) sem tocar o bootstrap da sessão.
    """
    for nid in list(wm.npcs_presentes):
        registrar_npc(wm, str(nid))


def retrato_seed(wm: Any, npc_id: str) -> str:
    """Seed do retrato Pollinations — id ORIGINAL de criação, estável pós-rename."""
    canonico = resolver_npc(wm, npc_id)
    entrada = _registro(wm).get(canonico)
    return str(entrada.get("retrato_seed", canonico)) if entrada else canonico


def resolver_falado(wm: Any, id_falado: str) -> str | None:
    """Id derivado da FALA ("ataco o monge") → chave canônica de um presente.

    Ordem: alias/canônico exato → subconjunto de tokens único entre os
    presentes ("monge" ⊆ "monge-da-taverna-kaelmund"). Ambíguo (0 ou 2+
    candidatos) → None, o caller decide o fallback. Conservador de propósito:
    nunca adivinha entre dois NPCs.
    """
    if not id_falado:
        return None
    canonico = resolver_npc(wm, id_falado)
    presentes_canon = {resolver_npc(wm, str(p)) for p in wm.npcs_presentes}
    if canonico in presentes_canon:
        return canonico
    tokens_falado = _tokens_uteis(id_falado)
    if not tokens_falado:
        return None
    candidatos = [
        p for p in presentes_canon if tokens_falado <= _tokens_uteis(p)
    ]
    return candidatos[0] if len(candidatos) == 1 else None


def revelar_nome(wm: Any, id_atual: str, nome_novo: str) -> str:
    """NPC declara o nome ("Sou Kael") → a chave canônica MIGRA pro nome.

    Decisão 05/07 ("nome vence, retrato preservado"): a nova chave é o kebab do
    nome revelado (ids limpos no grafo/prompt), mas a retrato_seed da entrada
    original viaja junto — o rosto não muda. O id antigo vira alias; todo estado
    (trust/voz/inimigo/presença) migra via fundir_estado.
    Colisão (o nome revelado JÁ é outro NPC registrado): funde no existente.
    """
    de = resolver_npc(wm, id_atual)
    para = _kebab(nome_novo)
    if not para or para == de:
        if de in _registro(wm) and nome_novo.strip():
            _registro(wm)[de]["nome"] = nome_novo.strip()[:60]
        return de
    registrar_npc(wm, de)
    entrada_de = _registro(wm).pop(de)
    if para in _registro(wm):
        # Colisão: "Kael" já existe — preserva a entrada de destino e funde.
        log.info("npc_reveal_colisao_fundido", de=de, para=para)
    else:
        _registro(wm)[para] = {
            "nome": nome_novo.strip()[:60],
            # A seed do retrato NUNCA re-seeda — herda da entrada original.
            "retrato_seed": entrada_de.get("retrato_seed", de),
        }
    _aliases(wm)[de] = para
    # Aliases antigos que apontavam pro id que acabou de migrar seguem a corrente.
    for alias, destino in list(_aliases(wm).items()):
        if destino == de:
            _aliases(wm)[alias] = para
    fundir_estado(wm, de, para)
    log.info("npc_nome_revelado", de=de, para=para)
    return para


def _trust_mais_forte(a: int | None, b: int | None) -> int | None:
    """Decisão 05/07 ("estado mais forte vence"): o valor mais distante do
    neutro (1) prevalece; empate de distância → o mais HOSTIL (menor). O mundo
    não perdoa um ataque porque o NPC trocou de nome."""
    if a is None:
        return b
    if b is None:
        return a
    da, db = abs(a - _TRUST_NEUTRO), abs(b - _TRUST_NEUTRO)
    if da != db:
        return a if da > db else b
    return min(a, b)


def fundir_estado(wm: Any, de_id: str, para_id: str) -> None:
    """Migra todo estado de `de_id` pra `para_id` nos substates da WM.

    trust: mais-forte-vence; voz/estado emocional/agenda: destino mantém o que
    tem, adota o do alias onde estiver vazio; inimigos_combate: entrada migra
    (flag relacao_abalada viaja); presença/apresentados: substituição sem dup.
    Afeto Neo4j NÃO é migrado aqui (remoto/async) — escritas futuras já vão
    pra chave canônica, o histórico antigo fica órfão no grafo (aceito).
    """
    if de_id == para_id:
        return
    scene = wm.scene
    # trust — mais forte vence
    t_de = scene.trust_levels.pop(de_id, None)
    t_para = scene.trust_levels.get(para_id)
    t_final = _trust_mais_forte(t_para, t_de)
    if t_final is not None:
        scene.trust_levels[para_id] = t_final
    # estado emocional — destino vence, alias preenche
    emo_de = scene.npc_estados_emocionais.pop(de_id, None)
    if emo_de and para_id not in scene.npc_estados_emocionais:
        scene.npc_estados_emocionais[para_id] = emo_de
    # voz TTS — destino vence, alias preenche
    vozes = getattr(wm.party, "npc_vozes", None)
    if isinstance(vozes, dict):
        voz_de = vozes.pop(de_id, None)
        if voz_de and para_id not in vozes:
            vozes[para_id] = voz_de
    # agenda narrativa — destino vence, alias preenche
    agenda = wm.narrative.agenda_npcs
    ag_de = agenda.pop(de_id, None)
    if ag_de and para_id not in agenda:
        agenda[para_id] = ag_de
    # inimigo em combate — migra a entrada inteira (relacao_abalada viaja)
    inim = wm.combat.inimigos_combate
    dados_de = inim.pop(de_id, None)
    if dados_de is not None:
        if para_id in inim:
            if dados_de.get("relacao_abalada"):
                inim[para_id]["relacao_abalada"] = True
        else:
            dados_de["nome"] = _registro(wm).get(para_id, {}).get(
                "nome", dados_de.get("nome", para_id)
            )
            inim[para_id] = dados_de
    # presença — substitui sem duplicar
    presentes = wm.npcs_presentes
    if de_id in presentes:
        if para_id in presentes:
            presentes.remove(de_id)
        else:
            presentes[presentes.index(de_id)] = para_id
    if de_id in scene.npcs_apresentados:
        scene.npcs_apresentados.discard(de_id)
        scene.npcs_apresentados.add(para_id)


def detectar_name_reveal(narracao: str, nome: str) -> bool:
    """True quando a narração APRESENTA alguém com este nome ("Sou Kael.",
    "me chamo Kael", "este é Kael"). Janela de 40 chars entre o verbo de
    apresentação e o nome — mesma folga da guarda do extractor."""
    return _pos_reveal(narracao, nome) is not None


def _pos_reveal(narracao: str, nome: str) -> int | None:
    """Posição (no texto normalizado) do início da frase de apresentação."""
    if not nome.strip():
        return None
    narr = _normalizar_reveal(narracao)
    nome_re = re.escape(_translit(nome).lower().strip())
    m = re.search(rf"{_RE_APRESENTACAO}[^.!?\n]{{0,40}}\b{nome_re}\b", narr)
    return m.start() if m else None


def _npcs_ancorados_em(wm: Any, janela: str) -> list[str]:
    """Presentes cujo token útil (≥3 chars) aparece na janela de texto dada."""
    ancorados: list[str] = []
    for p in {resolver_npc(wm, str(x)) for x in wm.npcs_presentes}:
        tokens = {t for t in _tokens_uteis(p) if len(t) >= 3}
        if any(re.search(rf"\b{re.escape(t)}\b", janela) for t in tokens):
            ancorados.append(p)
    return ancorados


def alvo_do_reveal(
    wm: Any, narracao: str, nome: str, *, contexto_extra: str = ""
) -> str | None:
    """Quem está revelando o nome? O NPC presente ANCORADO na narração.

    "O monge abaixa o capuz. 'Sou Kael.'" → o alvo do rename é o presente cujo
    token útil (≥3 chars) aparece na janela de ~120 chars ANTES da frase de
    apresentação. Exigir a âncora textual evita o erro grave da heurística
    "cena com 1 NPC": um recém-chegado dizendo "Sou Kael" numa cena onde só
    Brennan estava NÃO pode renomear Brennan. Ambíguo (0 ou 2+ presentes
    ancorados) → None; o caller registra o candidato como NPC novo (fluxo
    de sempre).

    NPC-REVEAL-TELEMETRIA-1 (playtest 06/07): o caso ambíguo logava só o id do
    candidato, sem contexto suficiente pra calibrar a heurística de âncora
    quando o problema reaparecer. Loga aqui (não no caller) porque é aqui que
    vivem a posição do reveal e a contagem de ancorados.

    NAME-REVEAL-DUP-1 (playtest 10/07): "qual é o nome dele, o grandão de
    barba espessa?" → "Aquele é... Gorvoth" — o descritor do alvo só aparece
    na PERGUNTA do jogador, nunca repetido pela narração do Mestre. Sem
    âncora na narração, `contexto_extra` (o texto do jogador NESTE turno) é
    tentado como segunda fonte — só quando a narração sozinha não ancorou
    ninguém, nunca para desempatar uma ambiguidade já existente nela.
    """
    pos = _pos_reveal(narracao, nome)
    if pos is None:
        return None
    janela = _normalizar_reveal(narracao)[max(0, pos - 120) : pos]
    ancorados = _npcs_ancorados_em(wm, janela)
    if not ancorados and contexto_extra:
        ancorados = _npcs_ancorados_em(wm, _normalizar_reveal(contexto_extra))
    if len(ancorados) == 1:
        return ancorados[0]
    trecho = narracao[max(0, pos - 60) : pos + 90].strip()[:150]
    log.info(
        "npc_name_reveal_ambiguo",
        candidato=nome, trecho=trecho, candidatos_ancorados=len(ancorados),
    )
    return None
