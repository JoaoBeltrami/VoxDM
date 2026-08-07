"""
Resumo contínuo intra-sessão (rolling summary) — memória de médio prazo.

Por que existe: a janela de diálogo do mestre é curta (MAX_DIALOGOS=6). Em
    sessões longas, turnos antigos saem da janela e o mestre "esquece" o que
    aconteceu há 10 minutos. Este módulo comprime incrementalmente o que já
    passou num parágrafo de prosa que é injetado no system prompt como memória
    interna — preservando continuidade sem reenviar todo o diálogo (economia de
    ~1.500 tokens/turno em sessão de 1h).
Dependências: engine/llm/{groq_client,tasks,prompt_builder}, engine/state/scene,
    engine/memory/working_memory, config, structlog.
Armadilha: NUNCA propagar exceção — esta função roda DEPOIS do turno já ter sido
    entregue ao jogador. Se a LLM falhar, o fallback concatena o diálogo bruto
    (truncado por aplicar_resumo_rolling) e segue. Nunca quebra a sessão.

Exemplo:
    if wm.narrative.deve_resumir(settings.ROLLING_SUMMARY_INTERVALO):
        await atualizar_resumo_rolling(wm)
    # → wm.narrative.resumo_rolling agora contém prosa atualizada; contador zerado
"""

from pathlib import Path

import structlog

from config import settings
from engine.llm.groq_client import GroqClient
from engine.llm.prompt_builder import _ler_prompt
from engine.llm.tasks import TaskType
from engine.memory.working_memory import WorkingMemory
from engine.state.scene import MAX_DIALOGOS

log = structlog.get_logger()

# Prompt em arquivo editável (hot-reload por mtime via _ler_prompt do prompt_builder).
_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "rolling_summary.md"

# Estado da cena é só contexto auxiliar no prompt de resumo — truncar pra não
# reintroduzir o inchaço de para_texto() que a própria Frente A combate.
_MAX_ESTADO_CHARS = 600

# Fallback inline caso o .md suma/corrompa — mantém o contrato de placeholders.
_PROMPT_FALLBACK = (
    "Atualize (não recomece) o resumo contínuo desta sessão de RPG, fundindo o "
    "resumo existente com o diálogo novo numa prosa de 4 a 6 frases em português, "
    "preservando tensão, fios em aberto, mudanças de relação e escolhas do jogador. "
    # SUMARIO-3A-PESSOA-1: o fallback precisa carregar a MESMA regra de pessoa
    # que o .md — senão um erro de leitura do arquivo reintroduz o bug calado.
    "Escreva em SEGUNDA PESSOA ('você entregou o aço'), nunca em terceira "
    "('Klaus entregou o aço'); terceira pessoa só para NPCs e o mundo. "
    "Sem listas, sem JSON, sem cabeçalhos, sem colchetes.\n\n"
    "Resumo até agora:\n{resumo_atual}\n\n"
    "Fios em aberto: {fios_soltos}\n\n"
    "Estado da cena:\n{estado}\n\n"
    "Diálogo novo:\n{dialogo_novo}\n\n"
    "Devolva apenas o resumo atualizado, em prosa."
)


def _montar_dialogo_novo(working_mem: WorkingMemory) -> str:
    """Formata a janela de diálogo recente como texto simples (Jogador/NPC: ...)."""
    linhas: list[str] = []
    for turno in working_mem.dialogo_recente:
        prefixo = "Jogador" if turno.falante == "player" else turno.falante
        linhas.append(f"{prefixo}: {turno.texto}")
    return "\n".join(linhas)


async def atualizar_resumo_rolling(working_mem: WorkingMemory) -> str:
    """Regera o resumo contínuo da sessão via compressão incremental.

    Funde `narrative.resumo_rolling` (o que já existe) com a janela atual de
    diálogo usando a LLM (TaskType.MEMORY_COMPRESSION — cascata prioriza Gemini).
    Em qualquer falha, faz fallback gracioso para o diálogo bruto concatenado e
    NÃO propaga a exceção. Em ambos os caminhos, `aplicar_resumo_rolling` zera o
    contador de turnos e trunca em settings.ROLLING_SUMMARY_MAX_CHARS.

    Returns:
        O resumo rolling resultante (já persistido em working_mem.narrative).
    """
    # Sanidade de config: INTERVALO é em TURNOS, MAX_DIALOGOS é em FALAS
    # (2 falas/turno). Se INTERVALO*2 passar da janela, um turno introduzido no
    # início do intervalo sai da janela de diálogo ANTES do resumo capturá-lo.
    if settings.ROLLING_SUMMARY_INTERVALO * 2 > MAX_DIALOGOS:
        log.warning(
            "rolling_summary_intervalo_invalido",
            intervalo_turnos=settings.ROLLING_SUMMARY_INTERVALO,
            max_dialogos_falas=MAX_DIALOGOS,
        )

    dialogo_novo = _montar_dialogo_novo(working_mem)
    resumo_atual = working_mem.narrative.resumo_rolling
    estado = working_mem.para_texto()[:_MAX_ESTADO_CHARS]
    fios = "; ".join(working_mem.fios_soltos) if working_mem.fios_soltos else "nenhum"

    template = _ler_prompt(_PROMPT_PATH) or _PROMPT_FALLBACK
    prompt = template.format(
        resumo_atual=resumo_atual or "(ainda não há resumo desta sessão)",
        dialogo_novo=dialogo_novo or "(sem diálogo novo)",
        estado=estado,
        fios_soltos=fios,
    )

    try:
        groq = GroqClient()
        novo = await groq.completar(
            [{"role": "user", "content": prompt}],
            temperatura=0.4,
            max_tokens=300,
            task=TaskType.MEMORY_COMPRESSION,
        )
        novo = novo.strip()
        if not novo:
            raise ValueError("resumo_rolling vazio")
        working_mem.narrative.aplicar_resumo_rolling(novo)
        log.info(
            "rolling_summary_atualizado",
            chars=len(working_mem.narrative.resumo_rolling),
        )
    except Exception as e:
        # Fallback gracioso — concatena resumo anterior + diálogo bruto. O
        # aplicar_resumo_rolling trunca no teto e zera o contador, garantindo
        # que a próxima janela não dispare resumo imediatamente de novo.
        log.warning("rolling_summary_falhou_usando_fallback", erro=str(e))
        bruto = f"{resumo_atual}\n{dialogo_novo}".strip() if resumo_atual else dialogo_novo
        working_mem.narrative.aplicar_resumo_rolling(bruto)

    return working_mem.narrative.resumo_rolling
