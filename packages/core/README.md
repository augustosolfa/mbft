# MBFT Core (`mbft-core`)

Pacote interno do monorepo MBFT contendo contratos canônicos de dados (modelos Pydantic v2), enums normativos e guardrails compartilhados entre os pipelines de extração, enriquecimento e carga.

## Módulos

- `mbft_core.models.extracao`: Modelos brutos de saída do extrator e guardrail de entrada do enriquecedor (`Ficha`, `CampoNormativo`, `FichaMapeada`).
- `mbft_core.models.enriquecimento`: Modelos normalizados, atributos extraídos e contratos de chunks/embeddings (`FichaEnriquecida`, `ChunkPayload`, `ChunkMetadados`, Enums).
- `mbft_core.models`: Ponto de entrada unificado re-exportando todos os modelos canônicos.
