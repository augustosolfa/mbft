# Diretrizes e Instruções do Projeto - MBFT Monorepo

Este documento define os padrões de desenvolvimento, governança de dados, regras estritas de integridade e arquitetura global do monorepo para o processamento e aplicações do Manual Brasileiro de Fiscalização de Trânsito (**MBFT**).

---

## 1. Ambiente, Ferramentas e Padrões de Execução

- **Gerenciador de Pacotes e Workspaces**: Usar SEMPRE `uv` (`uv venv`, `uv pip`, `uv add`, `uv run`, `uv sync`).
- **Arquitetura Monorepo (UV Workspace)**:
  - O `pyproject.toml` da raiz gerencia o workspace (`[tool.uv.workspace]`).
  - Cada componente possui seu próprio subdiretório e `pyproject.toml` declarando dependências específicas.
- **Versão do Python**: Python 3.14 (testado e homologado com CPython 3.14.6).
- **Ambiente Virtual**: Compartilhado na raiz (`.venv`), mantido e sincronizado via `uv sync`.
- **Aceleração de Hardware (GPU / CUDA)**:
  - O PyTorch é instalado a partir do índice oficial CUDA 13.2 (`https://download.pytorch.org/whl/cu132`) com `explicit = true`.
  - O Docling utiliza automaticamente `AcceleratorOptions(device="cuda")` com a GPU instalada (NVIDIA GeForce RTX 4070).

---

## 2. Regras Estritas de Integridade de Arquivos

- **`data/raw/mbft.pdf`**: Arquivo fonte bruto original (105 MB). **NUNCA DEVE SER MODIFICADO OU SOBRESCRITO**.

---

## 3. Estrutura Global do Monorepo

```text
mbft/
├── .git/
├── .venv/
├── .gitignore                   # Exclusões do git (ignora data/raw/, data/archive/ e caches)
├── .python-version              # Python 3.14
├── AGENTS.md                    # Entrada de regras de agentes de IA
├── GEMINI.md                    # Governança e regras globais do monorepo
├── README.md                    # Apresentação geral do projeto
├── pyproject.toml               # Raiz do UV Workspace (members = ["pipelines/*", "apps/*"])
│
├── data/
│   ├── raw/                     # Dados brutos originais (ex.: mbft.pdf) - NUNCA ALTERAR
│   ├── archive/                 # Dados arquivados locais (ignorado no git)
│   │   └── backup_extracao_v1/  # Backups de extrações consolidadas anteriores
│   └── processed/               # Dados tratados e artefatos consolidados por etapa
│       ├── extrator/            # Artefatos da extração (PMS-002)
│       │   ├── fichas_mbft.json # JSON canônico consolidado
│       │   ├── mbft_parte_geral.md # Parte geral normativa em Markdown
│       │   ├── relatorio_extracao.md
│       │   ├── imagens/         # Imagens vetoriais e recortes (300 DPI)
│       │   └── fichas/          # Fichas individuais JSON (opcional/ignorado no git)
│       ├── enriquecedor/        # Artefatos do enriquecimento (PMS-003)
│       │   ├── fichas_enriquecidas.json
│       │   └── relatorio_enriquecimento.md
│       ├── indexador/           # Artefatos da indexação vetorial/lexical (PMS-004)
│       │   └── embeddings_mbft.jsonl
│       └── site/                # Artefatos estáticos HTML gerados pelo SSG (PMS-007)
│           ├── index.html
│           ├── lista.html
│           ├── chat.html
│           ├── fichas/          # Páginas estáticas das fichas (/fichas/XXX.html)
│           └── imagens/         # Ativos visuais copiados para distribuição estática
│
├── docs/                        # Propostas de Melhoria do Sistema (PMS)
│   ├── PMS-000 - Template de PMS.md
│   ├── PMS-001 - Mecanismo RAG do Manual Brasileiro de Fiscalizacao de Transito.md
│   ├── PMS-002 - Design do extrator.md
│   ├── PMS-003 - Design do enriquecedor.md
│   ├── PMS-004 - Design do indexador.md
│   ├── PMS-005 - Design do recuperador.md
│   ├── PMS-006 - Design do gerador.md
│   ├── PMS-007 - Site Estático (SSG).md
│   └── PMS-008 - API e Ticketizador.md
│
├── pipelines/                   # Módulos e contratos de processamento assíncrono (batch)
│   ├── core/                    # Contratos canônicos de guardrail e domínio (mbft-core)
│   │   ├── pyproject.toml       # Dependência leve (pydantic)
│   │   ├── README.md
│   │   └── src/mbft_core/       # Modelos canônicos (Ficha, FichaEnriquecida, Enums)
│   ├── extrator/                # Extrator Estruturado de Alta Fidelidade (mbft-extrator)
│   ├── enriquecedor/            # Enriquecedor determinístico e semântico (mbft-enriquecedor)
│   ├── indexador/               # Gerador de chunks e embeddings BAAI/bge-m3 (mbft-indexador)
│   └── ssg/                     # Gerador de Site Estático HTML/Jinja2 (mbft-ssg)
│
└── apps/                        # Aplicações de borda e serviços online
    └── api/                     # API Gateway, Ticketizador e Motor RAG (mbft-api)
        ├── pyproject.toml       # Dependências de runtime enxutas (fastapi, pyjwt) + grupo dev
        ├── README.md            # Documentação da API e execução local/Workers
        ├── wrangler.jsonc       # Configuração de deploy Cloudflare Workers (Pyodide)
        ├── scripts/             # Scripts utilitários (ex.: testar_gerador.py)
        ├── tests/               # Testes unitários e de integração (busca híbrida RRF)
        └── src/mbft_api/        # Código-fonte unificado do Worker
            ├── main.py          # Entrypoint FastAPI e lifespan
            ├── database.py      # Persistência da fila global (Cloudflare D1 / SQLite local)
            ├── security.py      # TicketService (JWT + proteção anti-replay KV)
            ├── routers/         # Endpoints HTTP (/health, /busca, /ticket, /chat)
            ├── recuperador/     # Motor de Busca Híbrida RRF (PMS-005)
            └── gerador/         # Orquestrador Strict RAG e prompts LLM (PMS-006)
```

---

## 4. Módulos do Sistema

### 4.1. `pipelines/core` (`mbft-core`)
Território neutro de contratos canônicos e modelos de domínio (Pydantic v2) compartilhado entre os pipelines. Define os guardrails de saída do Extrator, de entrada e saída do Enriquecedor e de consumo dos demais pipelines batch (`indexador` e `ssg`), sem acoplamento a bibliotecas pesadas de visão/OCR ou ML.

### 4.2. `pipelines/extrator` (`mbft-extrator`)
Responsável pela extração, fatiamento geométrico, costura de canais paralelos entre páginas, extração semântica via Docling CUDA, estruturação do JSON canônico e geração de HTML e imagens a 300 DPI.
- **Documentação Técnica Completa**: Consulte [pipelines/extrator/README.md](file:///d:/dev/mbft%20-%20extrator/pipelines/extrator/README.md).
- **Casos de Teste Benchmark**: Consulte [pipelines/extrator/tests/casos_de_teste_benchmark.md](file:///d:/dev/mbft%20-%20extrator/pipelines/extrator/tests/casos_de_teste_benchmark.md).

### 4.3. `pipelines/enriquecedor` (`mbft-enriquecedor`)
Aplica enriquecimento determinístico, normalização de vocabulário e estruturação semântica às fichas extraídas, gerando `data/processed/enriquecedor/fichas_enriquecidas.json` (PMS-003).

### 4.4. `pipelines/indexador` (`mbft-indexador`)
Fatia as fichas enriquecidas e a parte geral em *chunks* contextualizados e gera vetores densos de 1024 dimensões (`BAAI/bge-m3` via CUDA), exportando `data/processed/indexador/embeddings_mbft.jsonl` (PMS-004).

### 4.5. `pipelines/ssg` (`mbft-ssg`)
Compila o portal estático HTML (`data/processed/site/`) com páginas individuais para cada ficha (`/fichas/XXX.html`), listagem geral e interface de busca/chat (PMS-007).

### 4.6. `apps/api` (`mbft-api`)
Monólito modular de borda (Cloudflare Workers Python / FastAPI) que unifica o **Ticketizador** de fila global (PMS-008), o **Recuperador** de busca híbrida RRF (`mbft_api.recuperador`, PMS-005) e o **Gerador** de respostas Strict RAG (`mbft_api.gerador`, PMS-006). Mantém apenas `fastapi` e `pyjwt` como dependências de produção para compatibilidade estrita com o Pyodide.

---

## 5. Padrões de Git e Conventional Commits

- Todas as mensagens de commit devem seguir rigorosamente o padrão **Conventional Commits** em português (ex.: `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `perf: ...`).
