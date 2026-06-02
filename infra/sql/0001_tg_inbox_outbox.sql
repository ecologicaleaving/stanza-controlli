-- Migration 0001: tg_inbox + tg_outbox per Gaia conversazionale (issue #2 / F1)
--
-- ISTRUZIONI: questa migration NON viene eseguita automaticamente dall'agente (ADR 0012).
-- Va eseguita manualmente da Davide sul VPS, connesso al DB el_brain:
--
--   psql "$DATABASE_URL" -f infra/sql/0001_tg_inbox_outbox.sql
--
-- Pre-requisito: lo schema el_brain deve già esistere (creato dalle migration precedenti).
-- Idempotente: usa CREATE TABLE IF NOT EXISTS per sicurezza.

-- ─── tg_inbox ─────────────────────────────────────────────────────────────────
-- Ogni messaggio umano (o comunque non-bot) nel gruppo viene scritto qui.
-- È la single source of truth inbound: il cervello (gaia_runner) legge da qui,
-- mai direttamente da Telegram.

CREATE TABLE IF NOT EXISTS el_brain.tg_inbox (
  id                  bigserial PRIMARY KEY,
  tg_message_id       bigint NOT NULL,
  chat_id             bigint NOT NULL,
  socio               text,                          -- NULL se utente sconosciuto
  sender_user_id      bigint NOT NULL,
  text                text NOT NULL,
  reply_to_message_id bigint,                        -- NULL se non è una reply
  is_to_gaia          boolean NOT NULL DEFAULT false, -- calcolato a write-time (trigger policy)
  processed           boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now()
);

-- Indice parziale per il runner: legge solo le righe non ancora processate,
-- ordinate per created_at. Evita full scan su una tabella che cresce nel tempo.
CREATE INDEX IF NOT EXISTS idx_tg_inbox_unprocessed
  ON el_brain.tg_inbox (created_at)
  WHERE NOT processed;


-- ─── tg_outbox ────────────────────────────────────────────────────────────────
-- Log di ogni messaggio inviato da Gaia nel gruppo.
-- Usato per: audit, rate limiting, contabilità token.

CREATE TABLE IF NOT EXISTS el_brain.tg_outbox (
  id          bigserial PRIMARY KEY,
  chat_id     bigint NOT NULL,
  text        text NOT NULL,
  in_reply_to bigint REFERENCES el_brain.tg_inbox(id),
  model       text,        -- es. "claude-sonnet-4-6"
  tokens_in   int,
  tokens_out  int,
  sent_at     timestamptz NOT NULL DEFAULT now()
);
