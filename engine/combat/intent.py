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
    atributo na última frase ao pedir teste). Peça ISOLADA e testada — wiring no
    fluxo de combate (api/websocket.py) fica PENDENTE de decisão do Beltrami sobre
    a estratégia de fallback pro caso "ambíguo" (mesmo padrão usado pro resto do
    combate engine-first: construir testado antes de wirar).
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
