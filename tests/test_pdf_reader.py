"""Testes para ingestor/pdf_reader.py."""

import io
from pathlib import Path

import fitz
import pytest

from ingestor.pdf_reader import extrair_paginas, filtrar_paginas_por_intervalo


def _criar_pdf_temporario(tmp_path: Path, paginas: list[str]) -> Path:
    """Cria um PDF real em disco com o texto informado por página."""
    caminho = tmp_path / "teste.pdf"
    doc = fitz.open()
    for texto in paginas:
        pagina = doc.new_page()
        if texto:
            pagina.insert_text((50, 50), texto)
    doc.save(str(caminho))
    doc.close()
    return caminho


@pytest.mark.anyio
async def test_extrair_paginas_retorna_texto(tmp_path: Path) -> None:
    """Extrai texto de PDF com 2 páginas com conteúdo."""
    caminho = _criar_pdf_temporario(tmp_path, ["Página um", "Página dois"])
    resultado = await extrair_paginas(str(caminho))

    assert len(resultado) == 2
    assert resultado[0]["pagina"] == 1
    assert "Página um" in resultado[0]["texto"]
    assert resultado[0]["char_count"] > 0


@pytest.mark.anyio
async def test_extrair_paginas_ignora_paginas_vazias(tmp_path: Path) -> None:
    """Páginas sem texto são ignoradas no resultado."""
    caminho = _criar_pdf_temporario(tmp_path, ["Conteúdo", "", "Mais conteúdo"])
    resultado = await extrair_paginas(str(caminho))

    assert len(resultado) == 2
    numeros = [p["pagina"] for p in resultado]
    assert 1 in numeros
    assert 3 in numeros


@pytest.mark.anyio
async def test_extrair_paginas_arquivo_inexistente() -> None:
    """FileNotFoundError quando arquivo não existe."""
    with pytest.raises(FileNotFoundError, match="PDF não encontrado"):
        await extrair_paginas("/caminho/que/nao/existe.pdf")


@pytest.mark.anyio
async def test_extrair_paginas_extensao_invalida(tmp_path: Path) -> None:
    """ValueError quando arquivo não é PDF."""
    arquivo_txt = tmp_path / "texto.txt"
    arquivo_txt.write_text("conteúdo")
    with pytest.raises(ValueError, match="não é um PDF"):
        await extrair_paginas(str(arquivo_txt))


def test_filtrar_paginas_por_intervalo() -> None:
    """Filtra corretamente pelo número de página."""
    paginas = [
        {"pagina": 1, "texto": "a", "char_count": 1},
        {"pagina": 2, "texto": "b", "char_count": 1},
        {"pagina": 3, "texto": "c", "char_count": 1},
        {"pagina": 4, "texto": "d", "char_count": 1},
    ]
    resultado = filtrar_paginas_por_intervalo(paginas, inicio=2, fim=3)
    assert len(resultado) == 2
    assert resultado[0]["pagina"] == 2
    assert resultado[1]["pagina"] == 3
