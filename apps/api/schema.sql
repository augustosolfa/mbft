-- ============================================================================
-- MBFT API - Schema e Migração Base para Cloudflare D1 (SQLite)
-- ============================================================================
-- Execução local (Miniflare / Wrangler):
--   npx wrangler d1 execute mbft-d1 --local --file=apps/api/schema.sql
--
-- Execução remota (Produção Cloudflare D1):
--   npx wrangler d1 execute mbft-d1 --remote --file=apps/api/schema.sql
-- ============================================================================

-- Índice Lexical FTS5 para Busca Híbrida RRF (PMS-005 / D1RelationalDB)
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
    id UNINDEXED,
    codigo,
    artigo,
    secao,
    texto_contextualizado,
    tokenize="unicode61 remove_diacritics 1"
);

-- Tabela de Histórico e Cache de Consultas RAG
CREATE TABLE IF NOT EXISTS historico_consultas (
    id TEXT PRIMARY KEY,
    query_hash TEXT NOT NULL,
    pergunta TEXT NOT NULL,
    busca_resultados_json TEXT NOT NULL,
    prompt_completo TEXT NOT NULL,
    resposta TEXT NOT NULL,
    from_cache INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_consultas_query_hash ON historico_consultas (query_hash);
