# MBFT - Manual Brasileiro de Fiscalização de Trânsito

Monorepo para processamento, extração de dados estruturados, indexação híbrida e aplicações inteligentes (RAG) baseadas no Manual Brasileiro de Fiscalização de Trânsito (**MBFT** - Resolução CONTRAN nº 985/2022 e alterações posteriores).

---

## 🏗️ Estrutura do Repositório

- **`data/raw/`**: Documento fonte original (`mbft.pdf`).
- **`data/processed/`**: Dados finais consolidados por etapa:
  - **`extrator/`**: `fichas_mbft.json` (402 fichas de fiscalização), `mbft_parte_geral.md` e `imagens/` (300 DPI).
  - **`enriquecedor/`**: `fichas_enriquecidas.json` com metadados normativos e vocabulário expandido.
  - **`indexador/`**: `embeddings_mbft.jsonl` com chunks contextualizados e vetores densos (`BAAI/bge-m3`).
  - **`site/`**: Páginas estáticas HTML geradas para consulta rápida (`/fichas/XXX.html`, `index.html`, `lista.html`, `chat.html`).
- **`pipelines/`**:
  - **`core/` (`mbft-core`)**: Modelos de domínio e contratos Pydantic compartilhados entre os pipelines (PMS-009).
  - **`extrator/` (`mbft-extrator`)**: Ingestão do PDF, OCR, costura geométrica de colunas e serialização com aceleração CUDA (PMS-002).
  - **`enriquecedor/` (`mbft-enriquecedor`)**: Enriquecimento determinístico e semântico das fichas (PMS-003).
  - **`indexador/` (`mbft-indexador`)**: Geração de chunks e embeddings densos a partir das fichas enriquecidas (PMS-004).
  - **`ssg/` (`mbft-ssg`)**: Gerador de site estático HTML via Jinja2 (PMS-007).
- **`apps/api/` (`mbft-api`)**: API Gateway FastAPI para Cloudflare Workers (Pyodide), consolidando o **Ticketizador** de fila global (PMS-008), o **Recuperador** de busca híbrida RRF (`mbft_api.recuperador`, PMS-005) e o **Gerador** Strict RAG (`mbft_api.gerador`, PMS-006).
- **`docs/`**: Propostas de Melhoria do Sistema (PMS) documentando todas as decisões de arquitetura (visão geral do mecanismo RAG na `PMS-001` e template na `PMS-000`).

---

## 🚀 Como Executar

Este projeto utiliza o gerenciador de pacotes **`uv`**.

### Instalação de Dependências

```bash
uv sync
```

### Pipelines Batch

```bash
# 1. Extrator (PDF -> JSON/Markdown/Imagens)
uv run mbft-extrator tudo

# 2. Enriquecedor (Fichas -> Fichas Enriquecidas)
uv run mbft-enriquecedor

# 3. Indexador (Fichas Enriquecidas -> JSONL de Embeddings)
uv run mbft-indexador

# 4. Gerador de Site Estático (SSG)
uv run mbft-ssg
```

### API e Motor RAG (`apps/api`)

```bash
# Subir servidor FastAPI em modo de desenvolvimento local
uv run uvicorn mbft_api.main:app --reload --port 8000

# Executar a suíte de testes automatizados
uv run pytest
```

Consulte [GEMINI.md](./GEMINI.md) e os guias operacionais de cada módulo ([core](./pipelines/core/README.md), [extrator](./pipelines/extrator/README.md), [enriquecedor](./pipelines/enriquecedor/README.md), [indexador](./pipelines/indexador/README.md), [ssg](./pipelines/ssg/README.md) e [api](./apps/api/README.md)) para detalhes técnicos e opções de CLI.
