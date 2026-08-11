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
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

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
    asi_pendente           TEXT    NOT NULL DEFAULT '[]',
    companions             TEXT    NOT NULL DEFAULT '{}',
    personagem_config      TEXT    NOT NULL DEFAULT '{}',
    dm_state               TEXT    NOT NULL DEFAULT '{}',
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
# LEVELUP-SEM-ESCOLHA-1: fila de Incremento de Atributo devido. Sem esta coluna
# a OFERTA se perdia ao fechar o browser (os scores já persistiam via
# personagem_config) e o personagem ficava "devendo" um ASI sem jeito de resgatar.
_MIGRATE_ASI_PENDENTE = "ALTER TABLE character_state ADD COLUMN asi_pendente TEXT NOT NULL DEFAULT '[]'"

# Migração idempotente — adiciona coluna companions (Fase 5.2).
# Bug narrativo grave: companion some entre sessões sem persistência.
_MIGRATE_COMPANIONS = "ALTER TABLE character_state ADD COLUMN companions TEXT NOT NULL DEFAULT '{}'"

# INVENTARIO-SEM-ESTADO-1 (10/08): a coluna `inventory` guarda só NOMES. O
# inventário estruturado (tipo, quantidade, equipado) precisa de coluna própria —
# reaproveitar `inventory` quebraria toda sessão salva antes de hoje. As duas
# convivem: `inventory` continua sendo a vista de nomes, e é dela que um banco
# antigo é migrado na primeira leitura.
_MIGRATE_INVENTARIO = (
    "ALTER TABLE character_state ADD COLUMN inventario TEXT NOT NULL DEFAULT '[]'"
)

# Migração idempotente — identidade completa do personagem.
# Salva numa única coluna JSON para não precisar de ~18 ALTER TABLE separados.
# Campos: player_name, player_class, player_race, player_background, player_subclass,
# player_description, tts_voice, dm_profile, str/dex/con/int/wis/cha scores,
# skill_profs, save_profs, location_id, location_nome, player_hp_max.
# Sem isso, continuar uma sessão exigia re-preencher o CharacterForm inteiro.
_MIGRATE_PERSONAGEM_CONFIG = (
    "ALTER TABLE character_state ADD COLUMN personagem_config TEXT NOT NULL DEFAULT '{}'"
)

# Migração idempotente — estado narrativo do mestre veterano.
# Persiste fios_soltos, agenda_npcs e cliffhanger_pendente entre sessões/crashes.
# Sem isso o DM "esquece" os fios narrativos a cada reconexão, rompendo a continuidade.
_MIGRATE_DM_STATE = (
    "ALTER TABLE character_state ADD COLUMN dm_state TEXT NOT NULL DEFAULT '{}'"
)


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
    # Inventário ESTRUTURADO (tipo, quantidade, equipado). `inventory` continua
    # sendo a vista de nomes, e é dela que um banco antigo é migrado na leitura.
    inventario: list[dict] = field(default_factory=list)
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
    asi_pendente: list[dict] = field(default_factory=list)
    # Aliados ativos (hireling, familiar, animal, summon) com estado de HP.
    # Persistimos para que Lyssa e companhia sobrevivam entre sessões.
    # Formato: {"lyssa": {"nome": "Lyssa", "tipo": "hireling", "hp": 17,
    #            "hp_max": 25, "ca": 15, "atq": "+4", "dano": "1d8"}}
    companions: dict[str, dict] = field(default_factory=dict)
    # Identidade completa do personagem — salva numa única coluna JSON.
    # Campos cobertos: player_name, player_class, player_race, player_background,
    # player_subclass, player_description, tts_voice, dm_profile,
    # str/dex/con/int/wis/cha scores, skill_profs, save_profs,
    # location_id, location_nome, player_hp_max.
    # Restaurado em iniciar_sessao() quando session_anterior_id é fornecido,
    # eliminando a necessidade de re-preencher o CharacterForm.
    personagem_config: dict = field(default_factory=dict)
    # Estado narrativo do mestre veterano — persiste entre sessões/crashes.
    # Formato: {"fios_soltos": [...], "agenda_npcs": {...}, "cliffhanger": ""}
    # Sem isso o mestre "esquece" os fios narrativos em reconexões.
    dm_state: dict = field(default_factory=dict)


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
            await _aplicar_migracao_idempotente(conn, _MIGRATE_ASI_PENDENTE, "asi_pendente")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_COMPANIONS, "companions")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_INVENTARIO, "inventario")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_PERSONAGEM_CONFIG, "personagem_config")
            await _aplicar_migracao_idempotente(conn, _MIGRATE_DM_STATE, "dm_state")
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
                     inventory, inventario, conditions, spells_conhecidas, player_level,
                     class_features, asi_pendente, companions, personagem_config, dm_state, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,unixepoch())
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
                    inventario=excluded.inventario,
                    conditions=excluded.conditions,
                    spells_conhecidas=excluded.spells_conhecidas,
                    player_level=excluded.player_level,
                    class_features=excluded.class_features,
                    asi_pendente=excluded.asi_pendente,
                    companions=excluded.companions,
                    personagem_config=excluded.personagem_config,
                    dm_state=excluded.dm_state,
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
                    json.dumps(state.inventario, ensure_ascii=False),
                    json.dumps(state.conditions),
                    json.dumps(state.spells_conhecidas),
                    state.player_level,
                    json.dumps(state.class_features),
                    json.dumps(state.asi_pendente),
                    json.dumps(state.companions),
                    json.dumps(state.personagem_config),
                    json.dumps(state.dm_state),
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
            # Banco anterior a 10/08 não tem a coluna preenchida — cai em [] e o
            # caller reconstrói a estrutura a partir dos NOMES, sem perder itens.
            inventario=json.loads(row["inventario"] or "[]") if "inventario" in row.keys() else [],
            conditions=json.loads(row["conditions"]),
            spells_conhecidas=json.loads(row["spells_conhecidas"] or "[]"),
            player_level=int(row["player_level"] or 3),
            class_features=json.loads(row["class_features"] or "{}"),
            asi_pendente=json.loads(row["asi_pendente"] or "[]"),
            companions=json.loads(row["companions"] or "{}"),
            personagem_config=json.loads(row["personagem_config"] or "{}"),
            dm_state=json.loads(row["dm_state"] or "{}"),
        )

    async def deletar(self, session_id: str) -> None:
        """Remove estado do personagem do banco."""
        async with self._conn() as conn:
            await conn.execute(
                "DELETE FROM character_state WHERE session_id = ?", (session_id,)
            )
            await conn.commit()

    async def listar_por_owner(self, owner_email: str) -> list[dict]:
        """Lista personagens com identidade salva para o owner, mais recentes primeiro.

        Diferente de EpisodicMemory.listar_com_metadata() (Qdrant, exige DELETE),
        este método lê do SQLite e inclui sessões apenas auto-checkpointadas.
        Retorna somente linhas que têm player_name em personagem_config.
        """
        async with self._conn() as conn:
            async with conn.execute(
                "SELECT session_id, player_level, hp_current, hp_max, "
                "personagem_config, updated_at "
                "FROM character_state WHERE owner_email = ? ORDER BY updated_at DESC",
                (owner_email,),
            ) as cur:
                rows = await cur.fetchall()

        resultado: list[dict] = []
        for row in rows:
            pc: dict = json.loads(row["personagem_config"] or "{}")
            nome = pc.get("player_name", "")
            if not nome:
                continue  # pula sessões criadas antes de personagem_config existir
            resultado.append({
                "session_id": row["session_id"],
                "player_name": nome,
                "player_class": pc.get("player_class", ""),
                "player_level": int(row["player_level"] or 3),
                "hp_atual": int(row["hp_current"] or 0),
                "hp_max": int(row["hp_max"] or 1),
                "ultima_sessao": float(row["updated_at"] or 0),
            })
        return resultado
