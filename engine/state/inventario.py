"""
Inventário como ESTADO real — item com identidade, tipo, quantidade e equipado.

Por que existe: até 10/08 o inventário era `list[str]` — nomes soltos que só o
    LLM interpretava. Duas consequências que apareceram no mesmo playtest: a
    engine não sabia com QUE arma o jogador atacava (o Mestre pediu Força a um
    Ranger de arco, porque ninguém sabia que ele tinha um arco), e "duas poções"
    era literalmente a string "duas poções", sem contagem. Item que o jogador
    carrega é estado do jogo, e estado do jogo é da engine (ADR-006).
Dependências: `engine.combat.weapon_table` (para reconhecer arma pelo nome).
Armadilha: o `id` é derivado do NOME e é a chave de identidade — "Poção de Cura"
    e "poção de cura" são o MESMO item. Sem essa normalização o jogador acumula
    duplicatas invisíveis, que foi o motivo de `adicionar_item` já fazer
    comparação case-insensitive antes de existir estrutura nenhuma.

Exemplo:
    itens = de_strings(["Arco longo", "Poção de Cura", "Poção de Cura"])
    # → arco-longo (arma, 1) · pocao-de-cura (consumível, 2)
    equipar(itens, "arco longo")
    arma_equipada(itens)
    # → "longbow"
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from engine.combat.arma import identificar_arma

Tipo = Literal["arma", "armadura", "consumivel", "misc"]

# Vocabulário FECHADO de tipo. Rótulo desconhecido vira "misc" — que é inerte e
# honesto, ao contrário de chutar "consumivel" e deixar a engine beber um anel.
_TIPOS: frozenset[str] = frozenset({"arma", "armadura", "consumivel", "misc"})

# Radicais que denunciam um consumível em PT-BR. **Lista canônica do projeto.**
#
# CONSUMIVEL-DUPLICADO-1 (varredura 11/08): existiam DUAS — esta, com 7 formas, e
# `item_authority._ITENS_CONSUMIVEIS`, com 17 — e elas discordavam: "frasco" e
# "ração" só existiam aqui, "tônico", "bálsamo", "kit de cura" e "scroll" só lá.
# O efeito era um item classificado como consumível pela ficha e não reconhecido
# na hora de beber, ou o contrário. Mora na camada de ESTADO de propósito: a
# autoridade depende do estado, nunca o inverso.
#
# O custo de errar para MAIS aqui é a engine achar que pode GASTAR algo que não
# se gasta — por isso a lista cresce por evidência, não por imaginação.
RADICAIS_CONSUMIVEL: tuple[str, ...] = (
    "pocao", "potion", "elixir", "pergaminho", "scroll", "racao",
    "antidoto", "antitoxina", "frasco", "ampola", "tonico", "unguento",
    "balsamo", "reagente", "granada", "kit de cura", "kit medico",
)
_CONSUMIVEL = RADICAIS_CONSUMIVEL
_ARMADURA = ("armadura", "cota", "escudo", "brunea", "gibao", "couraca", "malha")


@dataclass
class ItemInventario:
    """Um item que o jogador carrega. `dados` guarda o que é específico do tipo."""

    id: str
    nome: str
    tipo: Tipo = "misc"
    quantidade: int = 1
    equipado: bool = False
    dados: dict[str, Any] = field(default_factory=dict)

    def para_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "nome": self.nome, "tipo": self.tipo,
            "quantidade": int(self.quantidade), "equipado": bool(self.equipado),
            "dados": dict(self.dados),
        }

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "ItemInventario":
        tipo = str(d.get("tipo") or "misc")
        return cls(
            id=str(d.get("id") or normalizar_id(str(d.get("nome") or ""))),
            nome=str(d.get("nome") or ""),
            tipo=tipo if tipo in _TIPOS else "misc",  # type: ignore[arg-type]
            quantidade=max(1, int(d.get("quantidade") or 1)),
            equipado=bool(d.get("equipado")),
            dados=dict(d.get("dados") or {}),
        )


def _sem_acento(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalizar_id(nome: str) -> str:
    """Nome → id kebab-case, que é a identidade do item.

    IDs em kebab-case são convenção travada do projeto. Aqui ele também resolve
    a duplicata invisível: "Poção de Cura" e "pocao de cura" colapsam no mesmo id.
    """
    base = re.sub(r"[^a-z0-9]+", "-", _sem_acento(nome)).strip("-")
    return base or "item"


def classificar_tipo(nome: str) -> Tipo:
    """Tipo do item pelo nome. Arma é reconhecida pela tabela SRD, não por lista."""
    plano = _sem_acento(nome)
    if identificar_arma(nome)[0]:
        return "arma"
    if any(p in plano for p in _ARMADURA):
        return "armadura"
    if any(p in plano for p in _CONSUMIVEL):
        return "consumivel"
    return "misc"


def criar_item(nome: str, quantidade: int = 1) -> ItemInventario:
    nome_limpo = str(nome or "").strip()
    tipo = classificar_tipo(nome_limpo)
    dados: dict[str, Any] = {}
    if tipo == "arma":
        idx, _ = identificar_arma(nome_limpo)
        if idx:
            dados["arma_idx"] = idx
    return ItemInventario(
        id=normalizar_id(nome_limpo), nome=nome_limpo, tipo=tipo,
        quantidade=max(1, int(quantidade)), dados=dados,
    )


def buscar(itens: list[ItemInventario], nome_ou_id: str) -> ItemInventario | None:
    alvo = normalizar_id(nome_ou_id)
    for it in itens:
        if it.id == alvo:
            return it
    return None


def adicionar(itens: list[ItemInventario], nome: str, quantidade: int = 1) -> ItemInventario:
    """Empilha se já existe; cria se não. Devolve o item resultante."""
    existente = buscar(itens, nome)
    if existente is not None:
        existente.quantidade += max(1, int(quantidade))
        return existente
    novo = criar_item(nome, quantidade)
    itens.append(novo)
    return novo


def remover(itens: list[ItemInventario], nome: str, quantidade: int = 1) -> bool:
    """Tira `quantidade` do item. Some da lista quando zera. False se não tinha.

    Consumir o último frasco tem que REMOVER o item, não deixar quantidade 0 —
    inventário com item fantasma de quantidade zero é o tipo de estado que só
    aparece como bug de exibição semanas depois.
    """
    existente = buscar(itens, nome)
    if existente is None:
        return False
    existente.quantidade -= max(1, int(quantidade))
    if existente.quantidade <= 0:
        itens.remove(existente)
    return True


def equipar(itens: list[ItemInventario], nome: str) -> bool:
    """Equipa o item, desequipando o que ocupava o mesmo tipo de slot.

    Só arma e armadura equipam — equipar uma poção não significa nada, e aceitar
    isso calado deixaria `arma_equipada` devolver lixo.
    """
    alvo = buscar(itens, nome)
    if alvo is None or alvo.tipo not in ("arma", "armadura"):
        return False
    for it in itens:
        if it.tipo == alvo.tipo:
            it.equipado = False
    alvo.equipado = True
    return True


def arma_equipada(itens: list[ItemInventario]) -> str:
    """Índice SRD da arma equipada; "" quando nenhuma.

    É a ponte com `engine.combat.arma`: com isto, atacar sem dizer a arma passa a
    usar a que o personagem REALMENTE está segurando, em vez de cair no melhor
    atributo genérico.
    """
    for it in itens:
        if it.tipo == "arma" and it.equipado:
            return str(it.dados.get("arma_idx") or "")
    return ""


def de_strings(nomes: list[str]) -> list[ItemInventario]:
    """Migra o formato antigo (`list[str]`) para itens estruturados.

    Bancos e sessões antigas existem — esta função é o que impede o inventário de
    quem já jogava de sumir na virada. Repetição na lista vira quantidade.
    """
    itens: list[ItemInventario] = []
    for nome in nomes or []:
        if str(nome or "").strip():
            adicionar(itens, str(nome))
    return itens


def sincronizar(atuais: list[ItemInventario], nomes: list[str]) -> list[ItemInventario]:
    """Reconcilia a lista estruturada com uma lista de NOMES vinda de fora.

    O frontend sincroniza a ficha mandando só nomes. Reconstruir do zero a cada
    sync apagaria o que a engine sabe e o cliente não — qual arma está equipada e
    quantas poções restam — toda vez que o jogador abrisse a ficha. Item que
    sobrevive ao sync mantém estrutura; item novo nasce classificado; item que
    sumiu da lista sai.
    """
    por_id = {it.id: it for it in atuais}
    saida: list[ItemInventario] = []
    vistos: set[str] = set()
    for nome in nomes or []:
        texto = str(nome or "").strip()
        if not texto:
            continue
        chave = normalizar_id(texto)
        if chave in vistos:
            # Nome repetido na lista de fora = quantidade, igual em `de_strings`.
            saida[[it.id for it in saida].index(chave)].quantidade += 1
            continue
        vistos.add(chave)
        saida.append(por_id.get(chave) or criar_item(texto))
    return saida


def para_strings(itens: list[ItemInventario]) -> list[str]:
    """Vista `list[str]` do inventário — o formato que o resto do sistema já lê.

    Nomes PLANOS, sem decoração. É tentador devolver "Poção de Cura (×2)" aqui,
    e seria um bug: meio sistema consulta o inventário com `"Poção de Cura" in
    inventario`, e a decoração faria toda checagem de posse falhar em silêncio.
    Quem precisa do número chama `para_exibicao`.
    """
    return [it.nome for it in itens]


def para_exibicao(itens: list[ItemInventario]) -> list[str]:
    """Vista com quantidade e equipado — para prompt e UI, nunca para checagem."""
    saida: list[str] = []
    for it in itens:
        nome = it.nome
        if it.quantidade > 1:
            nome = f"{nome} (×{it.quantidade})"
        if it.equipado:
            nome = f"{nome} [equipado]"
        saida.append(nome)
    return saida
