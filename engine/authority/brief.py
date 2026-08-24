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

# TELL C (ADR-005 + medição 24/07): o fôlego do turno, decidido pela engine.
# Os três registros que um mestre humano alterna sem pensar.
# Medição de 24/07 (16 turnos): pedir CONTAGEM não funciona — adesão 0/5 a "UMA
# frase". O modelo encompria porque preenche SLOTS DE CONTEÚDO (ambiente + fala
# + gesto + gancho) e, sob teto de palavras, só comprime cada slot. A alavanca é
# tirar ou abrir SLOT, não contar palavra: sem ambiente e sem gancho, a resposta
# encurta sozinha — como um mestre humano que responde a pergunta e para.
_INSTRUCAO_RITMO: dict[str, str] = {
    "curto": "TOM: responda e PARE. Só a reação direta ao que ele fez/perguntou "
             "— nada de descrever o ambiente, nada de terceiros entrando, nada "
             "de gancho no fim. A cena fica parada esperando ele.",
    "medio": "TOM: turno comum — a reação e um gesto, sem florear.",
    "longo": "TOM: deixe a cena RESPIRAR — a reação, o ambiente ao redor, um "
             "detalhe que ninguém pediu e o mundo seguindo sem o jogador.",
}
_RITMOS_VALIDOS = frozenset(_INSTRUCAO_RITMO)

# A outra metade do TELL C: o COMPRIMENTO já era da engine, a FORMA de abrir não
# era de ninguém — e o modelo convergia em artigo ("O ferreiro olha..."). Medido
# em 17/08: uma corrida com as SEIS aberturas na mesma forma.
# Cada instrução manda UMA coisa concreta. "Varie a abertura" seria prompt contra
# amostragem — o ADR-006 já registra que isso baixa a frequência e não fecha a
# porta. Quem escolhe a forma do turno é a engine; aqui só mora o texto.
# Não existe forma "você": abrir pelo jogador é o TELL A.
_INSTRUCAO_ABERTURA: dict[str, str] = {
    "fala": "ABERTURA: a primeira coisa do turno é alguém FALANDO — comece pela "
            "fala, entre aspas.",
    "gesto": "ABERTURA: comece pelo CORPO de quem está em cena — o gesto antes "
             "da palavra.",
    "mundo": "ABERTURA: comece pelo mundo — um som, um cheiro, um objeto. Gente "
             "só depois.",
}
_ABERTURAS_VALIDAS = frozenset(_INSTRUCAO_ABERTURA)


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
    ritmo: str = "medio"
    # Forma de abertura decidida pela engine ("" = sem regra neste turno).
    abertura: str = ""
    rolling_summary: str = ""
    batismo_pendente: str = ""
    # Fios/agenda/cliffhanger em aberto — ver `_em_aberto`.
    em_aberto: str = ""

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
        if self.batismo_pendente:
            linhas.append(self.batismo_pendente[:MAX_CHARS_FATO * 2])
        tier = self.tier if self.tier in _TIERS_VALIDOS else "seco"
        # TELL C (ADR-005): dizer "1-3 frases" TODO turno É a monotonia — o
        # modelo converge no mesmo tamanho sempre, e a sessão inteira vira um
        # metrônomo. Quem decide o fôlego é a ENGINE (autoridade-primeiro), e
        # ela varia de propósito: um mestre humano às vezes corta com uma
        # frase, às vezes deixa a cena respirar.
        #
        # 26/07: o ramo "epico" SUBSTITUÍA esta linha. Com o pacing colado em 10
        # nos turnos 37-48 do playtest, o Mestre recebeu o MESMO TOM 12 turnos
        # seguidos e a rotação curto/médio/longo foi descartada em silêncio — o
        # metrônomo que o TELL C existe pra matar, reintroduzido pela porta dos
        # fundos. Pior: o teto de palavras continuava rotacionando (30/80/110),
        # então o prompt mandava "narre denso" e, logo abaixo, "máximo 30
        # palavras". Épico agora ACRESCENTA peso; não apaga o fôlego.
        linhas.append(_INSTRUCAO_RITMO.get(self.ritmo, _INSTRUCAO_RITMO["medio"]))
        if self.abertura in _ABERTURAS_VALIDAS:
            linhas.append(_INSTRUCAO_ABERTURA[self.abertura])
        if tier == "epico":
            linhas.append("PESO: momento-chave — densidade dramática, sem alongar.")
        if self.em_aberto:
            linhas.append(self.em_aberto)
        if self.rolling_summary:
            linhas.append(f"O QUE JÁ ACONTECEU NA SESSÃO:\n{self.rolling_summary}")
        return "\n".join(linhas)


# Teto do bloco de continuidade. O motivo do corte original era dump: agenda de 8
# NPCs + 5 fios viram parágrafo e afogam o brief, que tem MAX_CHARS_BRIEF=2000.
MAX_CHARS_ABERTO = 340


def _em_aberto(wm: Any) -> str:
    """O que o Mestre deixou pendente e pode puxar de volta.

    BRIEF-SEM-FIOS (playtest 26/07): `[FIO:]`, `[AGENDA:]` e `[CLIFFHANGER:]` eram
    ESCRITOS pelo pipeline mas lidos só pelo `montar_mensagens` legado — todos
    depois do early-return que desvia pro brief. Com BRIEF_ATIVO=True (default),
    nada disso jamais chegou ao prompt de produção. O código admitia: "Relógios/
    fios/agendas entram aqui no wiring futuro".

    Efeito sentido pelo jogador: "ele já tá improvisando demais na loucura sem ter
    provavelmente nenhuma ideia de follow up". Não era falta de criatividade — era
    amnésia: o Mestre criava o gancho e nunca mais o via.

    Agenda é filtrada pelos NPCs EM CENA — é o que impede o dump que motivou o
    corte: plano de NPC ausente não é gancho, é ruído.
    """
    linhas: list[str] = []
    cliff = str(getattr(wm, "cliffhanger_pendente", "") or "").strip()
    if cliff:
        linhas.append(f"guardado: {cliff}")
    for fio in list(getattr(wm, "fios_soltos", []) or [])[-3:]:
        if str(fio).strip():
            linhas.append(f"fio: {str(fio).strip()}")
    presentes = {str(n) for n in (getattr(wm, "npcs_presentes", []) or [])}
    agenda = getattr(wm, "agenda_npcs", {}) or {}
    for npc_id, plano in agenda.items():
        if str(npc_id) in presentes and str(plano).strip():
            linhas.append(f"{_nome_legivel(wm, str(npc_id))} quer: {str(plano).strip()}")
    if not linhas:
        return ""
    corpo = "; ".join(linhas)[:MAX_CHARS_ABERTO]
    return f"EM ABERTO (puxe UM se couber, não liste): {corpo}"


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


def _nome_legivel(wm: Any, npc_id: str) -> str:
    """Nome do registro canônico; o id kebab só como último recurso.

    NPC-SEM-BATISMO-2 (playtest 21/07): o brief imprimia `id.replace("-"," ")`,
    então o Mestre lia "Em cena: tavern eiro, pessoa andar superior" e re-usava
    isso como se fosse gente — o descritor voltava cimentado a cada turno.
    """
    registro = getattr(getattr(wm, "scene", None), "npc_registro", {}) or {}
    entrada = registro.get(npc_id) or {}
    nome = str(entrada.get("nome", "")).strip()
    return nome or str(npc_id).replace("-", " ")


def _fato_npcs(wm: Any) -> str:
    """NPCs em cena numa linha: apresentados por nome, resto como contagem."""
    presentes = list(getattr(wm, "npcs_presentes", []) or [])
    if not presentes:
        return ""
    apresentados = getattr(getattr(wm, "scene", None), "npcs_apresentados", set()) or set()
    conhecidos = [_nome_legivel(wm, str(n)) for n in presentes if n in apresentados]
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


def _batismo_pendente(wm: Any) -> str:
    """Cobra nome próprio de quem já está em cena há turnos e segue sem nome.

    NPC-SEM-BATISMO-2 (playtest 21/07): o registro da sessão tinha
    `tavern-eiro → "homem gordo e simpático"` e `pessoa-andar-superior` depois
    de 23 turnos. O fix de julho só ensinou o Mestre a inventar nome QUANDO
    PERGUNTADO; quem nunca é interrogado morre sem nome. Um por turno — batizar
    a taverna inteira de uma vez soa a chamada de classe.
    """
    try:
        from engine.npc.identity import precisa_de_batismo
        pendentes = precisa_de_batismo(wm)
    except Exception as e:
        log.warning("batismo_pendente_falhou", erro=str(e)[:80])
        return ""
    if not pendentes:
        return ""
    npc_id, descritor = pendentes[0]
    return (
        f"BATIZE: {descritor} já cruzou o caminho do jogador mais de uma vez e "
        f"segue sem nome. Dê um nome próprio na narração e registre com "
        f"[NPC: {npc_id}|Nome]."
    )


def montar_brief(
    wm: Any,
    fala_jogador: str,
    *,
    fatos_resolvidos: list[str] | None = None,
    tier: str = "seco",
    ritmo: str = "medio",
    abertura: str = "",
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
        ritmo=ritmo if ritmo in _RITMOS_VALIDOS else "medio",
        abertura=abertura if abertura in _ABERTURAS_VALIDAS else "",
        rolling_summary=str(getattr(wm, "resumo_rolling", "") or ""),
        batismo_pendente=_batismo_pendente(wm),
        em_aberto=_em_aberto(wm),
    )
    log.debug(
        "narration_brief_montado",
        fatos_cena=len(brief.fatos_cena),
        fatos_resolvidos=len(brief.fatos_resolvidos),
        chars=len(brief.to_prompt()),
    )
    return brief
