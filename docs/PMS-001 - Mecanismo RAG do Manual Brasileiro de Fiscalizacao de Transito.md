---
PMS: 001
Título: Mecanismo RAG do Manual Brasileiro de Fiscalização de Trânsito
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 06-Out-2026
Requer: Nenhum
Substitui: Nenhum
---

# PMS-001: Mecanismo RAG do Manual Brasileiro de Fiscalização de Trânsito

## 1. Contexto e Escopo
O Manual Brasileiro de Fiscalização de Trânsito (MBFT) é um documento oficial, aprovado por Resolução do CONTRAN (Conselho Nacional de Trânsito), destinado a *"autoridades de trânsito, seus agentes e órgãos de julgamento de 1ª e 2ª instâncias"*. [^mbft]
É disponibilizado apenas em formato PDF, tornando difícil a leitura em dispositivos com tela pequena e permitindo apenas a busca textual exata.
Este documento apresenta a visão geral do mecanismo proposto, com a descrição detalhada dos módulos sendo objeto de Propostas de Melhoria do Sistema (PMS) específicas.

[^mbft]: [Manual Brasileiro de Fiscalização de Trânsito.](https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-contran/resolucoes/mbvt20222.pdf)

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Extrair o conteúdo do MBFT de maneira estruturada.
  * Permitir busca semântica por intenção e linguagem natural.
  * Gerar respostas coerentes e contextuais, estritamente limitadas às informações presentes no manual.
  * Apresentar as fichas de enquadramento em formato web responsivo.
  * Fornecer interface web simples para entrada de consultas pelo usuário.

* **Não Objetivos (Non-Goals):**
  * Não é meta aplicar jurisprudência que modifique o entendimento normativo.
  * Não é meta tipificar juridicamente casos concretos em determinados enquadramentos (a responsabilidade da subsunção do fato à norma permanece com o agente/usuário).

---

## 3. Design da Solução

### Etapas / Módulos
O mecanismo divide-se em 5 etapas funcionais, separadas entre processamento assíncrono (*batch*) e atendimento síncrono (*runtime*):

```mermaid
flowchart TD
    subgraph BATCH["🔄 Processamento Assíncrono (Batch / Offline)"]
        PDF["📄 PDF MBFT Oficial\n(826 págs)"]

        subgraph MOD1["1. Extrator (PMS-002)"]
            EXT_PG["Docling Parser\n(Parte Geral pp. 1-31)"]
            EXT_FC["pypdfium2 Vetorial\n(Fichas pp. 32-826)"]
        end

        RAW_MD["mbft_parte_geral.md"]
        RAW_JSON["fichas_mbft.json"]
        RAW_IMG["imagens/*.png"]

        subgraph MOD2["2. Enriquecedor (PMS-003)"]
            NORM["Normalizador de Enums"]
            COMP["Resolução Lei 14.599/23"]
            IE_DET["Extração IE (Regex CTB/CONTRAN)"]
            LLM_FALLBACK["Fallback LLM Gemini 2.5"]
        end

        ENR_JSON["fichas_enriquecidas.json"]

        subgraph MOD3["3. Indexador (PMS-004)"]
            CHUNK["Chunking Semântico Contextual"]
            EMB_GEN["BAAI/bge-m3 (GPU CUDA)"]
        end

        OUT_JSONL["embeddings_mbft.jsonl\n(1024-d Vectors + Metadata)"]

        subgraph MOD7["SSG Generator (PMS-007)"]
            JINJA["Jinja2 + Pico.css"]
        end

        SITE_HTML["Site Estático HTML\n(/fichas/518-51.html)"]
    end

    subgraph STORES["☁️ Provedores & Storage (Cloudflare)"]
        D1[("Cloudflare D1\n(SQLite RDB)")]
        VEC[("Cloudflare Vectorize\n(Vector Index)")]
        PAGES["Cloudflare Pages\n(Static Host)"]
    end

    subgraph RUNTIME["⚡ Atendimento Síncrono (Runtime / Edge)"]
        USER(["👤 Usuário / Agente"])

        subgraph GATEWAY["API Gateway (PMS-008)"]
            FASTAPI["FastAPI / Pyodide Worker"]
            TICKET["Ticketizador & Rate Limiter"]
        end

        subgraph MOD5["4. Recuperador (PMS-005)"]
            RRF["RRF Engine\n(Reciprocal Rank Fusion)"]
        end

        subgraph MOD6["5. Gerador (PMS-006)"]
            PROMPT["Strict RAG System Prompt"]
            LLM["DeepSeek Flash (Workers AI)"]
        end
    end

    %% Flow connections
    PDF --> EXT_PG & EXT_FC
    EXT_PG --> RAW_MD
    EXT_FC --> RAW_JSON & RAW_IMG

    RAW_JSON --> MOD2
    MOD2 --> ENR_JSON

    ENR_JSON --> MOD3
    ENR_JSON --> MOD7

    EMB_GEN --> OUT_JSONL
    OUT_JSONL -->|wrangler insert| VEC
    ENR_JSON -->|SQL Import| D1
    SITE_HTML --> PAGES

    USER -->|Acessa Páginas| PAGES
    USER -->|Requisição /busca ou /chat| FASTAPI
    FASTAPI --> TICKET
    TICKET --> MOD5

    MOD5 -->|Busca Semântica| VEC
    MOD5 -->|Busca Texto FTS5| D1
    RRF --> MOD6
    MOD6 --> LLM
    LLM -->|Resposta Contextual| FASTAPI
    FASTAPI -->|JSON Response| USER
```

1. **Extrator** (PMS-002): recebe o arquivo PDF oficial do MBFT e retorna o texto da parte geral e uma lista em formato JSON com os campos extraídos das fichas de enquadramento, além das imagens associadas.
2. **Enriquecedor** (PMS-003): normaliza campos de dados categóricos (vocabulário controlado) e gera novos atributos estruturados com base em extração de informação (*Information Extraction*) a partir de campos de texto livre (como referências a artigos, flags de crime de trânsito e enquadramentos correlatos). Também realiza a extração de regras globais da Parte Geral para posterior uso em *prompts* (ex: validade de multas).
3. **Indexador** (PMS-004): responsável pela estratégia de *chunking* semântico, geração das representações vetoriais (*embeddings*) e por persistir os dados estruturados no banco relacional SQL e os respectivos vetores de busca no banco vetorial (Cloudflare Vectorize), mantendo a chave identificadora unificada.
4. **Recuperador** (PMS-005): recebe a busca textual do usuário, gera o seu *embedding*, consulta a base vetorial por proximidade semântica e recupera os registros correspondentes hidratados via SQL.
5. **Gerador** (PMS-006): utiliza um LLM para processar a pergunta do usuário, o contexto normativo resgatado pelo recuperador e um *prompt* orientador (com regras de ancoragem factual), devolvendo uma resposta contextualizada ao usuário.

As etapas 1, 2 e 3 são executadas apenas de forma pontual a cada atualização normativa do MBFT.
As etapas 4 e 5 são disponibilizadas para consumo contínuo por meio de uma API REST.

### Front End
Página web estática simples para interação do usuário e consumo da API do sistema.

---

## 4. Alternativas Consideradas

* **Busca Textual via FTS5 (SQLite):** Foi considerado o uso do módulo FTS5 (*Full-Text Search*) nativo do SQLite em vez de *embeddings*. No entanto, a busca puramente sintática não contempla a busca semântica por sinônimos nem a interpretação de descrições fáticas em linguagem natural. O custo computacional e de infraestrutura dos modelos modernos de *embedding* não justifica a perda de precisão e usabilidade.

---

## 5. Preocupações Transversais

* **Controle de Custos e Latência de LLM:** A geração de respostas via LLM apresenta custos e consumo de recursos sensíveis à escala, agravados por acessos automatizados de *crawlers* e *bots*. Devem ser implementados mecanismos de proteção na borda (*rate limiting* e mitigação de bots) e camadas de *cache* (exato e semântico) para reutilizar respostas de consultas frequentes sem disparar novas chamadas ao modelo.