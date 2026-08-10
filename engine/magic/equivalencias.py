"""
Equivalência SRD para as magias da lista PT-BR que não existem no SRD 5.1.

Por que existe: 19 das 154 magias de `spell_list.py` vêm de Xanathar's/Tasha's e
    não têm entrada mecânica no SRD 2014. Sem lastro, conjurá-las continuaria
    sendo PROSA mesmo com o P16 inteiro pronto — e o bruxo é o mais atingido
    (5 das 19; `Hex` é a magia de assinatura da classe).
    Decisão do Beltrami em 09/08: *"prefiro ter as magias mesmo que parecidas"*.
Dependências: engine.magic.spell_mechanics (tabela do SRD).
Armadilha: isto é APROXIMAÇÃO declarada, não equivalência exata. Cada linha foi
    escolhida por EFEITO + NÍVEL, e algumas doem: `Phantasmal Force` (nv2) cai em
    `phantasmal-killer` (nv4), que é bem mais forte. A tabela é a superfície de
    revisão — trocar uma linha não quebra mecânica nenhuma.

Exemplo:
    equivalente_srd("Hex")          # → "hunters-mark"
    equivalente_srd("Bola de Fogo") # → None (já está no SRD, não precisa)
"""

from __future__ import annotations

import unicodedata
from typing import Final

#: PT-BR e EN → índice SRD que empresta a mecânica. O motivo de cada escolha
#: está no comentário: sem ele, a próxima pessoa não sabe se pode mexer.
EQUIVALENCIA_SRD: Final[dict[str, str]] = {
    # ── Renomeações do SRD (NÃO são aproximação: é a MESMA magia) ────────────
    # O SRD 5.1 retira os nomes próprios de mago das magias clássicas. Estas
    # duas viviam só na tabela de um TESTE — produção nunca as resolveu, e o
    # teste de cobertura foi quem achou.
    "bigby's hand": "arcane-hand",
    "bigbys hand": "arcane-hand",
    "mao de bigby": "arcane-hand",
    "melf's acid arrow": "acid-arrow",
    "melfs acid arrow": "acid-arrow",
    "flecha acida de melf": "acid-arrow",

    # ── Bruxo (o mais atingido) ──────────────────────────────────────────────
    # Hex: amaldiçoa o alvo e soma 1d6 necrótico nos ataques. `hunters-mark` faz
    # exatamente isso (marca + dano extra por ataque), mesmo nível, sem dano
    # direto — é a equivalência mais limpa da tabela inteira.
    "hex": "hunters-mark",
    "armadura de hex": "hunters-mark",
    # Arms of Hadar: área curta, save de FOR, 2d6 necrótico. `thunderwave` é
    # área curta com save e 2d8 — mesmo formato, mesmo nível.
    "arms of hadar": "thunderwave",
    "maldicao de praga": "thunderwave",
    # Ray of Sickness: ataque de magia, 2d8 veneno. `ray-of-enfeeblement` é o
    # raio debilitante do SRD — ataque, mesma família, um nível acima.
    "ray of sickness": "ray-of-enfeeblement",
    "raio de doenca": "ray-of-enfeeblement",
    # Shadow of Moil: ataques contra você com desvantagem + escuridão.
    # `darkness` é a escuridão mágica do SRD, mesmo nível.
    "shadow of moil": "darkness",
    "rajada de sombras": "darkness",
    # Phantasmal Force: ilusão que fere 1d6/turno. Cai em `phantasmal-killer`.
    # ⚠️ A pior aproximação da tabela: nv2 → nv4, e o dano é 4d10 contra 1d6.
    "phantasmal force": "phantasmal-killer",
    "forca fantasmal": "phantasmal-killer",

    # ── Druida ───────────────────────────────────────────────────────────────
    # Thorn Whip: truque de ataque 1d6 que puxa. `shillelagh` é o truque de
    # combate corpo-a-corpo do druida; não puxa, mas é a arma mágica dele.
    "thorn whip": "shillelagh",
    "crescimento de espinhos": "shillelagh",
    # Frostbite: truque, save CON, 1d6 frio + desvantagem. `ray-of-frost` seria
    # ideal mas é ataque, não save; `bane` é save e impõe penalidade, nv1.
    "frostbite": "bane",
    "formacao de gelo": "bane",
    # Erupting Earth: cubo, 3d12, save DES, terreno difícil. `lightning-bolt`
    # é a área grande com save de DES do mesmo nível.
    "erupting earth": "lightning-bolt",
    "trovao esmagador": "lightning-bolt",
    # Summon Beast: convoca besta CR 1. `find-familiar` é a convocação do SRD.
    "summon beast": "find-familiar",
    "forma enxame": "find-familiar",
    # Wall of Water: muro que dá meia cobertura. `wall-of-stone` é o muro do SRD.
    # ⚠️ nv3 → nv5, e o de pedra é bem mais forte.
    "wall of water": "wall-of-stone",
    "muro de agua": "wall-of-stone",
    # Absorb Elements: reação defensiva de nv1. `shield` é a reação defensiva
    # de nv1 do SRD — não dá resistência elemental, mas é a mesma função.
    "absorb elements": "shield",
    "absorver elementos": "shield",

    # ── Clérigo ──────────────────────────────────────────────────────────────
    # Healing Spirit: cura recorrente. `healing-word` é a cura rápida do SRD.
    "healing spirit": "healing-word",
    "palavra de cura maior": "healing-word",
    # Consecrate: terreno sagrado contra mortos-vivos. `spirit-guardians` é a
    # área sagrada do SRD.
    "consecrate": "spirit-guardians",
    "consagrar": "spirit-guardians",

    # ── Paladino ─────────────────────────────────────────────────────────────
    # Blinding Smite e Wrathful Smite: golpes divinos com efeito. O SRD tem
    # `branding-smite` — o smite genérico, com dano extra no próximo acerto.
    "blinding smite": "branding-smite",
    "ouro cegante": "branding-smite",
    "wrathful smite": "branding-smite",
    "feridas da luz": "branding-smite",

    # ── Bardo / Mago ─────────────────────────────────────────────────────────
    # Dissonant Whispers: 3d6 psíquico, save SAB, um alvo. `moonbeam` é o dano
    # em área com save do mesmo nível de acesso do bardo.
    "dissonant whispers": "moonbeam",
    "sussurros dissonantes": "moonbeam",
    # Cloud of Daggers: área persistente de dano. `flaming-sphere` é a área
    # persistente de dano do SRD, mesmo nível.
    "cloud of daggers": "flaming-sphere",
    "nuvem de adormecimento": "flaming-sphere",

    # ── Patrulheiro ──────────────────────────────────────────────────────────
    # Conjure Barrage: cone de projéteis, save DES. `lightning-bolt` é a área
    # com save de DES do mesmo nível.
    "conjure barrage": "lightning-bolt",
    "voo de besta": "lightning-bolt",
    # Snare: armadilha que imobiliza, save DES. `entangle` é a imobilização
    # com save do SRD, mesmo nível.
    "snare": "entangle",
    "desestruturar terreno": "entangle",
}


def _normalizar(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def equivalente_srd(nome: str) -> str | None:
    """Índice SRD que empresta a mecânica a esta magia. None se não há mapa.

    Aceita o nome em PT-BR ou em inglês — o Beltrami pediu que o Mestre entenda
    os dois, e a mesma exigência vale aqui.
    """
    return EQUIVALENCIA_SRD.get(_normalizar(nome))
