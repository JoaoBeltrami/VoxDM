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
    "DANO", "CURA",
    # Economia
    "OURO", "LOOT", "PERDEU", "MERCADO", "FIM_MERCADO",
    # Aliados
    "COMPANION_ADD", "COMPANION_HP", "COMPANION_REMOVE",
    # Cena e persistência
    "DESCANSO", "VOZ", "AFETO", "CENA", "FEATURE_GASTA", "NPC",
    "CICATRIZ", "RELOGIO", "FICHA",
    # Diretor de Arco — o jogador declarou um segredo e o Mestre confirma.
    "SEGREDO_REVELADO",
    # Alinhamento — ato moral que só a narrativa sabe (poupar, trair, honrar).
    # O que a ENGINE já sabe (atacar NPC, dano, morte) não usa marcador.
    "ALINHAMENTO",
    # Rótulos de INSTRUÇÃO injetados no prompt (prompt_builder: [PRESSÁGIO],
    # [REINCORPORAR]; [PACING: CLÍMAX/ALTO/BAIXO]) — o LLM não deve emiti-los,
    # mas modelos ecoam tag de colchete com frequência; sem cobertura aqui o
    # eco vazava pro TTS/chat (auditoria de fios mortos, 04/07). Acento E
    # variante sem acento (o eco nem sempre preserva o acento).
    "PRESSÁGIO", "PRESSAGIO", "REINCORPORAR", "PACING",
)


# ── Marcadores OBSOLETOS (Bloco 3 — autoridade da engine) ────────────────────
#
# Nomes que a ENGINE passou a decidir. O LLM não deve mais emiti-los, o prompt
# não os pede, e nenhum handler os processa — se aparecerem, são ignorados em
# silêncio (mesmo tratamento que o vocabulário fechado de [ALINHAMENTO] dá pra
# ato inventado).
#
# ⚠️ POR QUE ELES NÃO SAEM DE VEZ. A regra de migração do Bloco 3, como escrita
# na fila, manda tirar o nome de `NOMES_MARCADORES`. Seguir isso ao pé da letra
# QUEBRA A VOZ: `RE_STRIP_MARCADORES` é DERIVADO daquela tupla, e é o único
# strip do TTS. Um nome removido de lá deixa de ser limpo do texto, e o jogador
# passa a OUVIR "colchete RELOGIO_AVANCA dois pontos guerra-das-vilas".
#
# Então a migração tem duas metades, e só uma delas é "remover":
#   1. o PROCESSAMENTO morre  → o handler sai de api/turn_pipeline.py
#   2. o STRIP continua vivo   → o nome muda de tupla, não some
#
# Isto vale pro P5, P8, P9 e P10 também — todo item do Bloco 3 termina aqui.
NOMES_OBSOLETOS: Final[tuple[str, ...]] = (
    # P7 (07/08): quem avança relógio é a engine (viagem, descanso longo, falha
    # em teste, efeito de quest). "Avançar N fatias" é QUANTO — território da
    # engine pelo ADR-006. O irmão `[RELOGIO: id|nome|segmentos]` CONTINUA
    # canônico de propósito: nomear uma ameaça que vira relógio visível responde
    # "o que isso significa", que é exatamente o que o LLM ainda pode decidir.
    "RELOGIO_AVANCA",
)


def e_obsoleto(nome: str) -> bool:
    """True se o marcador foi migrado pra engine e deve ser ignorado em silêncio."""
    return nome.strip().upper() in {n.upper() for n in NOMES_OBSOLETOS}


def _construir_regex_strip() -> re.Pattern[str]:
    """Gera o regex de strip a partir da tupla canônica.

    Match: `[NOME ...]` ou `[NOME=...]` para qualquer NOME na tupla.
    Também captura QUALQUER `[Rolagem ...]` (caso especial — nome com espaço,
    fica fora da tabela porque não segue o padrão `[X:...]`). Cobre as três
    variantes de uma só vez:
      - `[Rolagem visível: dX = Y]`  → rolagem do mestre (Fase 5.7); o número já
        foi extraído como `dado_rolado` pelo websocket ANTES do strip.
      - `[Rolagem interna: dX = Y]`  → rolagem atrás da tela (modo narrated); o
        jogador NUNCA deve ouvir/ver o número.
      - `[Rolagem: dX = Y]`          → formato do JOGADOR (input). Se aparecer na
        RESPOSTA do LLM é fabricação (ROLL-AUTHORITY-1): o mestre inventou uma
        rolagem do jogador. Stripar evita que o TTS leia o marcador e que o
        número fabricado confunda a autoridade de dados.
    """
    # Canônicos + OBSOLETOS: um marcador migrado pra engine para de ser
    # PROCESSADO, mas continua sendo LIMPO — senão o jogador o ouve no TTS.
    alternativa = "|".join(
        re.escape(n) for n in (*NOMES_MARCADORES, *NOMES_OBSOLETOS)
    )
    # TAG-MALFORM-1 (A/B 17/07): o LLM emitiu `[TAG: NPC: id|nome]` — envelope
    # "TAG:" espúrio em volta de um marker legítimo. O strip exigia o nome
    # conhecido logo após `[`, então o bloco inteiro vazava pro chat/TTS.
    # Prefixo opcional `TAG:` tolera o envelope sem afrouxar o resto (palavras
    # de prosa começando com "TAG" não casam — o nome canônico segue exigido).
    return re.compile(
        rf"\[(?:TAG:\s*)?(?:{alternativa})(?::|=)?[^\]]*\]"
        r"|"
        r"\[Rolagem\b[^\]]*\]",
        re.IGNORECASE,
    )


# Regex final — derivado da tupla canônica + caso especial "Rolagem visível"
RE_STRIP_MARCADORES: Final[re.Pattern[str]] = _construir_regex_strip()
