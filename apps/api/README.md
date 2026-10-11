# MBFT API (`mbft-api`)

API Gateway, **Ticketizador** de Fila Global e Motor **RAG Híbrido** (Recuperador + Gerador) do Manual Brasileiro de Fiscalização de Trânsito, projetado para rodar no **Cloudflare Workers** (runtime Python/Pyodide) e em ambiente local via **FastAPI**.

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação completa de arquitetura, decisões de design e trade-offs dos subsistemas unificados neste serviço, consulte os Documentos de Design:
> - **PMS-005** (`docs/PMS-005 - Design do recuperador.md`) — Motor de Busca Híbrida RRF (`mbft_api.recuperador`);
> - **PMS-006** (`docs/PMS-006 - Design do gerador.md`) — Orquestrador Strict RAG e engenharia de prompt (`mbft_api.gerador`);
> - **PMS-008** (`docs/PMS-008 - API e Ticketizador.md`) — API Gateway FastAPI e Fila Global (`mbft_api.routers`, `mbft_api.security`, `mbft_api.database`).

---

## Arquitetura Interna (`src/mbft_api/`)

Para garantir compatibilidade total com o bundler Pyodide do Cloudflare Workers — sem dependências cruzadas de workspace em `[project].dependencies` (`fastapi` e `pyjwt` apenas) — a aplicação consolida os módulos de borda em uma única árvore:

```text
apps/api/
├── pyproject.toml               # Produção: fastapi, pyjwt | Dev: uvicorn, google-genai, pytest
├── wrangler.jsonc               # Bindings Cloudflare (D1, Vectorize, Workers AI, KV)
├── scripts/
│   └── testar_gerador.py        # Script de validação local do Gerador com Gemini
├── tests/
│   ├── test_buscador.py         # Testes unitários RRF, diversificação e tokenização FTS5
│   └── test_integracao.py       # Testes de integração da Busca Híbrida sobre embeddings_mbft.jsonl
└── src/mbft_api/
    ├── main.py                  # Entrypoint FastAPI, CORS e ciclo de vida (lifespan)
    ├── database.py              # FilaRepository (Cloudflare D1 em prod / SQLite fila.db local)
    ├── security.py              # TicketService (JWT HS256 + anti-replay KV via jti)
    ├── routers/
    │   ├── health.py            # GET  /health
    │   ├── busca.py             # GET  /busca
    │   ├── ticket.py            # POST /ticket
    │   └── chat.py              # POST /chat
    ├── recuperador/             # Submódulo de Busca Híbrida (PMS-005)
    │   ├── interfaces.py        # Protocols: IVectorDB, IRelationalDB, IEmbedderClient
    │   ├── buscador.py          # BuscadorHibrido (Reciprocal Rank Fusion + diversificação)
    │   └── local_adapters.py    # Adaptadores locais (LocalSqliteDB FTS5, NumpyVectorDB, PyTorchEmbedder)
    └── gerador/                 # Submódulo de Geração Strict RAG (PMS-006)
        ├── interfaces.py        # Protocol: ILLMClient
        ├── orquestrador.py      # OrquestradorGeracao (Stateless, temp=0.0)
        ├── prompts.py           # SYSTEM_PROMPT_TEMPLATE (Zero-Hallucination)
        └── local_adapters.py    # Adaptador local (GeminiLLMClient via google-genai, lazy-loaded)
```

---

## Rotas Disponíveis

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/health/` | Verifica a disponibilidade do serviço. |
| `GET` | `/busca/?q=...&limit=5` | Executa Busca Híbrida (Denso + FTS5 via RRF) e retorna trechos normativos e links `/fichas/{codigo}.html`. |
| `POST` | `/ticket/` | Emite um Ticket JWT na fila global (header opcional `priority-token` para `TOKEN_TESTES` ou `TOKEN_ADMIN`). |
| `POST` | `/chat/` | Recebe `{"pergunta": "..."}` e o header `x-ticket`, executa o RAG completo e retorna a resposta fundamentada no MBFT. |

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `JWT_SECRET` | Sim (em `/ticket` e `/chat`) | Segredo HMAC-SHA256 para assinar e validar Tickets JWT (não pode ser `MUDAR_EM_PRODUCAO`). |
| `TOKEN_ADMIN` | Não | Token VIP para emissão de ticket sem espera na fila global. |
| `TOKEN_TESTES` | Não | Token para emissão de ticket com espera reduzida (+10s). |
| `GEMINI_API_KEY` | Apenas no modo local (LLM) | Chave da API Google Gemini utilizada por `GeminiLLMClient`. |

---

## Execução Local e Testes

A partir da raiz do monorepo:

```powershell
# 1. Sincronizar ambiente virtual
uv sync

# 2. Executar testes unitários (rápidos, sem GPU)
uv run pytest apps/api/tests/test_buscador.py

# 3. Executar suíte completa (inclui integração com BAAI/bge-m3 e embeddings_mbft.jsonl)
uv run pytest apps/api/tests/

# 4. Iniciar servidor FastAPI local
$env:JWT_SECRET="segredo-local-de-desenvolvimento"
uv run uvicorn mbft_api.main:app --reload --port 8000
```
