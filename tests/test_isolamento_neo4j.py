"""
Isolamento por dono no estado de NPC do Neo4j — teste NEGATIVO de vazamento.

Por que existe: o afeto de NPC era gravado direto no nó da LORE
    (`MATCH (n {id}) SET n.afeto = …`), sem dono — o achado que parou o P11.
    O humor que o Bjorn pegou do jogador A valia para o jogador B.
Dependências: nenhuma externa — um grafo falso em memória que aplica a MESMA
    chave que a Cypher declara (label + owner_email + npc_id).
Armadilha: o grafo falso não interpreta Cypher. Ele decide o que devolver pelos
    PARÂMETROS da query. Por isso existe o segundo grupo de testes, que lê o
    texto de cada query do cliente: é ele quem garante que o filtro de dono está
    DENTRO da Cypher e não ficou só nos parâmetros.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

import pytest

from engine.auth.identity import OWNER_LEGADO, DonoObrigatorio, Owner
from engine.memory import neo4j_client as modulo
from engine.memory.neo4j_client import CAMPOS_AFETO, LABEL_ESTADO_NPC, Neo4jMemoryClient

ALICE = Owner(email="alice@voxdm.test")
BOB = Owner(email="bob@voxdm.test")
ADMIN = Owner(email="admin@voxdm.test", is_admin=True)


class _Resultado:
    def __init__(self, linhas: list[dict[str, Any]]) -> None:
        self._linhas = linhas

    async def data(self) -> list[dict[str, Any]]:
        return self._linhas

    async def single(self) -> dict[str, Any] | None:
        return self._linhas[0] if self._linhas else None


class _GrafoFalso:
    """Estado por (owner_email, npc_id) + um nó de lore com afeto legado."""

    def __init__(self) -> None:
        self.estados: dict[tuple[str, str], dict[str, int]] = {}
        self.lore: dict[str, dict[str, Any]] = {
            "bjorn": {"id": "bjorn", "name": "Bjorn", "afeto": 9, "rancor": -4},
        }
        self.queries: list[tuple[str, dict[str, Any]]] = []

    # driver.session() devolve um async context manager
    def session(self) -> _GrafoFalso:
        return self

    async def __aenter__(self) -> _GrafoFalso:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def run(self, cypher: str, params: dict[str, Any]) -> _Resultado:
        self.queries.append((cypher, params))
        if "STARTS WITH" in cypher:
            return _Resultado([
                {"id": i} for i in self.lore
                if i == params["id"] or i.startswith(params["prefixo"])
            ])
        if LABEL_ESTADO_NPC in cypher and "MERGE" in cypher:
            chave = (params["owner_email"], params["npc_id"])
            estado = self.estados.setdefault(chave, {})
            campo = next(c for c in CAMPOS_AFETO if f"e.{c} =" in cypher)
            estado[campo] = max(-10, min(10, estado.get(campo, 0) + params["delta"]))
            return _Resultado([])
        if LABEL_ESTADO_NPC in cypher:
            return _Resultado([
                {"owner_email": dono, **{c: est.get(c) for c in CAMPOS_AFETO}}
                for (dono, npc), est in self.estados.items()
                if npc == params["npc_id"] and dono in params["owner_emails"]
            ])
        no = self.lore.get(params.get("id", ""))
        return _Resultado([{"props": dict(no)}] if no else [])


@pytest.fixture
def cliente() -> tuple[Neo4jMemoryClient, _GrafoFalso]:
    grafo = _GrafoFalso()
    c = Neo4jMemoryClient()
    c._driver = grafo  # type: ignore[assignment]
    return c, grafo


# ── Negativo de vazamento ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_afeto_da_alice_nao_aparece_pro_bob(cliente) -> None:
    c, _ = cliente
    await c.atualizar_afeto_npc(ALICE, "bjorn", "rancor", 5)
    assert await c.buscar_afeto_npc(ALICE, "bjorn") == {"rancor": 5}
    assert await c.buscar_afeto_npc(BOB, "bjorn") == {}


@pytest.mark.asyncio
async def test_cada_dono_tem_o_proprio_estado_com_o_mesmo_npc(cliente) -> None:
    c, grafo = cliente
    await c.atualizar_afeto_npc(ALICE, "bjorn", "afeto", 3)
    await c.atualizar_afeto_npc(BOB, "bjorn", "afeto", -7)
    assert await c.buscar_afeto_npc(ALICE, "bjorn") == {"afeto": 3}
    assert await c.buscar_afeto_npc(BOB, "bjorn") == {"afeto": -7}
    assert set(grafo.estados) == {("alice@voxdm.test", "bjorn"), ("bob@voxdm.test", "bjorn")}


@pytest.mark.asyncio
async def test_gravar_afeto_nao_toca_o_no_da_lore(cliente) -> None:
    c, grafo = cliente
    antes = dict(grafo.lore["bjorn"])
    await c.atualizar_afeto_npc(ALICE, "bjorn", "medo", 2)
    assert grafo.lore["bjorn"] == antes


@pytest.mark.asyncio
async def test_lore_nao_devolve_afeto_legado_gravado_no_no(cliente) -> None:
    """O humor que alguém deixou no nó da lore não pode sair como fato do mundo."""
    c, _ = cliente
    props = await c.buscar_entidade("bjorn")
    assert props == {"id": "bjorn", "name": "Bjorn"}


@pytest.mark.asyncio
async def test_legado_e_admin_only_e_o_proprio_vence(cliente) -> None:
    c, grafo = cliente
    grafo.estados[(OWNER_LEGADO, "bjorn")] = {"afeto": 9}
    assert await c.buscar_afeto_npc(ALICE, "bjorn") == {}
    assert await c.buscar_afeto_npc(ADMIN, "bjorn") == {"afeto": 9}
    await c.atualizar_afeto_npc(ADMIN, "bjorn", "afeto", 1)
    assert await c.buscar_afeto_npc(ADMIN, "bjorn") == {"afeto": 1}


@pytest.mark.asyncio
async def test_admin_nao_le_estado_de_outro_jogador(cliente) -> None:
    c, _ = cliente
    await c.atualizar_afeto_npc(BOB, "bjorn", "rancor", 8)
    assert await c.buscar_afeto_npc(ADMIN, "bjorn") == {}


# ── Impossível sem dono ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("ruim", [None, "alice@voxdm.test", Owner(email=""), Owner(email=OWNER_LEGADO)])
async def test_sem_dono_valido_levanta_e_nao_toca_o_grafo(cliente, ruim: object) -> None:
    c, grafo = cliente
    with pytest.raises(DonoObrigatorio):
        await c.atualizar_afeto_npc(ruim, "bjorn", "afeto", 1)  # type: ignore[arg-type]
    with pytest.raises(DonoObrigatorio):
        await c.buscar_afeto_npc(ruim, "bjorn")  # type: ignore[arg-type]
    assert grafo.queries == []


def test_dono_e_obrigatorio_e_posicional() -> None:
    for fn in (Neo4jMemoryClient.atualizar_afeto_npc, Neo4jMemoryClient.buscar_afeto_npc):
        dono = list(inspect.signature(fn).parameters.values())[1]
        assert dono.name == "owner"
        assert dono.default is inspect.Parameter.empty


# ── O filtro está DENTRO da Cypher (varredura do arquivo) ────────────────────


def _cyphers_do_cliente() -> list[str]:
    """Texto de toda string passada a `session.run(...)` no cliente, via ast."""
    arvore = ast.parse(Path(modulo.__file__).read_text(encoding="utf-8"))
    achadas: list[str] = []
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
            continue
        if no.func.attr != "run" or not no.args:
            continue
        arg = no.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            achadas.append(arg.value)
        elif isinstance(arg, ast.JoinedStr):
            # f-string: junta os pedaços literais e marca os interpolados
            achadas.append("".join(
                v.value if isinstance(v, ast.Constant) else "{…}" for v in arg.values
            ))
    return achadas


def test_o_arquivo_tem_queries_para_varrer() -> None:
    assert len(_cyphers_do_cliente()) >= 7


def test_toda_cypher_de_estado_filtra_por_dono_na_propria_query() -> None:
    """Uma só query de estado sem dono derruba o isolamento inteiro."""
    de_estado = [q for q in _cyphers_do_cliente() if "{…}" in q and ":{…}" in q]
    assert len(de_estado) == 2, "esperava a escrita e a leitura do :EstadoNPC"
    for q in de_estado:
        assert "owner_email" in q, q
        assert "$owner_email" in q or "$owner_emails" in q, q


def test_nenhuma_cypher_escreve_em_no_de_lore() -> None:
    """Lore é imutável em jogo: SET/MERGE/DELETE só no nó de estado."""
    for q in _cyphers_do_cliente():
        if ":{…}" in q:
            continue  # query de estado — coberta acima
        maiuscula = q.upper()
        for verbo in ("SET ", "MERGE ", "DELETE ", "CREATE ", "REMOVE "):
            assert verbo not in maiuscula, f"query de lore com escrita ({verbo.strip()}): {q}"


def test_leitura_de_lore_nunca_casa_no_de_estado() -> None:
    """Lore casa por `{id: …}`; o nó de estado não tem `id`, só `npc_id`."""
    fonte = inspect.getsource(Neo4jMemoryClient._gravar_afeto)
    assert "npc_id: $npc_id" in fonte
    assert "{id:" not in fonte.replace("{{", "{")


# ── AFETO-ID-CURTO-1: o modelo fala "bjorn", o grafo chama "bjorn-tharnsson" ──


@pytest.mark.asyncio
async def test_afeto_com_primeiro_nome_grava_no_id_do_grafo(cliente) -> None:
    """Achado no smoke de 14/10: `[AFETO: bjorn|rancor|-1]` gravava em `bjorn`,
    e a leitura (só ids do grafo) nunca encontrava — o NPC esquecia a ofensa."""
    c, grafo = cliente
    grafo.lore = {"bjorn-tharnsson": {"id": "bjorn-tharnsson", "name": "Bjorn"}}
    await c.atualizar_afeto_npc(ALICE, "bjorn", "rancor", -1)
    assert set(grafo.estados) == {("alice@voxdm.test", "bjorn-tharnsson")}
    assert await c.buscar_afeto_npc(ALICE, "bjorn-tharnsson") == {"rancor": -1}


@pytest.mark.asyncio
async def test_prefixo_ambiguo_nao_chuta(cliente) -> None:
    c, grafo = cliente
    grafo.lore = {"bjorn-tharnsson": {}, "bjorn-velho": {}}
    await c.atualizar_afeto_npc(ALICE, "bjorn", "afeto", 1)
    assert set(grafo.estados) == {("alice@voxdm.test", "bjorn")}


@pytest.mark.asyncio
async def test_npc_fora_do_grafo_mantem_o_id(cliente) -> None:
    c, grafo = cliente
    grafo.lore = {}
    await c.atualizar_afeto_npc(ALICE, "taverneiro-improvisado", "afeto", 2)
    assert set(grafo.estados) == {("alice@voxdm.test", "taverneiro-improvisado")}
