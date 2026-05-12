"""
Catálogo de vozes por perfil de NPC e atribuição determinística.

Por que existe: cada NPC precisa de uma voz consistente entre turnos e sessões,
    adequada ao gênero e raça, sem escolha manual. O narrador usa a voz
    selecionada pelo jogador nas Opções; NPCs usam vozes do catálogo.
Dependências: apenas stdlib — sem imports de engine (evita ciclo).
Armadilha: Edge TTS só tem 3 vozes pt-BR. Para criaturas não-humanas usamos
    vozes en-US para criar estranheza sonora deliberada.

Exemplo:
    perfil = selecionar_perfil("valdrek", genero="male", raca="humano")
    # → {"voz": "pt-BR-AntonioNeural", "rate": "-12%", "pitch": "+0Hz"}
"""

import hashlib
import unicodedata
from typing import TypedDict


class PerfilVoz(TypedDict):
    voz: str
    rate: str
    pitch: str


# ── Vozes pt-BR disponíveis (verificadas via edge_tts.list_voices()) ─────────
_PT_M = "pt-BR-AntonioNeural"
_PT_F_A = "pt-BR-FranciscaNeural"       # voz principal feminina
_PT_F_B = "pt-BR-ThalitaMultilingualNeural"  # feminina, mais jovem/leve

# Vozes en-US para criaturas/raças exóticas (estranheza sonora intencional)
_EN_M_A = "en-US-GuyNeural"
_EN_M_B = "en-US-EricNeural"
_EN_F_A = "en-US-AriaNeural"
_EN_F_B = "en-US-JennyNeural"

# ── Catálogo de perfis por categoria ─────────────────────────────────────────

# Taxa e tom base para narração (copiamos de tts.py para evitar import circular)
_R0 = "-12%"   # rate padrão narrativo
_P0 = "+0Hz"   # pitch neutro

_CATALOGO: dict[str, PerfilVoz] = {
    # Humanos — 2 variantes femininas distribuídas por hash
    "humano_m":       {"voz": _PT_M,   "rate": _R0,   "pitch": _P0},
    "humano_f_a":     {"voz": _PT_F_A, "rate": _R0,   "pitch": _P0},
    "humano_f_b":     {"voz": _PT_F_B, "rate": "-8%", "pitch": _P0},

    # Elfos — mais leves, pitch levemente mais alto
    "elfo_m":         {"voz": _PT_M,   "rate": "-8%",  "pitch": "+2Hz"},
    "elfo_f":         {"voz": _PT_F_B, "rate": "-6%",  "pitch": "+3Hz"},

    # Anões — mais lentos, pitch mais baixo
    "anao_m":         {"voz": _PT_M,   "rate": "-18%", "pitch": "-3Hz"},
    "anao_f":         {"voz": _PT_F_A, "rate": "-15%", "pitch": "-2Hz"},

    # Halflings/Gnomos — mais rápidos, pitch mais alto
    "halfling":       {"voz": _PT_F_B, "rate": "-4%",  "pitch": "+4Hz"},
    "gnomo":          {"voz": _PT_F_B, "rate": "-2%",  "pitch": "+5Hz"},

    # Orcs/Meio-orcs — en-US para estranheza, mais graves
    "orc_m":          {"voz": _EN_M_A, "rate": "-10%", "pitch": "-4Hz"},
    "orc_f":          {"voz": _EN_F_A, "rate": "-8%",  "pitch": "-3Hz"},

    # Goblins — en-US, agudos e rápidos
    "goblin":         {"voz": _EN_M_B, "rate": "+5%",  "pitch": "+5Hz"},

    # Tieflings — en-US, levemente sombrios
    "tiefling_m":     {"voz": _EN_M_A, "rate": _R0,   "pitch": "-2Hz"},
    "tiefling_f":     {"voz": _EN_F_B, "rate": _R0,   "pitch": "-1Hz"},

    # Draconatos — en-US, graves e lentos
    "draconato_m":    {"voz": _EN_M_A, "rate": "-14%", "pitch": "-5Hz"},
    "draconato_f":    {"voz": _EN_F_A, "rate": "-12%", "pitch": "-4Hz"},

    # Criaturas genéricas (monstros, animais inteligentes) — en-US
    "criatura_m":     {"voz": _EN_M_A, "rate": "-8%",  "pitch": "-3Hz"},
    "criatura_f":     {"voz": _EN_F_A, "rate": "-6%",  "pitch": "-2Hz"},
}

# Mapa raça normalizada → (chave_masc, chave_fem) no catálogo
_MAPA_RACA: dict[str, tuple[str, str]] = {
    "humano":         ("humano_m", "humano_f_a"),
    "humana":         ("humano_m", "humano_f_a"),
    "human":          ("humano_m", "humano_f_a"),
    "elfo":           ("elfo_m",   "elfo_f"),
    "elfa":           ("elfo_m",   "elfo_f"),
    "elfo alto":      ("elfo_m",   "elfo_f"),
    "elfo da floresta": ("elfo_m", "elfo_f"),
    "elf":            ("elfo_m",   "elfo_f"),
    "anão":           ("anao_m",   "anao_f"),
    "anã":            ("anao_m",   "anao_f"),
    "dwarf":          ("anao_m",   "anao_f"),
    "halfling":       ("halfling", "halfling"),
    "gnomo":          ("gnomo",    "gnomo"),
    "gnome":          ("gnomo",    "gnomo"),
    "orc":            ("orc_m",    "orc_f"),
    "meio-orc":       ("orc_m",    "orc_f"),
    "half-orc":       ("orc_m",    "orc_f"),
    "goblin":         ("goblin",   "goblin"),
    "tiefling":       ("tiefling_m", "tiefling_f"),
    "draconato":      ("draconato_m", "draconato_f"),
    "dragonborn":     ("draconato_m", "draconato_f"),
}

# Verbos de fala usados para detectar NPC falante numa sentença
VERBOS_FALA = frozenset({
    "diz", "fala", "murmura", "sussurra", "grita", "responde", "pergunta",
    "cospe", "ri", "sorri", "solta", "comenta", "replica", "reclama",
    "avisa", "ameaça", "insiste", "acrescenta", "continua", "conclui",
    "admite", "hesita", "interrompe", "corrige", "confirma", "nega",
    "resmunga", "exclama", "lamenta", "declara", "ordena",
    "implora", "suplica", "anuncia", "revela", "confessa", "promete",
})


def _normalizar(texto: str) -> str:
    """Remove acentos e converte para minúsculas para lookup case-insensitive."""
    return unicodedata.normalize("NFD", texto.lower()).encode("ascii", "ignore").decode()


def selecionar_perfil(
    npc_id: str,
    genero: str = "",
    raca: str = "",
) -> PerfilVoz:
    """
    Retorna perfil de voz determinístico para um NPC.

    A atribuição é baseada em raça e gênero quando disponíveis; quando não,
    usa hash do npc_id para distribuir consistentemente entre as variantes.

    Args:
        npc_id: ID kebab-case do NPC (ex: "valdrek", "fael-valdreksson").
        genero: "male"/"female"/"m"/"f"/"masculino"/"feminino" ou vazio.
        raca:   Raça em minúsculas (ex: "humano", "elfo", "orc") ou vazio.

    Returns:
        PerfilVoz com voz, rate e pitch.
    """
    raca_norm = _normalizar((raca or "").strip())
    genero_norm = (genero or "").lower().strip()
    eh_feminino = genero_norm in ("female", "f", "feminino", "fem")

    # Busca exata no mapa de raças (normalizado)
    _mapa_norm = {_normalizar(k): v for k, v in _MAPA_RACA.items()}
    par = _mapa_norm.get(raca_norm)
    if par is None:
        # Busca parcial (ex: "elfo alto" contém "elfo")
        for chave_n, perfis in _mapa_norm.items():
            if chave_n and (chave_n in raca_norm or raca_norm in chave_n):
                par = perfis
                break

    if par is None:
        # Sem raça reconhecida: fallback humano, gênero por hash do npc_id
        seed = int(hashlib.md5(npc_id.encode()).hexdigest(), 16)
        if not genero_norm:
            eh_feminino = seed % 3 == 0  # ~33% feminino por padrão
        par = ("humano_m", "humano_f_a")

    chave_m, chave_f = par
    chave = chave_f if eh_feminino else chave_m

    # Humanos femininos: distribui entre Francisca e Thalita por hash
    if chave == "humano_f_a":
        seed = int(hashlib.md5(npc_id.encode()).hexdigest(), 16)
        chave = "humano_f_b" if seed % 2 == 0 else "humano_f_a"

    return _CATALOGO.get(chave, _CATALOGO["humano_m"])


def nomes_para_ids(
    npc_ids: list[str],
) -> dict[str, str]:
    """
    Retorna mapa nome_display → npc_id para lookup rápido na detecção de fala.

    Ex: ["fael-valdreksson", "inn-keeper"] →
        {"Fael Valdreksson": "fael-valdreksson", "Inn Keeper": "inn-keeper"}
    """
    return {
        " ".join(p.capitalize() for p in nid.split("-")): nid
        for nid in npc_ids
    }
