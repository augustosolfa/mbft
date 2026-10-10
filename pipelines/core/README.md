# MBFT Core (`mbft-core`)

Pacote interno dos pipelines do monorepo MBFT (`pipelines/core`) contendo contratos canônicos de dados (modelos Pydantic v2), enums normativos, caminhos compartilhados e guardrails entre os pipelines de extração, enriquecimento, indexação e geração de site estático (SSG).

## Módulos

- `mbft_core.models.extracao`: Modelos brutos de saída do extrator e guardrail de entrada do enriquecedor (`Ficha`, `CampoNormativo`, `FichaMapeada`).
- `mbft_core.models.enriquecimento`: Modelos normalizados e atributos extraídos pelo enriquecedor (`FichaEnriquecida`, `ItemRegra`, `ReferenciaCTB`, Enums).
- `mbft_core.models.indexacao`: Contratos de chunks e payloads vetoriais gerados pelo indexador (`ChunkPayload`, `ChunkMetadados`).
- `mbft_core.models`: Ponto de entrada unificado re-exportando todos os modelos canônicos.
- `mbft_core.paths`: Resolução resiliente dos caminhos canônicos do monorepo (`RAIZ_REPO`, `DATA_DIR`, `RAW_DIR`, `PROCESSED_DIR`).
