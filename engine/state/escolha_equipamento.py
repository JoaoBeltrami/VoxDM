"""
Resolve as escolhas de equipamento inicial — a regra que ficha e VOZ compartilham.

Por que existe: pedido do Beltrami em 11/08 — oferecer as opções do SRD nos dois
    caminhos de criação. Se cada um resolvesse por conta, virariam duas regras
    divergentes, que é exatamente o tipo de duplicação que este projeto passou os
    últimos dias removendo (duas listas de verbos, duas de consumíveis).
Dependências: `engine.rules` — as escolhas vêm do SISTEMA ativo, nunca da
    tabela do D&D direto (lembrete do Beltrami em 11/08: a engine não vai narrar
    só D&D). Este módulo é a MECÂNICA da escolha, comum a qualquer sistema.
Armadilha: escolha por CATEGORIA ("uma arma marcial") não resolve sozinha — ela
    devolve `pendente`, e quem fecha é o jogador nomeando a arma. Preencher com
    um padrão seria escolher a build dele, e é o mesmo motivo pelo qual as opções
    não entram no equipamento fixo.

Exemplo:
    perguntas_de("Guerreiro")[0].texto
    # → 'Cota de malha, ou Armadura de couro, Arco longo, Flecha ×20?'
    resolver("Guerreiro", [0, 1, 1, 0])
    # → (["Cota de malha", "Machadinha", "Machadinha", "Mochila de masmorra"], [...])
"""

from dataclasses import dataclass, field
from typing import Any

from engine.combat.arma import identificar_arma


def _escolhas(classe: str) -> list[dict[str, Any]]:
    """As escolhas da classe, pelo SISTEMA ativo — nunca pela tabela do D&D.

    Lembrete do Beltrami (11/08): a engine não vai narrar só D&D. Este módulo
    resolve a MECÂNICA da escolha (interpretar resposta, aplicar no inventário),
    que é comum a qualquer sistema; QUAIS escolhas existem é conteúdo do sistema,
    e vem de trás do contrato.
    """
    from engine.rules import obter_sistema

    return list(obter_sistema().escolhas_de_equipamento(classe))


@dataclass
class Pergunta:
    """Uma escolha do SRD, pronta para virar botão na ficha OU fala do Mestre."""

    indice: int
    texto: str
    rotulos: list[str]
    # Índices das opções que NÃO se resolvem sozinhas (categoria aberta).
    abertas: list[int] = field(default_factory=list)


def perguntas_de(classe: str) -> list[Pergunta]:
    """As escolhas da classe, na ordem do SRD. [] para classe desconhecida."""
    saida: list[Pergunta] = []
    for i, escolha in enumerate(_escolhas(classe)):
        rotulos = [str(o.get("rotulo") or "") for o in escolha.get("opcoes", [])]
        abertas = [
            j for j, o in enumerate(escolha.get("opcoes", []))
            if o.get("categoria")
        ]
        saida.append(Pergunta(
            indice=i,
            texto=", ou ".join(rotulos) + "?",
            rotulos=rotulos,
            abertas=abertas,
        ))
    return saida


def interpretar_resposta(pergunta: Pergunta, fala: str) -> int | None:
    """Índice da opção que a FALA do jogador escolheu, ou None.

    Aceita a letra ("a", "b"), o número ("a primeira", "2") e o nome do item
    ("a cota de malha"). Existe porque a criação por voz não tem botão: o
    jogador responde do jeito que responderia numa mesa, e as três formas
    aparecem naturalmente.
    """
    texto = (fala or "").strip().lower()
    if not texto:
        return None

    # Letra isolada ou "opção b"
    for i in range(len(pergunta.rotulos)):
        letra = chr(ord("a") + i)
        if texto == letra or texto.startswith(f"{letra})") or f"opção {letra}" in texto:
            return i

    # Ordinal / número
    ordinais = ("primeir", "segund", "terceir", "quart")
    for i, raiz in enumerate(ordinais[:len(pergunta.rotulos)]):
        if raiz in texto or texto == str(i + 1):
            return i

    # Nome — casa a PALAVRA mais longa do rótulo, não o rótulo inteiro: o
    # jogador diz "a cota", não "Cota de malha, Arco longo, Flecha ×20".
    melhor, melhor_peso = None, 0
    for i, rotulo in enumerate(pergunta.rotulos):
        for palavra in rotulo.lower().replace(",", " ").split():
            if len(palavra) >= 4 and palavra in texto and len(palavra) > melhor_peso:
                melhor, melhor_peso = i, len(palavra)
    return melhor


def resolver(
    classe: str, escolhidos: list[int]
) -> tuple[list[str], list[str]]:
    """(itens para o inventário, perguntas ainda ABERTAS por serem categoria).

    `escolhidos` é o índice da opção por pergunta, na ordem de `perguntas_de`.
    Índice fora do intervalo é ignorado — resposta inválida não pode inventar
    equipamento nem derrubar a criação do personagem.
    """
    itens: list[str] = []
    pendentes: list[str] = []
    escolhas = _escolhas(classe)

    for i, escolha in enumerate(escolhas):
        if i >= len(escolhidos):
            continue
        opcoes = escolha.get("opcoes", [])
        j = escolhidos[i]
        if not isinstance(j, int) or not (0 <= j < len(opcoes)):
            continue
        opcao = opcoes[j]
        for item in opcao.get("itens", []):
            itens += [str(item["nome"])] * int(item.get("quantidade") or 1)
        if opcao.get("categoria"):
            pendentes.append(str(opcao["categoria"]))
    return itens, pendentes


def resolver_categoria(pendente: str, fala: str) -> str:
    """O item concreto que a fala escolheu para uma categoria aberta. "" se nenhum.

    Hoje só resolve ARMA — é a categoria que importa em combate e a única com
    tabela SRD no projeto. Foco arcano, símbolo sagrado e instrumento entram
    como item narrativo pelo nome que o jogador falar, e isso é decisão de
    conteúdo, não de regra.
    """
    if "arma" not in pendente.lower():
        return ""
    idx, termo = identificar_arma(fala)
    if not idx:
        return ""
    from engine.combat.weapon_table import ARMAS

    # Nome em PT-BR, nunca o `nome_en`: o inventário é comparado por NOME, e um
    # "Longsword" no meio de uma ficha em português é um item que nem o jogador
    # nem `classificar_tipo` acham depois.
    dados = ARMAS.get(idx) or {}
    pt = list(dados.get("nomes_pt") or [])
    return str(pt[0].capitalize() if pt else (termo or dados.get("nome_en", "")))


def aplicar(wm: Any, classe: str, escolhidos: list[int]) -> list[str]:
    """Resolve e ADICIONA ao inventário do personagem. Devolve os pendentes.

    Equipa a primeira arma escolhida se ainda não houver nada equipado — mesma
    razão do equipamento fixo: obrigar a equipar antes do primeiro golpe
    transformaria um padrão do SRD em pegadinha.
    """
    itens, pendentes = resolver(classe, escolhidos)
    for nome in itens:
        wm.character.adicionar_item(nome)
    if not wm.character.arma_equipada():
        for item in wm.character.inventario:
            if item.tipo == "arma":
                wm.character.equipar_item(item.nome)
                break
    return pendentes
