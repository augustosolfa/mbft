# Pipeline Indexador MBFT (`mbft-indexador`)

Módulo de processamento em lote (*batch*) responsável pela segmentação semântica contextualizada (*chunking*) das fichas enriquecidas do **Manual Brasileiro de Fiscalização de Trânsito (MBFT)** e geração de embeddings densos de 1024 dimensões via `BAAI/bge-m3` acelerado por GPU (CUDA).

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação completa de arquitetura, estratégia de prefixo enxuto, escolhas de formato e trade-offs, consulte o Documento de Design **PMS-004** em `docs/PMS-004 - Design do indexador.md`.
> Para os contratos de dados de entrada (`FichaEnriquecida`) e saída (`ChunkPayload`, `ChunkMetadados`), consulte a **PMS-009** e o pacote **`mbft-core`** em `pipelines/core/README.md`.

---

## 1. Uso da Linha de Comando (CLI)

Execute os comandos a partir da raiz do monorepo via `uv`:

```bash
# Geração completa de chunks e embeddings na GPU (salva em data/processed/indexador/embeddings_mbft.jsonl)
uv run mbft-indexador

# Especificar caminhos customizados e tamanho de batch na GPU
uv run mbft-indexador --input data/processed/enriquecedor/fichas_enriquecidas.json --output data/processed/indexador/embeddings_mbft.jsonl --batch-size 64

# Incluir os chunks da Parte Geral (auto-detecta parte_geral_enriquecida.json ao lado do input)
uv run mbft-indexador --parte-geral

# Ou informar um caminho explícito para a Parte Geral enriquecida
uv run mbft-indexador --parte-geral data/processed/enriquecedor/parte_geral_enriquecida.json

# Modo debug/teste rápido sem carregar o modelo real de embeddings (salva em embeddings_debug.jsonl)
uv run mbft-indexador --skip-embeddings
```

### Avaliação Offline de Qualidade (Recall@K) e Testes

```bash
# Executar a suíte de testes unitários do chunker e da CLI
uv run pytest pipelines/indexador/tests

# Avaliar aderência semântica (Top-1 / Top-5) contra os casos de referência
uv run python pipelines/indexador/scripts/avaliacao_aderencia.py --jsonl data/processed/indexador/embeddings_mbft.jsonl --casos pipelines/indexador/scripts/casos_aderencia.yaml
```

---

## 2. Entradas e Saídas

- **Entrada**:
  - `data/processed/enriquecedor/fichas_enriquecidas.json`: Artefato consolidado validado contra o contrato `FichaEnriquecida` (`mbft-core`).
- **Saídas**:
  - `data/processed/indexador/embeddings_mbft.jsonl`: Artefato NDJSON contendo `id`, `values` (vetor float32 de 1024 dimensões normalizado L2) e `metadata` (`ChunkPayload`).
  - `data/processed/indexador/embeddings_debug.jsonl`: Artefato de inspeção rápida gerado quando a flag `--skip-embeddings` é utilizada.
  - Quando `--parte-geral` (ou a auto-detecção de `parte_geral_enriquecida.json`) está ativo, também são gerados chunks da Parte Geral com `secao=PARTE_GERAL` e `codigo=PG_*` (ex.: `PG_8_1`).

---

## 3. Estrutura do Código-Fonte (`src/mbft_indexador/`)

- **`cli.py`**: Ponto de entrada da CLI (`mbft-indexador`), validação de argumentos e orquestração do fluxo batch.
- **`chunker.py`**: Fracionamento das fichas enriquecidas por seções temáticas (`EMENTA`, `QUANDO_AUTUAR`, `QUANDO_NAO_AUTUAR`, `DEFINICOES_PROCEDIMENTOS`, `EXEMPLOS_AIT`, `INFORMACOES_COMPLEMENTARES`) e montagem do prefixo contextual enxuto. Também expõe `gerar_chunks_parte_geral` para as seções da Parte Geral.
- **`embedder.py`**: Integração com `sentence-transformers` e PyTorch CUDA para inferência em lotes do modelo `BAAI/bge-m3`.
