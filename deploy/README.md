# Exportadores e Automação de Deploy Cloudflare (`mbft-deploy`)

Módulo responsável pela exportação de artefatos específicos para a nuvem (geração do dump SQL FTS5 `fts_chunks.sql` a partir dos chunks canônicos do indexador), provisionamento de recursos e automação de publicação na **Cloudflare** (D1, Vectorize, KV, Workers e Pages).

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação completa de arquitetura, motivação do desacoplamento das pipelines e trade-offs, consulte o Documento de Design **PMS-010** em `docs/PMS-010 - Exportacao e Deploy na Cloudflare.md`.
> Para os contratos canônicos consumidos por este módulo (`ChunkPayload`), consulte a **PMS-009** (`pipelines/core/README.md`).

---

## 1. Uso da Linha de Comando (`uv run mbft-deploy`)

Execute os comandos a partir da raiz do monorepo via `uv run mbft-deploy` (ou `uv run python -m mbft_deploy` no Windows com Smart App Control):

```powershell
# 1. Exportar apenas o dump SQL FTS5 para o D1 (gera data/processed/deploy/fts_chunks.sql)
uv run python -m mbft_deploy export-d1

# 2. Provisionar recursos na Cloudflare (D1, Vectorize 1024d cosine e KV) e atualizar apps/api/wrangler.jsonc
uv run python -m mbft_deploy provision

# 3. Sincronizar dados (gera fts_chunks.sql, aplica schema.sql + fts_chunks.sql no D1 e envia JSONL ao Vectorize)
uv run python -m mbft_deploy data

# Sincronizar apenas no D1 local (Miniflare) para testes locais com Wrangler
uv run python -m mbft_deploy data --local

# 4. Publicar o Worker da API (apps/api) no Cloudflare Workers
uv run python -m mbft_deploy api

# 5. Publicar o site estático (data/processed/site) no Cloudflare Pages (injetando a URL da API em config.js)
uv run python -m mbft_deploy site --api-url https://mbft-api.seu-subdominio.workers.dev

# 6. Fluxo completo de publicação (data -> api -> site)
uv run python -m mbft_deploy tudo --api-url https://mbft-api.seu-subdominio.workers.dev

# Simular qualquer comando sem executar chamadas reais ao Wrangler (--dry-run)
uv run python -m mbft_deploy tudo --dry-run
```

### Execução de Testes

```powershell
uv run pytest deploy/tests
```

---

## 2. Entradas e Saídas

- **Entradas**:
  - `data/processed/indexador/embeddings_mbft.jsonl`: Artefato NDJSON canônico validado contra `ChunkPayload` (`mbft-core`).
  - `apps/api/schema.sql` e `apps/api/wrangler.jsonc`: DDL base do Cloudflare D1 e manifesto do Worker.
  - `data/processed/site/`: Diretório estático gerado pelo `mbft-ssg` (PMS-007).
- **Saídas**:
  - `data/processed/deploy/fts_chunks.sql`: Script SQL idempotente (`DELETE FROM fts_chunks;` + `INSERT`s em lote) pronto para execução via `wrangler d1 execute`.
  - `data/processed/site/config.js`: Atualizado com `window.MBFT_CONFIG.apiBaseUrl` quando `--api-url` (ou `MBFT_API_URL`) é informado no deploy do site.

---

## 3. Estrutura do Código-Fonte (`src/mbft_deploy/`)

- **`__main__.py`** e **`cli.py`**: Ponto de entrada da CLI (`mbft-deploy` / `python -m mbft_deploy`) com os 6 subcomandos (`export-d1`, `provision`, `data`, `api`, `site`, `tudo`).
- **`exporters.py`**: Validação de `ChunkPayload`, bloqueio de artefatos de debug, geração atômica de `fts_chunks.sql` e injeção de `apiBaseUrl` em `site/config.js`.
- **`wrangler.py`**: Invocação do Cloudflare Wrangler CLI, provisionamento de D1/Vectorize/KV com atualização automática de IDs em `apps/api/wrangler.jsonc` e publicação de Workers/Pages.
