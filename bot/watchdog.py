"""Watchdog interno: monitora salute di Telegram API e DB.

Ogni `interval_seconds` fa ping a entrambi. Se fallisce `max_failures`
volte di fila, fa `sys.exit(1)` cosicché Docker `restart: unless-stopped`
ricrei il container da zero.

Risolve il caso "polling stuck in retry loop" (Bad Gateway loop di
python-telegram-bot) che ha bloccato il bot la notte del 2026-05-07.
"""

import asyncio
import logging
import sys

from telegram import Bot

from bot.db import DB

log = logging.getLogger(__name__)


async def run_watchdog(
    bot: Bot,
    db: DB,
    *,
    interval_seconds: int = 600,
    max_failures: int = 3,
) -> None:
    failures = 0
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await bot.get_me()
            async with db.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            if failures > 0:
                log.info("watchdog: salute ripristinata dopo %d fail", failures)
            failures = 0
        except Exception as e:
            failures += 1
            log.error("watchdog fail %d/%d: %s", failures, max_failures, e)
            if failures >= max_failures:
                log.error(
                    "watchdog: %d fail consecutivi, sys.exit(1) per forzare restart container",
                    max_failures,
                )
                sys.exit(1)
