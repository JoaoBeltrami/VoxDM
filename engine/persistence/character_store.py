"""
Persistência do estado do personagem via SQLite/aiosqlite.

Por que existe: WorkingMemory é volátil — spell slots, gold, XP, death saves e
    hit dice são perdidos ao reiniciar o servidor. Este módulo persiste esses
    campos entre sessões em voxdm.db na raiz do projeto.
Dependências: aiosqlite (já em requirements.txt)
Armadilha: chaves do dict spell_slots são int em Python mas string em JSON —
    _serialize/_deserialize fazem a conversão automática.

Exemplo:
    store = CharacterStore()
    await store.salvar(CharacterState(session_id="sess-01", gold=50, xp=900))
    state = await store.carregar("sess-01")  # → CharacterState | None
"""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import aiosqlite
import structlog

log = structlog.get_logger()

DB_PATH = Path(__file__).parent.parent.parent / "voxdm.db"


async def _aplicar_migracao_idempotente(
    conn: aiosqlite.Connection, sql: str, coluna: str
) -> None:
    """Roda uma migração ALTER TABLE engolindo SÓ o erro 'duplicate column'.

    Bug #13: a versão antiga era `try: ...; except Exception: pass` — qualquer
    erro (DB locked, disco cheio, permissão) era silenciosamente ignorado.
    Depois o INSERT seguinte dava `no such column` e o jogador via "Erro" sem
    pista do motivo. Agora só `OperationalError` com mensagem de coluna
    duplicada é tolerada; o resto sobe.
    """
    try:
        await conn.execute(sql)
    except aiosqlite.OperationalError as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "duplicate column name" in msg:
            return  # Migração já aplicada — OK
        log.error("character_store_migracao_falhou", coluna=coluna, erro=str(e))
        raise

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS character_state (
    session_id             TEXT    PRIMARY KEY,
    owner_email            TEXT    NOT NULL DEFAULT '',
    spell_slots            TEXT    NOT NULL DEFAULT '{}',
    hit_dice_current       INTEGER NOT NULL DEFAULT 3,
    hit_dice_max           INTEGER NOT NULL DEFAULT 3,
    hit_dice_type          INTEGER NOT NULL DEFAULT 8,
    death_saves_successes  INTEGER NOT NULL DEFAULT 0,
    death_saves_failures   INTEGER NOT NULL DEFAULT 0,
    death_saves_stable     INTEGER NOT NULL DEFAULT 0,
    gold                   INTEGER NOT NULL DEFAULT 0,
    xp                     INTEGER NOT NULL DEFAULT 0,
    inspiration            INTEGER NOT NULL DEFAULT 0,
    hp_current             INTEGER NOT NULL DEFAULT 30,
    hp_max                 INTEGER NOT NULL DEFAULT 30,
    inventory              TEXT    NOT NULL DEFAULT '[]',
    conditions             TEXT    NOT NULL DEFAULT '[]',
    spells_conhecidas      TEXT    NOT NULL DEFAULT '[]',
    player_level           INTEGER NOT NULL DEFAULT 3,
    class_features         TEXT    NOT NULL DEFAULT '{}',
    updated_at             REAL    NOT NULL DEFAULT (unixepoch())
)
"""

# Migração idempotente — adiciona coluna owner_email em bancos existentes sem a coluna.
# SQLite não suporta IF NOT EXISTS em ALTER COLUMN; o try/except faz a mesma coisa.
_MIGRATE_OWNER_EMAIL = "ALTER TABLE character_state ADD COLUMN owner_email TEXT NOT NULL DEFAULT ''"

# Migração idempotente — adiciona coluna spells_conhecidas em bancos existentes (pré-Fase 6.1).
_MIGRATE_SPELLS = "ALTER TABLE character_state ADD COLUMN spells_conhecidas TEXT NOT NULL DEFAULT '[]'"

# Migração idempotente — adiciona coluna player_level (Feature progressão).
_MIGRATE_PLAYER_LEVEL = "ALTER TABLE character_state ADD COLUMN player_level INTEGER NOT NULL DEFAULT 3"

# Migração idempotente — adiciona coluna class_features (Fase 6 + persistência).
_MIGRATE_CLASS_FEATURES = "ALTER TABLE character_state ADD COLUMN class_features TEXT NOT NULL DEFAULT '{}'"


@dataclass
class CharacterState:
    """Estado persistível do personagem — complementa a WorkingMemory volátil."""

    session_id: str
    owner_email: str = ""  # email do dono — rastreabilidade multi-tenant
    spell_slots: dict[int, dict[str, int]] = field(default_factory=dict)
    hit_dice_current: int = 3
    hit_dice_max: int = 3
    hit_dice_type: int = 8
    death_saves_successes: int = 0
    death_saves_failures: int = 0
    death_saves_stable: bool = False
    gold: int = 0
    xp: int = 0
    inspiration: bool = False
    hp_current: int = 30
    hp_max: int = 30
    inventory: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    # Magias selecionadas na criação do personagem — lista de nomes PT-BR
    # Ordem preservada: truques primeiro, depois magias por nível crescente.
    spells_conhecidas: list[str] = field(default_factory=list)
    # Nível do personagem — começa em 3 (decisão de projeto), sobe via [XP: +N]
    # detectado em api/turn_pipeline e processado por engine/progression.
    player_level: int = 3
    # Features de classe (Action Surge, Rage, Sneak Attack, etc.) com usos_atual.
    # Persistimos para que o estado de recursos seja restaurado entre sessões.
    # Formato: {"action-surge": {"nome": "Action Surge", "disponivel": true,
    #            "usos_max": 1, "usos_atual": 1, "restaura": "curto"}}
    class_features: dict[str, dict] = field(default_factory=dict)


class CharacterStore:
    """CRUD assíncrono para o estado do personagem em SQLite."""

    @asynccontextmanager
    async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
        # aiosqlite.connect() é um context manager — não fazer await separado
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute(_CREATE_TABLE)
            # Migrações idempotentes — adicionam colunas em bancos antigos.
            # Bug #13: o except antigo era `except Exception: pass` e mascarava
            # falhas reais (DB locked, disco cheio, permissão). Agora só engole
            # "duplicate column" do aiosqlite — o resto explode normalmente.
            await _aplicar_migracao_idempotente(conn, _MIGRATE_OWNER_EMAIL, "owner_email")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_SPELLS, "spells_conhecidas")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_PLAYER_LEVEL, "player_level")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_CLASS_FEATURES, "class_features")
            await conn.commit()
            yield conn

    async def salvar(self, state: CharacterState) -> None:
        """Upsert do estado completo do personagem."""
        # JSON não aceita int como chave — serializa como string
        slots_json = json.dumps({str(k): v for k, v in state.spell_slots.items()})
        async with self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO character_state
                    (session_id, owner_email, spell_slots, hit_dice_current, hit_dice_max,
                     hit_dice_type, death_saves_successes, death_saves_failures,
                     death_saves_stable, gold, xp, inspiration, hp_current, hp_max,
                     inventory, conditions, spells_conhecidas, player_level,
                     class_features, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,unixepoch())
                ON CONFLICT(session_id) DO UPDATE SET
                    owner_email=excluded.owner_email,
                    spell_slots=excluded.spell_slots,
                    hit_dice_current=excluded.hit_dice_current,
                    hit_dice_max=excluded.hit_dice_max,
                    hit_dice_type=excluded.hit_dice_type,
                    death_saves_successes=excluded.death_saves_successes,
                    death_saves_failures=excluded.death_saves_failures,
                    death_saves_stable=excluded.death_saves_stable,
                    gold=excluded.gold,
                    xp=excluded.xp,
                    inspiration=excluded.inspiration,
                    hp_current=excluded.hp_current,
                    hp_max=excluded.hp_max,
                    inventory=excluded.inventory,
                    conditions=excluded.conditions,
                    spells_conhecidas=excluded.spells_conhecidas,
                    player_level=excluded.player_level,
                    class_features=excluded.class_features,
                    updated_at=unixepoch()
                """,
                (
                    state.session_id,
                    state.owner_email,
                    slots_json,
                    state.hit_dice_current,
                    state.hit_dice_max,
                    state.hit_dice_type,
                    state.death_saves_successes,
                    state.death_saves_failures,
                    int(state.death_saves_stable),
                    state.gold,
                    state.xp,
                    int(state.inspiration),
                    state.hp_current,
                    state.hp_max,
                    json.dumps(state.inventory),
                    json.dumps(state.conditions),
                    json.dumps(state.spells_conhecidas),
                    state.player_level,
                    json.dumps(state.class_features),
                ),
            )
            await conn.commit()
        log.info("character_state_salvo", session_id=state.session_id)

    async def carregar(self, session_id: str) -> CharacterState | None:
        """Carrega estado do personagem. Retorna None se não houver registro."""
        async with self._conn() as conn:
            async with conn.execute(
                "SELECT * FROM character_state WHERE session_id = ?", (session_id,)
            ) as cur:
                row = await cur.fetchone()

        if row is None:
            return None

        # Converte chaves de string de volta para int
        slots_raw: dict[str, dict[str, int]] = json.loads(row["spell_slots"])
        slots: dict[int, dict[str, int]] = {int(k): v for k, v in slots_raw.items()}

        return CharacterState(
            session_id=session_id,
            owner_email=str(row["owner_email"] or ""),
            spell_slots=slots,
            hit_dice_current=row["hit_dice_current"],
            hit_dice_max=row["hit_dice_max"],
            hit_dice_type=row["hit_dice_type"],
            death_saves_successes=row["death_saves_successes"],
            death_saves_failures=row["death_saves_failures"],
            death_saves_stable=bool(row["death_saves_stable"]),
            gold=row["gold"],
            xp=row["xp"],
            inspiration=bool(row["inspiration"]),
            hp_current=row["hp_current"],
            hp_max=row["hp_max"],
            inventory=json.loads(row["inventory"]),
            conditions=json.loads(row["conditions"]),
            spells_conhecidas=json.loads(row["spells_conhecidas"] or "[]"),
            player_level=int(row["player_level"] or 3),
            class_features=json.loads(row["class_features"] or "{}"),
        )

    async def deletar(self, session_id: str) -> None:
        """Remove estado do personagem do banco."""
        async with self._conn() as conn:
            await conn.execute(
                "DELETE FROM character_state WHERE session_id = ?", (session_id,)
            )
            await conn.commit()
