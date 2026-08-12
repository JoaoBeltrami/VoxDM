"""
A engine DETECTA o uso de feature de classe pela fala do jogador.

Por que existe: no playtest de 11/08 o jogador disse *"vou aproveitar pra usar
    Fúria e usar Reckless Attack"* e o evento `feature_gasta` aparece ZERO vezes
    na sessão. Gastar feature dependia de o LLM emitir `[FEATURE_GASTA: rage]`, e
    ele não emitiu. Recurso que só some quando o modelo lembra não é recurso — é
    decoração, e o jogador percebe: ele terminou a luta com as três fúrias
    intactas depois de usar duas.
Dependências: nenhuma (função pura sobre o dict de features do personagem).
Armadilha: o marcador `[FEATURE_GASTA]` CONTINUA existindo e continua válido —
    ele responde "o que aconteceu", não "quanto", que é o corte do ADR-006. Esta
    detecção SOMA a ele; quem gastar duas vezes no mesmo turno (marcador + fala)
    é problema do call-site, que deve cobrar uma vez só.

    Segunda armadilha, a que custou o gate do combate no MESMO playtest: a lista
    de formas precisa cobrir a fala NATURAL. "Reckless Attack" em inglês, "ataque
    imprudente" em português, "entro em fúria" sem verbo de uso nenhum. Sinônimo
    que falta numa lista não falha alto — falha como se o jogador não tivesse
    feito nada.

Exemplo:
    detectar_feature("vou aproveitar pra usar Fúria", wm.class_features)
    # → "rage"
"""

import re
import unicodedata
from typing import Any

# Verbos que declaram uso. Reaproveita a lição do `engine/magic/casting.py`:
# `utilizar` faltava lá e custou o gate da magia — aqui ele nasce dentro.
_VERBOS: tuple[str, ...] = (
    "uso", "usar", "usando", "utilizo", "utilizar", "utilizando",
    "ativo", "ativar", "ativando", "aciono", "acionar",
    "entro", "entrar", "invoco", "invocar", "declaro", "declarar",
    "gasto", "gastar", "chamo", "chamar",
)
_RE_VERBO = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in _VERBOS) + r")\b", re.IGNORECASE
)

# Apelidos que o jogador usa na mesa e que NÃO são o nome da ficha. O inglês
# entra porque a mesa brasileira fala metade em inglês — o Beltrami disse
# "reckless attack" e "Fúria" na mesma frase.
_APELIDOS: dict[str, tuple[str, ...]] = {
    "rage": ("furia", "raiva", "rage", "enfurecer", "enfurecido"),
    "reckless-attack": ("ataque imprudente", "imprudente", "reckless attack", "reckless"),
    "action-surge": ("surto de acao", "action surge", "surto"),
    "second-wind": ("segundo folego", "second wind"),
    "sneak-attack": ("ataque furtivo", "sneak attack", "sneak", "furtivo"),
    "cunning-action": ("acao ardilosa", "cunning action", "ardilosa"),
    "divine-smite": ("investida divina", "divine smite", "smite"),
    "lay-on-hands": ("imposicao de maos", "lay on hands", "cura das maos"),
    "ki": ("ki", "chi"),
    "arcane-recovery": ("recuperacao arcana", "arcane recovery"),
    "superiority-dice": ("dado de superioridade", "dados de superioridade", "superiority"),
}

# Features que NÃO se gastam por uso — o SRD as dá "sempre que quiser", e o
# contador é -1 justamente por isso. Detectar continua valendo (o Mestre precisa
# saber que o jogador declarou), mas cobrar seria inventar um limite.
_SEM_CUSTO = -1


def _plano(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _termos(fid: str, dados: dict[str, Any]) -> tuple[str, ...]:
    nome = _plano(str(dados.get("nome") or ""))
    apelidos = _APELIDOS.get(fid, ())
    return tuple(t for t in (nome, _plano(fid.replace("-", " ")), *apelidos) if t)


def detectar_features(texto: str, features: dict[str, dict[str, Any]]) -> list[str]:
    """Ids das features que o jogador declarou usar, na ordem em que aparecem.

    LISTA, não uma só: a fala real do playtest foi *"vou aproveitar pra usar
    Fúria E usar Reckless Attack"* — duas features num fôlego. Devolver uma
    cobraria metade do que ele fez e deixaria a outra invisível pro Mestre.

    Exige o NOME (ou apelido) da feature E um verbo de uso, mesma regra da
    conjuração: sem o verbo, "a fúria dele era lendária" viraria uso de recurso.

    ⚠️ NÃO detecta estado contínuo de propósito. *"enquanto eu tô em fúria"*
    descreve uma fúria que JÁ está ativa — cobrar ali seria gastar o recurso
    duas vezes pela mesma ativação. Ativar é declarar; estar não é.
    """
    if not texto or not features:
        return []
    plano = _plano(texto)
    if not _RE_VERBO.search(plano):
        return []
    achados: list[tuple[int, str]] = []
    for fid, dados in features.items():
        melhor_pos = None
        for termo in _termos(fid, dados):
            m = re.search(rf"\b{re.escape(termo)}\b", plano)
            if m and (melhor_pos is None or m.start() < melhor_pos):
                melhor_pos = m.start()
        if melhor_pos is not None:
            achados.append((melhor_pos, fid))
    return [fid for _, fid in sorted(achados)]


def detectar_feature(texto: str, features: dict[str, dict[str, Any]]) -> str | None:
    """A primeira feature declarada, ou None. Açúcar sobre `detectar_features`."""
    achadas = detectar_features(texto, features)
    return achadas[0] if achadas else None


def pode_usar(features: dict[str, dict[str, Any]], fid: str) -> bool:
    """False quando a feature existe mas está esgotada."""
    dados = features.get(fid)
    if not dados:
        return False
    usos = int(dados.get("usos_atual", 0) or 0)
    return usos == _SEM_CUSTO or usos > 0


def gastar_feature(features: dict[str, dict[str, Any]], fid: str) -> dict[str, Any]:
    """Cobra um uso. Devolve o fato: {id, nome, gastou, restantes, esgotada}.

    Feature de uso ilimitado (`usos_atual == -1`) não perde nada — devolver
    `gastou=False` ali é resposta CERTA, não falha. O Mestre ainda precisa do
    fato pra narrar que o jogador entrou em fúria.
    """
    dados = features.get(fid)
    if not dados:
        return {"id": fid, "nome": fid, "gastou": False, "restantes": 0, "esgotada": True}

    nome = str(dados.get("nome") or fid)
    usos = int(dados.get("usos_atual", 0) or 0)

    if usos == _SEM_CUSTO:
        return {"id": fid, "nome": nome, "gastou": False, "restantes": -1, "esgotada": False}
    if usos <= 0:
        return {"id": fid, "nome": nome, "gastou": False, "restantes": 0, "esgotada": True}

    dados["usos_atual"] = usos - 1
    if dados["usos_atual"] <= 0:
        dados["disponivel"] = False
    return {
        "id": fid, "nome": nome, "gastou": True,
        "restantes": dados["usos_atual"], "esgotada": dados["usos_atual"] <= 0,
    }


def linha_de_feature(fato: dict[str, Any]) -> str:
    """Fato de engine pro canal `fatos_engine` — o Mestre narra, não decide."""
    nome = fato.get("nome") or fato.get("id")
    if fato.get("esgotada") and not fato.get("gastou"):
        return f"ENGINE: {nome} NÃO está disponível — sem usos restantes."
    if fato.get("restantes") == -1:
        return f"ENGINE: {nome} ativada (uso ilimitado — não consome recurso)."
    return f"ENGINE: {nome} ativada. Restam {fato.get('restantes')} usos."
