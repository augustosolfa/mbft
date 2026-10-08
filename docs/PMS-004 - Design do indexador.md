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

Este pipeline *batch* atua exclusivamente (nesta primeira fase) sobre:
1. `fichas_enriquecidas.json` (proveniente do Enriquecedor).
*(Nota: O chunking e vetorização da Parte Geral aguardam a extração prévia de regras globais pelo Enriquecedor, não fazendo parte deste escopo inicial).*

As principais responsabilidades deste módulo são:
1. **Segmentação Semântica Contextualizada (Chunking)**: Fracionar as 404 fichas por seções temáticas autônomas, utilizando prefixos curtos para ancoragem semântica e delegando campos administrativos para metadados estruturados.
2. **Geração de Embeddings Densos**: Calcular vetores densos (1024 dimensões em `float32`) utilizando o modelo `BAAI/bge-m3` com aceleração por hardware (PyTorch CUDA).
3. **Serialização e Carga**: Gravar os vetores em formato **NDJSON (JSONL)** e promover a carga nos repositórios do ambiente de runtime (Cloudflare D1 via SQL para metadados/FTS5 e Cloudflare Vectorize para busca semântica).

---

## 2. Granularidade de Segmentação e Metadados

Para busca vetorial em RAG jurídico, prefixos monolíticos muito longos causam distorção e diluição vetorial (*attention dilution*), aproximando artificialmente chunks diferentes da mesma ficha. O Indexador adota uma abordagem enxuta:

### A. Prefixo de Contexto e Metadados
O texto que passará pelo modelo de embedding receberá apenas as ancoragens indispensáveis de domínio e seção:

- **Prefixo Enxuto**:
  ```text
  [Infração {codigo_enquadramento} - {tipificacao_resumida} | {amparo_legal} | {secao}]
  ```
  *(Exemplo: `[Infração 501-0 - Dirigir sem CNH | Art. 162, I | Quando Autuar]`)*

Dessa forma, o prefixo consome apenas ~20 tokens. Atributos administrativos pesados (como `gravidade`, `penalidade`, `infrator`, `competencia`) **não** entram no texto vetorizado; eles são gravados como **Metadados Estruturados** no Cloudflare Vectorize e no SQLite para atuarem como filtros exatos (*pre-filtering*).

### B. Tipos de Chunks por Ficha
As fichas são fragmentadas pelas seguintes seções (que preenchem a variável `{secao}` no prefixo):
1. `EMENTA`: Cabeçalho completo e enquadramento formal;
2. `QUANDO_AUTUAR`: Itens normativos de lavratura do auto;
3. `QUANDO_NAO_AUTUAR`: Exceções e infrações subsidiárias;
4. `DEFINICOES_PROCEDIMENTOS`: Rotinas operacionais e medições;
5. `EXEMPLOS_AIT`: Textos padronizados para observações do auto;
6. `INFORMACOES_COMPLEMENTARES`: Texto de notas técnicas.

---

## 3. Geração de Embeddings (`BAAI/bge-m3`)

- **Modelo**: `BAAI/bge-m3`.
- **Dimensão Vetorial**: 1024 floats de 32 bits (normalizados em norma L2).
- **Justificativa e Paridade Cloudflare**:
  - O Indexador processa os embeddings localmente na GPU (FP32). 
  - A arquitetura prevê que o **Recuperador (PMS-005)** utilizará o modelo `@cf/baai/bge-m3` via Cloudflare Workers AI para inferir a pergunta do usuário.
  - **Atenção (Limitações da Borda):** O modelo da Cloudflare não tem custo zero (consome a cota de Neurons da conta) e tipicamente opera quantizado (FP16/INT8) para otimizar latência, não havendo paridade *bit a bit* exata com o vetor gerado localmente em FP32. Contudo, para métricas de similaridade por cosseno, essa variação decimal é tolerável.
- **Preparação para Busca Híbrida**: O modelo `bge-m3` possui capacidades excepcionais de recuperação *sparse* (lexical). Como a API do Cloudflare Vectorize foca no armazenamento denso, a estratégia de busca híbrida consistirá em cruzar a busca densa (Vectorize) com a busca textual exata (FTS5 do SQLite), fundindo os resultados através de um modelo de reranking (ex: `bge-reranker-base`) na Etapa do Recuperador (PMS-005).

---

## 4. Contratos de Dados e Artefatos (`mbft-core`)

A base do MBFT extraída gera aproximadamente 2.400 a 2.500 chunks para as 404 fichas. Considerando 1024 dimensões de `float32` e os metadados, o volume total de dados gerado é de apenas cerca de **12 a 15 MB**.

1. **Formato de Saída (`embeddings_mbft.jsonl`)**: Ao invés de formatos binários complexos, optou-se pelo arquivo NDJSON (JSONL). Além da simplicidade e baixo overhead para arquivos da ordem de 15 MB, este é o formato nativo exigido pelo CLI do Cloudflare Wrangler para cargas em massa no Vectorize.
2. Estrutura de cada linha JSONL:
   - `id` (`string`, chave primária do chunk);
   - `values` (`array<float32>`, dimensão fixa 1024);
   - `metadata` (`object`):
     - `origem_id` (ficha de origem);
     - `secao`;
     - `codigo`;
     - `artigo`;
     - `texto_contextualizado` (o fragmento com prefixo que foi vetorizado);
     - Demais filtros administrativos (`gravidade`, `competencia`, etc).

---

## 5. Alternativas Consideradas

* **Apache Parquet para Armazenamento Local:**
  * *Por que foi rejeitado:* Embora traga tipagem estrita e compressão, o Parquet demonstrou-se excessivo (*overengineering*) para os modestos ~15 MB do dataset. O JSONL atende perfeitamente à limitação de RAM e integra-se diretamente à ferramenta nativa da Cloudflare.
* **Prefixo Contextual Monolítico:**
  * *Por que foi rejeitado:* Injetar todo o cabedal burocrático (70-90 tokens de competência, valores, infrator, etc.) no texto do *chunk* causava aproximação indevida dos vetores de uma mesma ficha. A separação entre "texto mínimo vetorizável" e "metadados estruturados" resolve o problema de atenção diluída.
