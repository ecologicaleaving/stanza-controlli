"""Dispatcher outbox F2a — invia le risposte pending di Gaia a Telegram.

Il cervello (brain/, gira sul PC) scrive righe in el_brain.tg_outbox con
sent_at = NULL. Questo dispatcher viene schedulato ogni ~8 secondi dal job_queue
di python-telegram-bot: legge le righe pending, le invia e valorizza sent_at.

Contratto: sent_at IS NULL ↔ da inviare. Una riga con sent_at NOT NULL non viene
toccata (idempotente per doppia esecuzione, anche se non dovrebbe mai accadere).
"""

import logging

from telegram import Bot

from bot.db import DB

log = logging.getLogger(__name__)


async def dispatch_outbox(bot: Bot, db: DB) -> None:
    """Legge le righe pending di tg_outbox e le invia a Telegram.

    - Recupera fino a 10 righe pending (FIFO per id).
    - Per ciascuna: invia il messaggio al chat_id.
      in_reply_to referenzia tg_inbox.id (non un message_id Telegram),
      quindi non viene usato come reply — invia solo al chat.
    - In caso di successo: marca sent_at = now() e logga INFO.
    - In caso di errore sul singolo invio: logga ERROR e continua
      con le altre righe (la riga rimane pending, sarà ripresa al prossimo ciclo).
    """
    pending = await db.fetch_outbox_pending(limit=10)
    if not pending:
        return

    log.debug("dispatch_outbox: %d righe pending", len(pending))

    for row in pending:
        outbox_id: int = row["id"]
        chat_id: int = row["chat_id"]
        text: str = row["text"]
        try:
            await bot.send_message(chat_id=chat_id, text=text)
            await db.mark_outbox_sent(outbox_id)
            log.info(
                "dispatch_outbox: inviato outbox_id=%d chat_id=%d (%d chars)",
                outbox_id, chat_id, len(text),
            )
        except Exception:
            log.error(
                "dispatch_outbox: errore invio outbox_id=%d chat_id=%d — riga rimane pending",
                outbox_id, chat_id,
                exc_info=True,
            )
