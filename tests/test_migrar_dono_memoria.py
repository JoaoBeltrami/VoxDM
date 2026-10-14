"""
Migração de memória sem dono → legado: simular não escreve, aplicar não apaga.

Por que existe: a migração mexe em dado de jogo que não tem backup automático.
    Os dois modos de falha caros são "o --dry-run escreveu" e "a migração
    sobrescreveu o dono de alguém" — cada um tem teste aqui.
Dependências: qdrant-client em modo local (`:memory:`); grafo falso para Neo4j.
Armadilha: o grafo falso classifica a query como ESCRITA pelo verbo Cypher. É
    essa classificação que prova o dry-run — não troque por um contador de
    chamadas, porque o dry-run faz leituras de propósito.
"""

from __future__ import annotations

from typing import Any

import pytest

from engine.auth.identity import OWNER_LEGADO
from engine.memory.qdrant_client import CAMPO_DONO, COLECAO_EPISODICA
from scripts.migrar_dono_memoria import migrar_neo4j, migrar_qdrant

_VERBOS_DE_ESCRITA = ("MERGE", "SET ", "CREATE", "DELETE", "REMOVE")


def _qdrant_semeado() -> Any:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    client = QdrantClient(":memory:")
    client.create_collection(
        COLECAO_EPISODICA, vectors_config=VectorParams(size=4, distance=Distance.COSINE),
    )
    payloads = [
        {"session_id": "s-alice", CAMPO_DONO: "alice@voxdm.test", "text": "da Alice"},
        {"session_id": "s-sem-campo", "text": "pré-auth, sem o campo"},
        {"session_id": "s-vazio", CAMPO_DONO: "", "text": "pré-auth, campo vazio"},
    ]
    client.upsert(COLECAO_EPISODICA, points=[
        PointStruct(id=i + 1, vector=[1.0, 0.0, 0.0, 0.0], payload=p)
        for i, p in enumerate(payloads)
    ])
    return client


def _payloads(client: Any) -> dict[str, dict[str, Any]]:
    pontos, _ = client.scroll(COLECAO_EPISODICA, limit=100, with_payload=True)
    return {p.payload["session_id"]: dict(p.payload) for p in pontos}


def test_dry_run_do_qdrant_conta_e_nao_escreve() -> None:
    client = _qdrant_semeado()
    antes = _payloads(client)

    (rel,) = migrar_qdrant(client, aplicar=False)

    assert (rel.total, rel.com_dono, rel.sem_dono, rel.escritas) == (3, 1, 2, 0)
    assert rel.sem_dono_depois is None
    assert _payloads(client) == antes


@pytest.mark.filterwarnings("ignore:Payload indexes have no effect")
def test_aplicar_no_qdrant_marca_legado_sem_tocar_em_quem_tem_dono() -> None:
    client = _qdrant_semeado()

    (rel,) = migrar_qdrant(client, aplicar=True)

    depois = _payloads(client)
    assert rel.escritas == 2 and rel.sem_dono_depois == 0
    assert depois["s-alice"][CAMPO_DONO] == "alice@voxdm.test"
    assert depois["s-sem-campo"][CAMPO_DONO] == OWNER_LEGADO
    assert depois["s-vazio"][CAMPO_DONO] == OWNER_LEGADO
    # Só ACRESCENTA o campo: o resto do payload e o número de pontos não mudam.
    assert depois["s-sem-campo"]["text"] == "pré-auth, sem o campo"
    assert len(depois) == 3


@pytest.mark.filterwarnings("ignore:Payload indexes have no effect")
def test_aplicar_duas_vezes_e_idempotente() -> None:
    client = _qdrant_semeado()
    migrar_qdrant(client, aplicar=True)
    (rel,) = migrar_qdrant(client, aplicar=True)
    assert (rel.sem_dono, rel.escritas, rel.ja_legado) == (0, 0, 2)


def test_colecao_ausente_nao_e_erro() -> None:
    from qdrant_client import QdrantClient

    (rel,) = migrar_qdrant(QdrantClient(":memory:"), aplicar=True)
    assert rel.total == 0 and rel.escritas == 0
    assert "não existe" in rel.notas[0]


# ── Neo4j ────────────────────────────────────────────────────────────────────


class _Resultado:
    def __init__(self, linhas: list[dict[str, Any]]) -> None:
        self._linhas = linhas

    async def data(self) -> list[dict[str, Any]]:
        return self._linhas


class _GrafoFalso:
    def __init__(self) -> None:
        self.lore = [
            {"npc_id": "bjorn", "afeto": 4, "medo": None, "respeito": None, "rancor": -2},
            {"npc_id": "fael", "afeto": None, "medo": 3, "respeito": None, "rancor": None},
        ]
        self.estados: list[dict[str, Any]] = [
            {"owner_email": "alice@voxdm.test", "npc_id": "bjorn", "afeto": 9},
        ]
        self.escritas: list[str] = []

    def session(self) -> _GrafoFalso:
        return self

    async def __aenter__(self) -> _GrafoFalso:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def run(self, cypher: str, params: dict[str, Any]) -> _Resultado:
        if any(v in cypher.upper() for v in _VERBOS_DE_ESCRITA):
            self.escritas.append(cypher)
            if "MERGE" in cypher:
                chave = (params["owner_email"], params["npc_id"])
                if chave not in {(e["owner_email"], e["npc_id"]) for e in self.estados}:
                    self.estados.append(dict(params))
            return _Resultado([])
        if "RETURN e.owner_email" in cypher:
            return _Resultado([dict(e) for e in self.estados])
        return _Resultado([dict(n) for n in self.lore])


@pytest.mark.asyncio
async def test_dry_run_do_neo4j_nao_emite_nenhuma_escrita() -> None:
    grafo = _GrafoFalso()
    rel = await migrar_neo4j(grafo, aplicar=False)
    assert grafo.escritas == []
    assert (rel.sem_dono, rel.com_dono, rel.escritas) == (2, 1, 0)
    assert len(grafo.estados) == 1


@pytest.mark.asyncio
async def test_aplicar_no_neo4j_cria_legado_e_preserva_o_estado_com_dono() -> None:
    grafo = _GrafoFalso()
    rel = await migrar_neo4j(grafo, aplicar=True)

    assert rel.escritas == 2 and rel.sem_dono_depois == 0
    donos = {(e["owner_email"], e["npc_id"]) for e in grafo.estados}
    assert donos == {
        ("alice@voxdm.test", "bjorn"), (OWNER_LEGADO, "bjorn"), (OWNER_LEGADO, "fael"),
    }
    # O estado da Alice com o Bjorn continua o dela.
    assert grafo.estados[0] == {"owner_email": "alice@voxdm.test", "npc_id": "bjorn", "afeto": 9}

    de_novo = await migrar_neo4j(grafo, aplicar=True)
    assert (de_novo.sem_dono, de_novo.escritas, de_novo.ja_legado) == (0, 0, 2)


def test_a_migracao_nunca_apaga_nem_escreve_no_no_da_lore() -> None:
    """Varre as Cypher do script: sem DELETE/REMOVE, e SET só no nó de estado."""
    import scripts.migrar_dono_memoria as modulo

    cyphers = [
        modulo._CYPHER_LER_LORE_COM_AFETO, modulo._CYPHER_CONTAR_ESTADOS,
        modulo._CYPHER_CRIAR_LEGADO, *modulo._CYPHERS_INDICE,
    ]
    for c in cyphers:
        maiuscula = c.upper()
        assert "DELETE" not in maiuscula and "REMOVE" not in maiuscula, c
        assert "SET N." not in maiuscula, c


def test_o_padrao_da_linha_de_comando_e_simular(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.migrar_dono_memoria as modulo

    visto: list[bool] = []

    async def _falso(aplicar: bool) -> list[Any]:
        visto.append(aplicar)
        return []

    monkeypatch.setattr(modulo, "_rodar", _falso)
    assert modulo.main([]) == 0
    assert modulo.main(["--dry-run"]) == 0
    assert modulo.main(["--aplicar"]) == 0
    assert visto == [False, False, True]
    with pytest.raises(SystemExit):
        modulo.main(["--dry-run", "--aplicar"])
