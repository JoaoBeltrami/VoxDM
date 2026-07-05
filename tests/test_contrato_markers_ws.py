"""
Contrato ponta-a-ponta de markers e tipos WS — teste-guarda sistêmico.

Por que existe: a mesma classe de bug apareceu 3× em julho/26 — uma ponta do
    contrato foi cortada/esquecida e a feature morreu EM SILÊNCIO do outro lado:
    - "relacao" faltava no enum zod → a fronteira WS descartava TODOS os toasts
      de relação (nunca funcionaram até 04/07);
    - a doc de [FUGIU] foi cortada numa dieta de prompt → o LLM nunca mais
      soube que o marcador existia → fuga de combate morta;
    - "metricas" ficou no enum zod sem emissor nem handler (tipo fantasma).
    Este módulo valida as pontas AUTOMATICAMENTE — cortar qualquer lado do
    contrato agora quebra um teste com mensagem explicando o que religar.
Dependências: stdlib (re, pathlib) + engine.markers + quest_detector.
Armadilha: os testes leem ARQUIVOS-FONTE (prompts .md, ws-schema.ts, api/*.py)
    por texto — renomear/mover esses arquivos exige atualizar os paths aqui.
    É intencional: o contrato cruza fronteiras (Python↔Markdown↔TypeScript)
    que nenhum type-checker cobre.

Exemplo:
    uv run pytest tests/test_contrato_markers_ws.py -q
"""

import re
from pathlib import Path

from engine.markers import NOMES_MARCADORES
from engine.memory.quest_detector import strip_marcadores

_RAIZ = Path(__file__).resolve().parents[1]
_DOC_MARKERS = _RAIZ / "engine" / "llm" / "prompts" / "fragments" / "markers_lista.md"
_PROMPTS_DIR = _RAIZ / "engine" / "llm" / "prompts"
_PROMPT_BUILDER = _RAIZ / "engine" / "llm" / "prompt_builder.py"
_WS_SCHEMA_TS = _RAIZ / "frontend" / "lib" / "ws-schema.ts"

# Variantes de eco de OUTRO marker — existem só pra strip (o LLM ecoa a tag sem
# preservar o acento); não têm processador nem instrução própria por design.
_VARIANTES_STRIP_ONLY: frozenset[str] = frozenset({"PRESSAGIO"})  # gêmeo de PRESSÁGIO


# ── Helpers de parsing ────────────────────────────────────────────────────────


def _markers_documentados() -> set[str]:
    """Nomes de marker citados como `[NOME...]` no markers_lista.md."""
    texto = _DOC_MARKERS.read_text(encoding="utf-8")
    return set(re.findall(r"\[([A-ZÀ-Ü_]{2,})(?=[:\]\s])", texto))


def _fontes_processamento() -> str:
    """Concatenação dos .py de api/ + engine/ (exceto a própria tabela canônica)."""
    partes: list[str] = []
    for base in ("api", "engine"):
        for p in sorted((_RAIZ / base).rglob("*.py")):
            if p.name == "markers.py":
                continue
            partes.append(p.read_text(encoding="utf-8"))
    return "\n".join(partes)


def _fontes_instrucao_llm() -> str:
    """Tudo que o LLM vê sobre markers: prompts .md + injeções do prompt_builder."""
    partes = [p.read_text(encoding="utf-8") for p in sorted(_PROMPTS_DIR.rglob("*.md"))]
    partes.append(_PROMPT_BUILDER.read_text(encoding="utf-8"))
    return "\n".join(partes)


def _tipos_ws_emitidos() -> set[str]:
    """Tipos de mensagem WS que o backend emite — nas DUAS formas de construção:
    `MensagemWS(tipo="x")` e dict cru DENTRO de `_send_json_seguro(...)`
    (scene_image/npc_retrato). O dict cru precisa estar no call do send —
    `{"tipo": ...}` solto não conta (ex: combate_pendente usa a mesma chave
    pra estado interno e NÃO é mensagem WS)."""
    tipos: set[str] = set()
    for p in sorted((_RAIZ / "api").rglob("*.py")):
        texto = p.read_text(encoding="utf-8")
        tipos.update(re.findall(r'tipo="([a-z_]+)"', texto))
        tipos.update(
            re.findall(
                r'_send_json_seguro\([^)]*?"tipo":\s*"([a-z_]+)"', texto, re.DOTALL
            )
        )
    return tipos


def _tipos_ws_enum_zod() -> set[str]:
    """Valores do enum TIPOS_WS no ws-schema.ts, ignorando linhas de comentário
    (sem isso, o comentário '// "metricas" removido' voltaria como fantasma)."""
    texto = _WS_SCHEMA_TS.read_text(encoding="utf-8")
    m = re.search(r"const TIPOS_WS = \[(.*?)\] as const", texto, re.DOTALL)
    assert m, "bloco `const TIPOS_WS = [...] as const` não encontrado no ws-schema.ts"
    linhas_uteis = [
        linha for linha in m.group(1).splitlines()
        if not linha.strip().startswith("//")
    ]
    return set(re.findall(r'"([a-z_]+)"', "\n".join(linhas_uteis)))


# ── Ponta 1: doc do LLM ↔ tabela de strip ────────────────────────────────────


def test_todo_marker_documentado_esta_na_tabela_de_strip():
    """Marker ensinado ao LLM no markers_lista.md TEM que ser strippado —
    senão o LLM emite e o TTS lê o colchete em voz alta pro jogador."""
    fora_da_tabela = _markers_documentados() - set(NOMES_MARCADORES)
    assert not fora_da_tabela, (
        f"Markers documentados sem strip: {sorted(fora_da_tabela)} — "
        "adicionar em engine/markers.py NOMES_MARCADORES"
    )


def test_todo_marker_documentado_e_strippado_de_fato():
    """Funcional, não só de conjunto: cada marker da doc some do texto via
    strip_marcadores nas duas formas (com args e sem args)."""
    for nome in sorted(_markers_documentados()):
        com_args = strip_marcadores(f"antes [{nome}: x|y|z] depois")
        sem_args = strip_marcadores(f"antes [{nome}] depois")
        assert f"[{nome}" not in com_args, f"[{nome}: ...] sobreviveu ao strip"
        assert f"[{nome}" not in sem_args, f"[{nome}] sobreviveu ao strip"


# ── Ponta 2: tabela de strip ↔ processador na engine ─────────────────────────


def test_todo_marker_da_tabela_tem_referencia_de_processamento():
    """Marker na tabela de strip sem NENHUMA referência em api/+engine/ é um
    fio morto (strippado mas nunca processado — a feature não existe). Exceção:
    variantes de eco (_VARIANTES_STRIP_ONLY), que só existem pro strip."""
    fontes = _fontes_processamento()
    orfaos = [
        nome for nome in NOMES_MARCADORES
        if nome not in _VARIANTES_STRIP_ONLY and nome not in fontes
    ]
    assert not orfaos, (
        f"Markers strippados sem processador/referência: {orfaos} — "
        "ou implementar o handler ou remover da tabela"
    )


# ── Ponta 3: tabela de strip ↔ instrução pro LLM (classe do bug [FUGIU]) ─────


def test_todo_marker_da_tabela_e_instruido_ao_llm():
    """A dieta de prompt de 01/07 cortou a linha do [FUGIU] da doc e o marcador
    morreu em silêncio (processador vivo, LLM nunca mais soube que existia).
    Aqui: todo marker da tabela precisa aparecer em ALGUM lugar do que o LLM
    vê — prompts .md OU injeções do prompt_builder.py."""
    instrucao = _fontes_instrucao_llm()
    nao_instruidos = [
        nome for nome in NOMES_MARCADORES
        if nome not in _VARIANTES_STRIP_ONLY and nome not in instrucao
    ]
    assert not nao_instruidos, (
        f"Markers que o LLM nunca fica sabendo que existem: {nao_instruidos} — "
        "documentar num prompt .md ou remover a feature"
    )


# ── Ponta 4: emissões WS do backend ↔ enum zod do frontend ───────────────────


def test_todo_tipo_ws_emitido_esta_no_enum_zod():
    """Classe do bug do toast de relação: tipo emitido pelo backend fora do
    enum zod = parseMensagemWS descarta TODA mensagem daquele tipo na fronteira,
    em silêncio. A feature parece shipada e nunca dispara."""
    fora_do_enum = _tipos_ws_emitidos() - _tipos_ws_enum_zod()
    assert not fora_do_enum, (
        f"Tipos WS emitidos pelo backend fora do enum zod: {sorted(fora_do_enum)} — "
        "adicionar em frontend/lib/ws-schema.ts TIPOS_WS (e handler no useGameSession)"
    )


def test_enum_zod_sem_tipos_fantasma():
    """Classe do bug 'metricas': tipo no enum que o backend nunca emite é código
    morto que mascara a leitura do contrato — remover do enum e do union TS."""
    fantasmas = _tipos_ws_enum_zod() - _tipos_ws_emitidos()
    assert not fantasmas, (
        f"Tipos no enum zod que o backend nunca emite: {sorted(fantasmas)} — "
        "remover de TIPOS_WS e do union em api.ts (ou implementar o emissor)"
    )


# ── Sanidade dos helpers (o teste-guarda também pode quebrar em silêncio) ────


def test_helpers_encontram_conteudo_real():
    """Se um parser voltar vazio (arquivo movido, formato mudou), os testes de
    conjunto acima passariam vacuamente — aqui garantimos que cada helper acha
    um volume plausível de conteúdo."""
    assert len(_markers_documentados()) >= 20
    assert len(_tipos_ws_emitidos()) >= 10
    assert len(_tipos_ws_enum_zod()) >= 10
    assert "def " in _fontes_processamento()
    assert "IDIOMA" in _fontes_instrucao_llm() or len(_fontes_instrucao_llm()) > 10_000
