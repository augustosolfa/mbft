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
  * Desenvolver um submódulo Python agnóstico para recuperação de contexto (`mbft_api.recuperador`), integrado diretamente ao pacote da API (`apps/api`).
  * Implementar Busca Híbrida combinando banco vetorial (Cloudflare Vectorize) e busca de texto exato (FTS5 no Cloudflare D1 / SQLite).
  * Consolidar os resultados de múltiplas fontes via algoritmo matemático de fusão (Reciprocal Rank Fusion - RRF).
  * Garantir a testabilidade total da lógica de busca em ambiente local e *offline*, sem depender de infraestrutura em nuvem.

* **Não Objetivos (Non-Goals):**
  * Não é meta acoplar o motor de busca às rotas HTTP. A exposição HTTP cabe à camada de roteadores (`mbft_api.routers`), mantendo `mbft_api.recuperador` puramente focado na recuperação.
  * Não é meta implementar um LLM de Reranking neural denso (como `bge-reranker`) na primeira fase, priorizando o RRF para preservar latência mínima na borda.
  * Não é meta responsabilizar este módulo pela inserção/sincronização de dados. O upload do JSONL é tratado pelo Indexador.

---

## 3. Design da Solução

O submódulo `mbft_api.recuperador` (`apps/api/src/mbft_api/recuperador/`) materializa-se sob a arquitetura de **Monólito Modular** para rodar na borda. Ele reside diretamente na árvore de código do Worker (`apps/api`), desprovido de dependências nativas pesadas (como PyTorch) em seu caminho de execução padrão.

* **Injeção de Dependência (O Coração da Testabilidade):**
  A restrição do ambiente Pyodide no Cloudflare (que depende de *Bindings* como `env.D1` e não bibliotecas nativas de soquetes) força o desacoplamento. 
  A classe `BuscadorHibrido` exige três *Interfaces* (usando `typing.Protocol`) em sua instanciação:
  1. `IVectorDB`: Contrato para busca densa.
  2. `IRelationalDB`: Contrato para busca esparsa/exata.
  3. `IEmbedderClient`: Contrato para a conversão vetorial da pergunta inicial.
  
  Desta forma, durante **Testes Locais**, importam-se sob demanda os adaptadores de `mbft_api.recuperador.local_adapters` (`LocalSqliteDB`, `NumpyVectorDB`, `PyTorchEmbedder`). Em **Produção (Pyodide)**, injetam-se os adaptadores de `mbft_api.recuperador.cloudflare_adapters` (`D1RelationalDB`, `VectorizeDB`, `WorkersAIEmbedder`) sobre os Bindings nativos da Cloudflare (`env.DB`, `env.VECTORIZE`, `env.AI`) sem nunca importar bibliotecas pesadas, compartilhando o formatador de query FTS5 (`formatar_query_fts` / `formatar_token_fts`) entre `LocalSqliteDB` e `D1RelationalDB`.

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
* **Pacote Separado no Workspace (`packages/recuperador`) vs. Submódulo Interno (`mbft_api.recuperador`):**
  * *Por que foi rejeitada a separação física em pacote distinto:* Empacotar `mbft-recuperador` como dependência local (`{ workspace = true }`) em `apps/api/pyproject.toml` complica o *bundling* de dependências para o runtime Pyodide do Cloudflare Workers, que exige dependências puras de pacotes PyPI no `pyproject.toml` do Worker. Consolidar o código em `apps/api/src/mbft_api/recuperador/` elimina dependências cruzadas de workspace e preserva integralmente o isolamento arquitetural via `Protocol`.

---

## 5. Preocupações Transversais

* **Testabilidade e Vendor Lock-in:** 
  O uso de Injeção de Dependência protege a lógica de negócio do ecossistema proprietário da Cloudflare. A matemática do *Reciprocal Rank Fusion* (RRF) é testada em `apps/api/tests/` sem mock servers rebuscados ou necessidade de conexão de rede.
* **Performance e Latência na Borda:**
  Dado que o Pyodide possui tempos de *Cold Start* limitados e penalidades em processamento intensivo de CPU, a escolha do RRF matemático — que avalia posições de listas — mitiga o risco de *Timeout* que acompanharia o processamento de um LLM de Reranking pesado.
* **Armadilhas de Tokenização Lexical (Wildcards em FTS5):**
  Como validado nos testes de aderência com SQLite em memória, a busca híbrida depende da profundidade do *pool* de candidatos de cada banco (e.g. resgatar Top 60 antes de fundir para Top 5 via RRF). Além disso, há distorções na tokenização padrão: injetar curingas (`*`) indiscriminadamente em buscas exatas pode causar *false positives* (e.g. buscar `"I*"` e o FTS5 priorizar os incisos `"II"` e `"III"` por frequência de termo). O formatador `_formatar_token_fts` preserva termos curtos, numéricos e algarismos romanos sem curinga para evitar esse ruído.
* **Adjacência Implícita (AND) na Expressão FTS5:**
  `formatar_query_fts` une os tokens com espaço, expressão que o FTS5 interpreta como conjunção: todos os termos precisam coexistir no mesmo chunk. Perguntas longas, ou com vocabulário distante do texto normativo, podem assim devolver pouquíssimos candidatos esparsos — ou um único — sem que haja defeito na indexação; `sparse = 1` é um resultado legítimo. A cobertura desse caso é papel do lado denso, motivo pelo qual o RRF depende dos dois rankings (ver PMS-010 § 3.2). Ao diagnosticar uma busca degradada, compare as contagens de cada lado antes de suspeitar do índice.
* **Tipagem Estrita e Isolamento de Runtime:**
  As interfaces de busca utilizam exclusivamente tipos nativos da biblioteca padrão (`typing.Protocol`), garantindo que `mbft_api.recuperador` carregue instantaneamente no Pyodide sem exigir pacotes externos além dos já requeridos pela API.

