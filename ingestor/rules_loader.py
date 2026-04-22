"""
Carrega e normaliza regras do SRD 5e para chunks prontos para o Qdrant.

Por que existe: as regras do sistema (magias, condições, classes, equipamentos)
    precisam estar vetorizadas na coleção voxdm_rules para que o LLM responda
    perguntas como "o que Fireball faz?" com precisão baseada no SRD oficial.
Dependências: httpx, structlog, tenacity
Armadilha: desc nos JSONs do SRD é lista de strings (parágrafos), não string
    direta — sempre juntar com "\\n" antes de processar.

Exemplo:
    chunks = await carregar_regras(Path("./srd_data"))
    # → [ChunkRecord(text="Fireball (Magia Nível 3 — Evocação)...", source_type="spell", ...)]
"""

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingestor.chunker import ChunkRecord, _dividir_em_chunks

log = structlog.get_logger()

# Fonte pública — licença OGL / CC-BY 4.0
_SRD_URLS: dict[str, str] = {
    "spells":     "https://raw.githubusercontent.com/5e-bits/5e-database/main/src/5e-SRD-Spells.json",
    "conditions": "https://raw.githubusercontent.com/5e-bits/5e-database/main/src/5e-SRD-Conditions.json",
    "equipment":  "https://raw.githubusercontent.com/5e-bits/5e-database/main/src/5e-SRD-Equipment.json",
    "classes":    "https://raw.githubusercontent.com/5e-bits/5e-database/main/src/5e-SRD-Classes.json",
}

_NOMES_ARQUIVOS: dict[str, str] = {
    "spells":     "5e-SRD-Spells.json",
    "conditions": "5e-SRD-Conditions.json",
    "equipment":  "5e-SRD-Equipment.json",
    "classes":    "5e-SRD-Classes.json",
}

_SOURCE_TYPES: dict[str, str] = {
    "spells":     "spell",
    "conditions": "condition",
    "equipment":  "equipment",
    "classes":    "class",
}


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "srd_download_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    before_sleep=_logar_tentativa,
    reraise=True,
)
async def _baixar_arquivo(url: str, destino: Path) -> None:
    """Baixa um JSON do SRD e salva em disco."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resposta = await client.get(url)
        resposta.raise_for_status()
        destino.write_bytes(resposta.content)
    log.info("srd_arquivo_baixado", destino=str(destino))


async def garantir_srd_local(srd_dir: Path) -> None:
    """Garante que os JSONs do SRD estão em srd_dir, baixando os ausentes."""
    srd_dir.mkdir(parents=True, exist_ok=True)
    for categoria, nome_arquivo in _NOMES_ARQUIVOS.items():
        destino = srd_dir / nome_arquivo
        if destino.exists():
            log.info("srd_arquivo_presente", arquivo=nome_arquivo)
            continue
        log.info("srd_baixando", categoria=categoria)
        await _baixar_arquivo(_SRD_URLS[categoria], destino)


# ── Normalizadores de texto por categoria ─────────────────────────────────────

def _juntar_desc(desc: Any) -> str:
    """Junta lista de parágrafos em string única."""
    if isinstance(desc, list):
        return "\n".join(str(p) for p in desc if p)
    if isinstance(desc, str):
        return desc
    return ""


def _normalizar_magia(entry: dict[str, Any]) -> str:
    nome: str = entry.get("name", "")
    nivel: int = entry.get("level", 0)
    escola: str = entry.get("school", {}).get("name", "")
    casting_time: str = entry.get("casting_time", "")
    alcance: str = entry.get("range", "")
    componentes: list[str] = entry.get("components", [])
    material: str = entry.get("material", "")
    duracao: str = entry.get("duration", "")
    ritual: bool = entry.get("ritual", False)
    concentracao: bool = entry.get("concentration", False)
    desc: str = _juntar_desc(entry.get("desc", []))
    higher_level: str = _juntar_desc(entry.get("higher_level", []))
    classes: list[str] = [c.get("name", "") for c in entry.get("classes", [])]

    nivel_str = "Truque" if nivel == 0 else f"Nível {nivel}"
    comp_str = ", ".join(componentes)
    if material:
        comp_str += f" ({material})"
    flags = ""
    if ritual:
        flags += " | Ritual"
    if concentracao:
        flags += " | Concentração"
    classes_str = ", ".join(c for c in classes if c)

    partes = [
        f"{nome} (Magia {nivel_str} — {escola})",
        f"Conjuração: {casting_time} | Alcance: {alcance} | Componentes: {comp_str} | Duração: {duracao}{flags}",
    ]
    if desc:
        partes.append(desc)
    if higher_level:
        partes.append(f"Em níveis superiores: {higher_level}")
    if classes_str:
        partes.append(f"Classes: {classes_str}")
    return "\n".join(partes)


def _normalizar_condicao(entry: dict[str, Any]) -> str:
    nome: str = entry.get("name", "")
    desc: str = _juntar_desc(entry.get("desc", []))
    return f"{nome} (Condição D&D 5e)\n{desc}"


def _normalizar_equipamento(entry: dict[str, Any]) -> str:
    nome: str = entry.get("name", "")
    categoria: str = entry.get("equipment_category", {}).get("name", "")
    custo_qtd: Any = entry.get("cost", {}).get("quantity", "")
    custo_unit: str = entry.get("cost", {}).get("unit", "")
    peso: Any = entry.get("weight", "")
    desc: str = _juntar_desc(entry.get("desc", []))

    partes = [f"{nome} ({categoria})"]
    detalhes: list[str] = []
    if custo_qtd and custo_unit:
        detalhes.append(f"Custo: {custo_qtd} {custo_unit}")
    if peso:
        detalhes.append(f"Peso: {peso} lb")
    if detalhes:
        partes.append(" | ".join(detalhes))
    if desc:
        partes.append(desc)
    return "\n".join(partes)


def _normalizar_classe(entry: dict[str, Any]) -> str:
    nome: str = entry.get("name", "")
    hit_die: int = entry.get("hit_die", 0)
    saving_throws: list[str] = [s.get("name", "") for s in entry.get("saving_throws", [])]
    subclasses: list[str] = [s.get("name", "") for s in entry.get("subclasses", [])]
    proficiencias: list[str] = [p.get("name", "") for p in entry.get("proficiencies", [])]

    partes = [
        f"{nome} (Classe D&D 5e)",
        f"Dado de vida: d{hit_die}",
    ]
    if saving_throws:
        partes.append(f"Salvaguardas: {', '.join(s for s in saving_throws if s)}")
    if proficiencias:
        partes.append(f"Proficiências: {', '.join(p for p in proficiencias if p)}")
    if subclasses:
        partes.append(f"Subclasses: {', '.join(s for s in subclasses if s)}")
    return "\n".join(partes)


_NORMALIZADORES: dict[str, Callable[[dict[str, Any]], str]] = {
    "spells":     _normalizar_magia,
    "conditions": _normalizar_condicao,
    "equipment":  _normalizar_equipamento,
    "classes":    _normalizar_classe,
}


# ── Processamento ──────────────────────────────────────────────────────────────

def _processar_categoria(
    entries: list[dict[str, Any]],
    categoria: str,
) -> list[ChunkRecord]:
    """Normaliza e chunka todas as entradas de uma categoria SRD."""
    normalizador = _NORMALIZADORES[categoria]
    source_type = _SOURCE_TYPES[categoria]
    chunks: list[ChunkRecord] = []

    for entry in entries:
        source_id: str = entry.get("index", "")
        source_name: str = entry.get("name", source_id)
        if not source_id:
            continue

        texto = normalizador(entry)
        if not texto.strip():
            continue

        novos = _dividir_em_chunks(
            texto=texto,
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            campo="srd",
        )
        chunks.extend(novos)

    log.info(
        "srd_categoria_processada",
        categoria=categoria,
        entradas=len(entries),
        chunks=len(chunks),
    )
    return chunks


async def carregar_regras(srd_dir: Path, baixar: bool = True) -> list[ChunkRecord]:
    """
    Carrega os JSONs do SRD 5e e retorna chunks prontos para embedding.

    Args:
        srd_dir: Diretório onde estão (ou serão baixados) os JSONs.
        baixar: Se True, baixa arquivos ausentes automaticamente.

    Returns:
        Lista de ChunkRecord para todas as categorias SRD configuradas.
    """
    if baixar:
        await garantir_srd_local(srd_dir)

    todos: list[ChunkRecord] = []

    for categoria, nome_arquivo in _NOMES_ARQUIVOS.items():
        caminho = srd_dir / nome_arquivo
        if not caminho.exists():
            log.warning("srd_arquivo_ausente", categoria=categoria, path=str(caminho))
            continue

        with caminho.open(encoding="utf-8") as f:
            entries: list[dict[str, Any]] = json.load(f)

        if not isinstance(entries, list):
            log.error("srd_formato_invalido", categoria=categoria, tipo=type(entries).__name__)
            continue

        chunks = _processar_categoria(entries, categoria)
        todos.extend(chunks)

    log.info("srd_carregado", total_chunks=len(todos))
    return todos
