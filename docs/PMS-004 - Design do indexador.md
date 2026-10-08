---
PMS: 004
Título: Design do Indexador do MBFT
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 07-Out-2026
Requer: PMS-001, PMS-002, PMS-003
Substitui: Nenhum
---

# PMS-004: Design do Indexador do MBFT

## 1. Contexto e Escopo

No fluxo de extração e RAG do Manual Brasileiro de Fiscalização de Trânsito (MBFT), a etapa de enriquecimento de dados (PMS-003) lida com regras de negócio altamente estáveis. Em contraste, a formulação da **estratégia de recuperação de informações (chunking e embeddings)** é intrinsecamente experimental. As configurações ótimas exigem testes contínuos para balancear a recuperação de contexto pelo modelo contra o excesso de "ruído" nos *prompts*.

Para viabilizar este ciclo ágil de experimentação, foi criado o **Indexador**.

Este pipeline *batch* atua exclusivamente sobre os dados estáticos previamente extraídos, aplicando as diretrizes de quebra semântica, gerando vetores densos via modelo de inteligência artificial na GPU local e exportando o formato final para carga na nuvem.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Desenvolver um pipeline de processamento *batch* (`mbft-indexador`) para ingerir as `fichas_enriquecidas.json`.
  * Aplicar **Segmentação Semântica Contextualizada (Chunking)**, fracionando as 404 fichas por seções temáticas autônomas e injetando prefixos curtos para ancoragem semântica.
  * Gerar vetores densos (1024 dimensões) localmente via modelo `BAAI/bge-m3` acelerado por hardware (CUDA).
  * Serializar o artefato em formato NDJSON (JSONL) para promover a ingestão nativa no Cloudflare Vectorize e D1.
  * Fornecer scripts de implantação (*deploy*) via CLI para sincronização dos dados com a nuvem (Wrangler).

* **Não Objetivos (Non-Goals):**
  * Não é meta processar ou vetorizar a "Parte Geral" normativa nesta fase (isso aguardará a estruturação de regras globais pelo Enriquecedor).
  * Não é meta operar em tempo real nem expor rotas HTTP. O Indexador é estritamente um construtor de *assets* estáticos.
  * Não é meta implementar lógicas de Busca Híbrida ou LLM; estas pertencem ao Recuperador (PMS-005).

---

## 3. Design da Solução

### 3.1. Granularidade de Segmentação e Metadados
Para busca vetorial em RAG jurídico, prefixos monolíticos muito longos causam distorção e diluição vetorial (*attention dilution*), aproximando artificialmente chunks diferentes da mesma ficha. O Indexador adota uma abordagem enxuta separando texto vetorizável de filtros de metadados.

* **Prefixo Enxuto**: O texto a ser embeddado recebe apenas ancoragens críticas:
  ```text
  [Infração {codigo_enquadramento} - {tipificacao_resumida} | {amparo_legal} | {secao}]
  ```
  *(Exemplo: `[Infração 501-0 - Dirigir sem CNH | Art. 162, I | Quando Autuar]`)*

* **Tipos de Chunks por Ficha**: Fragmentados pelas seções (que preenchem a variável `{secao}`):
  `EMENTA`, `QUANDO_AUTUAR`, `QUANDO_NAO_AUTUAR`, `DEFINICOES_PROCEDIMENTOS`, `EXEMPLOS_AIT`, `INFORMACOES_COMPLEMENTARES`.

Atributos administrativos (ex: `gravidade`, `infrator`, `competencia`) são excluídos da vetorização e registrados como **Metadados Estruturados** para viabilizar *pre-filtering* exato.

### 3.2. Geração de Embeddings (`BAAI/bge-m3`)
* **Modelo**: `BAAI/bge-m3`.
* **Dimensão**: 1024 floats de 32 bits (normalizados L2).
* **Limitações da Borda vs Processamento Local**:
  O Indexador gera os embeddings na GPU (FP32). O Recuperador (PMS-005) rodará na Cloudflare consumindo cotas de Neurons e modelos tipicamente quantizados (FP16/INT8). Assume-se que a divergência vetorial residual é tolerável para métricas de similaridade de cosseno.

### 3.3. Contratos de Dados e Artefatos
As 404 fichas geram aproximadamente 1.600 a 2.500 chunks. Considerando os vetores de ponto flutuante, o artefato consome ~15 MB.
* **Formato de Saída (`embeddings_mbft.jsonl`)**: NDJSON. É o formato nativo e obrigatório exigido pelo CLI do Cloudflare Wrangler (`wrangler vectorize insert`).
* **Schema**:
  - `id` (`string`);
  - `values` (`array<float32>`);
  - `metadata` (`object` com filtros administrativos e texto).

---

## 4. Alternativas Consideradas

* **Apache Parquet para Armazenamento Local:**
  * *Por que foi rejeitado:* Embora traga tipagem estrita e compressão, o Parquet demonstrou-se excessivo (*overengineering*) para os modestos ~15 MB do dataset. O JSONL atende perfeitamente à limitação de RAM local e integra-se nativamente e sem fricção à ferramenta da Cloudflare.
* **Prefixo Contextual Monolítico:**
  * *Por que foi rejeitado:* Injetar todo o cabedal burocrático (70-90 tokens listando valores, competências e infratores) no texto do *chunk* causava aproximação indevida dos vetores de uma mesma ficha, anulando as especificidades das infrações. A separação estrita resolve a atenção diluída.

---

## 5. Preocupações Transversais

* **Gerenciamento de Memória (VRAM):**
  Como o motor utiliza `sentence-transformers` sobre PyTorch (CUDA), processar centenas de blocos simultaneamente excederia rapidamente os limites de VRAM da RTX 4070. O design prevê a orquestração via lotes paramétricos (*batch size* de 32 a 64), garantindo estabilidade no pipeline *batch*.
* **Qualidade e Validação Contínua (Recall@K):**
  A adoção de estratégias como o prefixo enxuto requer métricas de prova matemática. O pacote do Indexador possui um laboratório de testes embutido (RAG Offline) suportado por listas YAML de "casos de aderência", monitorando regressões na capacidade do espaço denso em localizar a resposta correta no Top 1 e Top 5.
