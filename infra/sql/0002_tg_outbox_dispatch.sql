-- Migration 0002: tg_outbox — rende sent_at nullable per il pattern dispatcher (issue #2 / F2a)
--
-- ISTRUZIONI: questa migration NON viene eseguita automaticamente dall'agente (ADR 0012).
-- Va eseguita manualmente da Davide/Claudio sul VPS, connesso al DB el_brain:
--
--   psql "$DATABASE_URL" -f infra/sql/0002_tg_outbox_dispatch.sql
--
-- Pre-requisito: migration 0001 già applicata (tabella el_brain.tg_outbox esistente).
-- La tabella è vuota in produzione — nessun backfill necessario.
-- Idempotente: le ALTER TABLE su colonne già nello stato corretto sono no-op in PostgreSQL.
--
-- Perché: con la topologia ibrida PC↔VPS (ADR 0012), il cervello (brain/ sul PC) scrive
-- righe in tg_outbox con sent_at = NULL. Il dispatcher sul VPS le raccoglie, le invia
-- a Telegram e valorizza sent_at = now(). Contratto: sent_at IS NULL ↔ da inviare.

-- Rende sent_at nullable (era NOT NULL DEFAULT now())
ALTER TABLE el_brain.tg_outbox ALTER COLUMN sent_at DROP NOT NULL;

-- Rimuove il DEFAULT now() — il cervello deve inserire esplicitamente NULL
ALTER TABLE el_brain.tg_outbox ALTER COLUMN sent_at DROP DEFAULT;

-- Indice parziale per il polling del dispatcher: legge solo le righe pending,
-- evita full scan su una tabella che può crescere nel tempo.
CREATE INDEX IF NOT EXISTS idx_tg_outbox_pending
  ON el_brain.tg_outbox (id)
  WHERE sent_at IS NULL;
