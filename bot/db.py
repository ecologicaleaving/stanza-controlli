import asyncpg


class DB:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    # ---------------- positions ----------------

    async def insert_position(
        self,
        *,
        socio: str,
        topic: str,
        claim: str,
        kind: str,
        source: str = "telegram",
        confidence: str = "medium",
        decision_id: str | None = None,
        supersedes_id: str | None = None,
    ) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.positions
                  (socio, topic, claim, kind, source, confidence, decision_id, supersedes_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id::text
                """,
                socio, topic, claim, kind, source, confidence, decision_id, supersedes_id,
            )
            return row["id"]

    async def positions_since(self, *, hours: int, exclude_socio: str | None = None) -> list[dict]:
        query = """
            SELECT id::text, socio, topic, claim, kind, created_at
            FROM el_brain.positions
            WHERE created_at >= now() - ($1::int * interval '1 hour')
        """
        params: list = [hours]
        if exclude_socio:
            query += " AND socio <> $2"
            params.append(exclude_socio)
        query += " ORDER BY created_at DESC"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    # ---------------- decisions_open ----------------

    async def insert_decision_open(self, *, title: str, parent_topic: str | None = None) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.decisions_open (title, parent_topic)
                VALUES ($1, $2)
                RETURNING id::text
                """,
                title, parent_topic,
            )
            return row["id"]

    async def decisions_open_active(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id::text, title, status, deadline, parent_topic, created_at
                FROM el_brain.decisions_open
                WHERE status NOT IN ('closed','dropped')
                ORDER BY created_at DESC
                """
            )
            return [dict(r) for r in rows]

    # ---------------- tasks ----------------

    async def insert_task(
        self,
        *,
        title: str,
        owner: str,
        deadline: str | None = None,
        context_link: str | None = None,
    ) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.tasks (title, owner, deadline, context_link)
                VALUES ($1, $2, $3::date, $4)
                RETURNING id::text
                """,
                title, owner, deadline, context_link,
            )
            return row["id"]

    async def tasks_due_within(self, *, days: int, owner: str | None = None) -> list[dict]:
        query = """
            SELECT id::text, title, owner, status, deadline
            FROM el_brain.tasks
            WHERE status NOT IN ('done','dropped')
              AND deadline IS NOT NULL
              AND deadline <= current_date + ($1::int * interval '1 day')
        """
        params: list = [days]
        if owner:
            query += " AND (owner = $2 OR owner = 'both')"
            params.append(owner)
        query += " ORDER BY deadline ASC NULLS LAST"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]

    # ---------------- tg_inbox / tg_outbox (F1 — issue #2) ----------------

    async def insert_inbox(
        self,
        *,
        tg_message_id: int,
        chat_id: int,
        socio: str | None,
        sender_user_id: int,
        text: str,
        reply_to_message_id: int | None,
        is_to_gaia: bool,
    ) -> int:
        """Scrive un messaggio in tg_inbox e ritorna l'id generato."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.tg_inbox
                  (tg_message_id, chat_id, socio, sender_user_id, text,
                   reply_to_message_id, is_to_gaia)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                tg_message_id, chat_id, socio, sender_user_id, text,
                reply_to_message_id, is_to_gaia,
            )
            return row["id"]

    async def insert_outbox(
        self,
        *,
        chat_id: int,
        text: str,
        in_reply_to: int | None = None,
        model: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
    ) -> int:
        """Scrive un messaggio pending in tg_outbox e ritorna l'id.

        sent_at viene lasciato NULL (pending) — il dispatcher legge queste righe,
        invia a Telegram e valorizza sent_at = now() via mark_outbox_sent().
        Contratto F2a: sent_at IS NULL ↔ da inviare.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO el_brain.tg_outbox
                  (chat_id, text, in_reply_to, model, tokens_in, tokens_out, sent_at)
                VALUES ($1, $2, $3, $4, $5, $6, NULL)
                RETURNING id
                """,
                chat_id, text, in_reply_to, model, tokens_in, tokens_out,
            )
            return row["id"]

    async def fetch_outbox_pending(self, limit: int = 10) -> list[dict]:
        """Ritorna le righe di tg_outbox non ancora inviate (sent_at IS NULL).

        Ordinate per id ASC (FIFO), con un limit per batch.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, chat_id, text, in_reply_to
                FROM el_brain.tg_outbox
                WHERE sent_at IS NULL
                ORDER BY id ASC
                LIMIT $1
                """,
                limit,
            )
            return [dict(r) for r in rows]

    async def mark_outbox_sent(self, outbox_id: int) -> None:
        """Valorizza sent_at = now() per una riga di tg_outbox già inviata."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE el_brain.tg_outbox SET sent_at = now() WHERE id = $1",
                outbox_id,
            )

    # ---------------- briefing_items (esistente) ----------------

    async def briefing_items_pending(self, *, socio: str) -> list[dict]:
        col_read = f"read_{socio}"
        col_approved = f"approved_{socio}"
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, title, link, {col_read} AS read, {col_approved} AS approved
                FROM briefing_items
                WHERE {col_read} = false OR {col_approved} = false
                ORDER BY id
                """
            )
            return [dict(r) for r in rows]
