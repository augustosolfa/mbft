# MBFT API (`mbft-api`)

API Gateway e Motor **RAG Híbrido** (Recuperador + Gerador) do Manual Brasileiro de Fiscalização de Trânsito, projetado para rodar no **Cloudflare Workers** (runtime Python/Pyodide) e em ambiente local via **FastAPI**.

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação completa de arquitetura, decisões de design e trade-offs dos subsistemas unificados neste serviço, consulte os Documentos de Design:
> - **PMS-005** (`docs/PMS-005 - Design do recuperador.md`) — Motor de Busca Híbrida RRF (`mbft_api.recuperador`);
> - **PMS-006** (`docs/PMS-006 - Design do gerador.md`) — Orquestrador Strict RAG e engenharia de prompt (`mbft_api.gerador`);
> - **PMS-008** (`docs/PMS-008 - API e Ticketizador.md`) — API Gateway FastAPI (o controle de taxa de tickets na aplicação foi descontinuado e delegado ao WAF/Rate Limiting da Cloudflare).

---

## Arquitetura Interna (`src/mbft_api/`)

Para garantir compatibilidade total com o bundler Pyodide do Cloudflare Workers — sem dependências cruzadas de workspace em `[project].dependencies` (`fastapi` apenas) — a aplicação consolida os módulos de borda em uma única árvore:

```text
apps/api/
├── pyproject.toml               # Produção: fastapi | Dev: uvicorn, google-genai, pytest
├── pylock.toml                  # Lockfile das dependências resolvidas para o alvo Pyodide (pylock)
├── wrangler.jsonc               # Bindings Cloudflare (D1, Vectorize, Workers AI), vars e main=src/entry.py
├── python_modules/              # Vendor das dependências do Worker (gerado por `pywrangler sync`)
├── schema.sql                   # Schema D1 idempotente (tabelas fts_chunks e historico_consultas)
├── scripts/
│   └── testar_gerador.py        # Script de validação local do Gerador com Gemini
├── tests/
│   ├── test_buscador.py         # Testes unitários RRF, diversificação, FTS5, adaptadores CF e DI
│   ├── test_cache_auditoria.py  # Testes de cache exato SHA-256 e auditoria/telemetria D1/SQLite
│   ├── test_integracao.py       # Testes de integração da Busca Híbrida sobre embeddings_mbft.jsonl
│   └── test_seguranca_chat.py   # Testes de validação de prompt injection e short-circuit
└── src/
    ├── entry.py                 # Entrypoint do Worker: workers.asgi -> mbft_api.main:app
    └── mbft_api/
        ├── main.py              # App FastAPI (lifespan e CORS), servido pelo Worker e pelo uvicorn local
        ├── database.py          # Adaptador D1 e SQLite para telemetria e cache exato (HistoricoRepository)
        ├── dependencies.py      # Depends() por requisição (get_buscador, get_gerador, get_historico_repo)
        ├── seguranca.py         # Validação heurística edge (teto de caracteres, anti-injection) e short-circuit
        ├── routers/
        │   ├── health.py        # GET  /health
        │   ├── busca.py         # GET  /busca
        │   └── chat.py          # POST /chat
        ├── recuperador/         # Submódulo de Busca Híbrida (PMS-005)
        │   ├── interfaces.py    # Protocols (IVectorDB, IRelationalDB, IEmbedderClient) e formatador FTS5
        │   ├── buscador.py      # BuscadorHibrido (Reciprocal Rank Fusion + diversificação)
        │   ├── cloudflare_adapters.py # Adaptadores Cloudflare (D1RelationalDB, VectorizeDB, WorkersAIEmbedder)
        │   └── local_adapters.py # Adaptadores locais (LocalSqliteDB FTS5, NumpyVectorDB, PyTorchEmbedder)
        └── gerador/             # Submódulo de Geração Strict RAG (PMS-006)
            ├── interfaces.py    # Protocol: ILLMClient
            ├── orquestrador.py  # OrquestradorGeracao (Stateless, temp=0.0)
            ├── prompts.py       # SYSTEM_PROMPT_TEMPLATE (Zero-Hallucination)
            ├── cloudflare_adapters.py # Adaptador Cloudflare (WorkersAILLMClient + limpeza de <think>)
            └── local_adapters.py # Adaptador local (GeminiLLMClient via google-genai, lazy-loaded)
```

O `main` declarado em `wrangler.jsonc` aponta para `src/entry.py`, que vive **fora** do pacote: o bundler
do Workers carrega o arquivo de `main` como módulo raiz, contexto em que imports relativos
(`from .routers import ...`) não têm pacote-pai e reprovam a validação de deploy. O app FastAPI continua
em `mbft_api.main`, servido pelo Worker (via `workers.asgi`) e pelo `uvicorn` no desenvolvimento local.

---

## Rotas Disponíveis

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health/` | Verifica a disponibilidade do serviço. |
| `GET` | `/busca/?q=...&limit=5` | Executa Busca Híbrida (Denso + FTS5 via RRF) e retorna trechos normativos e links `/fichas/{codigo}.html`. |
| `POST` | `/chat/` | Recebe `{"pergunta": "..."}`, executa o RAG completo e retorna a resposta fundamentada no MBFT. |

---

## Variáveis de Ambiente e Bindings

| Variável / Binding | Obrigatória | Descrição |
|---|---|---|
| `CF_LLM_MODEL` | Não (padrão em `wrangler.jsonc`) | Modelo do Cloudflare Workers AI usado por `WorkersAILLMClient` (padrão: `@cf/meta/llama-3.3-70b-instruct-fp8-fast`). |
| `CORS_ORIGINS` | Não | Lista de origens adicionais permitidas no CORS separadas por vírgula (ex.: `https://mbft-site.pages.dev`). Portas locais (`localhost:3000/5500/8080`) já são incluídas automaticamente. |
| `LLM_PROVIDER` | Não | Override explícito do provedor de geração (`workers_ai`/`cloudflare` ou `gemini`). Sem override, detecta `env.AI` no Workers e faz fallback para `app.state.gerador` localmente. |
| `GEMINI_API_KEY` | Apenas no modo local (`gemini`) | Chave da API Google Gemini utilizada por `GeminiLLMClient` (também aceita `GOOGLE_API_KEY`). Carregada automaticamente do `.env` da raiz por `mbft dev`; sem ela, o chat fica indisponível (HTTP 503) e a API registra um aviso na inicialização. |
| `DB`, `VECTORIZE`, `AI` | Em produção (Workers) | Bindings declarados em `wrangler.jsonc` para Cloudflare D1, Vectorize e Workers AI. |

---

## Vendorização de Dependências (Pyodide) e Publicação

O bundler do Cloudflare Workers **não** resolve as dependências do `pyproject.toml` no upload: o deploy
é reprovado pela validação da Cloudflare (`ModuleNotFoundError` / erro `10021`) até que elas estejam
vendorizadas em `apps/api/python_modules/`. Esse diretório é produzido pelo `pywrangler sync`
(pacote `workers-py`), que instala as wheels do alvo Pyodide a partir de `apps/api/pylock.toml`.

```bash
# Dentro de apps/api. No WSL2 (Windows) o PATH precisa de uv e node; no Linux/macOS basta o PATH nativo.
export PATH=$HOME/.local/bin:$HOME/.local/node/bin:$PATH
uvx --from workers-py pywrangler sync
```

```powershell
# Do Windows, o mesmo sync pode ser acionado pelo WSL2 (veja a nota abaixo sobre o Windows)
wsl -d Ubuntu -- bash -lc 'cd /caminho/do/repo/apps/api && uvx --from workers-py pywrangler sync'

# Publicar o Worker (da raiz do monorepo; no Windows com Smart App Control use o modulo)
uv run python -m mbft_deploy api
```

* **Por que o sync não roda no Windows nativo:** o `uv` precisa consultar o interpretador Pyodide, mas o
  sistema de arquivos virtual do Pyodide não resolve caminhos no estilo `C:/...` (`pyemscripten_2026_0_wasm32`).
  O `pywrangler` também requer Node no PATH, pois o launcher do Pyodide é executado sob Node.
* `pylock.toml` é versionado no repositório (reprodutibilidade das versões); `python_modules/` e
  `.venv-workers/` são artefatos gerados e não versionados.
* Para desenvolvimento local do Worker (`uv run pywrangler dev`), execute o comando no WSL2 no Windows.
* **Troca de modelo invalida o cache de respostas:** o cache exato é indexado apenas pelo SHA-256 da
  pergunta e devolve o registro mais recente daquele hash, sem conhecer a versão do modelo. Ao trocar
  `CF_LLM_MODEL`, purgue `historico_consultas` — caso contrário, perguntas já vistas continuam recebendo a
  resposta do modelo anterior (inclusive recusas). A purga também remove a telemetria acumulada, pois cache
  e auditoria compartilham a mesma tabela:
  `npx wrangler d1 execute mbft-d1 --remote --command "DELETE FROM historico_consultas"`.

---

## Execução Local, Migração D1 e Testes

A partir da raiz do monorepo:

```powershell
# 1. Sincronizar ambiente virtual
uv sync

# 2. Executar testes unitários (rápidos, sem GPU)
uv run pytest apps/api/tests/test_buscador.py

# 3. Executar suíte completa (inclui integração com BAAI/bge-m3 e embeddings_mbft.jsonl)
uv run pytest apps/api/tests/

# 4. Aplicar schema SQL no Cloudflare D1 (local ou remoto via Wrangler)
npx wrangler d1 execute mbft-d1 --local --file=apps/api/schema.sql
npx wrangler d1 execute mbft-d1 --remote --file=apps/api/schema.sql

# 5. Iniciar servidor FastAPI local
#    `mbft dev api` carrega o `.env` da raiz automaticamente (GEMINI_API_KEY).
uv run mbft dev api

# Alternativa direta via uvicorn, com as variáveis do `.env`
uv run uvicorn mbft_api.main:app --reload --port 8000 --env-file .env
```
