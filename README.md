# Stanza dei Controlli — bot Telegram

Bot Telegram per la **Stanza dei Controlli** di Ecological Leaving ([ADR 0008](https://github.com/ecologicaleaving/ecologicaleaving/blob/master/decisions/0008-stanza-controlli-posizioni-briefing.md)).

Tre cose:
1. **Briefing mattutino asincrono** alle 7:00 Europe/Rome a Davide e Ascanio
2. **Capture mobile** di posizioni, decisioni aperte, task tramite comandi Telegram
3. **Mini-briefing on-demand** via `/stato`

DB: schema `el_brain` su `supabase_db_maestro-test` (VPS 46.225.60.101, container Docker).

---

## Comandi

| Comando | Auth | Effetto |
|---|---|---|
| `/start` | aperto | Risponde con il chat ID + saluto. Usato per onboarding |
| `/help` | aperto | Lista comandi |
| `/posizione <topic>: <claim>` | autorizzato | Registra posizione (livello B: opinion o fact) |
| `/decisione <titolo>` | autorizzato | Apre decisione viva (PRE-ADR) |
| `/task <testo>` | autorizzato | Crea task (chiede owner+deadline in follow-up) |
| `/stato` | autorizzato | Mini-briefing on-demand |

**Auth**: chat ID nella whitelist `AUTHORIZED_CHAT_IDS`. Mappatura `chat_id → socio` via `DAVIDE_CHAT_ID` e `ASCANIO_CHAT_ID`.

---

## Setup locale (sviluppo)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env             # poi compila i valori
python -m bot.main
```

## Deploy VPS

Il bot gira come container Docker nella stessa network di Supabase, in modo da raggiungere `supabase_db_maestro-test` per nome container.

```bash
# Sul VPS
cd /opt/stanza-controlli
git pull
docker compose up -d --build
docker compose logs -f bot
```

---

## Variabili d'ambiente (`.env`)

Vedi `.env.example`. In sintesi:

- `BOT_TOKEN` — token bot da @BotFather
- `DATABASE_URL` — `postgres://postgres:PASSWORD@supabase_db_maestro-test:5432/postgres`
- `DAVIDE_CHAT_ID`, `ASCANIO_CHAT_ID` — chat ID Telegram dei due soci
- `BRIEFING_HOUR` — ora invio briefing mattutino (default 8)
- `BRIEFING_TIMEZONE` — timezone (default Europe/Rome)
- `LOG_LEVEL` — INFO/DEBUG (default INFO)
