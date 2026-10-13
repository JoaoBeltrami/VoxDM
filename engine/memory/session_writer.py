"""
Comprime e persiste uma sessão ao final — ponte entre sessões do VoxDM.

Por que existe: ao encerrar a sessão, o diálogo completo é resumido via Groq
    e gravado no Qdrant (coleção voxdm_episodic). Na próxima sessão, o
    context_builder recupera esse resumo como memória episódica.
Dependências: engine/llm/groq_client, engine/memory/{working_memory,qdrant_client}
    ingestor/embedder, structlog, config
Armadilha: o resumo usa Groq — se indisponível, gravar o diálogo bruto truncado
    em vez de falhar silenciosamente.
Armadilha: `owner` é o PRIMEIRO argumento e não tem default. Era `owner_email=""`
    opcional no fim da assinatura — um caller que esquecesse gravava memória
    sem dono, e memória sem dono é legado admin-only que ninguém reencontra.

Exemplo:
    writer = SessionWriter()
    dono = Owner(email="jogador@example.com")
    resumo = await writer.fechar_sessao(dono, working_mem, session_id="sess-02")
    # → {"session_id": "sess-02", "resumo": "O grupo chegou à aldeia...",
    #    "trust_levels": {"fael-valdreksson": 3}, "quest_stages": {...}}
"""

import time
import uuid
from pathlib import Path
from typing import Any

import structlog

from engine.auth.identity import Owner, exigir_dono
from engine.llm.groq_client import GroqClient
from engine.llm.tasks import TaskType
from engine.memory.qdrant_client import CAMPO_DONO, QdrantMemoryClient
from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Máximo de caracteres do diálogo passado ao Groq para resumo
_MAX_DIALOGO_CHARS = 6000

_PROMPT_RESUMO = """\
Você é um assistente que resume sessões de RPG de mesa de forma compacta.
Com base no resumo contínuo da sessão, no estado e na última janela de
diálogo abaixo, gere um parágrafo de 3-5 frases em português brasileiro
descrevendo: o que aconteceu, quais NPCs foram encontrados e como a relação
com eles evoluiu, que quests avançaram, e se o personagem ganhou aliados ou
acumulou recursos notáveis.
Seja factual e narrativo — sem opiniões, sem listas.

Resumo contínuo da sessão (memória do que já passou):
{resumo_rolling}

Estado da sessão:
{estado}

Aliados ativos: {companions}
Fios narrativos em aberto: {fios_soltos}

Última janela de diálogo:
{dialogo}
"""

# Guia de compressão de sessão (session_eval.md) usado como SYSTEM message — guia
# rico (5 momentos, estrutura, sinais de engajamento). Resolve drift #60: o arquivo
# existia mas o resumo usava só o prompt inline. Quando carrega, vira o system e
# _PROMPT_DADOS (só os dados) vira o user; se ausente, cai no _PROMPT_RESUMO inline
# (auto-suficiente) — sem regressão.
_SESSION_EVAL_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "session_eval.md"

_PROMPT_DADOS = """\
Resumo contínuo da sessão (memória do que já passou):
{resumo_rolling}

Estado da sessão:
{estado}

Aliados ativos: {companions}
Fios narrativos em aberto: {fios_soltos}

Última janela de diálogo:
{dialogo}
"""


def _carregar_session_eval() -> str | None:
    """Carrega session_eval.md (guia de compressão). Import tardio evita ciclo."""
    from engine.llm.prompt_builder import _ler_prompt
    return _ler_prompt(_SESSION_EVAL_PATH)


def _montar_dialogo(working_mem: WorkingMemory) -> str:
    """Formata o diálogo recente da working memory como texto simples."""
    linhas: list[str] = []
    for turno in working_mem.dialogo_recente:
        prefixo = "Jogador" if turno.falante == "player" else turno.falante
        linhas.append(f"{prefixo}: {turno.texto}")
    return "\n".join(linhas)


async def _resumir_via_groq(working_mem: WorkingMemory) -> str:
    """Gera resumo narrativo da sessão usando Groq. Fallback: diálogo bruto."""
    dialogo = _montar_dialogo(working_mem)[:_MAX_DIALOGO_CHARS]
    estado = working_mem.para_texto()

    # Companions — "Lyssa (hireling, 24/30 HP), Grumpf (animal, 15/15 HP)"
    companions_txt = ", ".join(
        f"{c.get('nome', cid)} ({c.get('tipo', 'aliado')}, {c.get('hp', '?')}/{c.get('hp_max', '?')} HP)"
        for cid, c in working_mem.companions.items()
    ) or "nenhum"

    # Fios soltos — lista ou "nenhum"
    fios_txt = "; ".join(working_mem.fios_soltos) if working_mem.fios_soltos else "nenhum"

    # Resumo contínuo (Frente A) — memória já comprimida do que passou nesta
    # sessão. Resumir A PARTIR dele dá fidelidade muito maior que truncar o
    # diálogo bruto em 6000 chars: turnos antigos (fora da janela) já estão
    # representados aqui. Pode estar vazio em sessão curta (< intervalo).
    resumo_rolling_txt = working_mem.resumo_rolling or "(sessão curta — sem resumo contínuo)"

    guia = _carregar_session_eval()
    if guia:
        # session_eval.md = guia (system); só os dados vão no user.
        dados = _PROMPT_DADOS.format(
            estado=estado,
            dialogo=dialogo,
            companions=companions_txt,
            fios_soltos=fios_txt,
            resumo_rolling=resumo_rolling_txt,
        )
        mensagens = [
            {"role": "system", "content": guia},
            {"role": "user", "content": dados},
        ]
    else:
        # Fallback: prompt inline auto-suficiente (session_eval.md ausente/curto).
        prompt = _PROMPT_RESUMO.format(
            estado=estado,
            dialogo=dialogo,
            companions=companions_txt,
            fios_soltos=fios_txt,
            resumo_rolling=resumo_rolling_txt,
        )
        mensagens = [{"role": "user", "content": prompt}]

    try:
        groq = GroqClient()
        # Resumo prioriza Gemini (cota grande, excelente em síntese) — evita
        # estourar TPD do Groq com tarefas auxiliares ao encerrar sessão.
        resumo = await groq.completar(
            mensagens, temperatura=0.4, max_tokens=512, task=TaskType.SUMMARIZATION,
        )
        log.info("resumo_gerado_llm", chars=len(resumo))
        return resumo
    except Exception as e:
        log.warning("resumo_groq_falhou_usando_dialogo", erro=str(e))
        # Fallback: primeiros 1000 chars do diálogo bruto
        return dialogo[:1000] if dialogo else "Sessão sem diálogo registrado."


class SessionWriter:
    """
    Serializa e persiste o estado de uma sessão ao final.

    Uso típico: instanciar uma vez, chamar fechar_sessao() ao término.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()

    async def fechar_sessao(
        self,
        owner: Owner,
        working_mem: WorkingMemory,
        session_id: str | None = None,
        npcs_mencionados: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Resumo + upsert no Qdrant. Retorna o dict de estado persistido.

        Args:
            owner: Dono da sessão — obrigatório. Sem dono válido levanta
                `DonoObrigatorio` ANTES de gastar a chamada de LLM do resumo.
            working_mem: Estado da sessão ao momento do encerramento.
            session_id: ID da sessão (usa working_mem.session_id se omitido).
            npcs_mencionados: NPCs relevantes para indexação (usa npcs_presentes se omitido).

        Returns:
            Dict com session_id, resumo, trust_levels, quest_stages e timestamp.
        """
        email = exigir_dono(owner)
        sid = session_id or working_mem.session_id
        npcs = npcs_mencionados or working_mem.npcs_presentes

        resumo = await _resumir_via_groq(working_mem)

        payload: dict[str, Any] = {
            "session_id": sid,
            CAMPO_DONO: email,   # chave de tenant — o cliente Qdrant recarimba
            "text": resumo,
            "trust_levels": working_mem.trust_levels,
            "faction_standings": working_mem.faction_standings,
            "quest_stages": working_mem.quest_stages,
            "location_final": working_mem.location_id,
            "npcs_mencionados": npcs,
            "timestamp": time.time(),
            "source_type": "episodic",
            "source_id": sid,
            "source_name": f"Sessão {sid}",
            # Campos novos — restauração de continuidade entre sessões
            "player_level": working_mem.player_level,
            "xp": working_mem.xp,
            "gold": working_mem.gold,
            "companions": dict(working_mem.companions),
            "dm_state": {
                "fios_soltos":          list(working_mem.fios_soltos),
                "agenda_npcs":          dict(working_mem.agenda_npcs),
                "cliffhanger_pendente": working_mem.cliffhanger_pendente or "",
                "resumo_rolling":       working_mem.resumo_rolling or "",
            },
        }

        # ID determinístico por session_id — refechar a mesma sessão sobrescreve
        # o próprio ponto em vez de empilhar resumos.
        ponto_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"voxdm-episodic-{sid}"))
        await self._qdrant.gravar_memoria(owner, ponto_id, resumo, payload)

        log.info(
            "sessao_persistida",
            session_id=sid,
            trust_levels=working_mem.trust_levels,
            quest_stages=working_mem.quest_stages,
            companions=len(working_mem.companions),
            fios_soltos=len(working_mem.fios_soltos),
        )
        return payload
