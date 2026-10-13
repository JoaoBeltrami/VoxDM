"""
Isolamento por dono na memória de jogo do Qdrant — teste NEGATIVO de vazamento.

Por que existe: o payload episódico sempre gravou `owner_email`, mas a busca
    nunca filtrava por ele (achado do P11) — toda sessão caía no mesmo balde,
    e a memória de um jogador entrava no prompt de outro.
Dependências: qdrant-client em modo local (`:memory:`) — o filtro que roda
    aqui é o filtro DE VERDADE do Qdrant, não um mock que aceita qualquer coisa.
Armadilha: o embedder é falso (vetor constante). Com vetor constante TODO ponto
    tem score 1.0, então o que separa Alice de Bob é só o filtro de dono. Se o
    filtro sumir, o teste falha — é exatamente o que ele vigia.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from engine.auth.identity import OWNER_LEGADO, DonoObrigatorio, Owner
from engine.memory import qdrant_client as modulo_qdrant
from engine.memory.episodic_memory import EpisodicMemory, so_metadado
from engine.memory.qdrant_client import (
    CAMPO_DONO,
    COLECAO_EPISODICA,
    QdrantMemoryClient,
    filtro_de_dono,
)
from engine.memory.semantic_memory import SemanticMemory
from engine.memory.session_writer import SessionWriter
from engine.memory.working_memory import WorkingMemory

ALICE = Owner(email="alice@voxdm.test")
BOB = Owner(email="bob@voxdm.test")
ADMIN = Owner(email="admin@voxdm.test", is_admin=True)


class _EmbedderFalso:
    """Vetor constante — tira a semântica da equação e deixa só o filtro."""

    def gerar(self, textos: list[str], show_progress: bool = False, modo: str = "passage"):
        return np.ones((len(textos), 8), dtype=np.float32)


@pytest.fixture
def cliente() -> QdrantMemoryClient:
    from qdrant_client import QdrantClient

    c = QdrantMemoryClient()
    c._client = QdrantClient(":memory:")
    c._embedder = _EmbedderFalso()  # type: ignore[assignment]
    return c


async def _semear(c: QdrantMemoryClient) -> None:
    await c.gravar_memoria(
        ALICE, "00000000-0000-0000-0000-00000000000a", "segredo da Alice",
        {"session_id": "sess-alice", "text": "Alice descobriu o túmulo de Valdrek", "timestamp": 10.0},
    )
    await c.gravar_memoria(
        BOB, "00000000-0000-0000-0000-00000000000b", "segredo do Bob",
        {"session_id": "sess-bob", "text": "Bob traiu Bjorn em Tharnvik", "timestamp": 20.0},
    )
    # Legado: ponto anterior ao isolamento, com a marca escrita pela migração.
    from qdrant_client.models import PointStruct
    c._get_client().upsert(
        collection_name=COLECAO_EPISODICA,
        points=[PointStruct(
            id="00000000-0000-0000-0000-00000000000c",
            vector=[1.0] * 8,
            payload={"session_id": "sess-velha", "text": "sessão pré-auth",
                     CAMPO_DONO: OWNER_LEGADO, "timestamp": 1.0},
        )],
    )


# ── Negativo de vazamento ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_alice_nao_le_memoria_do_bob_na_busca(cliente: QdrantMemoryClient) -> None:
    await _semear(cliente)
    achados = await cliente.buscar_memoria(ALICE, "qualquer coisa", top_k=10, score_threshold=0.0)
    assert [a["session_id"] for a in achados] == ["sess-alice"]
    assert all("Bob" not in a["text"] for a in achados)


@pytest.mark.asyncio
async def test_bob_nao_le_memoria_da_alice_na_listagem(cliente: QdrantMemoryClient) -> None:
    await _semear(cliente)
    achados = await cliente.listar_memoria(BOB)
    assert [a["session_id"] for a in achados] == ["sess-bob"]


@pytest.mark.asyncio
async def test_sessao_alheia_e_indistinguivel_de_inexistente(cliente: QdrantMemoryClient) -> None:
    """Bob pedindo a sessão da Alice recebe o MESMO None de um id que não existe."""
    await _semear(cliente)
    mem = EpisodicMemory()
    mem._qdrant = cliente
    assert await mem.buscar_por_session_id(BOB, "sess-alice") is None
    assert await mem.buscar_por_session_id(BOB, "sess-que-nao-existe") is None
    dele = await mem.buscar_por_session_id(BOB, "sess-bob")
    assert dele is not None and dele["text"].startswith("Bob")


@pytest.mark.asyncio
async def test_episodica_lista_so_as_sessoes_do_dono(cliente: QdrantMemoryClient) -> None:
    await _semear(cliente)
    mem = EpisodicMemory()
    mem._qdrant = cliente
    assert await mem.listar_sessoes(ALICE) == ["sess-alice"]
    metadados = await mem.listar_com_metadata(ALICE)
    assert [m["session_id"] for m in metadados] == ["sess-alice"]
    assert [c["session_id"] for c in await mem.buscar(ALICE, "túmulo", top_k=10)] == ["sess-alice"]


# ── Legado e admin ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legado_sem_dono_e_admin_only(cliente: QdrantMemoryClient) -> None:
    await _semear(cliente)
    assert "sess-velha" not in {a["session_id"] for a in await cliente.listar_memoria(ALICE)}
    assert "sess-velha" in {a["session_id"] for a in await cliente.listar_memoria(ADMIN)}


@pytest.mark.asyncio
async def test_admin_nao_recebe_narrativa_alheia_no_caminho_do_turno(
    cliente: QdrantMemoryClient,
) -> None:
    """Admin jogando NÃO pode ter a memória de outro jogador no próprio prompt."""
    await _semear(cliente)
    achados = await cliente.buscar_memoria(ADMIN, "x", top_k=10, score_threshold=0.0)
    assert {a["session_id"] for a in achados} == {"sess-velha"}


def test_so_metadado_corta_o_conteudo() -> None:
    entrada = {
        "session_id": "s", "owner_email": "bob@voxdm.test", "timestamp": 1.0,
        "location_final": "tharnvik", "player_level": 3,
        "resumo_curto": "Bob traiu Bjorn", "dm_state": {"fios_soltos": ["x"]},
        "companions": {"lyssa": {}}, "npcs_mencionados": ["bjorn"],
    }
    assert set(so_metadado(entrada)) == {
        "session_id", "owner_email", "timestamp", "location_final", "player_level",
    }


# ── Impossível consultar ou gravar sem dono ──────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("ruim", [None, "alice@voxdm.test", Owner(email=""), Owner(email=OWNER_LEGADO)])
async def test_sem_dono_valido_levanta(cliente: QdrantMemoryClient, ruim: object) -> None:
    with pytest.raises(DonoObrigatorio):
        await cliente.buscar_memoria(ruim, "x")  # type: ignore[arg-type]
    with pytest.raises(DonoObrigatorio):
        await cliente.listar_memoria(ruim)  # type: ignore[arg-type]
    with pytest.raises(DonoObrigatorio):
        await cliente.gravar_memoria(ruim, "00000000-0000-0000-0000-0000000000ff", "t", {})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_episodica_sem_dono_sobe_em_vez_de_virar_lista_vazia() -> None:
    """O try/except que engole 'coleção ausente' não pode engolir a falta de dono."""
    mem = EpisodicMemory()
    for chamada in (
        mem.buscar(None, "x"),  # type: ignore[arg-type]
        mem.buscar_por_npc(None, "bjorn"),  # type: ignore[arg-type]
        mem.listar_sessoes(None),  # type: ignore[arg-type]
        mem.listar_com_metadata(None),  # type: ignore[arg-type]
        mem.buscar_por_session_id(None, "s"),  # type: ignore[arg-type]
    ):
        with pytest.raises(DonoObrigatorio):
            await chamada


def test_caller_nao_sobrescreve_o_filtro_de_dono() -> None:
    with pytest.raises(ValueError, match="owner_email"):
        filtro_de_dono(ALICE, {CAMPO_DONO: "bob@voxdm.test"})
    filtro = filtro_de_dono(ALICE, {"session_id": "s1"})
    chaves = [c.key for c in filtro.must]  # type: ignore[union-attr]
    assert chaves == [CAMPO_DONO, "session_id"]


@pytest.mark.asyncio
async def test_gravacao_carimba_o_dono_do_owner_e_ignora_o_do_payload(
    cliente: QdrantMemoryClient,
) -> None:
    await cliente.gravar_memoria(
        ALICE, "00000000-0000-0000-0000-0000000000aa", "t",
        {"session_id": "s", CAMPO_DONO: "bob@voxdm.test"},
    )
    assert await cliente.listar_memoria(BOB) == []
    assert (await cliente.listar_memoria(ALICE))[0][CAMPO_DONO] == "alice@voxdm.test"


def test_dono_e_obrigatorio_e_posicional_nas_assinaturas() -> None:
    """Se a assinatura permitir esquecer o dono, alguém vai esquecer."""
    alvos = [
        QdrantMemoryClient.buscar_memoria, QdrantMemoryClient.listar_memoria,
        QdrantMemoryClient.gravar_memoria, EpisodicMemory.buscar,
        EpisodicMemory.buscar_por_npc, EpisodicMemory.listar_sessoes,
        EpisodicMemory.listar_com_metadata, EpisodicMemory.buscar_por_session_id,
        SessionWriter.fechar_sessao,
    ]
    for fn in alvos:
        params = list(inspect.signature(fn).parameters.values())
        dono = params[1]  # [0] é self
        assert dono.name == "owner", fn.__qualname__
        assert dono.default is inspect.Parameter.empty, fn.__qualname__
        assert dono.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD, fn.__qualname__


def test_nao_existe_mais_busca_generica_sem_dono() -> None:
    assert not hasattr(QdrantMemoryClient, "buscar")


# ── Acervo × memória ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_porta_do_acervo_recusa_colecao_de_memoria(cliente: QdrantMemoryClient) -> None:
    with pytest.raises(ValueError, match="acervo"):
        await cliente.buscar_acervo("x", colecao=COLECAO_EPISODICA)


@pytest.mark.asyncio
async def test_porta_da_memoria_recusa_colecao_de_acervo(cliente: QdrantMemoryClient) -> None:
    with pytest.raises(ValueError, match="memória de jogo"):
        await cliente.buscar_memoria(ALICE, "x", colecao="voxdm_modules")


@pytest.mark.asyncio
async def test_memoria_semantica_so_alcanca_acervo(cliente: QdrantMemoryClient) -> None:
    """A busca híbrida lê lore compartilhada — não pode ser apontada pro episódico."""
    mem = SemanticMemory()
    mem._qdrant = cliente
    with pytest.raises(ValueError, match="acervo"):
        await mem.buscar_enriquecido("x", colecao=COLECAO_EPISODICA)


def test_colecoes_de_acervo_e_de_memoria_nao_se_cruzam() -> None:
    assert not (modulo_qdrant.colecoes_acervo() & modulo_qdrant.COLECOES_MEMORIA)


# ── session_writer ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_session_writer_grava_no_dono_e_o_outro_nao_enxerga(
    cliente: QdrantMemoryClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _resumo_falso(_wm: WorkingMemory) -> str:
        return "Alice negociou com o ferreiro."

    monkeypatch.setattr("engine.memory.session_writer._resumir_via_groq", _resumo_falso)
    writer = SessionWriter()
    writer._qdrant = cliente
    await writer.fechar_sessao(ALICE, WorkingMemory(session_id="sess-w"))

    assert [p["session_id"] for p in await cliente.listar_memoria(ALICE)] == ["sess-w"]
    assert await cliente.listar_memoria(BOB) == []


@pytest.mark.asyncio
async def test_session_writer_sem_dono_nao_gasta_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    chamado = False

    async def _resumo(_wm: WorkingMemory) -> str:
        nonlocal chamado
        chamado = True
        return "x"

    monkeypatch.setattr("engine.memory.session_writer._resumir_via_groq", _resumo)
    with pytest.raises(DonoObrigatorio):
        await SessionWriter().fechar_sessao(Owner(email=""), WorkingMemory(session_id="s"))
    assert chamado is False
