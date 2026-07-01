"""
Classificação de intenção de uma rolagem SOLTA do jogador (ataque × teste de perícia).

Por que existe: "rolagem-solta-resolve" (pendência do combate engine-first) precisa
    saber, quando o jogador rola um d20 SEM ter declarado um ataque antes
    (`combate_pendente` vazio), se aquele d20 é a confirmação de um ATAQUE pedido em
    prosa livre ou um TESTE DE PERÍCIA (Persuasão, Furtividade...) — resolver um
    teste como ataque quebraria o turno (alvo errado, ação gasta à toa). Mirror
    exato da heurística JÁ VALIDADA no frontend
    (`frontend/app/page.tsx: parseRolagens`/`extrairMotivoRolagem`): se a última
    fala do Mestre nomeia uma perícia/salvaguarda D&D 5e PT-BR, é teste — alta
    confiança, contrato testado em produção (master_system.md exige nomear o
    atributo na última frase ao pedir teste). Wirado em api/websocket.py desde
    01/07. Estratégia de fallback do caso ambíguo DECIDIDA pelo Beltrami (01/07,
    pós-playtest): "regra ampliada, sem LLM" — eh_pedido_ataque() e
    menciona_magia_ofensiva() (abaixo) ampliam a cobertura determinística;
    ambíguo de verdade continua caindo no fluxo antigo (LLM narra).
Dependências: nenhuma (regex puro, sem I/O).
Armadilha: NÃO classifica ATAQUE por prosa livre — combat.md instrui o Mestre a
    "pedir a rolagem de ataque" mas não fixa o texto exato (sem contrato testável
    como o de perícia), então esta função só afirma "é teste" com confiança; o
    caso contrário é sempre "ambíguo" (None), nunca "é ataque".

Exemplo:
    eh_teste_pericia("A guarda está distraída, mas a distância é grande (Furtividade).")
    # → "Furtividade"
    eh_teste_pericia("O goblin avança, espada em punho.")
    # → None (ambíguo — não confirma teste nem ataque)
"""

import re
import unicodedata

# Perícias D&D 5e em PT-BR (sem acento) — mirror exato de SKILL_MAP em
# frontend/app/page.tsx. Qualquer adição lá precisa espelhar aqui (e vice-versa).
_PERICIAS_PT: tuple[str, ...] = (
    "persuasao", "enganacao", "engano", "intimidacao", "atuacao", "percepcao",
    "intuicao", "discernimento", "medicina", "sobrevivencia", "atletismo",
    "acrobacia", "furtividade", "prestidigitacao", "arcanismo", "historia",
    "investigacao", "natureza", "religiao", "iniciativa",
)

# Atributos de salvaguarda — só contam junto da palavra "salvaguarda" (mirror do
# gate em SAVE_MAP do frontend: "força"/"destreza" sozinhos aparecem demais na
# narração comum sem ser pedido de rolagem).
_ATRIBUTOS_SALVAGUARDA_PT: tuple[str, ...] = (
    "forca", "destreza", "constituicao", "inteligencia", "sabedoria", "carisma",
)

_NOME_EXIBICAO: dict[str, str] = {
    "persuasao": "Persuasão", "enganacao": "Enganação", "engano": "Enganação",
    "intimidacao": "Intimidação", "atuacao": "Atuação", "percepcao": "Percepção",
    "intuicao": "Intuição", "discernimento": "Discernimento", "medicina": "Medicina",
    "sobrevivencia": "Sobrevivência", "atletismo": "Atletismo", "acrobacia": "Acrobacia",
    "furtividade": "Furtividade", "prestidigitacao": "Prestidigitação",
    "arcanismo": "Arcanismo", "historia": "História", "investigacao": "Investigação",
    "natureza": "Natureza", "religiao": "Religião", "iniciativa": "Iniciativa",
    "forca": "Força", "destreza": "Destreza", "constituicao": "Constituição",
    "inteligencia": "Inteligência", "sabedoria": "Sabedoria", "carisma": "Carisma",
}

_RE_SALVAGUARDA = re.compile(r"\bsalvaguarda\b", re.IGNORECASE)


def _sem_acento(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def eh_teste_pericia(ultima_fala_mestre: str) -> str | None:
    """Nome de exibição da perícia/salvaguarda se a fala pede um TESTE, senão None.

    Alta confiança quando devolve um nome: NÃO é ataque (vocabulário de perícia é
    disjunto de vocabulário de combate). Devolve None tanto pra "claramente não é
    teste" quanto pra "ambíguo" — o caller nunca deve inferir ataque a partir de
    None; isso exige um sinal positivo separado (ex: combate_pendente já setado).
    """
    if not ultima_fala_mestre:
        return None
    norm = _sem_acento(ultima_fala_mestre)
    if _RE_SALVAGUARDA.search(norm):
        for nome in _ATRIBUTOS_SALVAGUARDA_PT:
            if re.search(rf"\b{nome}\b", norm):
                return _NOME_EXIBICAO[nome]
    for nome in _PERICIAS_PT:
        if re.search(rf"\b{nome}\b", norm):
            return _NOME_EXIBICAO[nome]
    return None


# ── Regra ampliada de combate (decisão Beltrami 01/07 — "regra pura, sem LLM") ──
#
# Playtest 01/07 (sess-7893f3bdbd28): 4 rolagens de d20 em combate ficaram ÓRFÃS
# (nenhuma pendência ativa) porque a declaração do jogador não tinha sido
# reconhecida ("vou usar a explosão eldritch" — infinitivo fora do RE_COMBATE).
# `combate_engine_resolveu` = 0 na sessão inteira. Duas peças novas fecham o gap:
#   1. eh_pedido_ataque(): a ÚLTIMA fala do Mestre pediu a rolagem de ATAQUE →
#      um d20 solto logo depois É a rolagem desse ataque (espelho estrutural do
#      eh_teste_pericia, lado oposto);
#   2. menciona_magia_ofensiva(): citar magia de DANO conhecida em combate é
#      declaração de ataque, independente da conjugação do verbo.

# Vocabulário de "pedir rolagem" + vocabulário de "ataque" na mesma fala.
# A fala do Mestre é curta (≤80 palavras por regra de prompt) — janela global.
_RE_PEDE_ROLAGEM = re.compile(
    r"\b(?:rolagem|role|rola|rolar|jogue|jogar|d20|dado)\b", re.IGNORECASE
)
_RE_VOCAB_ATAQUE = re.compile(
    r"\b(?:ataque|atacar|acert\w*|golpe|investida|atingir)\b", re.IGNORECASE
)


def eh_pedido_ataque(ultima_fala_mestre: str) -> bool:
    """True se a última fala do Mestre pediu a rolagem de ATAQUE do jogador.

    Alta confiança: exige vocabulário de rolagem E de ataque na mesma fala
    ("Descreva a investida e PEÇA a rolagem de ataque" — é o que o wrapper de
    pendência instrui o Mestre a fazer). Chame SEMPRE depois de
    `eh_teste_pericia` devolver None — perícia nomeada tem precedência ("o
    goblin desvia do seu ataque... role Percepção" é teste, não ataque).
    """
    if not ultima_fala_mestre:
        return False
    norm = _sem_acento(ultima_fala_mestre)
    return bool(_RE_PEDE_ROLAGEM.search(norm) and _RE_VOCAB_ATAQUE.search(norm))


def menciona_magia_ofensiva(
    texto_jogador: str, spells_conhecidas: list[str] | None
) -> str | None:
    """Nome da magia de DANO conhecida citada no texto do jogador, ou None.

    Regra pura: o jogador só pode atacar com magia que CONHECE (a lista vem da
    ficha, `sessao.spells_conhecidas`), e só conta magia ofensiva pela desc do
    SRD (`spell_e_ofensiva`) — "uso invisibilidade" nunca vira ataque. Match
    por nome completo sem acento ("explosão eldritch" ≡ "explosao eldritch").
    O caller ainda deve aplicar a guarda condicional (RE_COMBATE_CONDICIONAL)
    e o gate de combate ativo — esta função só responde "citou magia de dano?".
    """
    if not texto_jogador or not spells_conhecidas:
        return None
    from engine.magic.spell_list import spell_e_ofensiva

    texto_norm = _sem_acento(texto_jogador)
    # Mais específica primeiro: "explosão eldritch superior" antes de "explosão".
    for nome in sorted(spells_conhecidas, key=len, reverse=True):
        nome_norm = _sem_acento(str(nome).strip())
        if not nome_norm:
            continue
        if re.search(rf"\b{re.escape(nome_norm)}\b", texto_norm) and spell_e_ofensiva(nome):
            return str(nome)
    return None
