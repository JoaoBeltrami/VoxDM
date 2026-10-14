"""
Saves de campanha: round-trip, rotação que não destrói, isolamento e quebra-vidro.

Por que existe: é a Fase 2/3 do prompt de saves (13/10). O coração é o
    round-trip — salvar → restaurar devolve um estado IGUAL — e a garantia de
    que o save bom nunca é a vítima de uma gravação ou de uma rotação.
Dependências: aiosqlite e disco em `tmp_path` (sem rede).
Armadilha: `settings.SAVES_MANTER` é lido na hora da rotação — os testes que
    mexem nele usam monkeypatch, não o valor do .env.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from engine.auth.identity import DonoObrigatorio, Owner
from engine.auth.permissoes import (
    PAPEL_GM,
    PAPEL_PLAYER,
    pode_gerir_campanha,
    pode_ler_campanha,
    pode_ver_conteudo,
    pode_ver_metadado,
)
from engine.memory.working_memory import WorkingMemory
from engine.persistence.campanha_store import CampanhaStore, NaoEncontrado, SaveCorrompido
from engine.persistence.save_envelope import (
    SCHEMA_VERSION,
    SaveIncompativel,
    montar_envelope,
    restaurar_working_memory,
)
from engine.state.inventario import ItemInventario

ALICE = Owner(email="alice@voxdm.test")
BOB = Owner(email="bob@voxdm.test")
ADMIN = Owner(email="admin@voxdm.test", is_admin=True)


def _wm_rica() -> WorkingMemory:
    """Estado com os tipos que o JSON destrói: set, chave int, dataclass aninhada."""
    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-rica")
    wm.player_name = "Kaëla"
    wm.player_class = "Clérigo"
    wm.spell_slots = {1: {"max": 4, "atual": 2}, 2: {"max": 2, "atual": 0}}
    wm.npcs_apresentados = {"bjorn-tharnsson", "fael-valdreksson"}
    wm.trust_levels = {"bjorn-tharnsson": 3}
    wm.companions = {"lyssa": {"nome": "Lyssa", "tipo": "hireling", "hp": 17, "hp_max": 25}}
    wm.fios_soltos = ["o túmulo selado"]
    wm.gold = 42
    wm.character.inventario = [ItemInventario.de_dict({"nome": "Maça", "quantidade": 1})]
    wm.quests_completas = {"quest-1"}
    return wm


def _envelope(wm: WorkingMemory, campanha_id: str = "c") -> dict:
    return montar_envelope(wm, owner_email="alice@voxdm.test", session_id=wm.session_id, campanha_id=campanha_id)


@pytest.fixture
def store(tmp_path: Path) -> CampanhaStore:
    return CampanhaStore(db_path=tmp_path / "t.db", dir_saves=tmp_path / "saves")


# ── round-trip (o coração da fase) ───────────────────────────────────────────


def test_round_trip_do_envelope_devolve_estado_igual() -> None:
    wm = _wm_rica()
    env = json.loads(json.dumps(_envelope(wm)))  # passa pelo JSON de verdade
    volta = restaurar_working_memory(env)
    assert volta == wm
    assert isinstance(next(iter(volta.spell_slots)), int)
    assert isinstance(volta.npcs_apresentados, set)
    assert isinstance(volta.character.inventario[0], ItemInventario)


@pytest.mark.asyncio
async def test_round_trip_pelo_store_e_pelo_disco(store: CampanhaStore) -> None:
    wm = _wm_rica()
    camp = await store.criar_campanha(ALICE, "Valdrek")
    info = await store.salvar(ALICE, camp.id, "antes do dragão", _envelope(wm, camp.id))
    volta = restaurar_working_memory(await store.carregar(ALICE, camp.id, info.id))
    assert volta == wm
    assert info.manifest["personagens"] == [{"nome": "Kaëla", "classe": "Clérigo", "nivel": wm.player_level}]


def test_envelope_guarda_ponteiro_da_memoria_e_nao_o_conteudo() -> None:
    env = _envelope(_wm_rica())
    assert env["memoria"] == {"session_id": "sess-rica", "owner_email": "alice@voxdm.test"}
    assert env["schema_version"] == SCHEMA_VERSION


def test_versao_futura_recusa_dizendo_o_que_fazer() -> None:
    env = _envelope(_wm_rica())
    env["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(SaveIncompativel, match="atualize"):
        restaurar_working_memory(env)


def test_envelope_sem_versao_recusa() -> None:
    with pytest.raises(SaveIncompativel):
        restaurar_working_memory({"personagens": []})


def test_save_nao_instancia_classe_fora_da_engine() -> None:
    env = _envelope(_wm_rica())
    env["personagens"][0]["estado"] = {"__t": "dc", "c": "os:PathLike", "f": {}}
    with pytest.raises(SaveIncompativel, match="fora da engine"):
        restaurar_working_memory(env)


def test_campo_que_sumiu_da_classe_e_ignorado_sem_quebrar() -> None:
    env = json.loads(json.dumps(_envelope(_wm_rica())))
    env["personagens"][0]["estado"]["f"]["campo_que_nao_existe_mais"] = 1
    assert restaurar_working_memory(env).player_name == "Kaëla"


# ── escrita atômica e rotação ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_novo_nunca_sobrescreve_o_anterior(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    wm = _wm_rica()
    a = await store.salvar(ALICE, camp.id, "1", _envelope(wm, camp.id))
    wm.gold = 999
    b = await store.salvar(ALICE, camp.id, "2", _envelope(wm, camp.id))
    assert a.id != b.id
    assert restaurar_working_memory(await store.carregar(ALICE, camp.id, a.id)).gold == 42


@pytest.mark.asyncio
async def test_rotacao_mantem_as_n_mais_novas(store: CampanhaStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.persistence.campanha_store.settings.SAVES_MANTER", 3)
    camp = await store.criar_campanha(ALICE, "Valdrek")
    wm = _wm_rica()
    ids = []
    for i in range(5):
        wm.gold = i
        ids.append((await store.salvar(ALICE, camp.id, str(i), _envelope(wm, camp.id))).id)
    restantes = [s.id for s in await store.listar_saves(ALICE, camp.id)]
    assert restantes == list(reversed(ids[-3:]))
    arquivos = sorted(p.stem for p in (store.dir_saves / camp.id).glob("*.json"))
    assert arquivos == sorted(ids[-3:])
    assert restaurar_working_memory(await store.carregar(ALICE, camp.id, ids[-1])).gold == 4


@pytest.mark.asyncio
async def test_rotacao_com_um_so_save_nao_apaga_nada(store: CampanhaStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("engine.persistence.campanha_store.settings.SAVES_MANTER", 0)
    camp = await store.criar_campanha(ALICE, "Valdrek")
    info = await store.salvar(ALICE, camp.id, "único", _envelope(_wm_rica(), camp.id))
    assert [s.id for s in await store.listar_saves(ALICE, camp.id)] == [info.id]


@pytest.mark.asyncio
async def test_falha_na_gravacao_preserva_o_save_bom(
    store: CampanhaStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    bom = await store.salvar(ALICE, camp.id, "bom", _envelope(_wm_rica(), camp.id))

    def _explode(*_a: object, **_k: object) -> None:
        raise OSError("disco cheio no meio da gravação")

    monkeypatch.setattr("engine.persistence.campanha_store.os.replace", _explode)
    with pytest.raises(OSError):
        await store.salvar(ALICE, camp.id, "ruim", _envelope(_wm_rica(), camp.id))

    assert [s.id for s in await store.listar_saves(ALICE, camp.id)] == [bom.id]
    assert restaurar_working_memory(await store.carregar(ALICE, camp.id, bom.id)).gold == 42
    assert not list((store.dir_saves / camp.id).glob("*.tmp"))


@pytest.mark.asyncio
async def test_arquivo_adulterado_e_recusado(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    info = await store.salvar(ALICE, camp.id, "x", _envelope(_wm_rica(), camp.id))
    arquivo = store.dir_saves / info.manifest["arquivo"]
    arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("Kaëla", "Outra"), encoding="utf-8")
    with pytest.raises(SaveCorrompido):
        await store.carregar(ALICE, camp.id, info.id)


# ── isolamento (SQLite) ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bob_nao_le_campanha_nem_save_da_alice(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    info = await store.salvar(ALICE, camp.id, "x", _envelope(_wm_rica(), camp.id))

    assert await store.listar_campanhas(BOB) == []
    with pytest.raises(NaoEncontrado):
        await store.obter_campanha(BOB, camp.id)
    with pytest.raises(NaoEncontrado):
        await store.listar_saves(BOB, camp.id)
    with pytest.raises(NaoEncontrado):
        await store.carregar(BOB, camp.id, info.id)
    with pytest.raises(NaoEncontrado):
        await store.salvar(BOB, camp.id, "invasão", _envelope(_wm_rica(), camp.id))


@pytest.mark.asyncio
async def test_save_alheio_e_inexistente_dao_o_mesmo_erro(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    info = await store.salvar(ALICE, camp.id, "x", _envelope(_wm_rica(), camp.id))
    erros = []
    for sid in (info.id, "save-que-nao-existe"):
        with pytest.raises(NaoEncontrado) as e:
            await store.carregar(BOB, camp.id, sid)
        erros.append(type(e.value))
    assert erros[0] is erros[1]


@pytest.mark.asyncio
async def test_membro_player_le_e_salva_mas_nao_gere(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    await store.adicionar_membro(ALICE, camp.id, BOB.email, PAPEL_PLAYER)
    info = await store.salvar(BOB, camp.id, "do Bob", _envelope(_wm_rica(), camp.id))
    assert (await store.carregar(BOB, camp.id, info.id))["campanha_id"] == camp.id
    with pytest.raises(NaoEncontrado):
        await store.adicionar_membro(BOB, camp.id, "carol@voxdm.test", PAPEL_PLAYER)


@pytest.mark.asyncio
async def test_papel_desconhecido_e_recusado(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    with pytest.raises(ValueError, match="papel"):
        await store.adicionar_membro(ALICE, camp.id, BOB.email, "superuser")


@pytest.mark.asyncio
async def test_sem_dono_nada_funciona(store: CampanhaStore) -> None:
    for chamada in (
        store.criar_campanha(None, "x"),  # type: ignore[arg-type]
        store.listar_campanhas(Owner(email="")),
        store.listar_saves(Owner(email="__legado__"), "c"),
    ):
        with pytest.raises(DonoObrigatorio):
            await chamada


# ── admin: metadado sim, conteúdo só com quebra-vidro ────────────────────────


@pytest.mark.asyncio
async def test_admin_ve_metadado_e_nao_conteudo(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(BOB, "Mesa do Bob")
    info = await store.salvar(BOB, camp.id, "x", _envelope(_wm_rica(), camp.id))

    metas = await store.listar_metadados_admin(ADMIN)
    assert metas[0]["id"] == camp.id and metas[0]["owner_email"] == BOB.email
    assert metas[0]["personagens"] == ["Kaëla"] and metas[0]["saves"] == 1
    assert "fios_soltos" not in json.dumps(metas)  # nada de narrativa

    with pytest.raises(NaoEncontrado):
        await store.carregar(ADMIN, camp.id, info.id)
    with pytest.raises(NaoEncontrado):
        await store.listar_metadados_admin(ALICE)


@pytest.mark.asyncio
async def test_quebra_vidro_devolve_conteudo_e_cria_auditoria(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(BOB, "Mesa do Bob")
    info = await store.salvar(BOB, camp.id, "x", _envelope(_wm_rica(), camp.id))

    env = await store.carregar_quebra_vidro(ADMIN, info.id, "bug report do Bob, sessão travada")
    assert restaurar_working_memory(env).player_name == "Kaëla"

    linhas = await store.auditoria(ADMIN, camp.id)
    qv = [linha for linha in linhas if linha["acao"] == "quebra_vidro"]
    assert len(qv) == 1
    assert qv[0]["email"] == ADMIN.email and "bug report" in qv[0]["motivo"]


@pytest.mark.asyncio
async def test_quebra_vidro_sem_motivo_ou_sem_admin_e_recusado(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(BOB, "Mesa do Bob")
    info = await store.salvar(BOB, camp.id, "x", _envelope(_wm_rica(), camp.id))
    with pytest.raises(ValueError, match="motivo"):
        await store.carregar_quebra_vidro(ADMIN, info.id, "  ")
    with pytest.raises(NaoEncontrado):
        await store.carregar_quebra_vidro(ALICE, info.id, "curiosidade")
    assert not [r for r in await store.auditoria(BOB, camp.id) if r["acao"] == "quebra_vidro"]


@pytest.mark.asyncio
async def test_quebra_vidro_nao_entrega_conteudo_se_a_auditoria_falhar(
    store: CampanhaStore, monkeypatch: pytest.MonkeyPatch,
) -> None:
    camp = await store.criar_campanha(BOB, "Mesa do Bob")
    info = await store.salvar(BOB, camp.id, "x", _envelope(_wm_rica(), camp.id))

    async def _falha(*_a: object, **_k: object) -> None:
        raise RuntimeError("disco do audit cheio")

    monkeypatch.setattr(CampanhaStore, "_auditar", staticmethod(_falha))
    with pytest.raises(RuntimeError):
        await store.carregar_quebra_vidro(ADMIN, info.id, "motivo válido aqui")


# ── permissões puras ─────────────────────────────────────────────────────────


def test_permissoes_metadado_conteudo() -> None:
    assert pode_ver_metadado(ADMIN, BOB.email) and pode_ver_metadado(BOB, BOB.email)
    assert not pode_ver_metadado(ALICE, BOB.email)
    assert pode_ver_conteudo(BOB, BOB.email)
    assert not pode_ver_conteudo(ADMIN, BOB.email)
    assert pode_ver_conteudo(ADMIN, BOB.email, quebra_vidro=True)
    assert not pode_ver_conteudo(ALICE, BOB.email, quebra_vidro=True)
    assert not pode_ver_conteudo(ALICE, "")
    # Legado sem dono: admin-only, como no `pode_ver`.
    assert pode_ver_conteudo(ADMIN, "") and pode_ver_conteudo(ADMIN, "__legado__")
    assert not pode_ver_conteudo(ALICE, "__legado__")


def test_pode_ver_nao_mudou_de_semantica() -> None:
    """A suíte depende de `pode_ver`: admin vê tudo, legado vazio é admin-only."""
    assert ADMIN.pode_ver(BOB.email) and ADMIN.pode_ver("")
    assert not ALICE.pode_ver(BOB.email) and not ALICE.pode_ver(None)


@pytest.mark.parametrize("papel", [None, "", "GM", "admin", "superuser", 1])
def test_papel_desconhecido_e_sem_acesso(papel: object) -> None:
    assert not pode_ler_campanha(papel)
    assert not pode_gerir_campanha(papel)


def test_papeis_validos() -> None:
    assert pode_ler_campanha(PAPEL_GM) and pode_ler_campanha(PAPEL_PLAYER)
    assert pode_gerir_campanha(PAPEL_GM) and not pode_gerir_campanha(PAPEL_PLAYER)


def test_admin_da_instancia_nao_e_gm_da_mesa() -> None:
    assert dataclasses.fields(Owner)  # Owner não carrega papel — papel é por campanha
    assert "papel" not in {f.name for f in dataclasses.fields(Owner)}


# ── arquivar (o "apagar" que não apaga) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_arquivar_some_das_listas_e_nao_apaga_nada(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    info = await store.salvar(ALICE, camp.id, "x", _envelope(_wm_rica(), camp.id))
    await store.arquivar_campanha(ALICE, camp.id)

    assert await store.listar_campanhas(ALICE) == []
    with pytest.raises(NaoEncontrado):
        await store.listar_saves(ALICE, camp.id)
    with pytest.raises(NaoEncontrado):
        await store.salvar(ALICE, camp.id, "depois", _envelope(_wm_rica(), camp.id))
    # O arquivo continua em disco e o admin ainda vê o metadado e abre por quebra-vidro.
    assert (store.dir_saves / info.manifest["arquivo"]).exists()
    meta = await store.listar_metadados_admin(ADMIN)
    assert meta[0]["arquivada_em"] > 0 and meta[0]["saves"] == 1
    env = await store.carregar_quebra_vidro(ADMIN, info.id, "recuperar save arquivado")
    assert env["campanha_id"] == camp.id
    acoes = [linha["acao"] for linha in await store.auditoria(ADMIN, camp.id)]
    assert "arquivar_campanha" in acoes


@pytest.mark.asyncio
async def test_so_o_gm_arquiva(store: CampanhaStore) -> None:
    camp = await store.criar_campanha(ALICE, "Valdrek")
    await store.adicionar_membro(ALICE, camp.id, BOB.email, PAPEL_PLAYER)
    with pytest.raises(NaoEncontrado):
        await store.arquivar_campanha(BOB, camp.id)
    with pytest.raises(NaoEncontrado):
        await store.arquivar_campanha(ADMIN, camp.id)  # admin da instância ≠ GM


@pytest.mark.asyncio
async def test_banco_de_antes_do_arquivamento_ganha_a_coluna(tmp_path: Path) -> None:
    """Banco criado sem `arquivada_em` (13/10) migra sozinho e continua listando."""
    import aiosqlite

    db = tmp_path / "velho.db"
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "CREATE TABLE campanha (id TEXT PRIMARY KEY, owner_email TEXT NOT NULL, nome TEXT NOT NULL, "
            "criada_em REAL NOT NULL, atualizada_em REAL NOT NULL, schema_version INTEGER NOT NULL)"
        )
        await conn.execute("INSERT INTO campanha VALUES ('c-velha','alice@voxdm.test','Velha',1,1,1)")
        await conn.execute(
            "CREATE TABLE campanha_membro (campanha_id TEXT NOT NULL, email TEXT NOT NULL, "
            "papel TEXT NOT NULL, PRIMARY KEY (campanha_id, email))"
        )
        await conn.execute("INSERT INTO campanha_membro VALUES ('c-velha','alice@voxdm.test','gm')")
        await conn.commit()

    store = CampanhaStore(db_path=db, dir_saves=tmp_path / "s")
    assert [c.id for c in await store.listar_campanhas(ALICE)] == ["c-velha"]
    nova = await store.criar_campanha(ALICE, "Nova")
    assert {c.id for c in await store.listar_campanhas(ALICE)} == {"c-velha", nova.id}
