"""
Detecção automática de idioma para texto transcrito (PT-BR vs EN).

Por que existe: O jogo roda em PT-BR mas termos D&D são em inglês — a engine
precisa saber o idioma dominante para selecionar a voz TTS correta.
Dependências: nenhuma externa — heurística baseada em stopwords.
Armadilha: textos curtos (< 2 palavras) são ambíguos — padrão é pt-BR.

Exemplo:
    idioma = detectar_idioma("eu lanço Fireball no goblin")
    # → "pt-BR"
    idioma = detectar_idioma("I cast fireball at the goblin")
    # → "en"
"""

import re
from typing import Literal

import structlog

IdiomaDetectado = Literal["pt-BR", "en"]

_log = structlog.get_logger(__name__)

# Stopwords que identificam PT-BR com alta confiança
_STOPWORDS_PT: frozenset[str] = frozenset({
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas",
    "ao", "aos", "à", "às", "pelo", "pela", "pelos", "pelas",
    "e", "ou", "mas", "se", "que", "com", "por", "para", "como",
    "eu", "tu", "ele", "ela", "nós", "eles", "elas", "você", "vocês",
    "meu", "minha", "meus", "minhas", "seu", "sua", "seus", "suas",
    "isso", "este", "esta", "estes", "estas", "esse", "essa",
    "aqui", "ali", "lá", "aquele", "aquela",
    "não", "sim", "já", "ainda", "também", "só", "mais", "menos",
    "muito", "pouco", "bem", "mal", "quando", "onde", "quem",
    "quero", "vou", "tenho", "estou", "sou", "está", "são", "foi",
    "lanço", "ataco", "movo", "uso", "falo", "vejo", "ouço",
    "preciso", "posso", "quero", "devo", "seria", "seria",
})

# Stopwords que identificam EN com alta confiança
_STOPWORDS_EN: frozenset[str] = frozenset({
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "with",
    "and", "or", "but", "if", "that", "this", "it", "is", "are",
    "was", "were", "be", "been", "have", "has", "do", "does", "did",
    "i", "you", "he", "she", "we", "they", "my", "your", "his", "her",
    "its", "our", "their", "me", "him", "us", "them",
    "cast", "attack", "move", "want", "use", "roll", "look",
    "go", "run", "fight", "hit", "kill", "search", "open",
    "can", "will", "would", "could", "should", "shall", "may", "might",
    "not", "no", "yes", "here", "there", "where", "when", "who", "what",
})


def detectar_idioma(texto: str) -> IdiomaDetectado:
    """Detecta PT-BR ou EN baseado em stopwords dominantes no texto."""
    # Extrai apenas sequências de letras (ignora números, pontuação, espaços)
    palavras = re.findall(r"\b[a-záéíóúâêîôûãõàèìòùçñ]+\b", texto.lower())

    if len(palavras) < 2:
        # Texto curto — padrão PT-BR por ser o idioma do jogo
        return "pt-BR"

    score_pt = sum(1 for p in palavras if p in _STOPWORDS_PT)
    score_en = sum(1 for p in palavras if p in _STOPWORDS_EN)

    idioma: IdiomaDetectado = "en" if score_en > score_pt else "pt-BR"

    _log.debug(
        "idioma.detectado",
        idioma=idioma,
        score_pt=score_pt,
        score_en=score_en,
        palavras=len(palavras),
    )

    return idioma


def e_termo_misto(texto: str) -> bool:
    """Retorna True se o texto contém tanto palavras PT-BR quanto EN.

    Útil para decidir se SSML é necessário na síntese TTS.
    """
    palavras = re.findall(r"\b[a-záéíóúâêîôûãõàèìòùçñ]+\b", texto.lower())
    if len(palavras) < 3:
        return False

    score_pt = sum(1 for p in palavras if p in _STOPWORDS_PT)
    score_en = sum(1 for p in palavras if p in _STOPWORDS_EN)

    # Considera misto se ambos os idiomas têm presença significativa
    total = score_pt + score_en
    if total == 0:
        return False

    proporcao_menor = min(score_pt, score_en) / total
    return proporcao_menor >= 0.2  # pelo menos 20% do idioma minoritário
