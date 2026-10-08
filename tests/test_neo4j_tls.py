"""
TLS do Neo4j: `+s` vira verificação estrita com as raízes do certifi.

Por que existe (07/10/26): a instância nova do Aura veio com cadeia SSL.com e a
    loja de certificados do Windows não tinha a raiz — todo driver falhou com
    "self-signed certificate in certificate chain". O conserto não pode virar
    `+ssc` (aceita qualquer certificado) e precisa valer nos OITO lugares que
    abrem driver, não só no que estava quebrando na hora.
Dependências: pytest, neo4j, certifi — nenhuma conexão real.
Armadilha: o driver recusa `encrypted`/`trusted_certificates` junto de um
    esquema `+s` (ConfigurationError). Por isso o teste cria o driver de verdade:
    checar só o dict passaria verde com uma combinação que explode no uso.

Exemplo:
    uv run pytest tests/test_neo4j_tls.py -q
"""

import ast
import pathlib

import certifi
import pytest
from neo4j import AsyncGraphDatabase, TrustCustomCAs

from engine.memory.neo4j_tls import config_tls_neo4j

_RAIZ = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        ("neo4j+s://abcd1234.databases.neo4j.io", "neo4j://abcd1234.databases.neo4j.io"),
        ("bolt+s://abcd1234.databases.neo4j.io:7687", "bolt://abcd1234.databases.neo4j.io:7687"),
    ],
)
def test_esquema_verificado_vira_tls_com_certifi(entrada: str, esperada: str) -> None:
    uri, tls = config_tls_neo4j(entrada)
    assert uri == esperada
    assert tls["encrypted"] is True
    assert isinstance(tls["trusted_certificates"], TrustCustomCAs)
    assert certifi.where() in tls["trusted_certificates"].certs


@pytest.mark.parametrize("entrada", ["neo4j://localhost:7687", "neo4j+ssc://x.databases.neo4j.io"])
def test_outros_esquemas_passam_intactos(entrada: str) -> None:
    assert config_tls_neo4j(entrada) == (entrada, {})


@pytest.mark.asyncio
async def test_driver_aceita_a_combinacao() -> None:
    """Sem rede: só a construção, que é onde o ConfigurationError apareceria."""
    uri, tls = config_tls_neo4j("neo4j+s://abcd1234.databases.neo4j.io")
    driver = AsyncGraphDatabase.driver(uri, auth=("u", "p"), **tls)
    await driver.close()


def test_ninguem_abre_driver_com_a_uri_crua() -> None:
    """Todo `AsyncGraphDatabase.driver(...)` do projeto passa pelo helper."""
    crus: list[str] = []
    for arq in _RAIZ.rglob("*.py"):
        partes = arq.relative_to(_RAIZ).parts
        if partes[0] in {".venv", "venv", "tests", "frontend", "node_modules", ".claude", ".internal", ".git"}:
            continue
        arvore = ast.parse(arq.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Attribute)
                and no.func.attr == "driver"
                and isinstance(no.func.value, ast.Name)
                and no.func.value.id in {"AsyncGraphDatabase", "GraphDatabase"}
                and not any(kw.arg is None for kw in no.keywords)  # sem **argumentos_driver_neo4j()
            ):
                crus.append(f"{arq.relative_to(_RAIZ)}:{no.lineno}")
    assert not crus, f"driver aberto sem argumentos_driver_neo4j(): {crus}"
