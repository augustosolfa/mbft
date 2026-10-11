---
PMS: 009
Título: Contratos Canônicos de Domínio e Núcleo Compartilhado (mbft-core)
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 10-Out-2026
Requer: PMS-001
Substitui: Nenhum
---

# PMS-009: Contratos Canônicos de Domínio e Núcleo Compartilhado (mbft-core)

## 1. Contexto e Escopo

Os pipelines de processamento assíncrono (*batch*) do monorepo MBFT operam em cadeia sequencial: o
Extrator (PMS-002) gera dados brutos estruturados, o Enriquecedor (PMS-003) normaliza e expande
metadados normativos, o Indexador (PMS-004) produz *chunks* e vetores densos, e o Gerador de Site
Estático (PMS-007) renderiza o portal HTML de consulta.

Se cada pipeline declarasse suas próprias classes de validação ou importasse modelos diretamente do
código-fonte do pipeline produtor, surgiria um acoplamento transitivo severo — obrigando módulos
leves (como o Enriquecedor ou o SSG) a carregar dependências pesadas de visão computacional e GPU
(PyTorch, Docling, `sentence-transformers`) apenas para validar schemas JSON.

Esta PMS especifica o pacote neutro `mbft-core` (`pipelines/core`), que centraliza os contratos
canônicos de domínio (Pydantic v2), enumerações normativas e resolução de diretórios do workspace.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Fornecer um pacote Python leve (`mbft-core`, dependente apenas de `pydantic>=2.0`) como fonte
    única de verdade para os contratos de dados entre os pipelines *batch*.
  * Definir *guardrails* estritos de validação de entrada e saída para cada fronteira de etapa:
    extração (`PMS-002`), enriquecimento (`PMS-003`), indexação (`PMS-004`) e publicação (`PMS-007`).
  * Centralizar a resolução determinística de caminhos de dados do monorepo (`data/raw/`,
    `data/processed/`) de forma independente do diretório de trabalho da execução.
* **Não Objetivos (Non-Goals):**
  * Não é meta incluir regras de negócio, algoritmos de OCR, inferência ou transformações de dados
    dentro do `mbft-core`; o pacote deve conter exclusivamente modelos, constantes e invariantes.
  * Não é meta ser importado em tempo de execução pela aplicação de borda `apps/api` (`mbft-api`,
    PMS-008), visto que o bundler Python do Cloudflare Workers (Pyodide) exige dependências puras
    publicadas no PyPI sem referências a pacotes locais de UV Workspace.

---

## 3. Design da Solução

### 3.1. Topologia de Contratos e Consumidores

O `mbft-core` atua como camada de contrato desacoplada no centro dos pipelines *batch*:

`[ mbft-extrator ] ──> (mbft-core) ──> [ mbft-enriquecedor ] ──> (mbft-core) ──> [ mbft-indexador / mbft-ssg ]`

O pacote é subdividido por domínio de fronteira:

* **Fronteira de Extração (`mbft_core.models.extracao`):**
  - Contratos: `Ficha`, `CampoNormativo`, `FichaMapeada`.
  - **Produtor:** `mbft-extrator` (PMS-002) ao serializar `fichas_mbft.json`.
  - **Consumidores:** `mbft-enriquecedor` (PMS-003) na ingestão e `mbft-ssg` (PMS-007).
* **Fronteira de Enriquecimento (`mbft_core.models.enriquecimento`):**
  - Contratos: `FichaEnriquecida`, `ReferenciaCTB`, `GravidadeEnum`, `CompetenciaEnum`,
    `CompetenciaFonteEnum`.
  - **Produtor:** `mbft-enriquecedor` (PMS-003) ao gerar `fichas_enriquecidas.json`.
  - **Consumidores:** `mbft-indexador` (PMS-004) e `mbft-ssg` (PMS-007).
* **Fronteira de Indexação (`mbft_core.models.indexacao`):**
  - Contratos: `ChunkMetadados`, `ChunkPayload`.
  - **Produtor:** `mbft-indexador` (PMS-004) ao exportar `embeddings_mbft.jsonl`.
* **Contratos da Parte Geral (`mbft_core.models.enriquecimento`):**
  - `TipoSecaoParteGeralEnum`, `ItemGlossario`, `SecaoParteGeral` e `ParteGeralEnriquecida`: definem o contrato canônico de curadoria, glossário e vinculação temática da Parte Geral do MBFT (`parte_geral_enriquecida.json`), produzido pelo `mbft-enriquecedor` (PMS-003) e consumido pelo `mbft-indexador` (PMS-004) e pelo `mbft-ssg` (PMS-007).
* **Resolução de Caminhos (`mbft_core.paths`):**
  - Expõe constantes imutáveis de localização no monorepo (`RAIZ_REPO`, `DATA_DIR`, `RAW_DIR`,
    `PROCESSED_DIR`), ancoradas na descoberta da raiz do UV Workspace.


---

## 4. Alternativas Consideradas

* **Alternativa 1: Importação direta entre pipelines (ex.: `enriquecedor` importar `mbft_extrator.models`).**
  * *Por que foi rejeitada:* Acoplaria a árvore de dependências de todos os pipelines *batch* às
    bibliotecas de visão computacional e CUDA do extrator, inviabilizando execuções leves ou
    isoladas de enriquecimento e geração de site estático.
* **Alternativa 2: Duplicação de modelos Pydantic em cada pacote consumidor.**
  * *Por que foi rejeitada:* Violaria o princípio DRY, permitindo deriva silenciosa de schemas
    (*schema drift*) entre o JSON produzido por uma etapa e o esperado pela etapa seguinte.

---

## 5. Preocupações Transversais

* **Isolamento de Dependências:** O `pyproject.toml` do `mbft-core` é estritamente restrito ao
  `pydantic>=2.0`, proibindo a introdução de bibliotecas de I/O de rede, banco de dados ou ML.
* **Validação Falha-Rápido (*Fail-Fast*):** Qualquer divergência estrutural nos artefatos JSON em
  `data/processed/` interrompe imediatamente o pipeline consumidor na desserialização Pydantic,
  impedindo a propagação silenciosa de dados corrompidos para os índices vetoriais ou para o SSG.
