"""
Campanhas, membros e saves — SQLite para o índice, arquivo JSON para o snapshot.

Por que existe: continuidade solo. A unidade do save é a CAMPANHA (mesa), não o
    personagem: uma campanha tem membros com papel (gm|player) e N saves, cada
    um um envelope versionado (`save_envelope`). Mesma doutrina do
    `character_store`: migração idempotente, owner em toda linha.
Dependências: aiosqlite, engine/auth, engine/persistence/save_envelope, config
Armadilha: TODO método público recebe `Owner` como primeiro argumento e não
    existe leitura sem ele. Campanha ou save de outra pessoa levanta
    `NaoEncontrado` — o MESMO erro de "não existe" (vira 404 na rota, nunca 403).
Armadilha: o save é escrito em arquivo temporário + fsync + `os.replace`, e só
    depois de RELIDO e conferido pelo sha256 ele entra no índice. A rotação
    roda por último e mantém as `SAVES_MANTER` versões mais novas — nunca apaga
    quando há N ou menos, então o único save bom nunca é a vítima. O Beltrami
    já perdeu arquivo crítico por truncamento (28/09).
Armadilha: quebra-vidro grava a linha de auditoria ANTES de ler o conteúdo. Se
    a auditoria falhar, o conteúdo não sai.

Exemplo:
    store = CampanhaStore()
    camp = await store.criar_campanha(dono, "Os Filhos de Valdrek")
    info = await store.salvar(dono, camp.id, "antes do dragão", envelope)
    envelope2 = await store.carregar(dono, camp.id, info.id)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite
import structlog

from config import settings
from engine.auth.identity import Owner, exigir_dono
from engine.auth.permissoes import (
    PAPEL_GM,
    pode_ler_campanha,
    pode_salvar_campanha,
    pode_ver_conteudo,
)
from engine.persistence import character_store
from engine.persistence.save_envelope import SCHEMA_VERSION, resumo_manifesto

log = structlog.get_logger()

_CREATE: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS campanha (
        id              TEXT PRIMARY KEY,
        owner_email     TEXT NOT NULL,
        nome            TEXT NOT NULL,
        criada_em       REAL NOT NULL,
        atualizada_em   REAL NOT NULL,
        schema_version  INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campanha_membro (
        campanha_id TEXT NOT NULL,
        email       TEXT NOT NULL,
        papel       TEXT NOT NULL,
        PRIMARY KEY (campanha_id, email)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS save (
        id              TEXT PRIMARY KEY,
        campanha_id     TEXT NOT NULL,
        rotulo          TEXT NOT NULL,
        criado_em       REAL NOT NULL,
        schema_version  INTEGER NOT NULL,
        manifest        TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS save_audit (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        em          REAL NOT NULL,
        email       TEXT NOT NULL,
        acao        TEXT NOT NULL,
        campanha_id TEXT NOT NULL,
        save_id     TEXT NOT NULL DEFAULT '',
        motivo      TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_campanha_owner ON campanha(owner_email)",
    "CREATE INDEX IF NOT EXISTS idx_membro_email ON campanha_membro(email)",
    "CREATE INDEX IF NOT EXISTS idx_save_campanha ON save(campanha_id, criado_em)",
)


class NaoEncontrado(LookupError):
    """Não existe OU não é seu — indistinguível de propósito."""


class SaveCorrompido(RuntimeError):
    """O arquivo do save não bate com o checksum do índice."""


@dataclass(frozen=True)
class Campanha:
    id: str
    owner_email: str
    nome: str
    criada_em: float
    atualizada_em: float
    schema_version: int
    papel: str = ""  # papel de QUEM pediu (vazio em listagem de admin)


@dataclass(frozen=True)
class SaveInfo:
    id: str
    campanha_id: str
    rotulo: str
    criado_em: float
    schema_version: int
    manifest: dict[str, Any]


def _dir_saves() -> Path:
    return Path(settings.SAVES_DIR)


def _escrever_atomico(destino: Path, dados: bytes) -> None:
    """tmp no MESMO diretório + fsync + os.replace. Nunca escreve no destino direto."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, destino)
    finally:
        if tmp.exists():
            tmp.unlink()


class CampanhaStore:
    """CRUD de campanha/membro/save com dono obrigatório."""

    def __init__(self, db_path: Path | None = None, dir_saves: Path | None = None) -> None:
        self._db = db_path or character_store.DB_PATH
        self._dir = dir_saves

    @property
    def dir_saves(self) -> Path:
        return self._dir or _dir_saves()

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._db) as conn:
            conn.row_factory = aiosqlite.Row
            for sql in _CREATE:
                await conn.execute(sql)
            await conn.commit()
            yield conn

    # ── auditoria ────────────────────────────────────────────────────────────

    @staticmethod
    async def _auditar(
        conn: aiosqlite.Connection, email: str, acao: str, campanha_id: str,
        save_id: str = "", motivo: str = "",
    ) -> None:
        await conn.execute(
            "INSERT INTO save_audit (em, email, acao, campanha_id, save_id, motivo) "
            "VALUES (?,?,?,?,?,?)",
            (time.time(), email, acao, campanha_id, save_id, motivo),
        )
        await conn.commit()

    async def auditoria(self, owner: Owner, campanha_id: str) -> list[dict[str, Any]]:
        """Linhas de auditoria da campanha — para o GM dela ou para o admin."""
        email = exigir_dono(owner)
        async with self._conn() as conn:
            papel = await self._papel(conn, campanha_id, email)
            if papel != PAPEL_GM and not owner.is_admin:
                raise NaoEncontrado(campanha_id)
            async with conn.execute(
                "SELECT em, email, acao, save_id, motivo FROM save_audit "
                "WHERE campanha_id = ? ORDER BY id", (campanha_id,),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    # ── campanha ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _papel(conn: aiosqlite.Connection, campanha_id: str, email: str) -> str | None:
        async with conn.execute(
            "SELECT papel FROM campanha_membro WHERE campanha_id = ? AND email = ?",
            (campanha_id, email),
        ) as cur:
            row = await cur.fetchone()
        return str(row["papel"]) if row else None

    @staticmethod
    def _campanha(row: aiosqlite.Row, papel: str = "") -> Campanha:
        return Campanha(
            id=row["id"], owner_email=row["owner_email"], nome=row["nome"],
            criada_em=float(row["criada_em"]), atualizada_em=float(row["atualizada_em"]),
            schema_version=int(row["schema_version"]), papel=papel,
        )

    async def criar_campanha(self, owner: Owner, nome: str) -> Campanha:
        """Cria a campanha; quem cria vira GM dela."""
        email = exigir_dono(owner)
        nome = nome.strip()
        if not nome:
            raise ValueError("campanha precisa de nome")
        agora = time.time()
        cid = f"camp-{uuid.uuid4().hex[:12]}"
        async with self._conn() as conn:
            await conn.execute(
                "INSERT INTO campanha VALUES (?,?,?,?,?,?)",
                (cid, email, nome, agora, agora, SCHEMA_VERSION),
            )
            await conn.execute(
                "INSERT INTO campanha_membro VALUES (?,?,?)", (cid, email, PAPEL_GM),
            )
            await self._auditar(conn, email, "criar_campanha", cid)
        log.info("campanha_criada", campanha_id=cid)
        return Campanha(cid, email, nome, agora, agora, SCHEMA_VERSION, PAPEL_GM)

    async def listar_campanhas(self, owner: Owner) -> list[Campanha]:
        """Campanhas em que este dono é membro (com papel válido)."""
        email = exigir_dono(owner)
        async with self._conn() as conn:
            async with conn.execute(
                "SELECT c.*, m.papel FROM campanha c JOIN campanha_membro m "
                "ON m.campanha_id = c.id WHERE m.email = ? ORDER BY c.atualizada_em DESC",
                (email,),
            ) as cur:
                rows = await cur.fetchall()
        return [self._campanha(r, r["papel"]) for r in rows if pode_ler_campanha(r["papel"])]

    async def obter_campanha(self, owner: Owner, campanha_id: str) -> Campanha:
        email = exigir_dono(owner)
        async with self._conn() as conn:
            papel = await self._papel(conn, campanha_id, email)
            if not pode_ler_campanha(papel):
                raise NaoEncontrado(campanha_id)
            async with conn.execute("SELECT * FROM campanha WHERE id = ?", (campanha_id,)) as cur:
                row = await cur.fetchone()
        if row is None:
            raise NaoEncontrado(campanha_id)
        return self._campanha(row, str(papel))

    async def adicionar_membro(
        self, owner: Owner, campanha_id: str, email_membro: str, papel: str,
    ) -> None:
        """Só o GM da mesa adiciona membros. Papel desconhecido é recusado."""
        email = exigir_dono(owner)
        alvo = exigir_dono(Owner(email=email_membro))
        if not pode_ler_campanha(papel):
            raise ValueError(f"papel desconhecido: {papel!r}")
        async with self._conn() as conn:
            if await self._papel(conn, campanha_id, email) != PAPEL_GM:
                raise NaoEncontrado(campanha_id)
            await conn.execute(
                "INSERT INTO campanha_membro VALUES (?,?,?) "
                "ON CONFLICT(campanha_id, email) DO UPDATE SET papel = excluded.papel",
                (campanha_id, alvo, papel),
            )
            await self._auditar(conn, email, f"membro:{alvo}:{papel}", campanha_id)

    async def listar_membros(self, owner: Owner, campanha_id: str) -> list[dict[str, str]]:
        """Membros e papéis — visível para qualquer membro da campanha."""
        email = exigir_dono(owner)
        async with self._conn() as conn:
            if not pode_ler_campanha(await self._papel(conn, campanha_id, email)):
                raise NaoEncontrado(campanha_id)
            async with conn.execute(
                "SELECT email, papel FROM campanha_membro WHERE campanha_id = ? ORDER BY papel, email",
                (campanha_id,),
            ) as cur:
                return [{"email": r["email"], "papel": r["papel"]} for r in await cur.fetchall()]

    # ── saves ────────────────────────────────────────────────────────────────

    def _arquivo(self, campanha_id: str, save_id: str) -> Path:
        return self.dir_saves / campanha_id / f"{save_id}.json"

    async def salvar(
        self, owner: Owner, campanha_id: str, rotulo: str, envelope: dict[str, Any],
    ) -> SaveInfo:
        """Grava um save novo (nunca sobrescreve) e rotaciona os antigos."""
        email = exigir_dono(owner)
        async with self._conn() as conn:
            if not pode_salvar_campanha(await self._papel(conn, campanha_id, email)):
                raise NaoEncontrado(campanha_id)

            sid = f"save-{uuid.uuid4().hex[:12]}"
            dados = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode("utf-8")
            sha = hashlib.sha256(dados).hexdigest()
            destino = self._arquivo(campanha_id, sid)
            await asyncio.to_thread(_escrever_atomico, destino, dados)

            # Relê do disco antes de indexar: só entra no índice o que foi
            # comprovadamente gravado inteiro.
            relido = await asyncio.to_thread(destino.read_bytes)
            if hashlib.sha256(relido).hexdigest() != sha:
                raise SaveCorrompido(f"releitura do save {sid} não bate com o que foi escrito")

            manifest = {
                "arquivo": f"{campanha_id}/{sid}.json",
                "sha256": sha,
                "bytes": len(dados),
                **resumo_manifesto(envelope),
            }
            agora = time.time()
            versao = int(envelope.get("schema_version", SCHEMA_VERSION))
            await conn.execute(
                "INSERT INTO save VALUES (?,?,?,?,?,?)",
                (sid, campanha_id, rotulo.strip() or "sem rótulo", agora, versao, json.dumps(manifest)),
            )
            await conn.execute(
                "UPDATE campanha SET atualizada_em = ? WHERE id = ?", (agora, campanha_id),
            )
            await self._auditar(conn, email, "salvar", campanha_id, sid)
            await self._rotacionar(conn, campanha_id)
        log.info("save_gravado", campanha_id=campanha_id, save_id=sid, bytes=len(dados))
        return SaveInfo(sid, campanha_id, rotulo, agora, versao, manifest)

    async def _rotacionar(self, conn: aiosqlite.Connection, campanha_id: str) -> None:
        """Mantém as N versões mais novas. Com N ou menos, não apaga nada."""
        manter = max(1, int(settings.SAVES_MANTER))
        async with conn.execute(
            "SELECT id FROM save WHERE campanha_id = ? ORDER BY criado_em DESC, rowid DESC",
            (campanha_id,),
        ) as cur:
            ids = [r["id"] for r in await cur.fetchall()]
        for velho in ids[manter:]:
            await conn.execute("DELETE FROM save WHERE id = ?", (velho,))
            await conn.commit()
            arquivo = self._arquivo(campanha_id, velho)
            if arquivo.exists():
                await asyncio.to_thread(arquivo.unlink)
            log.info("save_rotacionado", campanha_id=campanha_id, save_id=velho)

    @staticmethod
    def _save(row: aiosqlite.Row) -> SaveInfo:
        return SaveInfo(
            id=row["id"], campanha_id=row["campanha_id"], rotulo=row["rotulo"],
            criado_em=float(row["criado_em"]), schema_version=int(row["schema_version"]),
            manifest=json.loads(row["manifest"]),
        )

    async def listar_saves(self, owner: Owner, campanha_id: str) -> list[SaveInfo]:
        """Saves da campanha, mais novo primeiro — só para membros."""
        email = exigir_dono(owner)
        async with self._conn() as conn:
            if not pode_ler_campanha(await self._papel(conn, campanha_id, email)):
                raise NaoEncontrado(campanha_id)
            async with conn.execute(
                "SELECT * FROM save WHERE campanha_id = ? ORDER BY criado_em DESC, rowid DESC",
                (campanha_id,),
            ) as cur:
                return [self._save(r) for r in await cur.fetchall()]

    async def _ler_arquivo(self, info: SaveInfo) -> dict[str, Any]:
        arquivo = self.dir_saves / str(info.manifest["arquivo"])
        dados = await asyncio.to_thread(arquivo.read_bytes)
        if hashlib.sha256(dados).hexdigest() != info.manifest.get("sha256"):
            raise SaveCorrompido(f"save {info.id} não bate com o checksum do índice")
        envelope: dict[str, Any] = json.loads(dados)
        return envelope

    async def carregar(self, owner: Owner, campanha_id: str, save_id: str) -> dict[str, Any]:
        """Conteúdo do save — só para membro da campanha."""
        email = exigir_dono(owner)
        async with self._conn() as conn:
            if not pode_ler_campanha(await self._papel(conn, campanha_id, email)):
                raise NaoEncontrado(save_id)
            async with conn.execute(
                "SELECT * FROM save WHERE id = ? AND campanha_id = ?", (save_id, campanha_id),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                raise NaoEncontrado(save_id)
            await self._auditar(conn, email, "carregar", campanha_id, save_id)
        return await self._ler_arquivo(self._save(row))

    # ── admin da instância ───────────────────────────────────────────────────

    async def listar_metadados_admin(self, owner: Owner) -> list[dict[str, Any]]:
        """Todas as campanhas da instância, SÓ metadado. Exige admin."""
        email = exigir_dono(owner)
        if not owner.is_admin:
            raise NaoEncontrado("admin")
        async with self._conn() as conn:
            async with conn.execute(
                "SELECT c.id, c.owner_email, c.nome, c.criada_em, c.atualizada_em, "
                "COUNT(s.id) AS saves FROM campanha c LEFT JOIN save s "
                "ON s.campanha_id = c.id GROUP BY c.id ORDER BY c.atualizada_em DESC"
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            async with conn.execute(
                "SELECT id, campanha_id, rotulo, criado_em, manifest FROM save "
                "ORDER BY criado_em DESC"
            ) as cur:
                manifests = await cur.fetchall()
        tamanho: dict[str, int] = {}
        personagens: dict[str, list[str]] = {}
        # Rótulo, data e tamanho de cada save são METADADO (decisão de 13/10) —
        # é o que o admin precisa para apontar um quebra-vidro. O arquivo não abre.
        lista: dict[str, list[dict[str, Any]]] = {}
        for m in manifests:
            man = json.loads(m["manifest"])
            lista.setdefault(m["campanha_id"], []).append({
                "id": m["id"], "rotulo": m["rotulo"],
                "criado_em": float(m["criado_em"]), "bytes": int(man.get("bytes", 0)),
            })
            tamanho[m["campanha_id"]] = tamanho.get(m["campanha_id"], 0) + int(man.get("bytes", 0))
            for p in man.get("personagens", []):
                nomes = personagens.setdefault(m["campanha_id"], [])
                if p.get("nome") and p["nome"] not in nomes:
                    nomes.append(p["nome"])
        log.info("admin_listou_metadados", admin=email, campanhas=len(rows))
        return [
            {
                **r,
                "bytes": tamanho.get(r["id"], 0),
                "personagens": personagens.get(r["id"], []),
                "saves_lista": lista.get(r["id"], []),
            }
            for r in rows
        ]

    async def carregar_quebra_vidro(
        self, owner: Owner, save_id: str, motivo: str,
    ) -> dict[str, Any]:
        """Admin lê o CONTEÚDO de um save alheio. Audita antes de abrir."""
        email = exigir_dono(owner)
        motivo = motivo.strip()
        if not motivo:
            raise ValueError("quebra-vidro exige motivo")
        async with self._conn() as conn:
            async with conn.execute(
                "SELECT s.*, c.owner_email AS dono FROM save s JOIN campanha c "
                "ON c.id = s.campanha_id WHERE s.id = ?", (save_id,),
            ) as cur:
                row = await cur.fetchone()
            if row is None or not pode_ver_conteudo(owner, row["dono"], quebra_vidro=True):
                raise NaoEncontrado(save_id)
            # Auditoria PRIMEIRO: se ela falhar, a exceção sobe e o conteúdo não sai.
            await self._auditar(conn, email, "quebra_vidro", row["campanha_id"], save_id, motivo)
        log.warning("quebra_vidro_save", admin=email, save_id=save_id, motivo=motivo)
        return await self._ler_arquivo(self._save(row))
