"""
Keep-alive dos bancos free tier: escreve sem rastro e acusa falha no exit code.

Por que existe: em 07/10/26 o Neo4j e o Qdrant tinham sido apagados por
    inatividade. O script diário só serve se (1) o que ele manda pro Aura
    contar como ESCRITA, (2) não deixar lixo no grafo do módulo e (3) o
    agendador conseguir ver quando ele falha.
Dependências: pytest — os dois serviços são trocados por stubs.
Armadilha: não testar o script contra o Aura real aqui; quem prova isso é
    rodar `uv run python -m scripts.manter_vivo` e contar os nós antes e depois.

Exemplo:
    uv run pytest tests/test_manter_vivo.py -q
"""

import pytest

from scripts import manter_vivo


def test_escrita_cria_e_apaga_na_mesma_query() -> None:
    q = manter_vivo._ESCRITA_NEO4J.upper()
    assert "CREATE" in q and "DELETE" in q, "o Aura só conta escrita, e o nó não pode ficar"


@pytest.mark.asyncio
async def test_tudo_ok_devolve_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    async def neo4j_ok() -> None:
        return None

    async def qdrant_ok() -> int:
        return 3

    monkeypatch.setattr(manter_vivo, "_bater_neo4j", neo4j_ok)
    monkeypatch.setattr(manter_vivo, "_bater_qdrant", qdrant_ok)
    assert await manter_vivo.main() == 0


@pytest.mark.asyncio
async def test_um_servico_fora_devolve_um(monkeypatch: pytest.MonkeyPatch) -> None:
    async def neo4j_fora() -> None:
        raise ConnectionError("instância pausada")

    async def qdrant_ok() -> int:
        return 3

    monkeypatch.setattr(manter_vivo, "_bater_neo4j", neo4j_fora)
    monkeypatch.setattr(manter_vivo, "_bater_qdrant", qdrant_ok)
    assert await manter_vivo.main() == 1
