---
trigger: glob
globs: "pipelines/core/**"
description: "Isolamento de dependências leves e contratos canônicos em pipelines/core (mbft-core)"
---

# Guardrails de Isolamento — `pipelines/core` (`mbft-core`)

O pacote `pipelines/core` (`mbft-core`, regido pela `PMS-009`) é o território neutro de contratos canônicos de dados compartilhados entre os pipelines batch (`extrator`, `enriquecedor`, `indexador` e `ssg`):

1. **Zero Dependências Pesadas**:
   - Deve depender exclusivamente de **`pydantic`** (e biblioteca padrão do Python).
   - **Proibido** acoplar bibliotecas pesadas de visão computacional/OCR (`docling`, `pymupdf`, `pillow`), ML/GPU (`torch`, `sentence-transformers`) ou motores de template (`jinja2`).
2. **Escopo do Pacote**:
   - Restrito a modelos Pydantic v2 (`mbft_core.models.*`), enumerações normativas de domínio e resolução de caminhos canônicos do monorepo (`mbft_core.paths`).
