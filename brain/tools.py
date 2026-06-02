"""Tool SDK per Gaia: lettura stato (briefing) e registrazione su el_brain.

Scrittura consentita SOLO su queste tabelle (paletti ADR 0014 §7: registrare
posizioni/task/decisioni è tra i "PUÒ"). Nessun accesso a filesystem o canone.
"""

import logging

from claude_agent_sdk import create_sdk_mcp_server, tool

from db import BrainDB

log = logging.getLogger("gaia.tools")

# DB condiviso (stesso pool/loop del runner), impostato da build_gaia_server().
_db: BrainDB | None = None

_OPINION_MARKERS = ("penso", "secondo me", "credo", "preferisco", "dovrebbe", "non dobbiamo", "dobbiamo")
_VALID_SOCI = {"davide", "ascanio"}
_VALID_OWNERS = {"davide", "ascanio", "both"}


def _text(s: str) -> dict:
    return {"content": [{"type": "text", "text": s}]}


@tool("stato", "Restituisce il briefing della Stanza dei Controlli: posizioni recenti, decisioni aperte, task in scadenza.", {})
async def stato(_args: dict) -> dict:
    positions = await _db.positions_since(hours=48)
    decisions = await _db.decisions_open_active()
    tasks = await _db.tasks_due_within(days=7)

    out = ["STATO STANZA DEI CONTROLLI", ""]
    out.append(f"Posizioni (48h): {len(positions)}")
    for p in positions[:8]:
        out.append(f"  - [{p['socio']}] {p['topic']}: {p['claim'][:100]}")
    out.append(f"Decisioni aperte: {len(decisions)}")
    for d in decisions[:8]:
        ddl = f" (scade {d['deadline']})" if d.get("deadline") else ""
        out.append(f"  - {d['title']}{ddl}")
    out.append(f"Task in scadenza (7g): {len(tasks)}")
    for t in tasks[:8]:
        out.append(f"  - {t['title']} -> {t['owner']} ({t['deadline']})")
    return _text("\n".join(out))


@tool("registra_posizione", "Registra una posizione strategica di un socio. socio: davide|ascanio.", {"socio": str, "topic": str, "claim": str})
async def registra_posizione(args: dict) -> dict:
    socio = (args.get("socio") or "").strip().lower()
    topic = (args.get("topic") or "").strip()
    claim = (args.get("claim") or "").strip()
    if socio not in _VALID_SOCI:
        return _text(f"Errore: socio '{socio}' non valido (davide|ascanio).")
    if not topic or not claim:
        return _text("Errore: topic e claim obbligatori.")
    kind = "opinion" if any(m in claim.lower() for m in _OPINION_MARKERS) else "fact"
    pos_id = await _db.insert_position(socio=socio, topic=topic, claim=claim, kind=kind)
    log.info("registrata posizione %s socio=%s topic=%s", pos_id, socio, topic)
    return _text(f"Posizione registrata (id {pos_id[:8]}, kind {kind}).")


@tool("registra_task", "Crea una task. owner: davide|ascanio|both. deadline opzionale formato YYYY-MM-DD.", {"title": str, "owner": str, "deadline": str})
async def registra_task(args: dict) -> dict:
    title = (args.get("title") or "").strip()
    owner = (args.get("owner") or "").strip().lower()
    deadline = (args.get("deadline") or "").strip() or None
    if not title:
        return _text("Errore: title obbligatorio.")
    if owner not in _VALID_OWNERS:
        return _text(f"Errore: owner '{owner}' non valido (davide|ascanio|both).")
    task_id = await _db.insert_task(title=title, owner=owner, deadline=deadline)
    log.info("registrata task %s owner=%s", task_id, owner)
    ddl = f" entro {deadline}" if deadline else ""
    return _text(f"Task creata (id {task_id[:8]}): {title} -> {owner}{ddl}.")


@tool("apri_decisione", "Apre una decisione viva (da dibattere). Le posizioni si registrano a parte.", {"title": str})
async def apri_decisione(args: dict) -> dict:
    title = (args.get("title") or "").strip()
    if not title:
        return _text("Errore: title obbligatorio.")
    dec_id = await _db.insert_decision_open(title=title)
    log.info("aperta decisione %s", dec_id)
    return _text(f"Decisione aperta (id {dec_id[:8]}): {title}.")


# Nomi completi dei tool come li vede l'SDK (mcp__<server>__<tool>).
TOOL_NAMES = [
    "mcp__gaia__stato",
    "mcp__gaia__registra_posizione",
    "mcp__gaia__registra_task",
    "mcp__gaia__apri_decisione",
]


def build_gaia_server(db: BrainDB):
    """Crea il server MCP in-process con i tool, legandolo al DB del runner."""
    global _db
    _db = db
    return create_sdk_mcp_server(
        name="gaia",
        version="1.0.0",
        tools=[stato, registra_posizione, registra_task, apri_decisione],
    )
