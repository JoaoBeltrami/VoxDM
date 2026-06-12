"""
Extractor estruturado de estado de combate — Frente A mínima (12/06).

Por que existe: o teste ao vivo #3 provou que markers opcionais = features
    dormentes (o LLM nunca emitiu [INIMIGO] e o beat de turno inimigo não rodou
    a sessão inteira). Este módulo inverte a autoridade: após cada turno de
    combate, uma chamada LLM curta (ENTITY_EXTRACTION → 8B/Gemini) lê a narração
    e devolve JSON com inimigos/estados/dano — a engine aplica, com ou sem
    markers. É o primeiro passo dos structured outputs da Frente A.
Dependências: engine.llm.groq_client (facade), engine.llm.tasks.
Armadilha: o JSON vem por prompt ("responda APENAS JSON"), não por
    response_format nativo — parse SEMPRE via extrair_json_defensivo(), que
    tolera prefixo/sufixo de texto. Falha de parse = turno segue sem extração.

Exemplo:
    estado = await extrair_estado_combate(groq, narracao, inimigos_atuais)
    # → {"inimigos": [{"id": "guarda-1", "nome": "Guarda", "estado": "ferido"}],
    #    "dano_ao_jogador": 0}
"""

import json
import re
from typing import Any

import structlog

from engine.llm.tasks import TaskType

log = structlog.get_logger()

# Bloco JSON dentro de texto livre — o LLM às vezes embrulha em prosa/markdown
_RE_BLOCO_JSON = re.compile(r"\{.*\}", re.DOTALL)

_ESTADOS_VALIDOS = {"intacto", "ferido", "grave", "morto"}

_SYSTEM_EXTRACTOR = (
    "Você extrai estado de combate de narração de RPG em PT-BR. Responda "
    "APENAS com JSON válido, sem texto antes ou depois, no formato:\n"
    '{"inimigos": [{"id": "kebab-case", "nome": "Nome", "estado": '
    '"intacto|ferido|grave|morto"}], "dano_ao_jogador": 0}\n'
    "Regras: liste TODOS os inimigos ativos na cena (inclua os já conhecidos, "
    "com estado atualizado). dano_ao_jogador = PV que o PERSONAGEM DO JOGADOR "
    "perdeu NESTA narração (0 se nenhum). NPCs aliados e espectadores NÃO são "
    "inimigos. Se não há combate na narração, devolva inimigos como lista vazia."
)


def extrair_json_defensivo(texto: str) -> dict[str, Any] | None:
    """Parse de JSON tolerante a prefixo/sufixo de prosa. None se irrecuperável."""
    texto = texto.strip()
    try:
        return json.loads(texto)
    except (json.JSONDecodeError, ValueError):
        m = _RE_BLOCO_JSON.search(texto)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            return None


def _sanitizar(bruto: dict[str, Any]) -> dict[str, Any]:
    """Valida e clampa a saída do LLM — nunca confiar em JSON de modelo."""
    inimigos: list[dict[str, str]] = []
    for item in (bruto.get("inimigos") or [])[:8]:  # cap defensivo
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id", "")).strip().lower()
        iid = re.sub(r"[^a-z0-9-]", "-", iid)[:48].strip("-")
        nome = str(item.get("nome", "")).strip()[:40]
        estado = str(item.get("estado", "intacto")).strip().lower()
        if not iid or estado not in _ESTADOS_VALIDOS:
            continue
        inimigos.append({"id": iid, "nome": nome or iid, "estado": estado})
    dano = bruto.get("dano_ao_jogador", 0)
    dano = int(dano) if isinstance(dano, (int, float)) and dano > 0 else 0
    return {"inimigos": inimigos, "dano_ao_jogador": min(dano, 60)}


async def extrair_estado_combate(
    groq: Any,
    narracao: str,
    inimigos_atuais: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Extrai inimigos/estados/dano da narração via LLM barato (JSON por prompt).

    Retorna dict sanitizado ou None (falha = jogo segue sem extração).
    """
    if not narracao.strip():
        return None
    atuais = ", ".join(
        f"{iid} ({d.get('nome', iid)}: {d.get('estado', '?')})"
        for iid, d in inimigos_atuais.items()
    ) or "nenhum registrado"
    try:
        resposta = await groq.completar(
            [
                {"role": "system", "content": _SYSTEM_EXTRACTOR},
                {
                    "role": "user",
                    "content": (
                        f"Inimigos já registrados: {atuais}\n\n"
                        f"Narração do turno:\n{narracao[:1500]}"
                    ),
                },
            ],
            temperatura=0.1,
            max_tokens=300,
            task=TaskType.ENTITY_EXTRACTION,
        )
    except Exception as e:
        log.warning("extractor_llm_falhou", erro=str(e)[:120])
        return None
    bruto = extrair_json_defensivo(resposta or "")
    if bruto is None:
        log.warning("extractor_json_invalido", amostra=(resposta or "")[:80])
        return None
    return _sanitizar(bruto)


def aplicar_estado_extraido(wm: Any, estado: dict[str, Any]) -> None:
    """Aplica o resultado do extractor na WorkingMemory (engine-authoritative).

    - Inimigos novos são registrados; conhecidos têm o estado atualizado.
    - O placeholder "oponente-1" (auto-registro F0) é substituído quando o
      extractor identifica inimigos reais.
    - Dano ao jogador SÓ aplica se o turno não teve [DANO] explícito (o caller
      decide passando dano>0 apenas nesse caso).
    """
    inimigos = estado.get("inimigos", [])
    if inimigos:
        reais = [i for i in inimigos if i["id"] != "oponente-1"]
        if reais and "oponente-1" in wm.inimigos_combate:
            wm.remover_inimigo("oponente-1")
        for i in inimigos:
            if i["id"] in wm.inimigos_combate:
                wm.atualizar_estado_inimigo(i["id"], i["estado"])
            else:
                wm.registrar_inimigo(i["id"], i["nome"], i["estado"])
    dano = int(estado.get("dano_ao_jogador", 0))
    if dano > 0:
        antes = wm.player_hp
        depois = wm.character.aplicar_dano(dano)
        log.info("extractor_dano_aplicado", dano=dano, hp=f"{antes}->{depois}")
