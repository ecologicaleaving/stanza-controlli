"""Scheduler APScheduler per il briefing mattutino."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot

from bot.briefing import send_morning_briefing
from bot.config import Config
from bot.db import DB

log = logging.getLogger(__name__)


def start_scheduler(bot: Bot, db: DB, config: Config) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.briefing_timezone)
    scheduler.add_job(
        send_morning_briefing,
        trigger=CronTrigger(
            hour=config.briefing_hour,
            minute=0,
            timezone=config.briefing_timezone,
        ),
        kwargs={"bot": bot, "db": db, "config": config},
        id="morning_briefing",
        replace_existing=True,
    )
    scheduler.start()
    log.info(
        "scheduler avviato — briefing alle %02d:00 %s",
        config.briefing_hour,
        config.briefing_timezone,
    )
    return scheduler
