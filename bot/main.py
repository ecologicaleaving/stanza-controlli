"""Entry point del bot Telegram della Stanza dei Controlli."""

import asyncio
import logging
import signal

from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.config import Config
from bot.db import DB
from bot.handlers import (
    TASK_DEADLINE,
    TASK_OWNER,
    cmd_decisione,
    cmd_help,
    cmd_posizione,
    cmd_start,
    cmd_stato,
    cmd_task_start,
    task_cancel,
    task_deadline,
    task_owner,
)
from bot.scheduler import start_scheduler


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def amain() -> None:
    config = Config.load()
    setup_logging(config.log_level)
    log = logging.getLogger("stanza-controlli")

    db = DB(config.database_url)
    await db.connect()
    log.info("db connesso")

    application = Application.builder().token(config.bot_token).build()
    application.bot_data["config"] = config
    application.bot_data["db"] = db

    # Comandi base
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("posizione", cmd_posizione))
    application.add_handler(CommandHandler("decisione", cmd_decisione))
    application.add_handler(CommandHandler("stato", cmd_stato))

    # /task come conversation
    task_conv = ConversationHandler(
        entry_points=[CommandHandler("task", cmd_task_start)],
        states={
            TASK_OWNER: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_owner)],
            TASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_deadline)],
        },
        fallbacks=[CommandHandler("annulla", task_cancel)],
    )
    application.add_handler(task_conv)

    # Scheduler briefing mattutino
    scheduler = start_scheduler(application.bot, db, config)

    # Avvio polling
    log.info("bot avviato — polling")
    stop_event = asyncio.Event()

    def _on_stop(*_args):
        log.info("ricevuto segnale di stop")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_stop)
        except NotImplementedError:
            # Windows: signals limitati
            pass

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)

    try:
        await stop_event.wait()
    finally:
        log.info("shutdown in corso")
        scheduler.shutdown(wait=False)
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await db.close()
        log.info("shutdown completo")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
