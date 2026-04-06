"""
Lê um arquivo PDF e extrai o texto de cada página via PyMuPDF.

Por que existe: primeiro passo do pipeline de ingestão — transforma o PDF
do módulo de RPG em texto bruto antes de qualquer processamento por LLM.
Dependências: PyMuPDF (fitz)
Armadilha: `fitz.open()` aceita caminhos inválidos sem erro imediato —
o erro só aparece ao iterar as páginas. Validar existência antes de abrir.

Exemplo:
    paginas = await extrair_paginas("curse_of_strahd.pdf")
    # → [{"pagina": 1, "texto": "...", "char_count": 3200}, ...]
"""

from pathlib import Path

import fitz  # PyMuPDF
import structlog

logger = structlog.get_logger(__name__)


async def extrair_paginas(caminho_pdf: str) -> list[dict]:
    """Extrai texto de todas as páginas de um PDF.

    Args:
        caminho_pdf: Caminho para o arquivo PDF.

    Returns:
        Lista de dicionários com chaves: pagina (int, 1-based),
        texto (str), char_count (int). Páginas sem texto são ignoradas.

    Raises:
        FileNotFoundError: Se o arquivo não existir no caminho informado.
        RuntimeError: Se o PDF estiver corrompido ou protegido por senha.
    """
    caminho = Path(caminho_pdf)

    if not caminho.exists():
        raise FileNotFoundError(f"PDF não encontrado: {caminho_pdf}")

    if caminho.suffix.lower() != ".pdf":
        raise ValueError(f"Arquivo não é um PDF: {caminho_pdf}")

    log = logger.bind(caminho=str(caminho))
    log.info("abrindo_pdf")

    try:
        doc: fitz.Document = fitz.open(str(caminho))
    except Exception as e:
        raise RuntimeError(f"Falha ao abrir PDF '{caminho_pdf}': {e}") from e

    total_paginas: int = len(doc)
    log.info("pdf_aberto", total_paginas=total_paginas)

    paginas: list[dict] = []

    for numero in range(total_paginas):
        pagina: fitz.Page = doc[numero]
        texto: str = pagina.get_text().strip()

        if not texto:
            log.debug("pagina_vazia", pagina=numero + 1)
            continue

        paginas.append({
            "pagina": numero + 1,
            "texto": texto,
            "char_count": len(texto),
        })

    doc.close()

    paginas_com_texto: int = len(paginas)
    char_total: int = sum(p["char_count"] for p in paginas)

    log.info(
        "extracao_concluida",
        paginas_com_texto=paginas_com_texto,
        paginas_vazias=total_paginas - paginas_com_texto,
        char_total=char_total,
    )

    return paginas


def filtrar_paginas_por_intervalo(
    paginas: list[dict],
    inicio: int,
    fim: int,
) -> list[dict]:
    """Filtra páginas pelo número (1-based, intervalo inclusivo).

    Útil para processar seções específicas do PDF sem reabrir o arquivo.

    Args:
        paginas: Lista retornada por extrair_paginas().
        inicio: Número da primeira página a incluir (1-based).
        fim: Número da última página a incluir (1-based).

    Returns:
        Subconjunto das páginas no intervalo [inicio, fim].
    """
    return [p for p in paginas if inicio <= p["pagina"] <= fim]
