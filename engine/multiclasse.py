"""
Regras de multiclasse do SRD 5.1 — pré-requisitos e o que se ganha.

Por que existe: o level up só oferecia +2 de atributo, e a decisão do Beltrami
    (29/07) foi "um simples pra própria classe e a opção de multiclasse". No
    intervalo de jogo real (nível 3 pra cima) o SRD dá POUCAS escolhas de feature
    — subclasse já foi escolhida na criação, Estilo de Luta é nível 1-2. O que
    existe em TODO level up é a opção de pegar um nível em outra classe. É aí que
    o level up passa a parecer D&D de verdade.
Dependências: apenas stdlib. Módulo PURO — não toca WorkingMemory.
Armadilha: pré-requisito de multiclasse é DOS DOIS LADOS. Pra sair de Guerreiro
    e pegar Mago, é preciso ter FOR ou DES 13 (a classe de origem) E INT 13 (a de
    destino). Errar isso deixa o jogador pegar combinações ilegais.

Exemplo:
    pode, faltando = pode_multiclassar("Guerreiro", "Mago", {"str_score": 16, "int_score": 11})
    # → (False, ["Mago exige Inteligência 13 (tem 11)"])
"""

from typing import Any

# Pré-requisito de atributo por classe (SRD 5.1, tabela de Multiclasse).
# Lista de listas = OU dentro da lista interna, E entre as externas.
# Guerreiro é ["str_score", "dex_score"] → FOR **ou** DES 13.
# Paladino é [["str_score"], ["cha_score"]] → FOR 13 **e** CAR 13.
_PRE_REQUISITOS: dict[str, list[list[str]]] = {
    "barbaro":    [["str_score"]],
    "bardo":      [["cha_score"]],
    "clerigo":    [["wis_score"]],
    "druida":     [["wis_score"]],
    "feiticeiro": [["cha_score"]],
    "guerreiro":  [["str_score", "dex_score"]],
    "ladino":     [["dex_score"]],
    "mago":       [["int_score"]],
    "monge":      [["dex_score"], ["wis_score"]],
    "paladino":   [["str_score"], ["cha_score"]],
    "ranger":     [["dex_score"], ["wis_score"]],
    "bruxo":      [["cha_score"]],
}

_MINIMO = 13

_NOME_ATRIBUTO: dict[str, str] = {
    "str_score": "Força", "dex_score": "Destreza", "con_score": "Constituição",
    "int_score": "Inteligência", "wis_score": "Sabedoria", "cha_score": "Carisma",
}

# Dado de vida por classe — o que o personagem ganha ao pegar o 1º nível nela.
_HIT_DIE: dict[str, int] = {
    "barbaro": 12, "guerreiro": 10, "paladino": 10, "ranger": 10,
    "bardo": 8, "clerigo": 8, "druida": 8, "ladino": 8, "monge": 8, "bruxo": 8,
    "feiticeiro": 6, "mago": 6,
}

# Nome canônico exibido, a partir da chave normalizada.
_EXIBICAO: dict[str, str] = {
    "barbaro": "Bárbaro", "bardo": "Bardo", "clerigo": "Clérigo",
    "druida": "Druida", "feiticeiro": "Feiticeiro", "guerreiro": "Guerreiro",
    "ladino": "Ladino", "mago": "Mago", "monge": "Monge",
    "paladino": "Paladino", "ranger": "Ranger", "bruxo": "Bruxo",
}


def _normalizar(classe: str) -> str:
    """Chave sem acento e em minúsculas — o jogador digita/fala de tudo."""
    txt = (classe or "").strip().lower()
    for de, para in (("á", "a"), ("â", "a"), ("ã", "a"), ("é", "e"), ("ê", "e"),
                     ("í", "i"), ("ó", "o"), ("ô", "o"), ("õ", "o"), ("ú", "u"),
                     ("ç", "c")):
        txt = txt.replace(de, para)
    return txt


def classes_srd() -> list[str]:
    """As 12 classes do SRD, em nome de exibição."""
    return [_EXIBICAO[k] for k in sorted(_EXIBICAO)]


def hit_die_da_classe(classe: str) -> int:
    """Dado de vida (8 se desconhecida — o default mais comum no SRD)."""
    return _HIT_DIE.get(_normalizar(classe), 8)


def _falta(chave: str, scores: dict[str, int], classe_exib: str) -> str | None:
    """Mensagem do requisito não cumprido, ou None se cumpre."""
    grupo = _PRE_REQUISITOS.get(chave)
    if not grupo:
        return None
    pendencias: list[str] = []
    for alternativas in grupo:
        # Dentro do grupo é OU: basta uma alternativa bater.
        if any(int(scores.get(a, 10)) >= _MINIMO for a in alternativas):
            continue
        nomes = " ou ".join(_NOME_ATRIBUTO.get(a, a) for a in alternativas)
        tem = ", ".join(f"{int(scores.get(a, 10))}" for a in alternativas)
        pendencias.append(f"{classe_exib} exige {nomes} {_MINIMO} (tem {tem})")
    return "; ".join(pendencias) if pendencias else None


def pode_multiclassar(
    classe_atual: str, classe_nova: str, scores: dict[str, int]
) -> tuple[bool, list[str]]:
    """Checa o pré-requisito DOS DOIS LADOS (SRD 5.1).

    Pra pegar um nível numa classe nova é preciso cumprir o requisito da classe
    que já se tem E o da nova. Esquecer o lado de origem é o erro clássico —
    deixa um Guerreiro de FOR 10/DES 10 (que só chegou lá por sorte de rolagem)
    virar Mago sem cumprir nada.

    Returns:
        (pode, motivos). `motivos` vazio quando pode; senão, uma frase por
        requisito faltando, já pronta pra exibir.
    """
    origem = _normalizar(classe_atual)
    destino = _normalizar(classe_nova)
    if destino not in _PRE_REQUISITOS:
        return False, [f"'{classe_nova}' não é uma classe do SRD"]
    if origem == destino:
        return False, ["já é a sua classe atual"]

    motivos: list[str] = []
    if origem in _PRE_REQUISITOS:
        # Classe de origem desconhecida (ficha antiga, classe custom) não bloqueia
        # — cobrar requisito de algo que não sabemos modelar puniria o jogador.
        falta_origem = _falta(origem, scores, _EXIBICAO.get(origem, classe_atual))
        if falta_origem:
            motivos.append(falta_origem)
    falta_destino = _falta(destino, scores, _EXIBICAO[destino])
    if falta_destino:
        motivos.append(falta_destino)
    return (not motivos), motivos


def opcoes_de_multiclasse(
    classe_atual: str, scores: dict[str, int]
) -> list[dict[str, Any]]:
    """Todas as classes do SRD com o veredito de elegibilidade de cada uma.

    Devolve TODAS, inclusive as bloqueadas, com o motivo — a UI mostra o que
    falta em vez de simplesmente esconder a opção. Saber que "Mago exige
    Inteligência 13 (tem 11)" é informação de jogo; a opção sumir não é.
    """
    saida: list[dict[str, Any]] = []
    for chave in sorted(_EXIBICAO):
        nome = _EXIBICAO[chave]
        if _normalizar(classe_atual) == chave:
            continue
        pode, motivos = pode_multiclassar(classe_atual, nome, scores)
        saida.append({
            "classe": nome,
            "elegivel": pode,
            "motivo": "; ".join(motivos),
            "hit_die": _HIT_DIE[chave],
        })
    return saida
