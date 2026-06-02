"""Cervello Gaia via Claude Agent SDK.

Usa la STESSA identità delle sessioni Claude Code: carica `.claude/agents/gaia.md`
dalla repo Ecological Leaving e gira con cwd su quella repo, così può consultare
wiki/ e decisions/ in sola lettura. Niente Bash/Write/Edit: guardia esplicita.
"""

import logging
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

log = logging.getLogger("gaia.brain")

# Sola lettura: questi soli sono ammessi...
READ_ONLY_TOOLS = ["Read", "Grep", "Glob"]
# ...e questi esplicitamente vietati (paletti ADR 0014 §7).
BLOCKED_TOOLS = [
    "Bash", "Write", "Edit", "NotebookEdit", "MultiEdit",
    "WebFetch", "WebSearch", "Task", "KillShell", "BashOutput",
]

TELEGRAM_GUIDANCE = """

## Contesto operativo: sei su Telegram (gruppo Ecological Leaving)

Stai rispondendo nel gruppo Telegram con Davide e Ascanio, non in una sessione di lavoro.
- Rispondi BREVE: 1-6 righe, tono diretto, niente preamboli, niente markdown pesante.
- Una cosa alla volta. Se serve una domanda, una sola.
- Puoi consultare wiki/ e decisions/ della repo (sola lettura) se ti serve un fatto preciso.
- NON puoi modificare file, fare commit/merge, eseguire comandi: sei in sola lettura.
- Se non sai o manca contesto, dillo. Non inventare.
- Rispondi SOLO con il testo del messaggio da inviare, nient'altro.
"""


def load_system_prompt(el_repo_path: str) -> str:
    """Identità Gaia da gaia.md (senza frontmatter) + guida Telegram."""
    gaia_md = Path(el_repo_path) / ".claude" / "agents" / "gaia.md"
    body = ""
    if gaia_md.exists():
        raw = gaia_md.read_text(encoding="utf-8")
        # togli il frontmatter YAML iniziale --- ... ---
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            body = parts[2] if len(parts) >= 3 else raw
        else:
            body = raw
    else:
        log.warning("gaia.md non trovato in %s — uso identità minima", gaia_md)
        body = "Sei Gaia, terza socia di Ecological Leaving. Diretta, niente fronzoli."
    return body.strip() + TELEGRAM_GUIDANCE


def build_prompt(context_msgs: list[dict]) -> str:
    """Trasforma gli ultimi messaggi del gruppo in un prompt leggibile."""
    lines = ["Conversazione recente nel gruppo:\n"]
    for m in context_msgs:
        who = (m.get("socio") or "sconosciuto").capitalize()
        lines.append(f"{who}: {m['text']}")
    lines.append("\nL'ultimo messaggio ti interpella. Rispondi nel gruppo.")
    return "\n".join(lines)


async def generate_reply(
    *, system_prompt: str, prompt: str, el_repo_path: str, model: str
) -> str:
    opts = ClaudeAgentOptions(
        system_prompt=system_prompt,
        cwd=el_repo_path,
        allowed_tools=READ_ONLY_TOOLS,
        disallowed_tools=BLOCKED_TOOLS,
        permission_mode="default",
        model=model,
        max_turns=6,
    )
    chunks: list[str] = []
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
    return "\n".join(c.strip() for c in chunks if c.strip()).strip()
