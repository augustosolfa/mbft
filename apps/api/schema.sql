-- ============================================================================
-- MBFT API - Schema e Migração Base para Cloudflare D1 (SQLite)
-- ============================================================================
-- Execução local (Miniflare / Wrangler):
--   npx wrangler d1 execute mbft-d1 --local --file=apps/api/schema.sql
--
-- Execução remota (Produção Cloudflare D1):
--   npx wrangler d1 execute mbft-d1 --remote --file=apps/api/schema.sql
-- ============================================================================

-- 1. Controle Transacional da Fila Indiana Global (PMS-008 / D1FilaRepository)
CREATE TABLE IF NOT EXISTS fila_global (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_available DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO fila_global (id) VALUES (1);

-- 2. Índice Lexical FTS5 para Busca Híbrida RRF (PMS-005 / D1RelationalDB)
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
    id UNINDEXED,
    codigo,
    artigo,
    secao,
    texto_contextualizado,
    tokenize="unicode61 remove_diacritics 1"
);
