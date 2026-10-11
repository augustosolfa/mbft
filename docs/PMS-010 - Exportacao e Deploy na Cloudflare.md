---
PMS: 010
Título: Exportadores de Nuvem, Provisionamento e Automação de Deploy na Cloudflare (mbft-deploy)
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Arquitetura e Engenharia (Engineering Track)
Criado: 11-Out-2026
Requer: PMS-004, PMS-007, PMS-008, PMS-009
Substitui: Nenhum
---

# PMS-010: Exportadores de Nuvem, Provisionamento e Automação de Deploy na Cloudflare (mbft-deploy)

## 1. Contexto e Escopo

Os pipelines de dados do monorepo MBFT (`mbft-extrator`, `mbft-enriquecedor`, `mbft-indexador` e
`mbft-ssg`) foram projetados para operar como transformadores puros e determinísticos em lote
(*batch*), lendo contratos de entrada validados pelo `mbft-core` (PMS-009) e gravando os artefatos
canônicos da sua respectiva etapa em `data/processed/<etapa>/`.

A publicação do sistema na infraestrutura de borda da **Cloudflare** (Workers, Pages, D1, Vectorize e
KV) exige etapas de adaptação e transporte que não pertencem a nenhum pipeline isolado:
1. Conversão do artefato canônico `embeddings_mbft.jsonl` em um dump relacional SQL (`fts_chunks.sql`)
   compatível com as restrições transacionais da API HTTP do Cloudflare D1;
2. Provisionamento automatizado de recursos na nuvem e sincronização de identificadores de binding em
   `apps/api/wrangler.jsonc`;
3. Injeção de configuração de ambiente (`config.js`) no site estático e orquestração do deploy
   transversal (dados + API Worker + portal Cloudflare Pages).

Esta PMS especifica o pacote `mbft-deploy` (`deploy/`), isolando toda a responsabilidade de
exportação para nuvem e automação do Wrangler fora das pipelines de processamento de dados e fora do
pacote Pyodide da API.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Desacoplar integralmente as pipelines *batch* (`pipelines/*`) de ferramentas e formatos
    específicos de nuvem (Wrangler CLI, dumps SQL do D1 e URLs de ambiente do Cloudflare Workers).
  * Fornecer um exportador determinístico (`export-d1`) que lê `data/processed/indexador/embeddings_mbft.jsonl`,
    valida cada linha contra o contrato `ChunkPayload` (`mbft-core`) e gera `data/processed/deploy/fts_chunks.sql`
    para popular a tabela virtual FTS5 `fts_chunks` no Cloudflare D1.
  * Automatizar via CLI (`mbft-deploy`) o ciclo completo de provisionamento (`provision`), carga de
    dados (`data`), deploy do Worker FastAPI (`api`) e deploy do portal estático no Pages (`site`).
  * Permitir a injeção da URL de produção da API em `data/processed/site/config.js` no momento do
    deploy sem exigir nova execução da pipeline `mbft-ssg`.

* **Não Objetivos (Non-Goals):**
  * Não é meta gerar embeddings, reprocessar fichas ou renderizar templates HTML dentro do
    `mbft-deploy`; o pacote consome exclusivamente os artefatos prontos em `data/processed/`.
  * Não é meta ser empacotado ou importado em tempo de execução pelo Cloudflare Workers (`apps/api`).

---

## 3. Design da Solução

### 3.1. Topologia Desacoplada de Publicação

O `mbft-deploy` atua na fronteira final entre os artefatos locais de `data/processed/` e a nuvem da
Cloudflare:

```text
[ mbft-indexador ] ──> embeddings_mbft.jsonl ──┬──> [ mbft-deploy export-d1 ] ──> fts_chunks.sql ──> Cloudflare D1
                                               └──> [ mbft-deploy data ] ──────────────────────────> Cloudflare Vectorize
[ mbft-ssg ]       ──> data/processed/site/  ─────> [ mbft-deploy site ] (+ config.js) ────────────> Cloudflare Pages
[ mbft-api ]       ──> apps/api/             ─────> [ mbft-deploy api ]  ──────────────────────────> Cloudflare Workers
```

### 3.2. Exportador SQL FTS5 para Cloudflare D1 (`exporters.py`)
* **Validação de Contrato e Proteção contra Debug:** Antes de exportar ou enviar dados, o módulo
  verifica o nome do arquivo de entrada, rejeitando imediatamente artefatos gerados com
  `--skip-embeddings` (`embeddings_debug.jsonl`), e valida cada linha contra `ChunkPayload`.
* **Idempotência e Restrição de Transação do D1 Remoto:** O endpoint remoto do `wrangler d1 execute`
  rejeita scripts SQL que contenham `BEGIN TRANSACTION` ou `COMMIT` explícitos. O arquivo
  `data/processed/deploy/fts_chunks.sql` inicia com `DELETE FROM fts_chunks;` seguido de instruções
  `INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado) VALUES ...;` agrupadas
  em lotes configuráveis (padrão: 100 tuplas por `INSERT`) com escape estrito de aspas simples.

### 3.3. Desacoplamento de Configuração Frontend (`config.js`) e CORS
* A pipeline `mbft-ssg` (PMS-007) gera um arquivo neutro `data/processed/site/config.js` com
  `window.MBFT_CONFIG = { apiBaseUrl: "" }`.
* Quando acionado com `--api-url` (ou via variável `MBFT_API_URL`), o subcomando `mbft-deploy site`
  sobrescreve apenas o `config.js` antes de invocar `wrangler pages deploy`, preservando a imutabilidade
  do HTML gerado pela pipeline.
* Na `mbft-api` (PMS-008), o middleware `EnvAwareCORSMiddleware` combina dinamicamente as portas
  locais de desenvolvimento com a variável `CORS_ORIGINS` declarada no ambiente ou em `wrangler.jsonc`.

---

## 4. Alternativas Consideradas

* **Alternativa 1: Manter os exportadores e comandos Wrangler dentro das pipelines (`pipelines/indexador`).**
  * *Por que foi rejeitada:* Poluía a pipeline de indexação com responsabilidades de transporte e
    infraestrutura de nuvem (`deploy.py` e flag `--deploy`), violando o princípio de que cada
    pipeline deve apenas produzir os dados canônicos da sua etapa.
* **Alternativa 2: Alocar os scripts de deploy dentro de `apps/api/`.**
  * *Por que foi rejeitada:* O processo de deploy é transversal ao monorepo (envolve dados do
    `indexador`, páginas estáticas do `ssg` para o Cloudflare Pages e o Worker da `api`). Colocar
    essa orquestração dentro de `apps/api` inverteria a hierarquia de responsabilidades e misturaria
    ferramentas locais de build/CLI com o diretório empacotado pelo Pyodide para o Cloudflare Workers.

---

## 5. Preocupações Transversais

* **Prevenção de Poluição de Índices de Produção:** Tanto o exportador SQL (`export-d1`) quanto o
  uploader vetorial (`fazer_deploy_vectorize`) bloqueiam programaticamente qualquer arquivo cujo nome
  contenha `debug`, impedindo que vetores sintéticos (`FakeEmbedder`) sobrescrevam o índice de produção.
* **Execução Segura e Auditável (`--dry-run`):** Todos os subcomandos que invocam o Wrangler suportam
  a flag `--dry-run`, registrando os comandos exatos e diretórios de trabalho sem efetuar mutações na
  conta Cloudflare.
* **Escrita Atômica de Artefatos:** O dump `fts_chunks.sql` é gravado em arquivo temporário (`.tmp`)
  e promovido via `os.replace`, evitando arquivos SQL truncados em caso de interrupção.
