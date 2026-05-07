import logging
from datetime import date, datetime, timedelta

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import Config
from bot.db import DB

log = logging.getLogger(__name__)


# Stati conversazione /task
TASK_OWNER, TASK_DEADLINE = range(2)


def _need_socio(update: Update, config: Config) -> str | None:
    """Restituisce socio o None se non autorizzato (e risponde all'utente)."""
    chat_id = update.effective_chat.id
    if not config.is_authorized(chat_id):
        return None
    return config.socio_for(chat_id)


# ---------- /start ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = update.effective_user
    name = user.first_name if user else "amico"
    text = (
        f"Ciao *{name}*\\!\n\n"
        f"Il tuo chat ID è `{chat_id}`\\.\n\n"
        "Se sei Davide o Ascanio, gira questo numero a chi sta facendo il setup\\.\n"
        "Sennò, ciao\\."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    log.info("/start from chat_id=%s user=%s", chat_id, user.username if user else None)


# ---------- /help ----------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "*Comandi Stanza dei Controlli*\n\n"
        "`/posizione <topic>: <claim>` — registra una posizione (livello B)\n"
        "`/decisione <titolo>` — apre una decisione viva\n"
        "`/task <testo>` — crea una task \\(chiede owner e deadline\\)\n"
        "`/stato` — mini\\-briefing on\\-demand\n"
        "`/start` — il tuo chat ID\n"
        "`/help` — questo messaggio\n\n"
        "Briefing mattutino automatico alle 07:00 \\(Europe/Rome\\)\\."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)


# ---------- /posizione ----------

async def cmd_posizione(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.application.bot_data["config"]
    db: DB = context.application.bot_data["db"]

    socio = _need_socio(update, config)
    if not socio:
        await update.message.reply_text("Non sei autorizzato.")
        return

    raw = update.message.text.split(" ", 1)
    if len(raw) < 2 or ":" not in raw[1]:
        await update.message.reply_text(
            "Formato: /posizione <topic>: <claim>\n"
            "Esempio: /posizione pricing-tier: tier base €49/mese"
        )
        return

    topic_part, claim_part = raw[1].split(":", 1)
    topic = topic_part.strip()
    claim = claim_part.strip()
    if not topic or not claim:
        await update.message.reply_text("Topic e claim non possono essere vuoti.")
        return

    # Inferenza kind: opinion vs fact (heuristica leggera)
    lower = claim.lower()
    opinion_markers = ("penso", "secondo me", "credo", "preferisco", "dovrebbe", "non dobbiamo", "dobbiamo")
    kind = "opinion" if any(m in lower for m in opinion_markers) else "fact"

    pos_id = await db.insert_position(
        socio=socio, topic=topic, claim=claim, kind=kind, source="telegram",
    )
    await update.message.reply_text(
        f"✅ Posizione registrata\n"
        f"   topic: {topic}\n"
        f"   kind:  {kind}\n"
        f"   id:    {pos_id[:8]}…"
    )
    log.info("position %s by %s topic=%s", pos_id, socio, topic)


# ---------- /decisione ----------

async def cmd_decisione(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.application.bot_data["config"]
    db: DB = context.application.bot_data["db"]

    socio = _need_socio(update, config)
    if not socio:
        await update.message.reply_text("Non sei autorizzato.")
        return

    raw = update.message.text.split(" ", 1)
    if len(raw) < 2 or not raw[1].strip():
        await update.message.reply_text("Formato: /decisione <titolo>")
        return

    title = raw[1].strip()
    dec_id = await db.insert_decision_open(title=title)
    await update.message.reply_text(
        f"✅ Decisione aperta\n"
        f"   titolo: {title}\n"
        f"   id:     {dec_id[:8]}…\n\n"
        f"Le posizioni vostre su questa decisione si dichiarano con /posizione."
    )
    log.info("decision_open %s by %s title=%s", dec_id, socio, title)


# ---------- /task (conversation) ----------

async def cmd_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config: Config = context.application.bot_data["config"]
    socio = _need_socio(update, config)
    if not socio:
        await update.message.reply_text("Non sei autorizzato.")
        return ConversationHandler.END

    raw = update.message.text.split(" ", 1)
    if len(raw) < 2 or not raw[1].strip():
        await update.message.reply_text("Formato: /task <descrizione>")
        return ConversationHandler.END

    context.user_data["task_title"] = raw[1].strip()
    await update.message.reply_text(
        "Owner? Rispondi: davide / ascanio / both / annulla"
    )
    return TASK_OWNER


async def task_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().lower()
    if text == "annulla":
        await update.message.reply_text("Ok, annullato.")
        return ConversationHandler.END
    if text not in {"davide", "ascanio", "both"}:
        await update.message.reply_text("Owner non valido. Davide / Ascanio / both / annulla")
        return TASK_OWNER

    context.user_data["task_owner"] = text
    await update.message.reply_text(
        "Deadline? Formato YYYY-MM-DD oppure 'no' per nessuna. ('annulla' per uscire)"
    )
    return TASK_DEADLINE


async def task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db: DB = context.application.bot_data["db"]
    text = update.message.text.strip().lower()

    if text == "annulla":
        await update.message.reply_text("Ok, annullato.")
        return ConversationHandler.END

    deadline: str | None = None
    if text != "no":
        try:
            datetime.strptime(text, "%Y-%m-%d")
            deadline = text
        except ValueError:
            await update.message.reply_text("Formato non valido. YYYY-MM-DD oppure 'no'.")
            return TASK_DEADLINE

    title = context.user_data["task_title"]
    owner = context.user_data["task_owner"]
    task_id = await db.insert_task(title=title, owner=owner, deadline=deadline)

    deadline_str = f" entro {deadline}" if deadline else ""
    await update.message.reply_text(
        f"✅ Task creata\n"
        f"   {title}\n"
        f"   → {owner}{deadline_str}\n"
        f"   id: {task_id[:8]}…"
    )
    return ConversationHandler.END


async def task_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Ok, annullato.")
    return ConversationHandler.END


# ---------- /stato ----------

async def cmd_stato(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.application.bot_data["config"]
    db: DB = context.application.bot_data["db"]

    socio = _need_socio(update, config)
    if not socio:
        await update.message.reply_text("Non sei autorizzato.")
        return

    altro = "ascanio" if socio == "davide" else "davide"

    positions_altro = await db.positions_since(hours=24, exclude_socio=socio)
    decisions_open = await db.decisions_open_active()
    tasks_due = await db.tasks_due_within(days=2, owner=socio)
    briefing_pending = await db.briefing_items_pending(socio=socio)

    today = date.today().isoformat()
    lines = [f"📋 *Stato — {today}*", ""]

    lines.append(f"📬 *Posizioni nuove di {altro.capitalize()} \\(24h\\)*")
    if not positions_altro:
        lines.append("  _nessuna_")
    else:
        for p in positions_altro[:5]:
            lines.append(f"  • {_md(p['topic'])}: {_md(p['claim'])[:80]}")

    lines.append("")
    lines.append(f"🟡 *Decisioni aperte*")
    if not decisions_open:
        lines.append("  _nessuna_")
    else:
        for d in decisions_open[:5]:
            ddl = f" \\(scade {d['deadline']}\\)" if d.get("deadline") else ""
            lines.append(f"  • {_md(d['title'])}{ddl}")

    lines.append("")
    lines.append(f"📅 *Task in scadenza \\(48h\\)*")
    if not tasks_due:
        lines.append("  _nessuna_")
    else:
        for t in tasks_due[:5]:
            lines.append(f"  • {_md(t['title'])} \\— {t['deadline']}")

    lines.append("")
    lines.append("✍️ *In coda di approvazione/lettura*")
    if not briefing_pending:
        lines.append("  _niente_")
    else:
        for b in briefing_pending[:5]:
            lines.append(f"  • {_md(b['title'])[:80]}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN_V2)


def _md(s: str) -> str:
    """Escape MarkdownV2 special chars."""
    if s is None:
        return ""
    specials = r"_*[]()~`>#+-=|{}.!"
    return "".join("\\" + c if c in specials else c for c in str(s))
