"""
Detecção de amarelada/sanitização do LLM em cenas de ficção sombria.

Por que existe: a detecção existente (_e_recusa em groq.py) só pega recusa HARD
    no início da resposta ("não posso ajudar", "como IA..."). Não pega amarelada
    SUAVE: fade-to-black voluntário, moralização mid-stream, disclaimer inserido
    no meio da narração. Este módulo trata esses casos.
Dependências: nenhuma (stdlib apenas).
Armadilha: gating por cena sombria é OBRIGATÓRIO antes de usar e_amarelada().
    Um NPC moralizante dentro da ficção ("o senhor não deveria fazer isso") é fala
    legítima de personagem, não amarelada. Só chamar quando a cena for sombria.

Exemplo:
    if cena_sombria and e_amarelada(resposta_llm):
        # cascatear para provider menos filtrado
"""

from __future__ import annotations

# Frases de fade-to-black / sanitização voluntária.
# O LLM descreve que NÃO vai descrever — o pior cenário pra imersão.
_FRASES_FADE = (
    "prefiro não detalhar",
    "deixo à imaginação",
    "deixarei à imaginação",
    "vamos pular essa parte",
    "vamos saltar essa parte",
    "é horrível demais para descrever",
    "poupando os detalhes",
    "poupo os detalhes",
    "não vou descrever",
    "melhor não descrever",
    "deixarei os detalhes",
    "optando por não detalhar",
    "sem entrar em detalhes",
)

# Frases de moralização / disclaimer inserido pelo LLM.
# O LLM sai do personagem para comentar sobre o conteúdo.
_FRASES_MORAL = (
    "é importante lembrar que",
    "não condono esse tipo",
    "conteúdo sensível",
    "antes de continuar, gostaria",
    "com a devida responsabilidade",
    "de forma responsável",
    "este conteúdo pode ser perturbador",
    "aviso de conteúdo",
)


def e_amarelada(texto: str) -> bool:
    """True quando a resposta do LLM contém fade-to-black ou moralização.

    Usar APENAS quando a cena é sombria — fala de NPC moralizante dentro da
    ficção NÃO é amarelada. Ver docstring do módulo.
    """
    t = texto.lower()
    return any(f in t for f in _FRASES_FADE + _FRASES_MORAL)


# Keywords de atrocidade — presença no texto do jogador sugere cena sombria.
# Lista conservadora: evita falsos positivos em combate normal.
# "massacre" sozinho seria falso positivo em "massacrei os goblins" —
# usar só combinações ou contextos claramente além do combate de dungeon.
KEYWORDS_ATROCIDADE: tuple[str, ...] = (
    "massacre de aldeões",
    "massacre de civis",
    "massacre de inocentes",
    "chacina",
    "tortura",
    "sacrifício humano",
    "sacrificio humano",
    "queimar vivos",
    "queimar a vila",
    "incendiar a vila",
    "crucificar",
    "desmembrar",
    "exterminar a população",
    "extermínio",
    "exterminio",
    "escravizar",
)


def e_cena_sombria(texto: str) -> bool:
    """True quando o texto do jogador contém keywords de atrocidade.

    Usado para injetar o fragmento grimdark.md mesmo sem dm_profile="sombrio".
    """
    t = texto.lower()
    return any(kw in t for kw in KEYWORDS_ATROCIDADE)
