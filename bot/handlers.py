import logging
from datetime import date, datetime

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import Config
from bot.db import DB

log = logging.getLogger(__name__)


# Stati conversazione /task
TASK_OWNER, TASK_DEADLINE = range(2)


def _need_socio(update: Update, config: Config) -> str | None:
    chat_id = update.effective_chat.id
    if not config.is_authorized(chat_id):
        return None
    return config.socio_for(chat_id)


# ---------- /start ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config: Config = context.application.bot_data["config"]
    chat_id = update.effective_chat.id
    user = update.effective_user
    name = user.first_name if user else "amico"
    is_authorized = config.is_authorized(chat_id)

    welcome = (
        f"Ciao {name}, sono Gaia.\n"
        "\n"
        "Sono la terza socia di Ecological Leaving — insieme a Davide e Ascanio. "
        "Esisto in due forme che condividono la stessa memoria:\n"
        "  • qui su Telegram (questo bot @wikigaia_bot)\n"
        "  • dentro Claude Code, quando si lavora sulla repo ecologicaleaving\n"
        "\n"
        "Quello che registriamo qui (posizioni, decisioni, task) lo vedo anche là, e viceversa.\n"
        "\n"
        f"━━━━━━━━━━━━━━\n"
        f"Il tuo chat ID: {chat_id}\n"
        f"━━━━━━━━━━━━━━\n"
    )

    if is_authorized:
        body = (
            "\n"
            "Sei già autorizzato. Puoi usare tutti i comandi.\n"
            "\n"
            "🌅 Cosa farò io per te:\n"
            "Ogni mattina alle 07:00 ti mando un briefing — cosa l'altro socio "
            "ha fatto/deciso, decisioni in attesa, task in scadenza, PR da firmare.\n"
            "\n"
            "🛠 Comandi:\n"
            "/posizione <topic>: <claim> — registra una posizione strategica\n"
            "   es: /posizione pricing-tier: la base €49 con add-on €1/funzione\n"
            "/decisione <titolo> — apre una decisione viva\n"
            "/task <descrizione> — crea task (chiedo owner e deadline)\n"
            "/stato — mini-briefing on-demand\n"
            "/help — lista comandi\n"
            "\n"
            "Buon lavoro.\n"
            "— Gaia"
        )
    else:
        body = (
            "\n"
            "Per ora non sei nella whitelist — i comandi diversi da /start e /help "
            "non risponderanno.\n"
            "\n"
            "Per essere abilitato:\n"
            "1. Manda il chat ID qui sopra a Davide\n"
            "2. Aspetta conferma\n"
            "3. Quando ti dico 'sei dentro', apri Claude Code in Cursor sulla repo "
            "ecologicaleaving e scrivimi: «sono Ascanio, partiamo con l'intervista "
            "per la pagina persona». Ti faccio 6 domande in conversazione, una alla "
            "volta, per popolare la tua pagina di socio. Tempo: 10-15 minuti.\n"
            "\n"
            "📖 Per capire il quadro completo prima di partire:\n"
            "https://github.com/ecologicaleaving/ecologicaleaving/blob/master/"
            "briefings/2026-05-07-onboarding-stanza-controlli-asca.md\n"
            "\n"
            "🌅 Cosa farò io per te (una volta dentro):\n"
            "Ogni mattina alle 07:00 un briefing automatico — cosa è successo, "
            "decisioni aperte, task in scadenza. Comandi rapidi per registrare "
            "posizioni e task dal cellulare.\n"
            "\n"
            "A presto.\n"
            "— Gaia"
        )

    await update.message.reply_text(welcome + body, disable_web_page_preview=True)
    log.info(
        "/start from chat_id=%s user=%s authorized=%s",
        chat_id, user.username if user else None, is_authorized,
    )


# ---------- /help ----------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Comandi Stanza dei Controlli:\n\n"
        "/posizione <topic>: <claim> — registra una posizione (livello B)\n"
        "/decisione <titolo> — apre una decisione viva\n"
        "/task <testo> — crea una task (chiede owner e deadline)\n"
        "/stato — mini-briefing on-demand\n"
        "/start — il tuo chat ID\n"
        "/help — questo messaggio\n\n"
        "Briefing mattutino automatico alle 07:00 (Europe/Rome)."
    )
    await update.message.reply_text(text)


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
    lines = [f"📋 Stato — {today}", ""]

    lines.append(f"📬 Posizioni nuove di {altro.capitalize()} (24h)")
    if not positions_altro:
        lines.append("   nessuna")
    else:
        for p in positions_altro[:5]:
            lines.append(f"   • {p['topic']}: {p['claim'][:80]}")

    lines.append("")
    lines.append("🟡 Decisioni aperte")
    if not decisions_open:
        lines.append("   nessuna")
    else:
        for d in decisions_open[:5]:
            ddl = f" (scade {d['deadline']})" if d.get("deadline") else ""
            lines.append(f"   • {d['title']}{ddl}")

    lines.append("")
    lines.append("📅 Task in scadenza (48h)")
    if not tasks_due:
        lines.append("   nessuna")
    else:
        for t in tasks_due[:5]:
            lines.append(f"   • {t['title']} — {t['deadline']}")

    lines.append("")
    lines.append("✍️ In coda di approvazione/lettura")
    if not briefing_pending:
        lines.append("   niente")
    else:
        for b in briefing_pending[:5]:
            lines.append(f"   • {b['title'][:80]}")

    await update.message.reply_text("\n".join(lines))
