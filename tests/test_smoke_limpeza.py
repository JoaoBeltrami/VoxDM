"""
A limpeza do smoke de ponta a ponta apaga SÓ o que ele criou.

Por que existe: o smoke roda como o dono real (DEV_USER_EMAIL em DEBUG). Uma
    limpeza larga demais apagaria memória de jogo de verdade; estreita demais
    deixaria um personagem de teste na memória do Mestre.
Dependências: qdrant-client local (`:memory:`), sqlite em tmp_path, grafo falso.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from scripts.smoke_ponta_a_ponta import (
    limpar_arquivos_debug,
    limpar_qdrant,
    limpar_sqlite,
    restaurar_afeto,
)

DONO = "eu@voxdm.test"


def test_qdrant_apaga_so_as_sessoes_do_smoke_e_do_dono() -> None:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    c = QdrantClient(":memory:")
    c.create_collection("voxdm_episodic", vectors_config=VectorParams(size=2, distance=Distance.COSINE))
    c.upsert("voxdm_episodic", points=[
        PointStruct(id=1, vector=[1, 0], payload={"session_id": "smoke-1", "owner_email": DONO}),
        PointStruct(id=2, vector=[1, 0], payload={"session_id": "real-1", "owner_email": DONO}),
        PointStruct(id=3, vector=[1, 0], payload={"session_id": "smoke-1", "owner_email": "outro@x"}),
    ])
    assert limpar_qdrant(c, DONO, ["smoke-1"]) == 1
    restantes = {(p.payload["session_id"], p.payload["owner_email"]) for p in c.scroll("voxdm_episodic")[0]}
    assert restantes == {("real-1", DONO), ("smoke-1", "outro@x")}


def test_sqlite_apaga_so_as_linhas_do_smoke(tmp_path: Path) -> None:
    db = tmp_path / "v.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE character_state (session_id TEXT, owner_email TEXT)")
    con.executemany("INSERT INTO character_state VALUES (?,?)",
                    [("smoke-1", DONO), ("real-1", DONO), ("smoke-1", "outro@x")])
    con.commit()
    con.close()
    assert limpar_sqlite(db, DONO, ["smoke-1"]) == 1
    con = sqlite3.connect(db)
    assert sorted(con.execute("SELECT session_id, owner_email FROM character_state").fetchall()) == [
        ("real-1", DONO), ("smoke-1", "outro@x"),
    ]
    con.close()


def test_arquivos_de_debug(tmp_path: Path) -> None:
    (tmp_path / "smoke-1.json").write_text("{}")
    (tmp_path / "real-1.json").write_text("{}")
    assert limpar_arquivos_debug(tmp_path, ["smoke-1", "nao-existe"]) == 1
    assert [p.name for p in tmp_path.iterdir()] == ["real-1.json"]


class _Res:
    def __init__(self, linhas: list[dict[str, Any]]) -> None:
        self._l = linhas

    async def data(self) -> list[dict[str, Any]]:
        return self._l


class _Grafo:
    def __init__(self, estados: dict[str, dict[str, Any]]) -> None:
        self.estados = estados

    def session(self) -> _Grafo:
        return self

    async def __aenter__(self) -> _Grafo:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def run(self, cypher: str, p: dict[str, Any]) -> _Res:
        if "DELETE" in cypher:
            self.estados.pop(p["n"])
        elif "SET e = $p" in cypher:
            self.estados[p["n"]] = dict(p["p"])
        else:
            return _Res([{"n": n, "p": v} for n, v in self.estados.items()])
        return _Res([])


@pytest.mark.asyncio
async def test_afeto_volta_ao_snapshot_de_antes() -> None:
    antes = {"fael": {"owner_email": DONO, "npc_id": "fael", "afeto": 3}}
    grafo = _Grafo({
        "fael": {"owner_email": DONO, "npc_id": "fael", "afeto": 1},          # mudou
        "bjorn-tharnsson": {"owner_email": DONO, "npc_id": "bjorn-tharnsson", "rancor": -1},  # nasceu
    })
    assert await restaurar_afeto(grafo, DONO, antes) == 2
    assert grafo.estados == antes


def test_suite_nao_escreve_no_banco_de_jogo_real() -> None:
    """Guarda do fixture autouse do conftest: o DB_PATH de produção não é usado."""
    from api import debug_archive
    from engine.persistence import character_store

    raiz = Path(__file__).resolve().parent.parent
    assert character_store.DB_PATH != raiz / "voxdm.db"
    assert debug_archive._ARQUIVO_DIR != raiz / ".internal" / "playtest_debug"
