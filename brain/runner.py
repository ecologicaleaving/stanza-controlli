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


async def process_once(cfg: Config, db: BrainDB, system_prompt: str) -> None:
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
    cfg = Config.load()
    tunnel = SSHTunnel(cfg)
    db = BrainDB(cfg)
    system_prompt = load_system_prompt(cfg.el_repo_path)

    tunnel.ensure()
    await db.connect()
    log.info("cervello Gaia avviato — DB connesso via tunnel")

    drained = await db.drain_backlog()
    if drained:
        log.info("backlog drenato: %d messaggi marcati processed (nessuna risposta)", drained)

    try:
        while True:
            try:
                tunnel.ensure()
                await process_once(cfg, db, system_prompt)
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
