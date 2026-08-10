"""
Resolve o ATAQUE DE MAGIA: a engine decide o acerto e o dano, o Mestre narra.

Por que existe: até 09/08 conjurar era prosa. O detector achava a magia (quando
    achava) e apenas INJETAVA os dados no prompt — nenhuma rolagem, nenhum dano,
    e o slot ficava intacto. É o mesmo "quanto" que o ADR-006 proíbe, e o
    ADR-007 (decisões 3 e 4) fechou o desenho: o jogador rola o d20 na UI, a
    engine resolve vs a CA e puxa o dado de dano da tabela local.
Dependências: engine.combat.resolver (a matemática de acerto/dano já existe e é
    testada — esta camada NÃO a reimplementa), engine.magic.spell_mechanics
    (tabela estática, sem rede), engine.magic.slot_tracker (consumo).
Armadilha: truque e magia de slot escalam por coisas DIFERENTES — truque pelo
    nível do PERSONAGEM, magia de slot pelo nível do SLOT. A tabela diz qual em
    `dano.escala_por`; usar a chave errada dá 1d10 onde deveria ser 4d10.

Exemplo:
    r = resolver_ataque_de_magia(wm, "Chama Sagrada", "goblin-1", d20=17)
    r["contexto"]   # → "ENGINE: Chama Sagrada acerta o Goblin — 7 de dano radiante."
"""

from __future__ import annotations

import random
import unicodedata
from typing import Any

from engine.combat.enemy_turn import rolar_dado
from engine.combat.resolver import resolver_ataque, resolver_dano
from engine.magic.spell_mechanics import MECANICA_MAGIA, POR_NOME_EN

# Nível de personagem em que cada degrau de truque entra (SRD 5.1): o dano de
# truque escala em 5/11/17. As chaves da tabela são exatamente esses degraus.
_DEGRAUS_TRUQUE: tuple[int, ...] = (1, 5, 11, 17)

# A tabela vem do SRD em inglês; a linha vai pro Mestre, que narra em PT-BR.
# Sem isto o prompt recebia "3 de dano fire" — inglês no meio da narração.
_PT_PARA_EN: dict[str, str] | None = None

_TIPO_DANO_PT: dict[str, str] = {
    "acid": "ácido", "bludgeoning": "concussão", "cold": "frio",
    "fire": "fogo", "force": "energia", "lightning": "elétrico",
    "necrotic": "necrótico", "piercing": "perfurante", "poison": "veneno",
    "psychic": "psíquico", "radiant": "radiante", "slashing": "cortante",
    "thunder": "trovejante",
}


def _normalizar(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _indice_pt_para_en() -> dict[str, str]:
    """PT-BR normalizado → nome inglês, a partir de `spell_list`. Cache no módulo.

    Sem esta ponte, "Bola de Fogo" não achava a mecânica de Fireball: a tabela é
    chaveada em INGLÊS e a lista PT-BR nunca era consultada. O Beltrami pediu em
    09/08 que o Mestre entenda os dois idiomas — isto é a metade mecânica disso.
    """
    global _PT_PARA_EN
    if _PT_PARA_EN is None:
        from engine.magic.spell_list import SPELLS_POR_CLASSE
        _PT_PARA_EN = {
            _normalizar(e.nome_pt): e.nome_en
            for lista in SPELLS_POR_CLASSE.values()
            for e in lista
            if e.nome_pt and e.nome_en
        }
    return _PT_PARA_EN


def mecanica_da_magia(nome_pt: str, nome_en: str = "") -> dict[str, Any] | None:
    """Registro mecânico da magia, em PT-BR ou em inglês. None se não há.

    Três caminhos, do mais direto ao mais indulgente:
      1. o nome inglês (a tabela é chaveada por ele);
      2. o nome PT-BR, traduzido pela ponte de `spell_list`;
      3. a equivalência declarada, pras magias fora do SRD 2014.
    """
    ponte = _indice_pt_para_en()
    for candidato in (nome_en, nome_pt):
        chave = _normalizar(candidato)
        if not chave:
            continue
        indice = POR_NOME_EN.get(chave)
        if indice:
            return MECANICA_MAGIA.get(indice)
        # O mesmo nome, agora traduzido do PT-BR.
        en = ponte.get(chave)
        if en:
            indice = POR_NOME_EN.get(_normalizar(en))
            if indice:
                return MECANICA_MAGIA.get(indice)
    # Fora do SRD 2014 (Xanathar's/Tasha's): empresta a mecânica da equivalência
    # declarada. Decisão do Beltrami em 09/08 — "prefiro ter as magias mesmo que
    # parecidas". Sem isto, 19 magias da lista PT-BR continuavam sendo prosa.
    from engine.magic.equivalencias import equivalente_srd
    for candidato in (nome_pt, nome_en):
        indice = equivalente_srd(candidato)
        if indice:
            return MECANICA_MAGIA.get(indice)
    return None


def _dado_de_dano(mecanica: dict[str, Any], nivel_pj: int, nivel_slot: int) -> str:
    """A string NdM certa para este conjurador e este slot.

    Truque escala pelo nível do PERSONAGEM; magia de slot, pelo nível do SLOT.
    Errar isso é a diferença entre 1d10 e 4d10 na mesma magia.
    """
    dano = mecanica.get("dano") or {}
    por = dano.get("por") or {}
    if not por:
        return ""
    if dano.get("escala_por") == "nivel_personagem":
        degrau = max(d for d in _DEGRAUS_TRUQUE if d <= max(1, nivel_pj))
        # A tabela do SRD indexa truque por nível de personagem; se o degrau
        # exato não existir, cai no maior degrau disponível abaixo dele.
        disponiveis = sorted((int(k) for k in por if str(k).isdigit()), reverse=True)
        chave = next((str(d) for d in disponiveis if d <= degrau), None)
        return str(por.get(chave, "")) if chave else ""
    disponiveis = sorted(int(k) for k in por if str(k).isdigit())
    if not disponiveis:
        return ""
    # Slot abaixo do mínimo da magia não deveria acontecer (o caller valida),
    # mas cair no menor degrau é melhor que devolver vazio e não causar dano.
    alvo = max(disponiveis[0], min(int(nivel_slot), disponiveis[-1]))
    return str(por.get(str(alvo), ""))


def resolver_ataque_de_magia(
    wm: Any,
    nome_pt: str,
    alvo_id: str,
    d20: int,
    *,
    nome_en: str = "",
    nivel_slot: int = 0,
    rng: random.Random | None = None,
) -> dict[str, Any] | None:
    """Resolve uma magia de ATAQUE contra um inimigo. None quando não se aplica.

    Devolve None (e não levanta) quando: a magia não está na tabela, não é de
    ataque, o alvo não existe ou já morreu. O caller trata como "não resolvido"
    e o turno segue — silêncio é melhor que número inventado.

    NÃO consome slot: quem faz isso é `consumir_slot_da_magia`, porque o consumo
    tem que acontecer UMA vez por conjuração, e esta função é pura o bastante pra
    ser chamada em teste sem efeito colateral.
    """
    mecanica = mecanica_da_magia(nome_pt, nome_en)
    if not mecanica or mecanica.get("resolucao") != "ataque":
        return None
    alvo = (getattr(wm, "inimigos_combate", {}) or {}).get(alvo_id)
    if not alvo or alvo.get("estado") == "morto":
        return None

    rng = rng or random.Random()
    ca = int(alvo.get("ca", 12))
    r = resolver_ataque(d20, wm.mod_ataque(), ca)

    nome_alvo = str(alvo.get("nome") or alvo_id)
    dano = 0
    estado = str(alvo.get("estado", ""))
    tipo_bruto = str((mecanica.get("dano") or {}).get("tipo") or "").lower()
    tipo_dano = _TIPO_DANO_PT.get(tipo_bruto, tipo_bruto)

    if r.acertou:
        dado = _dado_de_dano(
            mecanica,
            nivel_pj=int(getattr(wm, "player_level", 1) or 1),
            nivel_slot=int(nivel_slot or mecanica.get("nivel", 0) or 0),
        )
        rolado = rolar_dado(dado, rng)
        # Magia de ataque NÃO soma modificador de atributo no dano (SRD) — o
        # bônus entra no acerto, não no dado. Por isso `mod_dano=0`.
        dano = resolver_dano(rolado, 0, critico=r.critico)
        estado = wm.aplicar_dano_inimigo(alvo_id, dano)

    if r.acertou:
        sufixo = " (CRÍTICO)" if r.critico else ""
        contexto = (
            f"ENGINE: {nome_pt} acerta {nome_alvo}{sufixo} — {dano} de dano"
            f"{(' ' + tipo_dano) if tipo_dano else ''}. Narre o efeito, não o número."
        )
    else:
        contexto = (
            f"ENGINE: {nome_pt} erra {nome_alvo}. Narre o quase, não a rolagem."
        )

    return {
        "valido": True,
        "magia": nome_pt,
        "alvo": alvo_id,
        "acertou": r.acertou,
        "critico": r.critico,
        "dano": dano,
        "tipo_dano": tipo_dano,
        "estado_alvo": estado,
        "contexto": contexto,
    }


def consumir_slot_da_magia(wm: Any, nome_pt: str, nome_en: str = "") -> int:
    """Gasta o espaço de magia. Retorna o nível gasto (0 = truque ou sem slot).

    O playtest de 09/08 terminou com os slots INTACTOS depois de uma sessão
    inteira conjurando: o recurso não existia de fato. Truque não gasta nada,
    por regra do SRD — devolver 0 aqui é resposta certa, não falha.
    """
    mecanica = mecanica_da_magia(nome_pt, nome_en)
    if not mecanica:
        return 0
    nivel = int(mecanica.get("nivel", 0) or 0)
    if nivel <= 0:
        return 0
    from engine.magic.slot_tracker import decrementar_slot

    return nivel if decrementar_slot(wm, nivel) else 0
