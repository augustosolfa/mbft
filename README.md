# MBFT - Manual Brasileiro de Fiscalização de Trânsito

Monorepo para processamento, extração de dados estruturados, indexação híbrida e aplicações inteligentes (RAG) baseadas no Manual Brasileiro de Fiscalização de Trânsito (**MBFT** - Resolução CONTRAN nº 985/2022 e alterações posteriores).

---

## 🏗️ Estrutura do Repositório

- **`data/raw/`**: Documento fonte original (`mbft.pdf`).
- **`data/processed/`**: Dados finais consolidados por etapa:
  - **`extrator/`**: `fichas_mbft.json` (402 fichas de fiscalização), `mbft_parte_geral.md` e `imagens/` (300 DPI).
  - **`enriquecedor/`**: `fichas_enriquecidas.json` com metadados normativos e vocabulário expandido.
  - **`indexador/`**: `embeddings_mbft.jsonl` com chunks contextualizados e vetores densos (`BAAI/bge-m3`).
  - **`site/`**: Páginas estáticas HTML geradas para consulta rápida (`/fichas/XXX.html`, `index.html`, `lista.html`, `chat.html`, `404.html`, `config.js`), publicadas como *Static Assets* pelo Worker único `mbft`.
  - **`deploy/`**: `fts_chunks.sql` exportado para carga na tabela virtual FTS5 do Cloudflare D1.
- **`pipelines/`**:
  - **`core/` (`mbft-core`)**: Modelos de domínio e contratos Pydantic compartilhados entre os pipelines (PMS-009).
  - **`extrator/` (`mbft-extrator`)**: Ingestão do PDF, OCR, costura geométrica de colunas e serialização com aceleração CUDA (PMS-002).
  - **`enriquecedor/` (`mbft-enriquecedor`)**: Enriquecimento determinístico e semântico das fichas (PMS-003).
  - **`indexador/` (`mbft-indexador`)**: Geração de chunks e embeddings densos a partir das fichas enriquecidas (PMS-004).
  - **`ssg/` (`mbft-ssg`)**: Gerador de site estático HTML via Jinja2 (PMS-007).
- **`apps/api/` (`mbft-api`)**: Worker único `mbft` (Cloudflare Workers/Pyodide) que serve, na mesma origem, os assets estáticos do SSG e a API Gateway FastAPI, consolidando o **Ticketizador** de fila global (PMS-008), o **Recuperador** de busca híbrida RRF (`mbft_api.recuperador`, PMS-005) e o **Gerador** Strict RAG (`mbft_api.gerador`, PMS-006).
- **`deploy/` (`mbft-deploy`)**: Exportadores de dados para nuvem (`fts_chunks.sql`), provisionamento e automação de deploy do Worker único (API + Static Assets) na Cloudflare via Wrangler (PMS-010).
- **`docs/`**: Propostas de Melhoria do Sistema (PMS) documentando todas as decisões de arquitetura (visão geral do mecanismo RAG na `PMS-001` e template na `PMS-000`).

---

## 🚀 Como Executar (CLI Unificada `mbft`)

Este projeto utiliza o gerenciador de pacotes **`uv`** e centraliza todas as operações no executável **`mbft`**:

```bash
# Instalar e sincronizar dependências do workspace
uv sync
```

### 1. Pipelines de Dados (`mbft pipeline`)

```bash
# Executar todas as 4 etapas em sequência (extrator -> enriquecedor -> indexador -> ssg)
uv run mbft pipeline tudo

# Ou executar apenas uma etapa específica
uv run mbft pipeline extrator
uv run mbft pipeline enriquecedor
uv run mbft pipeline indexador
uv run mbft pipeline ssg
```

### 2. Ambiente de Desenvolvimento Local (`mbft dev`)

O comando carrega automaticamente o arquivo `.env` da raiz do monorepo (quando presente),
sem sobrescrever variáveis já exportadas no shell — é assim que `GEMINI_API_KEY` chega ao
Gerador LLM local. Crie o `.env` na raiz (ele é ignorado pelo Git) tomando `.env.example`
como referência; o mesmo arquivo pode definir `MBFT_HOSTNAME` para o deploy.

```bash
# Subir API FastAPI (porta 8000) + Site Estático (porta 3000) simultaneamente
uv run mbft dev

# Ou subir apenas um dos serviços
uv run mbft dev api
uv run mbft dev site
```

### 3. Testes, Governança e Benchmarks (`mbft testes`)

```bash
# Suíte rápida (testes unitários de todos os pacotes + governança documental, sem GPU)
uv run mbft testes

# Suíte completa (inclui integração vetorial densa na GPU com BAAI/bge-m3)
uv run mbft testes tudo

# Apenas auditoria de governança documental (PMS / README / pyproject.toml)
uv run mbft testes governanca

# Benchmarks e auditorias específicas
uv run mbft testes recall
uv run mbft testes diff-extracao
uv run mbft testes gerador
```

### 4. Exportação e Deploy na Cloudflare (`mbft deploy`)

```bash
# Provisionar recursos na Cloudflare (D1 e Vectorize) e atualizar wrangler.jsonc
uv run mbft deploy provision

# Exportar SQL FTS5 e publicar Dados (D1/Vectorize) + Worker único `mbft` (API + site estático)
uv run mbft deploy tudo

# Opcional: configurar um Custom Domain (ou definir MBFT_HOSTNAME no .env da raiz)
uv run mbft deploy tudo --hostname mbft.seu-dominio.com
```

Consulte [GEMINI.md](./GEMINI.md) e os guias operacionais de cada módulo ([core](./pipelines/core/README.md), [extrator](./pipelines/extrator/README.md), [enriquecedor](./pipelines/enriquecedor/README.md), [indexador](./pipelines/indexador/README.md), [ssg](./pipelines/ssg/README.md), [api](./apps/api/README.md) e [deploy](./deploy/README.md)) para detalhes técnicos e opções avançadas.
