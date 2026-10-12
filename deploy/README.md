# Exportadores e Automação de Deploy Cloudflare (`mbft-deploy`)

Módulo responsável pela exportação de artefatos específicos para a nuvem (geração do dump SQL FTS5 `fts_chunks.sql` a partir dos chunks canônicos do indexador), provisionamento de recursos e automação de publicação na **Cloudflare** (D1, Vectorize e o Worker único `mbft` com Static Assets).

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

# 3. Provisionar recursos na Cloudflare (D1 e Vectorize)
#    e atualizar apps/api/wrangler.jsonc
uv run python -m mbft_deploy provision

# 4. Sincronizar dados (somente recursos alterados; primeira execução faz carga completa)
uv run python -m mbft_deploy data

# Forçar a sincronização completa de D1 e Vectorize
uv run python -m mbft_deploy data --force

# Sincronizar apenas no D1 local (Miniflare) para testes locais com Wrangler
uv run python -m mbft_deploy data --local

# 5. Publicar o Worker único `mbft` (FastAPI + assets de data/processed/site) no Cloudflare Workers.
#    Requer o SSG já compilado (`uv run mbft pipeline ssg`).
uv run python -m mbft_deploy api

# Configurar também o Custom Domain (precede MBFT_HOSTNAME do .env)
uv run python -m mbft_deploy api --hostname mbft.seu-dominio.com

# 6. Fluxo completo de publicação (data -> api)
uv run python -m mbft_deploy tudo

# Simular qualquer comando sem executar chamadas reais ao Wrangler (--dry-run)
uv run python -m mbft_deploy tudo --dry-run
```

### Pré-requisitos e Credenciais

* As credenciais `CLOUDFLARE_API_TOKEN` e `CLOUDFLARE_ACCOUNT_ID` são carregadas automaticamente do
  `.env` da raiz por qualquer subcomando (variáveis já exportadas no shell têm precedência), dispensando
  `wrangler login` interativo.
* `MBFT_HOSTNAME` (opcional, no mesmo `.env`) define o hostname de produção do Worker único. O deploy
  resolve o alvo pela precedência `--hostname` > `MBFT_HOSTNAME` > nenhum. Havendo hostname, um
  Custom Domain para `<hostname>` é declarado no manifesto do Wrangler e o `workers_dev` é
  **desativado**; sem hostname, o Worker permanece acessível apenas em
  `<worker>.<conta>.workers.dev`.
* O subcomando `api` publica um **Python Worker** com Static Assets: exige as dependências já
  vendorizadas em `apps/api/python_modules/` **e** o diretório `data/processed/site/` compilado
  (`uv run mbft pipeline ssg`). O bundler do Workers não resolve o `pyproject.toml` durante o upload
  (instruções de vendorização em `apps/api/README.md`).
* O `provision --status` é somente leitura e verifica D1, Vectorize e se o Worker possui deployment publicado.
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
  - `deploy/migrations/deploy_manifest.sql`: Migração própria e idempotente da tabela de controle do deploy.
  - `data/processed/site/`: Diretório estático gerado pelo `mbft-ssg` (PMS-007).
- **Saídas**:
  - `data/processed/deploy/fts_chunks.sql`: Script SQL idempotente (`DELETE FROM fts_chunks;` + `INSERT`s em lote) pronto para execução via `wrangler d1 execute`.
  - `data/processed/indexador/vectorize/parte_NN.jsonl`: Partes do NDJSON de embeddings, geradas apenas quando o arquivo excede o teto de 100 MB por upload do Cloudflare Vectorize.
  - Worker único `mbft` publicado com a API FastAPI e os assets de `data/processed/site/` (incluindo `404.html`); o `config.js` permanece neutro (`apiBaseUrl: ""`), pois o frontend passa a usar a mesma origem sob o prefixo `/api`.

---

## 3. Estrutura do Código-Fonte (`src/mbft_deploy/`)

- **`__main__.py`** e **`cli.py`**: Ponto de entrada da CLI (`mbft-deploy` / `python -m mbft_deploy`) com os 5 subcomandos (`export-d1`, `provision`, `data`, `api`, `tudo`).
- **`exporters.py`**: Validação de `ChunkPayload`, bloqueio de artefatos de debug, geração atômica de `fts_chunks.sql` e fatiamento do JSONL de vetores (teto de 100 MB do Vectorize).
- **`wrangler.py`**: Invocação do Cloudflare Wrangler CLI, provisionamento de D1/Vectorize com atualização automática de IDs em `apps/api/wrangler.jsonc`, validação da configuração de assets, resolução de hostname (`--hostname` > `MBFT_HOSTNAME`) e publicação do Worker único `mbft` (API + Static Assets). Gera um manifesto efêmero (`apps/api/.wrangler.deploy.jsonc`, não versionado) por deploy para declarar o Custom Domain e ajustar `workers_dev` ao alvo resolvido, passando-o via `--config`.

---

### Sincronização incremental

O módulo `manifest.py` calcula fingerprints SHA-256 e consulta/atualiza o manifesto remoto por recurso (`d1_schema`, `d1_content` e `vectorize`).

O `data` garante primeiro a tabela `deploy_manifest` no D1 por meio de uma migração própria. Na primeira execução, ou quando um registro estiver ausente, pendente, com falha ou com hash divergente, o recurso é sincronizado. Quando o hash local coincide com um registro `ready`, a operação é ignorada. O registro passa por `pending` e só é marcado como `ready` depois do sucesso; falhas ficam explícitas no manifesto para serem tentadas novamente.

O hash do schema, do dump SQL e do JSONL de embeddings é calculado localmente. O manifesto não faz comparação linha a linha nem armazena os dados dos artefatos. Use `data --force` (ou `tudo --force`) para ignorar os hashes e repetir deliberadamente a carga.

## 4. Verificação Pós-Deploy e Diagnóstico

```powershell
# Worker único `mbft` (workers.dev ou Custom Domain): assets servidos direto pelo edge
curl.exe -s -o NUL -w "%{http_code}" https://mbft.seu-dominio.com/index.html
curl.exe -s -o NUL -w "%{http_code}" https://mbft.seu-dominio.com/fichas/518-51.html

# As três rotas de API devem responder 200 sob o prefixo /api (o /chat/ depende do índice)
curl.exe -s https://mbft.seu-dominio.com/api/health/
curl.exe -s "https://mbft.seu-dominio.com/api/busca/?q=pneu%20careca"
curl.exe -s -X POST -H "Content-Type: application/json" --data "@pergunta.json" https://mbft.seu-dominio.com/api/chat/
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
