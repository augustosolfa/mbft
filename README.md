# MBFT - Manual Brasileiro de Fiscalização de Trânsito

Monorepo para processamento, extração de dados estruturados e aplicações inteligentes baseadas no Manual Brasileiro de Fiscalização de Trânsito (**MBFT** - Resolução CONTRAN nº 985/2022 e alterações posteriores).

---

## 📐 Arquitetura Geral do Sistema

```mermaid
flowchart TD
    subgraph BATCH["🔄 Processamento Assíncrono (Batch Pipeline)"]
        PDF["📄 PDF MBFT Raw\n(data/raw/mbft.pdf)"]

        EXT["1. Extrator (mbft-extrator)\nDocling + pypdfium2"]
        ENR["2. Enriquecedor (mbft-enriquecedor)\nNormalização + IE + Lei 14.599"]
        IDX["3. Indexador (mbft-indexador)\nChunking + BAAI/bge-m3 Embeddings"]
        SSG["4. SSG Generator (mbft-ssg)\nJinja2 + HTML Estático"]

        PDF --> EXT
        EXT -->|fichas_mbft.json| ENR
        ENR -->|fichas_enriquecidas.json| IDX
        ENR -->|fichas_enriquecidas.json| SSG
    end

    subgraph CLOUD["☁️ Cloud Infrastructure (Cloudflare)"]
        D1[("Cloudflare D1\nSQL Database")]
        VEC[("Cloudflare Vectorize\nVector Store")]
        PAGES["Cloudflare Pages\nStatic Hosting (/fichas/*.html)"]
    end

    subgraph RUNTIME["⚡ Edge Runtime (Cloudflare Workers / Pyodide)"]
        API["FastAPI Gateway / Ticketizador"]
        REC["Recuperador (RAG Híbrido: Vectorize + FTS5)"]
        GER["Gerador LLM (DeepSeek Flash / Workers AI)"]

        API --> REC
        REC --> GER
    end

    IDX -->|wrangler insert| VEC
    ENR -->|D1 Import| D1
    SSG --> PAGES

    REC -->|Vector Search| VEC
    REC -->|SQL/FTS5 Search| D1
```

---

## 🏗️ Estrutura do Repositório

- **`data/raw/`**: Documento fonte original (`mbft.pdf`).
- **`data/processed/`**: Dados finais consolidados por etapa:
  - **`extrator/`**:
    - `fichas_mbft.json`: Base estruturada contendo as 402 fichas de fiscalização com metadados, regras e conteúdo normativo.
    - `mbft_parte_geral.md`: Transcrição semântica da parte geral (páginas 1 a 31).
    - `imagens/`: Ilustrações, placas de sinalização e diagramas de trânsito em alta definição (300 DPI).
- **`pipelines/extrator/`**: Módulo em Python responsável pela ingestão, OCR, costura geométrica de colunas e serialização com aceleração CUDA.

---

## 🚀 Como Executar

Este projeto utiliza o gerenciador de pacotes **`uv`**.

### Instalação de Dependências

```bash
uv sync
```

### Execução do Extrator

A partir da raiz do monorepo, via script de console:

```bash
# Executar extração da parte geral
uv run mbft-extrator geral

# Executar extração das fichas estruturadas
uv run mbft-extrator fichas

# Executar pipeline completo
uv run mbft-extrator tudo
```

Ou diretamente através do script auxiliar:

```bash
uv run python pipelines/extrator/extrair.py tudo
```

Consulte [pipelines/extrator/README.md](file:///d:/dev/mbft%20-%20extrator/pipelines/extrator/README.md) para detalhes técnicos da arquitetura do extrator.
