---
PMS: 005
Título: Design do Recuperador do MBFT (RAG)
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 07-Out-2026
Requer: PMS-001, PMS-004
Substitui: Nenhum
---

# PMS-005: Design do Recuperador do MBFT

## 1. Contexto e Escopo

O Recuperador é o motor central do pipeline de RAG (Retrieval-Augmented Generation). Ele atua como a ponte puramente lógica entre a pergunta em linguagem natural do usuário e a base de dados preparada previamente pelo Indexador (PMS-004).

Como provado nos testes de aderência matemática, buscas puramente semânticas (densas) apresentam taxa de erro significativa ao parear nomenclaturas legais exatas (ex.: "Art. 162 I"). Para mitigar isso sem degradar o ecossistema na borda (*edge*), este documento propõe a construção de uma camada de **Busca Híbrida** (amalgamando Dense Retrieval e Sparse Retrieval) empacotada como uma biblioteca limpa e perfeitamente suportada pelo interpretador Python (Pyodide) do **Cloudflare Workers**.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Desenvolver uma biblioteca Python agnóstica para recuperação de contexto.
  * Implementar Busca Híbrida combinando banco vetorial (Cloudflare Vectorize) e busca de texto exato (FTS5 no Cloudflare D1 / SQLite).
  * Consolidar os resultados de múltiplas fontes via algoritmo matemático de fusão (Reciprocal Rank Fusion - RRF).
  * Garantir a testabilidade total da lógica de busca em ambiente local e *offline*, sem depender de infraestrutura em nuvem.

* **Não Objetivos (Non-Goals):**
  * Não é meta transformar o Recuperador em uma API HTTP nesta fase. A exposição via rotas HTTP caberá ao microsserviço maestro (App/API).
  * Não é meta implementar um LLM de Reranking neural denso (como `bge-reranker`) na primeira fase, priorizando o RRF para preservar latência mínima na borda.
  * Não é meta responsabilizar este pacote pela inserção/sincronização de dados. O upload do JSONL é tratado pelo Indexador.

---

## 3. Design da Solução

O pacote `mbft-recuperador` materializar-se-á sob a arquitetura de **Monólito Modular** para rodar na borda. Ele é uma biblioteca embutida, isolada e desprovida de dependências nativas pesadas (como PyTorch).

* **Injeção de Dependência (O Coração da Testabilidade):**
  A restrição do ambiente Pyodide no Cloudflare (que depende de *Bindings* como `env.D1` e não bibliotecas nativas de soquetes) força o desacoplamento. 
  A classe `BuscadorHibrido` exige três *Interfaces* (usando `typing.Protocol`) em sua instanciação:
  1. `IVectorDB`: Contrato para busca densa.
  2. `IRelationalDB`: Contrato para busca esparsa/exata.
  3. `IEmbedderClient`: Contrato para a conversão vetorial da pergunta inicial.
  
  Desta forma, durante **Testes Locais**, injeta-se o `sqlite3` e cálculos locais com `numpy`. Em **Produção**, injetam-se classes invólucro para os Bindings da Cloudflare.

* **Fluxo Coreográfico da Busca (RRF):**
  ```text
  Pergunta -> [ Embedder ] -> Vetor
  Vetor    -> [ Busca Vectorize ] -> Top N (Semântico)
  Pergunta -> [ Busca D1 / FTS5 ] -> Top N (Exato)
  Ambos    -> [ RRF Engine ]      -> Chunk Final Consolidado
  ```

---

## 4. Alternativas Consideradas

* **Uso de LangChain ou LlamaIndex:**
  * *Por que foi rejeitada:* Estes frameworks são excessivamente "inchados" (*bloated*), abstratos e apresentam graves quebras de compatibilidade no Pyodide (Cloudflare Workers). A implementação enxuta focada puramente nas rotinas matemáticas garante latência de instanciamento mínima na *edge*.
* **Microsserviços Distribuídos (Worker conversando com Worker):**
  * *Por que foi rejeitada:* Desacoplar fisicamente o Recuperador do Gerador RAG exigiria requisições HTTP internas. Isso insere latência inaceitável de rede entre os passos e fragmenta o gerenciamento de erros (Rate Limit, Timeout). O monólito modular os une na mesma memória RAM, chamando-se sequencialmente através de módulos padrão do Python.

---

## 5. Preocupações Transversais

* **Testabilidade e Vendor Lock-in:** 
  O uso de Injeção de Dependência protege a lógica de negócio do ecossistema proprietário da Cloudflare. A matemática do *Reciprocal Rank Fusion* (RRF) poderá ser testada em pipelines de CI/CD instantâneos sem mock servers rebuscados ou necessidade de conexão de rede.
* **Performance e Latência na Borda:**
  Dado que o Pyodide possui tempos de *Cold Start* limitados e penalidades em processamento intensivo de CPU, a escolha do RRF matemático — que avalia posições de listas — mitiga o risco de *Timeout* que acompanharia o processamento de um LLM de Reranking pesado.
* **Armadilhas de Tokenização Lexical (Wildcards em FTS5):**
  Como validado nos testes de aderência com SQLite em memória, a busca híbrida depende da profundidade do *pool* de candidatos de cada banco (e.g. resgatar Top 60 antes de fundir para Top 5 via RRF). Além disso, há distorções na tokenização padrão: injetar curingas (`*`) indiscriminadamente em buscas exatas pode causar *false positives* (e.g. buscar `"I*"` e o FTS5 priorizar os incisos `"II"` e `"III"` por frequência de termo). Estratégias futuras de *query expansion* no Gerador LLM (PMS-006) ou ajuste fino no SQL deverão contornar esse ruído.
* **Tipagem Estrita e Confiabilidade:**
  As interfaces e contratos de troca de dados dependem fortemente do módulo `mbft-core`, blindando a borda contra falhas silenciosas ou desvios inesperados nos JSONs de comunicação.
