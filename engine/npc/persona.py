"""
Assinatura de voz por NPC — dá a cada NPC uma maneira de falar DISTINTA e estável.

Por que existe: depois de várias cenas, os NPCs da VoxDM soavam todos iguais
(feedback do Beltrami: "os NPCs são muito iguais"). Um mestre veterano nunca
deixa dois NPCs borrarem — cada um tem um RITMO de fala e um tique. Aqui a engine
atribui, de forma DETERMINÍSTICA pelo id (sem storage, estável entre sessões,
token-zero), um registro + um tique por NPC, injetado no prompt SÓ quando o NPC
está na cena (gating em prompt_builder; combate fica de fora pela dieta de token).

Por que determinístico-por-id: mesmo NPC → sempre a mesma voz, sem precisar
persistir nada nem chamar LLM. 12 registros × 12 tiques = 144 combinações, com
sais distintos pra registro e tique variarem independentes.

Dependências: stdlib (hashlib). Sem I/O, sem LLM.
Armadilha: os registros são de RITMO/maneira (servem a QUALQUER NPC — terso,
    prolixo, irônico…), não de conteúdo/classe social — evita atribuir "gíria de
    rua" a um rei de forma jarring. A distinção vem da CONSISTÊNCIA + variedade.

Exemplo:
    assinatura_voz("aldric-drevasson")
    # → "seco e direto, frases curtas; encerra com uma pergunta de volta"
"""

import hashlib
from collections.abc import Callable

# Registros de RITMO/maneira de falar — fiction-safe (cabem em qualquer NPC).
_REGISTROS: tuple[str, ...] = (
    "seco e direto, frases curtas",
    "prolixo, floreia e às vezes se perde",
    "irônico, mede o interlocutor antes de responder",
    "formal e cerimonioso",
    "caloroso, fala como a um velho amigo",
    "desconfiado, guarda as palavras",
    "teatral, gosta do próprio drama",
    "pausado, escolhe cada palavra",
    "tagarela, salta de um assunto a outro",
    "grave e sentencioso, fala como quem avisa",
    "afável mas evasivo, sorri sem responder direito",
    "rude e impaciente, vai direto ao osso",
)

# Tiques verbais — pequenos hábitos que assinam a fala (também genéricos).
_TIQUES: tuple[str, ...] = (
    "começa as falas com um 'Olha...'",
    "encerra com uma pergunta de volta",
    "repete a última palavra de quem falou",
    "jura por algo a cada frase",
    "inventa um apelido pra quem fala com ele",
    "deixa frases morrerem no meio",
    "ri baixo no meio das frases",
    "usa metáforas do próprio ofício",
    "abaixa a voz como quem confidencia",
    "responde com um ditado popular",
    "gesticula ou tamborila enquanto fala",
    "corrige o próprio jeito de dizer ('ou melhor...')",
)


def _idx(npc_id: str, n: int, sal: str) -> int:
    """Índice determinístico em [0, n) a partir do id (sha1 estável)."""
    bruto = f"{sal}:{npc_id.strip().lower()}".encode()
    return int(hashlib.sha1(bruto).hexdigest()[:8], 16) % n


def assinatura_voz(npc_id: str) -> str:
    """Registro + tique DETERMINÍSTICOS de um NPC (estável, distinto, token-zero).

    Vazio se o id for vazio. Sais distintos ('reg'/'tic') fazem registro e tique
    variarem independente — dois NPCs com o mesmo registro raramente têm o mesmo tique.
    """
    if not npc_id or not npc_id.strip():
        return ""
    registro = _REGISTROS[_idx(npc_id, len(_REGISTROS), "reg")]
    tique = _TIQUES[_idx(npc_id, len(_TIQUES), "tic")]
    return f"{registro}; {tique}"


# Baldes QUANTIZADOS e bem-espaçados de pitch/rate. Antes (faixa fina -8..+8 /
# -12..+12) dois NPCs caíam a 1Hz/2% um do outro → indistinguíveis ao ouvido. Em
# baldes, vozes adjacentes diferem por ≥4Hz ou ≥6% (claramente distintas). Dentro
# dos caps do turn_pipeline (±10Hz / ±15%). 5×5 = 25 combos (colisão baixa numa
# cena de ≤8 NPCs).
_PITCH_BUCKETS: tuple[int, ...] = (-8, -4, 0, 4, 8)
_RATE_BUCKETS: tuple[int, ...] = (-12, -6, 0, 6, 12)


def assinatura_tts(npc_id: str) -> dict[str, str]:
    """Pitch/rate DETERMINÍSTICOS e CLARAMENTE distintos por NPC (N2/F3, 24/06).

    Gênero-safe DE PROPÓSITO: varia a VOZ-BASE do Mestre (pitch/rate), não troca
    de voz — nunca mis-genera (queixa do playtest "misturou por gênero"). Baldes
    bem-espaçados (≥4Hz / ≥6% entre adjacentes) pra serem audivelmente diferentes.
    Determinístico = mesmo NPC soa igual entre sessões, sem storage. Evita (0,0)
    pra nenhum NPC soar idêntico ao narrador.

    Retorna {} para id vazio. Ex.: {"pitch": "+4Hz", "rate": "-6%"}.
    """
    if not npc_id or not npc_id.strip():
        return {}
    pitch = _PITCH_BUCKETS[_idx(npc_id, len(_PITCH_BUCKETS), "pitch")]
    rate = _RATE_BUCKETS[_idx(npc_id, len(_RATE_BUCKETS), "rate")]
    if pitch == 0 and rate == 0:  # idêntico ao narrador — desempata p/ um lado
        rate = 6 if _idx(npc_id, 2, "tie") == 0 else -6
    return {
        "pitch": f"{'+' if pitch >= 0 else ''}{pitch}Hz",
        "rate": f"{'+' if rate >= 0 else ''}{rate}%",
    }


def bloco_assinaturas(
    npcs_presentes: list[str] | set[str],
    id_para_nome: Callable[[str], str] | None = None,
    cap: int = 3,
    seed_de: Callable[[str], str] | None = None,
) -> str:
    """Bloco de prompt com a assinatura de voz dos NPCs presentes (cap defensivo).

    Retorna "" quando não há NPC presente — custo-zero em cena sem NPC. Cap pra
    não inflar o prompt quando a cena tem muita gente (a "regra dura — um por vez"
    do master_system já limita o foco; aqui é só teto de segurança de token).

    `seed_de` (NPC-IDENTIDADE 05/07): resolve o id → seed ESTÁVEL de identidade
    (id original de criação). NPC renomeado via name-reveal mantém o MESMO
    registro/tique de fala — sem isso o rename trocaria a personalidade junto
    com o nome (mesma classe do bug do retrato).
    """
    linhas: list[str] = []
    for nid in list(npcs_presentes)[:cap]:
        assn = assinatura_voz(seed_de(nid) if seed_de else nid)
        if not assn:
            continue
        nome = id_para_nome(nid) if id_para_nome else nid
        linhas.append(f"• {nome}: {assn}")
    if not linhas:
        return ""
    return (
        "\n=== ASSINATURA DE VOZ DOS NPCs (mantenha cada um DISTINTO) ===\n"
        + "\n".join(linhas)
        + "\nCada NPC fala no SEU ritmo e tique — nunca deixe dois soarem igual."
    )
