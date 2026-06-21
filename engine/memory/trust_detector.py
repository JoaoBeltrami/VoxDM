"""
Detecta mudanças de trust baseadas nas ações do jogador via regex.

Por que existe: trust_levels existe na WorkingMemory mas nunca muda durante o jogo.
    Esta camada analisa o texto do jogador e retorna deltas (npc_id, delta) para
    atualizar o trust após cada turno sem chamar o LLM.
Dependências: apenas stdlib (re)
Armadilha: a detecção é conservadora — falso-negativo é preferível a falso-positivo.
    Melhor não detectar uma traição do que punir o jogador por uma ação ambígua.

Exemplo:
    mudancas = detectar_mudancas_trust("eu ajudo Fael a se levantar", ["fael-valdreksson"])
    # → [("fael-valdreksson", +1)]
"""

import re

# Verbos de ação positiva DIRIGIDA a um NPC — ajuda, cura, presente, aliança.
#
# FILOSOFIA (conservadora): só verbos que implicam ação deliberada em benefício de alguém.
# Removidos: concordo (frequente e genérico), dou/dei (ambíguos), ofereço (frequente),
#            compartilho (genérico), concordo (sem contexto de NPC).
# Adicionados: perdoo (reconciliação explícita), elogio (reconhecimento),
#              cubro (cobertura em combate), ao lado de (luta junto).
_RE_POSITIVO = re.compile(
    r"\b("
    # ── Ação direta de benefício ───────────────────────────────────────────────
    r"ajudo|ajudei|ajudar|"
    r"salvo|salvei|salvar|"
    r"protejo|protegi|proteger|"
    r"curo|curei|curar|"
    r"(?<!me )defend(?:o|i|er)|"  # "defendo/defendi Bjorn"; "me defendo/defendi" (autodefesa) NÃO conta
    r"agradeço|agradeci|agradecer|"     # reconhecimento explícito — gesto comum de boa-fé
    r"presenteio|presenteei|"
    r"dou (?:minha|meu|um presente|uma poção|comida|ouro|dinheiro)|"  # dar item
    r"ofereço (?:minha|meu|ajuda|proteção|aliança|cura|comida|ouro)|"
    # ── Reconciliação / aliança ────────────────────────────────────────────────
    r"faço as pazes|"
    r"perdoo|perdoei|perdoar|"
    r"me reconcilio|me reconciliei|"
    r"acordo|acord[oa]mos|"
    # ── Lealdade demonstrada ───────────────────────────────────────────────────
    r"confio (?:em|nele|nela)|"
    r"juro (?:lealdade|proteger|ajudar|defender)|"
    r"prometo (?:proteger|ajudar|defender|não trair)|"
    r"apoio|apoiei|"
    r"elogio|elogiei|"
    r"consolo|consolei|"
    r"fico ao lado (?:de|dele|dela)|"
    r"luto ao lado|"                    # fight alongside — luto aqui é verbo lutar
    r"coopero|cooperei|"
    r"compartilho (?:comida|recursos|ouro|informação com)\b|"  # compartilhar itens
    r"alian[cç]a|parceria(?! comercial)"
    r")\b",
    re.IGNORECASE,
)

# Verbos de traição, violência, roubo ou manipulação DIRIGIDA a um NPC.
#
# FILOSOFIA (precisa): ação explícita contra a pessoa, não circunstancial.
# Removidos: ignoro (ambíguo), troco (trocar de roupa), abandono (pode ser lugar).
# Adicionados: desarm[ao] (desarmar alguém), expulso, desrespeito, escravizo.
_RE_NEGATIVO = re.compile(
    r"\b("
    # ── Violência direta ───────────────────────────────────────────────────────
    r"traio|trai\b|trair|"
    r"ataco|ataquei|atacar|"
    r"mato|matei|matar|"
    r"apunhalo|apunhalei|"
    r"golpeio|golpeei|"
    r"agrido|agredi|agredir|"
    r"assassino|assassinei|"
    r"envenen[ao]|envenenei|envenenar|"
    r"intoxic[ao]|intoxiquei|intoxicar|"
    r"desarmo|desarmei|"               # tomar a arma de alguém
    # ── Engano e manipulação ───────────────────────────────────────────────────
    r"minto (?:para|pra)|menti (?:para|pra)|"   # mentira dirigida
    r"ameaço|ameac[eo]i|amea[cç]ar|"
    r"manipulo|manipulei|manipular|"
    r"extorqu[oe]|extorqui|extorquir|"
    r"chantage[io]|chantagei|chantagear|"
    r"espio|espiei|"                   # espionagem ativa
    # ── Desrespeito e abandono deliberado ──────────────────────────────────────
    r"humilho|humilhei|humilhar|"
    r"insulto|insultei|insultar|"
    r"desrespeito|desrespeitei|"
    r"desprezo|desprezei|"
    r"expulso|expulsei|"               # expulsar da cena/grupo
    r"abandono (?:ele|ela|você|o grupo)\b|"   # abandono explícito de pessoa
    # ── Roubo ─────────────────────────────────────────────────────────────────
    r"roubo|roubei|roubar"
    r")\b",
    re.IGNORECASE,
)

# Revelação de segredo sem permissão — penaliza todos os NPCs presentes.
# Mais específico: exige contexto de segredo/confiança, não apenas "conto".
_RE_REVELAR_SEGREDO = re.compile(
    r"\b("
    r"revelo o segredo|conto o segredo|revelo tudo|"
    r"traio a confiança|traio o segredo|"
    r"delato|denuncio|"
    r"entrego (?:o grupo|o plano|a localização|tudo)|"
    r"conto tudo (?:para|pra)|"
    r"revelo (?:o plano|a identidade|o esconderijo)"
    r")\b",
    re.IGNORECASE,
)


def _extrair_npc_mencionado(texto: str, npcs_presentes: list[str]) -> str | None:
    """
    Tenta identificar qual NPC do texto é alvo da ação.

    Compara tokens do texto contra os componentes do ID kebab-case de cada NPC.
    Retorna o primeiro NPC cujo nome (ou primeiro nome) aparece no texto.
    """
    texto_lower = texto.lower()
    for npc_id in npcs_presentes:
        partes = npc_id.replace("-", " ").split()
        primeiro_nome = partes[0] if partes else ""
        nome_completo = " ".join(partes)
        if nome_completo in texto_lower or (len(primeiro_nome) >= 3 and primeiro_nome in texto_lower):
            return npc_id
    return None


def detectar_mudancas_trust(
    texto_jogador: str,
    npcs_presentes: list[str],
) -> list[tuple[str, int]]:
    """
    Analisa o texto do jogador e retorna deltas de trust para NPCs presentes.

    Args:
        texto_jogador: O que o jogador disse ou fez neste turno.
        npcs_presentes: IDs (kebab-case) dos NPCs na cena atual.

    Returns:
        Lista de (npc_id, delta) — delta é +1 (positivo) ou -1 (negativo).
        Lista vazia se nenhuma mudança foi detectada.
    """
    if not npcs_presentes or not texto_jogador.strip():
        return []

    mudancas: list[tuple[str, int]] = []

    # Revelação de segredo penaliza todos os NPCs da cena
    if _RE_REVELAR_SEGREDO.search(texto_jogador):
        for npc_id in npcs_presentes:
            mudancas.append((npc_id, -1))
        return mudancas

    # Ações negativas contra NPC específico
    if _RE_NEGATIVO.search(texto_jogador):
        alvo = _extrair_npc_mencionado(texto_jogador, npcs_presentes)
        if alvo:
            mudancas.append((alvo, -1))

    # Ações positivas em favor de NPC específico
    if _RE_POSITIVO.search(texto_jogador):
        alvo = _extrair_npc_mencionado(texto_jogador, npcs_presentes)
        if alvo:
            # Não adicionar +1 se o mesmo NPC já recebeu -1 neste turno (traição prevalece)
            npcs_negativos = {npc for npc, delta in mudancas if delta < 0}
            if alvo not in npcs_negativos:
                mudancas.append((alvo, +1))

    return mudancas
