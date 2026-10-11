# MBFT Core (`mbft-core`)

Pacote interno dos pipelines do monorepo MBFT (`pipelines/core`) contendo contratos canônicos de dados (modelos Pydantic v2), enums normativos, caminhos compartilhados e guardrails entre os pipelines de extração, enriquecimento, indexação e geração de site estático (SSG).

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação de arquitetura, isolamento de dependências e mapa de consumidores (`PMS-002`, `PMS-003`, `PMS-004` e `PMS-007`), consulte o Documento de Design **PMS-009** em `docs/PMS-009 - Contratos Canonicos e Nucleo Compartilhado (mbft-core).md`.

## Módulos

- `mbft_core.models.extracao`: Modelos brutos de saída do extrator e guardrail de entrada do enriquecedor (`Ficha`, `CampoNormativo`, `FichaMapeada`).
- `mbft_core.models.enriquecimento`: Modelos normalizados e atributos extraídos pelo enriquecedor (`FichaEnriquecida`, `ItemRegra`, `ReferenciaCTB`, Enums).
- `mbft_core.models.indexacao`: Contratos de chunks e payloads vetoriais gerados pelo indexador (`ChunkPayload`, `ChunkMetadados`).
- `mbft_core.models`: Ponto de entrada unificado re-exportando todos os modelos canônicos.
- `mbft_core.paths`: Resolução resiliente dos caminhos canônicos do monorepo (`RAIZ_REPO`, `DATA_DIR`, `RAW_DIR`, `PROCESSED_DIR`).
