"""
Registro canônico dos nomes de marcadores de Mestre Veterano.

Por que existe: o conjunto de markers era duplicado em 3 lugares:
  - 20+ regexes individuais em api/turn_pipeline.py (cada handler)
  - regex monstro _RE_MESTRE_VET em engine/memory/quest_detector.py (strip do TTS)
  - lista em engine/llm/prompts/master_system.md (documentação pro LLM)

Esquecer de adicionar um marker em um desses lugares era fácil. Esta tabela
única vira a fonte da verdade pro strip — adicionar marker novo agora é uma
linha aqui + um regex específico em turn_pipeline pra extrair os grupos.

Dependências: stdlib (re).
Armadilha: nomes com caracteres não-ASCII (ex: CONSEQUÊNCIA) entram aqui
exatamente como aparecem na resposta do LLM. O regex IGNORECASE compara
em case-insensitive, mas o Unicode literal precisa estar correto.

Exemplo:
    from engine.markers import RE_STRIP_MARCADORES
    texto_limpo = RE_STRIP_MARCADORES.sub("", resposta_llm).strip()
"""

import re
from typing import Final

# Nomes canônicos — fonte da verdade. Ordem não importa para o regex
# (alternação), mas mantemos agrupado por categoria para legibilidade.
NOMES_MARCADORES: Final[tuple[str, ...]] = (
    # Narrativa contínua
    "FIO", "CLIFFHANGER", "AGENDA", "CONSEQUÊNCIA", "ANCORA",
    "XP", "LAMPEJO",
    # Combate
    "POSICAO", "MOV", "INIMIGO_MORTO", "INIMIGO", "FUGIU", "COMBATE",
    # Economia
    "OURO", "LOOT", "PERDEU", "MERCADO", "FIM_MERCADO",
    # Aliados
    "COMPANION_ADD", "COMPANION_HP", "COMPANION_REMOVE",
    # Cena e persistência
    "DESCANSO", "VOZ", "AFETO", "CENA",
)


def _construir_regex_strip() -> re.Pattern[str]:
    """Gera o regex de strip a partir da tupla canônica.

    Match: `[NOME ...]` ou `[NOME=...]` para qualquer NOME na tupla.
    Também captura `[Rolagem visível: ...]` (caso especial — nome com
    espaço, fica fora da tabela porque não segue o padrão `[X:...]`).
    """
    alternativa = "|".join(re.escape(n) for n in NOMES_MARCADORES)
    return re.compile(
        rf"\[(?:{alternativa})(?::|=)?[^\]]*\]"
        r"|"
        r"\[Rolagem\s+visível:[^\]]*\]",
        re.IGNORECASE,
    )


# Regex final — derivado da tupla canônica + caso especial "Rolagem visível"
RE_STRIP_MARCADORES: Final[re.Pattern[str]] = _construir_regex_strip()
