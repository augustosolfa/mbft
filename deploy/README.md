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

# 2. Verificar o estado sem criar ou alterar recursos
uv run python -m mbft_deploy provision --status

# 3. Provisionar recursos na Cloudflare (D1, Vectorize e projeto Pages)
#    e atualizar apps/api/wrangler.jsonc
uv run python -m mbft_deploy provision

# 4. Sincronizar dados (gera fts_chunks.sql, aplica schema.sql + fts_chunks.sql no D1 e envia JSONL ao Vectorize)
uv run python -m mbft_deploy data

# Sincronizar apenas no D1 local (Miniflare) para testes locais com Wrangler
uv run python -m mbft_deploy data --local

# 5. Publicar o Worker da API (apps/api) no Cloudflare Workers
uv run python -m mbft_deploy api

# 6. Publicar o site estático (data/processed/site) no Cloudflare Pages (injetando a URL da API em config.js)
uv run python -m mbft_deploy site --api-url https://mbft-api.seu-subdominio.workers.dev

# 7. Fluxo completo de publicação (data -> api -> site)
uv run python -m mbft_deploy tudo --api-url https://mbft-api.seu-subdominio.workers.dev

# Simular qualquer comando sem executar chamadas reais ao Wrangler (--dry-run)
uv run python -m mbft_deploy tudo --dry-run
```

### Pré-requisitos e Credenciais

* As credenciais `CLOUDFLARE_API_TOKEN` e `CLOUDFLARE_ACCOUNT_ID` são carregadas automaticamente do
  `.env` da raiz por qualquer subcomando (variáveis já exportadas no shell têm precedência), dispensando
  `wrangler login` interativo.
* O subcomando `api` publica um **Python Worker** e exige as dependências já vendorizadas em
  `apps/api/python_modules/` — o bundler do Workers não resolve o `pyproject.toml` durante o upload
  (instruções de vendorização em `apps/api/README.md`).
* O projeto Cloudflare Pages é garantido pelo `provision` e também automaticamente na primeira execução de `site`/`tudo`.
* O `provision --status` é somente leitura e verifica D1, Vectorize, projeto Pages e se o Worker possui deployment publicado.
* Quando `embeddings_mbft.jsonl` excede o teto de 100 MB por upload do Vectorize, o envio é fatiado
  automaticamente em `parte_NN.jsonl` com validação prévia dos limites por vetor.

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
  - `data/processed/indexador/vectorize/parte_NN.jsonl`: Partes do NDJSON de embeddings, geradas apenas quando o arquivo excede o teto de 100 MB por upload do Cloudflare Vectorize.
  - `data/processed/site/config.js`: Atualizado com `window.MBFT_CONFIG.apiBaseUrl` quando `--api-url` (ou `MBFT_API_URL`) é informado no deploy do site.

---

## 3. Estrutura do Código-Fonte (`src/mbft_deploy/`)

- **`__main__.py`** e **`cli.py`**: Ponto de entrada da CLI (`mbft-deploy` / `python -m mbft_deploy`) com os 6 subcomandos (`export-d1`, `provision`, `data`, `api`, `site`, `tudo`).
- **`exporters.py`**: Validação de `ChunkPayload`, bloqueio de artefatos de debug, geração atômica de `fts_chunks.sql`, fatiamento do JSONL de vetores (teto de 100 MB do Vectorize) e injeção de `apiBaseUrl` em `site/config.js`.
- **`wrangler.py`**: Invocação do Cloudflare Wrangler CLI, provisionamento de D1/Vectorize com atualização automática de IDs em `apps/api/wrangler.jsonc` e publicação de Workers/Pages.

---

## 4. Verificação Pós-Deploy e Diagnóstico

```powershell
# API publicada: as tres rotas devem responder 200 (o /chat/ depende do indice)
curl.exe -s https://mbft-api.<conta>.workers.dev/health/
curl.exe -s "https://mbft-api.<conta>.workers.dev/busca/?q=pneu%20careca"
curl.exe -s -X POST -H "Content-Type: application/json" --data "@pergunta.json" https://mbft-api.<conta>.workers.dev/chat/

# Site publicado (links internos usam *.html; o Pages responde 308 e resolve para a URL sem extensao)
curl.exe -s -L -o NUL -w "%{http_code} %{url_effective}" https://mbft-site.pages.dev/chat.html
```

* **Contagem de dados no D1:** use `--json` com `--command` para receber as **linhas**; com `--file`, o
  `--json` devolve apenas o resumo da execução (`Rows read`/`Rows written`), e o campo `num_tables` da
  listagem de bancos vem vazio — não use nenhum dos dois como evidência de tabela populada.
  ```powershell
  npx wrangler d1 execute mbft-d1 --remote --json --command "SELECT COUNT(*) FROM fts_chunks"
  ```
* **Contagem de vetores:** a API da Cloudflare expõe `vectorCount` em
  `GET /accounts/<conta>/vectorize/v2/indexes/mbft-embeddings/info`. Os dois lados do índice híbrido
  (linhas do FTS5 e vetores) devem coincidir; ver a nota de coerência em PMS-010 § 3.2.
* **Logs de produção:** `npx wrangler tail --format pretty` (executado em `apps/api`) transmite as
  requisições em tempo real, incluindo `print`/`logger` do Worker — é o caminho para diagnosticar
  qualquer falha de execução sem instrumentar o código.
* **Cache de respostas:** uma resposta fica presa ao hash da pergunta, então **trocar `CF_LLM_MODEL`
  exige purgar `historico_consultas`** (ver `apps/api/README.md`).

---

## 5. Pré-requisitos de Ambiente

* **Wrangler: instalado e autenticado** (`npx wrangler whoami`), com as credenciais em `.env` (seção 1).
* **Dependências do Worker vendorizadas:** o subcomando `api` exige `apps/api/python_modules/` já gerado
  pelo `pywrangler sync` (ver `apps/api/README.md`); no Windows essa etapa roda no WSL2, com `uv` e
  `node` disponíveis.
* **No Windows com Smart App Control:** prefira `uv run python -m mbft_deploy` ao entrypoint `mbft-deploy`,
  que pode ser bloqueado pela política de controle de aplicativo.
