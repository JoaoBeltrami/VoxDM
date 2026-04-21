"""
engine/voice/language.py
Detecção de idioma do texto transcrito pelo STT.

O VoxDM opera em idioma misto: o jogador fala em PT-BR mas menciona
termos técnicos em inglês (nomes de magias, monstros, classes, etc.).

Este módulo detecta o idioma dominante do texto para:
  1. Selecionar a voz TTS correta (pt-BR vs en-US)
  2. Aplicar pronúncias corretas via SSML no Edge TTS
  3. Formatar a resposta do Mestre no idioma adequado

Design: heurísticas leves baseadas em palavras-chave PT-BR.
Sem modelos externos — latência desprezível para frases curtas.
"""

import re
from enum import StrEnum

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Enum de idiomas
# ---------------------------------------------------------------------------


class Idioma(StrEnum):
    """Idiomas suportados pelo pipeline de voz do VoxDM."""

    PTBR = "pt-BR"
    EN = "en-US"
    MISTO = "mixed"  # PT-BR dominante com termos EN


# ---------------------------------------------------------------------------
# Vocabulário de referência
# ---------------------------------------------------------------------------

# Termos D&D em inglês que NÃO indicam idioma inglês quando isolados.
# Um jogador brasileiro diz "vou conjurar Fireball" → texto é PT-BR.
_TERMOS_DND_NEUTROS: frozenset[str] = frozenset({
    # Classes
    "wizard", "cleric", "paladin", "ranger", "rogue", "barbarian",
    "bard", "druid", "fighter", "monk", "sorcerer", "warlock",
    # Magias comuns
    "fireball", "shatter", "bless", "cure", "hold", "charm",
    "sleep", "fly", "haste", "slow", "silence", "darkness",
    # Termos técnicos
    "dungeon", "master", "dm", "rpg", "hp", "ac", "dc",
    "npc", "pc", "str", "dex", "con", "int", "wis", "cha",
    "d4", "d6", "d8", "d10", "d12", "d20", "d100",
    # Itens
    "shortsword", "longsword", "rapier", "crossbow", "shield",
    # Monstros comuns
    "goblin", "orc", "troll", "dragon", "vampire", "zombie",
})

# Palavras funcionais comuns em PT-BR (artigos, pronomes, preposições, verbos).
# Presença de 2+ indica texto em português.
_PALAVRAS_PTBR: frozenset[str] = frozenset({
    # Pronomes pessoais
    "eu", "tu", "ele", "ela", "nós", "vós", "eles", "elas",
    "você", "voce", "vocês", "voces",
    "me", "te", "se", "nos", "vos", "lhe", "lhes",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "isso", "isto", "aquilo", "esse", "essa", "este", "esta",
    # Artigos — os mais frequentes do português
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    # Preposições e contrações — altíssima frequência
    "de", "do", "da", "dos", "das",
    "no", "na", "nos", "nas",
    "ao", "à", "aos", "às",
    "pelo", "pela", "pelos", "pelas",
    "num", "numa",
    "com", "para", "por", "sem", "sob", "sobre", "até", "após",
    # Conjunções
    "que", "mas", "ou", "nem", "porque", "então", "pois",
    "quando", "como", "onde", "quanto", "porém", "contudo",
    "embora", "enquanto", "portanto", "logo",
    # Verbos — formas mais frequentes
    "não", "sim", "já", "ainda", "também", "sempre", "nunca",
    "está", "estou", "estamos", "estão", "estive", "estava", "estavam",
    "vou", "vai", "vamos", "vão", "fui", "foi", "fomos", "foram",
    "tenho", "tem", "temos", "têm", "tinha", "tive", "tivemos",
    "posso", "pode", "podemos", "podem", "podia", "podiam",
    "quero", "quer", "queremos", "querem", "queria",
    "faço", "faz", "fazemos", "fazem", "fiz", "fez", "fizemos",
    "sou", "és", "somos", "são", "era", "eram", "serão",
    "disse", "diz", "dizem", "fala", "falou", "falam",
    "lança", "lançou", "conjura", "conjurou", "ataca", "atacou",
    "entra", "entrou", "sai", "saiu", "corre", "correu",
    # Advérbios e interjeições comuns
    "aqui", "ali", "lá", "aí", "agora", "depois", "antes",
    "muito", "pouco", "mais", "menos", "bem", "mal",
    "tá", "né", "cara", "opa", "uau", "pera",
    # Substantivos de alta frequência em contexto de RPG PT-BR
    "mão", "mãos", "olhos", "voz", "porta", "sala", "lugar",
    "grupo", "volta", "lado", "vez", "tempo", "tipo",
})


# ---------------------------------------------------------------------------
# Funções públicas
# ---------------------------------------------------------------------------


def detectar_idioma(texto: str) -> Idioma:
    """
    Detecta o idioma dominante do texto transcrito.

    Algoritmo:
      1. Tokeniza texto em palavras minúsculas
      2. Remove termos D&D neutros (não indicam idioma)
      3. Conta interseção com palavras PT-BR conhecidas
      4. Score >= 2 → PT-BR; score == 1 → MISTO; score == 0 → EN

    Args:
        texto: Texto transcrito pelo STT (frase ou parágrafo curto).

    Returns:
        Idioma detectado.
    """
    if not texto.strip():
        return Idioma.PTBR  # fallback padrão para texto vazio

    palavras = frozenset(re.findall(r"\b\w+\b", texto.lower()))

    # Remove termos neutros de D&D para não enviesar a detecção
    palavras_relevantes = palavras - _TERMOS_DND_NEUTROS

    score_ptbr = len(palavras_relevantes & _PALAVRAS_PTBR)

    if score_ptbr >= 2:
        idioma = Idioma.PTBR
    elif score_ptbr == 1:
        idioma = Idioma.MISTO
    else:
        idioma = Idioma.EN

    log.debug(
        "Idioma detectado",
        idioma=idioma,
        score_ptbr=score_ptbr,
        texto_preview=texto[:60],
    )
    return idioma


def extrair_termos_en(texto: str) -> list[str]:
    """
    Extrai termos em inglês de um texto predominantemente PT-BR.

    Usado pelo TTS para aplicar SSML de pronúncia nos termos D&D
    que aparecem dentro de frases em português.

    Critério de extração:
      - Palavra com 4+ caracteres (evita preposições curtas compartilhadas)
      - Não está no vocabulário PT-BR comum
      - Está na lista de termos D&D neutros (é um termo técnico em EN)

    Args:
        texto: Texto para analisar.

    Returns:
        Lista de termos em inglês encontrados, preservando capitalização original.
    """
    # Encontra todas as palavras preservando capitalização
    palavras_originais = re.findall(r"\b[a-zA-Z]{4,}\b", texto)

    termos_en = [
        p for p in palavras_originais
        if p.lower() in _TERMOS_DND_NEUTROS
    ]

    if termos_en:
        log.debug("Termos EN extraídos", termos=termos_en, total=len(termos_en))

    return termos_en
