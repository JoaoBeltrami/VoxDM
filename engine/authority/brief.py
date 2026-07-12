"""
NarrationBrief — o briefing curto que substituirá o dump do para_texto() no prompt.

Por que existe: a tese "autoridade-primeiro, LLM-fino" (Beltrami 20/06) termina
    aqui — a engine resolve tudo determinístico e entrega à LLM um objeto PEQUENO
    (persona cacheável fica fora; por turno vão só fala + fatos resolvidos +
    2-3 fatos de cena + tier + evento de mundo + rolling summary, orçamento
    travado por Beltrami em 01/07: "enxuto + rolling summary sempre incluso").
    Decomposição bloco a bloco do para_texto() que fundamenta cada escolha:
    `.internal/NARRATION_BRIEF_DECOMPOSICAO.md` (12/07).
Dependências: nenhuma externa — funções puras sobre a WorkingMemory (mesmo
    padrão de engine/npc/identity.py). NÃO muta a WM.
Armadilha: peça ISOLADA, não wirada — trocar a fonte do prompt
    (prompt_builder para_texto()→brief) é o passo 🔴 do roadmap que exige
    validação ao vivo de qualidade narrativa. Este módulo nasce testado e
    espera o wiring, como engine/combat/ nasceu antes da costura no WS.

Exemplo:
    brief = montar_brief(wm, "Ataco o goblin!", fatos_resolvidos=linhas_engine)
    system_extra = brief.to_prompt()
    # → bloco "=== BRIEFING DO TURNO ===" com ≤ 2 000 chars garantido por teste
"""

from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger()

# Caps duros do orçamento "enxuto" — validados por teste (test_narration_brief).
# 3 fatos de cena espelham a decisão de 01/07 ("2-3 fatos de cena"); 160 chars
# por fato evita que um único fato reintroduza um dump disfarçado.
MAX_FATOS_CENA = 3
MAX_CHARS_FATO = 160
# Teto do bloco final. Referência: o conjunto wm+outros+fragmentos que o brief
# substitui custava ~5-8k no playtest 10/07; 2k é a meta declarada na decomposição.
MAX_CHARS_BRIEF = 2_000

# Tiers válidos — mesmo vocabulário de engine/combat/narration.classificar_tier.
_TIERS_VALIDOS = frozenset({"seco", "epico"})


@dataclass
class NarrationBrief:
    """Payload por turno pra LLM narrar — NÃO é a WorkingMemory inteira.

    Campos na ordem de autoridade: o que a engine JÁ resolveu vem primeiro
    (fatos_resolvidos, verbatim das linhas "ENGINE: ..."); o resto é contexto
    mínimo de cena. `rolling_summary` viaja SEMPRE que existir (decisão 01/07)
    — é a memória de médio prazo que permitiu cortar quests/consequências.
    """

    fala_jogador: str = ""
    fatos_resolvidos: list[str] = field(default_factory=list)
    fatos_cena: list[str] = field(default_factory=list)
    estado_vital: str = ""
    evento_mundo: str = ""
    tier: str = "seco"
    rolling_summary: str = ""

    def to_prompt(self) -> str:
        """Bloco compacto pro system prompt. Caps aplicados na montagem
        (montar_brief) E aqui (defensivo — o dataclass pode ser construído
        direto por um caller futuro)."""
        linhas: list[str] = ["=== BRIEFING DO TURNO ==="]
        for f in self.fatos_cena[:MAX_FATOS_CENA]:
            linhas.append(f[:MAX_CHARS_FATO])
        if self.estado_vital:
            linhas.append(self.estado_vital[:MAX_CHARS_FATO])
        if self.fatos_resolvidos:
            linhas.append("FATOS JÁ RESOLVIDOS PELA ENGINE (narre, não recalcule):")
            linhas.extend(self.fatos_resolvidos)
        if self.evento_mundo:
            linhas.append(f"EVENTO A TECER: {self.evento_mundo[:MAX_CHARS_FATO]}")
        tier = self.tier if self.tier in _TIERS_VALIDOS else "seco"
        if tier == "epico":
            linhas.append("TOM: momento-chave — narre denso, com peso dramático.")
        else:
            linhas.append("TOM: turno comum — 1-3 frases diretas, sem florear.")
        if self.rolling_summary:
            linhas.append(f"O QUE JÁ ACONTECEU NA SESSÃO:\n{self.rolling_summary}")
        return "\n".join(linhas)


def _fato_local(wm: Any) -> str:
    """1ª linha fixa: âncora mínima de cena (local + hora, clima se houver)."""
    partes = [f"Local: {getattr(wm, 'location_nome', '') or getattr(wm, 'location_id', '?')}"]
    hora = getattr(wm, "time_of_day", "")
    if hora:
        partes.append(hora)
    clima = getattr(wm, "weather", "")
    if clima:
        partes.append(clima)
    return " | ".join(partes)


def _fato_npcs(wm: Any) -> str:
    """NPCs em cena numa linha: apresentados por nome, resto como contagem."""
    presentes = list(getattr(wm, "npcs_presentes", []) or [])
    if not presentes:
        return ""
    apresentados = getattr(getattr(wm, "scene", None), "npcs_apresentados", set()) or set()
    conhecidos = [str(n).replace("-", " ") for n in presentes if n in apresentados]
    fundo = len(presentes) - len(conhecidos)
    partes: list[str] = []
    if conhecidos:
        partes.append(", ".join(conhecidos))
    if fundo > 0:
        partes.append(f"(+{fundo} ao fundo)")
    return f"Em cena: {' '.join(partes)}" if partes else ""


def _fato_aliados(wm: Any) -> str:
    """Aliados compactos: nome + estado de saúde. Stats de combate são da engine."""
    companions = getattr(wm, "companions", {}) or {}
    if not companions:
        return ""
    def _status(c: dict) -> str:
        hp, hp_max = int(c.get("hp", 0)), max(int(c.get("hp_max", 1)), 1)
        pct = hp / hp_max
        if pct <= 0:
            return "caído"
        if pct <= 0.5:
            return "ferido"
        return "bem"
    nomes = [f"{c.get('nome', cid)} ({_status(c)})" for cid, c in companions.items()]
    return f"Aliados: {', '.join(nomes)}"


def _estado_vital(wm: Any) -> str:
    """HP como ESTADO narrativo (não número), só quando importa (ratio ≤ 0.5).
    Condições ativas anexam na mesma linha — volátil e curto."""
    hp = int(getattr(wm, "player_hp", 0) or 0)
    hp_max = int(getattr(wm, "player_hp_max", 0) or 0)
    partes: list[str] = []
    if hp_max > 0:
        ratio = hp / hp_max
        if ratio <= 0.3:
            partes.append("Jogador em ESTADO CRÍTICO — dor, exaustão, desespero")
        elif ratio <= 0.5:
            partes.append("Jogador FERIDO — esforço e cansaço visíveis")
    condicoes = list(getattr(wm, "player_conditions", []) or [])
    if condicoes:
        partes.append(f"condições: {', '.join(condicoes[:5])}")
    return " | ".join(partes)


def _evento_mundo(wm: Any) -> str:
    """UM evento a tecer, primeiro-que-existir (aftermath > tensão).

    Relógios/fios/agendas entram aqui no wiring futuro — a prioridade entre
    eventos concorrentes é decisão registrada pro Beltrami na decomposição.
    """
    if getattr(wm, "saiu_combate_recentemente", False):
        return (
            "o combate acabou de terminar — narre o silêncio que retorna, "
            "as feridas, o que mudou no cenário"
        )
    turnos_calmos = int(getattr(wm, "turnos_sem_tensao", 0) or 0)
    em_combate = bool(getattr(wm, "em_combate", False))
    if not em_combate and turnos_calmos >= 5:
        return (
            f"{turnos_calmos} turnos sem confronto — introduza pressão ambiental, "
            "rumor ou sinal de ameaça próxima"
        )
    return ""


def montar_brief(
    wm: Any,
    fala_jogador: str,
    *,
    fatos_resolvidos: list[str] | None = None,
    tier: str = "seco",
) -> NarrationBrief:
    """Compõe o NarrationBrief a partir da WM — função PURA (não muta nada).

    `fatos_resolvidos` são as linhas "ENGINE: ..." que o orchestrator/authority
    já produziu neste turno (combate resolvido, custo de ouro validado, trust
    aplicado) — entram verbatim, são a autoridade. `tier` vem de
    classificar_tier() quando houver combate; default "seco".
    """
    fatos: list[str] = []
    for fato in (_fato_local(wm), _fato_npcs(wm), _fato_aliados(wm)):
        if fato:
            fatos.append(fato[:MAX_CHARS_FATO])
        if len(fatos) >= MAX_FATOS_CENA:
            break

    brief = NarrationBrief(
        fala_jogador=fala_jogador,
        fatos_resolvidos=list(fatos_resolvidos or []),
        fatos_cena=fatos,
        estado_vital=_estado_vital(wm),
        evento_mundo=_evento_mundo(wm),
        tier=tier if tier in _TIERS_VALIDOS else "seco",
        rolling_summary=str(getattr(wm, "resumo_rolling", "") or ""),
    )
    log.debug(
        "narration_brief_montado",
        fatos_cena=len(brief.fatos_cena),
        fatos_resolvidos=len(brief.fatos_resolvidos),
        chars=len(brief.to_prompt()),
    )
    return brief
