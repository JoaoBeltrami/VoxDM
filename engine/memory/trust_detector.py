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

# Verbos de ação positiva em relação a NPCs (ajuda, cura, defesa, presente, aliança)
_RE_POSITIVO = re.compile(
    r"\b(ajudo|ajudei|ajudar|salvo|salvei|salvar|protejo|protegi|proteger|"
    r"curo|curei|curar|defendo|defendi|defender|presenteio|presenteei|"
    r"acordo|acord[oa]mos|faço as pazes|parceiro|aliado|"
    r"concordo|concordei|compartilho|compartilhei|"
    r"dou|dei|ofereço|ofereci|ofertar|"
    r"apoio|apoiei|apoiar|confio|confiei|confiar|"
    r"consolo|consolei|consolar|"
    r"prometo|prometi|prometer|juro|jurei|jurar|"
    r"coopero|cooperei|cooperar|"
    r"nego[cs]io|negociei|negociar|"
    r"alian[cç]a|amizade|companheiro|parceria)\b",
    re.IGNORECASE,
)

# Verbos de traição, violência, roubo ou manipulação contra NPCs
_RE_NEGATIVO = re.compile(
    r"\b(traio|trai|trair|ataco|ataquei|atacar|mato|matei|matar|roubo|"
    r"roubei|roubar|minto|menti|mentir|ameaço|ameac[eo]i|amea[cç]ar|golpeio|"
    r"golpeei|firo|feri|apunhalo|apunhalei|assassino|assassinei|"
    r"envenen[oa]|envenenei|envenenar|intoxic[ao]|intoxiquei|intoxicar|"
    r"humilho|humilhei|humilhar|insulto|insultei|insultar|"
    r"ignoro|ignorei|ignorar|desprezo|desprezei|desprezar|"
    r"abandono|abandonei|abandonar|"
    r"tro[ck]o|troquei|trocar|"
    r"espio|espiei|espiar|espi[oa]no|"
    r"manipulo|manipulei|manipular|"
    r"extorqu[oe]|extorqui|extorquir|"
    r"chantage[io]|chantagei|chantagear)\b",
    re.IGNORECASE,
)

# Revelação de segredo sem permissão — penaliza todos os NPCs presentes
_RE_REVELAR_SEGREDO = re.compile(
    r"\b(revelo o segredo|conto o segredo|revelo tudo|entrego|"
    r"denuncio|delato|traio a confiança|conto tudo|entrego tudo|"
    r"delato ele|delato ela|denuncio ele|denuncio ela)\b",
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
