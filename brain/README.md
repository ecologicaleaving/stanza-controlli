# Cervello Gaia (F2b) — gira sul PC, non sul VPS

Questo è il **cervello** di Gaia conversazionale (issue #2, topologia ibrida).
Gira sul PC di Davide con l'autenticazione di Claude Code, mentre il **corpo**
(bot ingestore + dispatcher) gira nel container sul VPS.

```
tg_inbox (VPS)  ──►  brain/ (PC, Agent SDK)  ──►  tg_outbox (VPS)  ──►  dispatcher (VPS)  ──►  Telegram
```

## Come funziona

`runner.py` ogni `POLL_INTERVAL_SEC`:
1. garantisce il **tunnel SSH** verso il Postgres del VPS (`tunnel.py`);
2. legge da `el_brain.tg_inbox` i trigger nuovi (`is_to_gaia=true`, `processed=false`);
3. costruisce il contesto (ultimi `CONTEXT_MSGS` messaggi del gruppo) e genera **una** risposta
   con il **Claude Agent SDK** (`gaia.py`), usando l'identità da `ecologicaleaving/.claude/agents/gaia.md`
   e accesso **in sola lettura** a `wiki/`/`decisions/` (tool `Read`/`Grep`/`Glob`; `Bash`/`Write`/`Edit` bloccati);
4. scrive la risposta in `el_brain.tg_outbox` (`sent_at=NULL`) → la invia il dispatcher sul VPS;
5. marca i trigger `processed=true`.

All'avvio **drena il backlog**: i messaggi pendenti preesistenti vengono marcati `processed`
senza risposta, così Gaia parte "pulita" e risponde solo ai messaggi nuovi.

## Setup

```powershell
python -m venv brain\.venv
brain\.venv\Scripts\python.exe -m pip install -r brain\requirements.txt
copy brain\.env.example brain\.env   # poi compila i valori (NON committare .env)
```

## Avvio

- Manuale: `brain\start_gaia_brain.bat`
- Automatico: registrato nel **Task Scheduler** (trigger *At log on*, task `GaiaBrain`).
  Verifica: `schtasks /Query /TN GaiaBrain`

## Note

- **Auth**: usa le credenziali del CLI `claude` (Claude Code). Nessuna `ANTHROPIC_API_KEY` necessaria.
- **Sicurezza**: `.env` (segreti DB) e `.venv/` sono gitignored. Tool di scrittura/esecuzione vietati a livello SDK.
- **Log**: `brain/gaia_brain.log` (gitignored).
- Il DB del VPS è raggiunto **solo** via tunnel SSH cifrato.
