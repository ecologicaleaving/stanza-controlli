"""Accesso al DB el_brain dal cervello (via tunnel SSH, asyncpg).

Legge i trigger da tg_inbox e scrive le risposte in tg_outbox (sent_at=NULL,
le invierà il dispatcher sul VPS).
"""

import logging

import asyncpg

from config import Config

log = logging.getLogger("gaia.db")


class BrainDB:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(
            host="127.0.0.1",
            port=self.cfg.local_db_port,
            user=self.cfg.pg_user,
            password=self.cfg.pg_password,
            database=self.cfg.pg_database,
            min_size=1,
            max_size=3,
        )

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def drain_backlog(self) -> int:
        """All'avvio: marca processed tutti i pending esistenti, così Gaia non
        risponde al backlog vecchio. Ritorna quante righe ha drenato."""
        async with self.pool.acquire() as conn:
            res = await conn.execute(
                "UPDATE el_brain.tg_inbox SET processed = true WHERE processed = false"
            )
            # res es. "UPDATE 3"
            try:
                return int(res.split()[-1])
            except (ValueError, IndexError):
                return 0

    async def fetch_new_triggers(self) -> list[dict]:
        """Messaggi che attivano una risposta e non ancora processati."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, tg_message_id, chat_id, socio, text, created_at
                FROM el_brain.tg_inbox
                WHERE processed = false AND is_to_gaia = true
                ORDER BY created_at ASC
                """
            )
            return [dict(r) for r in rows]

    async def fetch_recent_context(self, chat_id: int, limit: int) -> list[dict]:
        """Ultimi N messaggi del gruppo (per dare a Gaia il filo del discorso)."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT socio, text, created_at
                FROM el_brain.tg_inbox
                WHERE chat_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                chat_id, limit,
            )
            return list(reversed([dict(r) for r in rows]))

    async def insert_outbox(
        self, *, chat_id: int, text: str, in_reply_to: int | None, model: str
    ) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.tg_outbox (chat_id, text, in_reply_to, model, sent_at)
                VALUES ($1, $2, $3, $4, NULL)
                RETURNING id
                """,
                chat_id, text, in_reply_to, model,
            )
            return row["id"]

    async def mark_processed(self, ids: list[int]) -> None:
        if not ids:
            return
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE el_brain.tg_inbox SET processed = true WHERE id = ANY($1::bigint[])",
                ids,
            )

    # ---------------- Stanza dei Controlli: lettura (briefing) ----------------

    async def positions_since(self, *, hours: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT socio, topic, claim, kind, created_at
                FROM el_brain.positions
                WHERE created_at >= now() - ($1::int * interval '1 hour')
                ORDER BY created_at DESC
                """,
                hours,
            )
            return [dict(r) for r in rows]

    async def decisions_open_active(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT title, status, deadline, parent_topic, created_at
                FROM el_brain.decisions_open
                WHERE status NOT IN ('closed','dropped')
                ORDER BY created_at DESC
                """
            )
            return [dict(r) for r in rows]

    async def tasks_due_within(self, *, days: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT title, owner, status, deadline
                FROM el_brain.tasks
                WHERE status NOT IN ('done','dropped')
                  AND deadline IS NOT NULL
                  AND deadline <= current_date + ($1::int * interval '1 day')
                ORDER BY deadline ASC
                """,
                days,
            )
            return [dict(r) for r in rows]

    # ---------------- Stanza dei Controlli: scrittura (registrazione) ----------------

    async def insert_position(self, *, socio: str, topic: str, claim: str, kind: str) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.positions (socio, topic, claim, kind, source)
                VALUES ($1, $2, $3, $4, 'telegram')
                RETURNING id::text
                """,
                socio, topic, claim, kind,
            )
            return row["id"]

    async def insert_task(self, *, title: str, owner: str, deadline: str | None) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.tasks (title, owner, deadline)
                VALUES ($1, $2, $3::date)
                RETURNING id::text
                """,
                title, owner, deadline,
            )
            return row["id"]

    async def insert_decision_open(self, *, title: str) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.decisions_open (title)
                VALUES ($1)
                RETURNING id::text
                """,
                title,
            )
            return row["id"]
