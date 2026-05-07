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
