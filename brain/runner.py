"""Runner del cervello Gaia (gira sul PC, auto-start).

Loop:
  1. garantisce il tunnel SSH al DB
  2. legge da tg_inbox i trigger nuovi (is_to_gaia=true, processed=false)
  3. per ogni batch costruisce il contesto e genera UNA risposta con l'Agent SDK
  4. scrive la risposta in tg_outbox (sent_at=NULL → la invia il dispatcher VPS)
  5. marca processed i trigger gestiti

All'avvio drena il backlog: i pending preesistenti vengono marcati processed
senza risposta, così Gaia parte "pulita" e risponde solo ai messaggi nuovi.
"""

import asyncio
import logging
import socket
import sys
from pathlib import Path

# Windows: evita crash di logging/print su testo unicode (emoji, accenti)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import Config
from db import BrainDB
from gaia import build_prompt, generate_reply, load_system_prompt
from tools import TOOL_NAMES, build_gaia_server
from tunnel import SSHTunnel

# Log su file (per l'avvio headless via Task Scheduler) + stream se in console.
_LOG_FILE = Path(__file__).parent / "gaia_brain.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("gaia.runner")

# Lock single-instance: bind esclusivo su una porta locale. Se occupata,
# c'è già un cervello attivo (es. auto-start + avvio manuale) → si esce.
_LOCK_PORT = 47654


def acquire_single_instance_lock() -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", _LOCK_PORT))
        s.listen(1)
    except OSError:
        log.error("un'altra istanza del cervello è già attiva — esco")
        sys.exit(0)
    return s


async def process_once(cfg: Config, db: BrainDB, system_prompt: str, mcp_server) -> None:
    triggers = await db.fetch_new_triggers()
    if not triggers:
        return

    log.info("%d trigger nuovi", len(triggers))
    context = await db.fetch_recent_context(cfg.group_chat_id, cfg.context_msgs)
    prompt = build_prompt(context)

    reply = await generate_reply(
        system_prompt=system_prompt,
        prompt=prompt,
        el_repo_path=cfg.el_repo_path,
        model=cfg.model,
        mcp_server=mcp_server,
        extra_tools=TOOL_NAMES,
    )

    handled_ids = [t["id"] for t in triggers]
    if not reply:
        log.warning("risposta vuota — marco processed senza inviare")
        await db.mark_processed(handled_ids)
        return

    last_trigger_id = triggers[-1]["id"]
    out_id = await db.insert_outbox(
        chat_id=cfg.group_chat_id,
        text=reply,
        in_reply_to=last_trigger_id,
        model=cfg.model,
    )
    await db.mark_processed(handled_ids)
    log.info("risposta in outbox id=%s (%d caratteri)", out_id, len(reply))


async def main() -> None:
    _lock = acquire_single_instance_lock()  # noqa: F841 — tenuto vivo per tutta la sessione
    cfg = Config.load()
    tunnel = SSHTunnel(cfg)
    db = BrainDB(cfg)
    system_prompt = load_system_prompt(cfg.el_repo_path)

    tunnel.ensure()
    await db.connect()
    gaia_server = build_gaia_server(db)
    log.info("cervello Gaia avviato — DB connesso via tunnel, tool Stanza dei Controlli pronti")

    drained = await db.drain_backlog()
    if drained:
        log.info("backlog drenato: %d messaggi marcati processed (nessuna risposta)", drained)

    try:
        while True:
            try:
                tunnel.ensure()
                await process_once(cfg, db, system_prompt, gaia_server)
            except Exception:
                log.exception("errore nel ciclo — continuo")
            await asyncio.sleep(cfg.poll_interval_sec)
    finally:
        await db.close()
        tunnel.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
