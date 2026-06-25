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
from typing import Callable

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
    bruto = f"{sal}:{npc_id.strip().lower()}".encode("utf-8")
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


def assinatura_tts(npc_id: str) -> dict[str, str]:
    """Pitch/rate DETERMINÍSTICOS por NPC pra o TTS (N2/F3, playtest 24/06).

    Gênero-safe DE PROPÓSITO: varia a VOZ-BASE do Mestre (pitch/rate), não troca
    de voz — então nunca mis-genera um NPC (a queixa do playtest: "misturou as
    vozes por gênero"). Faixas dentro dos caps do turn_pipeline (±10Hz / ±15%):
    pitch em [-8, +8] Hz, rate em [-12, +12] %. Sais distintos pra variarem
    independente. Determinístico = mesmo NPC soa igual entre sessões, sem storage.

    Retorna {} para id vazio. Ex.: {"pitch": "+5Hz", "rate": "-8%"}.
    """
    if not npc_id or not npc_id.strip():
        return {}
    pitch = _idx(npc_id, 17, "pitch") - 8   # 0..16 → -8..+8 Hz
    rate = _idx(npc_id, 25, "rate") - 12     # 0..24 → -12..+12 %
    return {
        "pitch": f"{'+' if pitch >= 0 else ''}{pitch}Hz",
        "rate": f"{'+' if rate >= 0 else ''}{rate}%",
    }


def bloco_assinaturas(
    npcs_presentes: list[str] | set[str],
    id_para_nome: Callable[[str], str] | None = None,
    cap: int = 3,
) -> str:
    """Bloco de prompt com a assinatura de voz dos NPCs presentes (cap defensivo).

    Retorna "" quando não há NPC presente — custo-zero em cena sem NPC. Cap pra
    não inflar o prompt quando a cena tem muita gente (a "regra dura — um por vez"
    do master_system já limita o foco; aqui é só teto de segurança de token).
    """
    linhas: list[str] = []
    for nid in list(npcs_presentes)[:cap]:
        assn = assinatura_voz(nid)
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
