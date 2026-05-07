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
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger()

DB_PATH = Path(__file__).parent.parent.parent / "voxdm.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS character_state (
    session_id             TEXT    PRIMARY KEY,
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
    updated_at             REAL    NOT NULL DEFAULT (unixepoch())
)
"""


@dataclass
class CharacterState:
    """Estado persistível do personagem — complementa a WorkingMemory volátil."""

    session_id: str
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


class CharacterStore:
    """CRUD assíncrono para o estado do personagem em SQLite."""

    async def _conn(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(DB_PATH)
        conn.row_factory = aiosqlite.Row
        await conn.execute(_CREATE_TABLE)
        await conn.commit()
        return conn

    async def salvar(self, state: CharacterState) -> None:
        """Upsert do estado completo do personagem."""
        # JSON não aceita int como chave — serializa como string
        slots_json = json.dumps({str(k): v for k, v in state.spell_slots.items()})
        async with await self._conn() as conn:
            await conn.execute(
                """
                INSERT INTO character_state
                    (session_id, spell_slots, hit_dice_current, hit_dice_max, hit_dice_type,
                     death_saves_successes, death_saves_failures, death_saves_stable,
                     gold, xp, inspiration, hp_current, hp_max, inventory, conditions,
                     updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,unixepoch())
                ON CONFLICT(session_id) DO UPDATE SET
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
                    updated_at=unixepoch()
                """,
                (
                    state.session_id,
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
                ),
            )
            await conn.commit()
        log.info("character_state_salvo", session_id=state.session_id)

    async def carregar(self, session_id: str) -> CharacterState | None:
        """Carrega estado do personagem. Retorna None se não houver registro."""
        async with await self._conn() as conn:
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
        )

    async def deletar(self, session_id: str) -> None:
        """Remove estado do personagem do banco."""
        async with await self._conn() as conn:
            await conn.execute(
                "DELETE FROM character_state WHERE session_id = ?", (session_id,)
            )
            await conn.commit()
