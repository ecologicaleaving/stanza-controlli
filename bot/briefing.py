"""Composizione e invio del briefing mattutino."""

import logging
from datetime import date

from telegram import Bot

from bot.config import Config
from bot.db import DB

log = logging.getLogger(__name__)


async def compose_briefing(db: DB, *, socio: str) -> str:
    """Costruisce il testo del briefing per un socio (plain text)."""
    altro = "ascanio" if socio == "davide" else "davide"

    positions_altro = await db.positions_since(hours=24, exclude_socio=socio)
    decisions_open = await db.decisions_open_active()
    tasks_due = await db.tasks_due_within(days=2, owner=socio)
    briefing_pending = await db.briefing_items_pending(socio=socio)

    today = date.today().isoformat()

    if (
        not positions_altro
        and not decisions_open
        and not tasks_due
        and not briefing_pending
    ):
        return f"☀️ Briefing — {today}\n\nNiente di nuovo. Buongiorno."

    lines = [f"☀️ Briefing — {today}", ""]

    lines.append(f"📬 Posizioni nuove di {altro.capitalize()} (24h)")
    if not positions_altro:
        lines.append("   nessuna")
    else:
        for p in positions_altro[:10]:
            kind_icon = "💭" if p["kind"] == "opinion" else "📊"
            lines.append(f"   {kind_icon} {p['topic']}: {p['claim'][:120]}")

    lines.append("")
    lines.append("🟡 Decisioni aperte")
    if not decisions_open:
        lines.append("   nessuna")
    else:
        for d in decisions_open[:10]:
            ddl = f" (scade {d['deadline']})" if d.get("deadline") else ""
            lines.append(f"   • {d['title']}{ddl}")

    lines.append("")
    lines.append("📅 Task in scadenza (prossimi 2 giorni)")
    if not tasks_due:
        lines.append("   nessuna")
    else:
        for t in tasks_due[:10]:
            owner_str = "" if t["owner"] == socio else f" [→ {t['owner']}]"
            lines.append(f"   • {t['title']} — {t['deadline']}{owner_str}")

    lines.append("")
    lines.append("✍️ In coda di approvazione/lettura")
    if not briefing_pending:
        lines.append("   niente")
    else:
        for b in briefing_pending[:10]:
            lines.append(f"   • {b['title'][:100]}")

    return "\n".join(lines)


async def send_morning_briefing(bot: Bot, db: DB, config: Config) -> None:
    """Invia il briefing mattutino a entrambi i soci."""
    targets = []
    if config.davide_chat_id:
        targets.append(("davide", config.davide_chat_id))
    if config.ascanio_chat_id:
        targets.append(("ascanio", config.ascanio_chat_id))

    for socio, chat_id in targets:
        try:
            text = await compose_briefing(db, socio=socio)
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                disable_web_page_preview=True,
            )
            log.info("briefing inviato a %s (%s)", socio, chat_id)
        except Exception:
            log.exception("errore inviando briefing a %s (%s)", socio, chat_id)
