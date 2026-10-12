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

A publicação do sistema na infraestrutura de borda da **Cloudflare** (Workers, Pages, D1 e Vectorize)
exige etapas de adaptação e transporte que não pertencem a nenhum pipeline isolado:
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

O subcomando `api` publica o Worker da `mbft-api` (PMS-008), que exige as dependências Python já
vendorizadas em `apps/api/python_modules/` — o bundler do Workers não resolve o `pyproject.toml` no
momento do upload, e a Cloudflare valida executando o módulo de entrada e seus imports.

Essa vendorização é a única etapa do fluxo que **não** roda em qualquer ambiente de desenvolvimento: o
`uv` precisa consultar o interpretador Pyodide para resolver as wheels do alvo, e o `pywrangler` requer
Node no `PATH` (o launcher do Pyodide é executado sob Node). Como o sistema de arquivos virtual do
Pyodide não resolve caminhos no estilo `C:/...`, o `uv` do Windows falha ao consultar o interpretador e
o `python_modules/` não pode ser gerado nativamente nesse sistema operacional — no Windows, a etapa roda
no **WSL2** (ver Alternativa 3).

### 3.2. Exportador SQL FTS5 para Cloudflare D1 (`exporters.py`)
* **Validação de Contrato e Proteção contra Debug:** Antes de exportar ou enviar dados, o módulo
  verifica o nome do arquivo de entrada, rejeitando imediatamente artefatos gerados com
  `--skip-embeddings` (`embeddings_debug.jsonl`), e valida cada linha contra `ChunkPayload`.
* **Idempotência e Restrição de Transação do D1 Remoto:** O endpoint remoto do `wrangler d1 execute`
  rejeita scripts SQL que contenham `BEGIN TRANSACTION` ou `COMMIT` explícitos. O arquivo
  `data/processed/deploy/fts_chunks.sql` inicia com `DELETE FROM fts_chunks;` seguido de instruções
  `INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado) VALUES ...;` agrupadas
  em lotes configuráveis (padrão: 100 tuplas por `INSERT`) com escape estrito de aspas simples.
* **Fatiamento do Upload Vetorial (Teto de 100 MB do Cloudflare Vectorize):** O Vectorize recusa uploads
  acima de 100 MB por chamada. Quando `embeddings_mbft.jsonl` excede esse teto, `dividir_jsonl_vectorize`
  o fatia em `parte_NN.jsonl` (ao lado do artefato de origem), sem cortar linhas ao meio e validando por
  vetor os limites de 64 bytes do `id` e 10 KiB de metadata antes de iniciar o envio. A contagem é feita
  em bytes físicos (leitura e escrita binárias), para não sofrer tradução de newline no Windows.
* **Coerência do Índice Híbrido (D1 + Vectorize):** `embeddings_mbft.jsonl` é a fonte única dos **dois**
  lados da busca: o dump SQL do D1 (FTS5) e os vetores do Vectorize. Um lado vazio não impede a
  publicação — a API responde com o que existir —, mas degrada a recuperação, porque o RRF funde dois
  rankings e, com apenas um deles, a relevância cai e o gerador passa a recusar perguntas legítimas. Por
  isso `mbft-deploy data` publica os dois lados na mesma execução, e a verificação de pós-deploy compara
  a contagem de linhas de `fts_chunks` com a contagem de vetores do índice.

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
* **Alternativa 3: Vendorizar `python_modules/` nativamente no Windows, sem WSL2.**
  * *Por que foi rejeitada:* O `uv` do Windows não consegue consultar o interpretador Pyodide: o launcher
    executa sob Node e o sistema de arquivos virtual do Pyodide não resolve o caminho `C://...` que o
    `uv` injeta no `sys.path`, resultando em `ModuleNotFoundError: No module named 'python'` (reproduzido
    tanto no `uv` 0.12.17 quanto no 0.13.0). Contornar fixando a plataforma (`--python-platform
    wasm32-pyodide2025`) também não serve: as wheels do alvo real (`pyemscripten_2026_0_wasm32`) não casam
    com as tags expostas pelo `uv`, o que deixa `pydantic-core` sem wheel e quebra a resolução. Restou
    executar essa única etapa em ambiente POSIX (WSL2), mantendo o deploy do Worker e do Pages nativo.
* **Alternativa 4: Servir o Worker sem FastAPI, reescrevendo a borda em JavaScript.**
  * *Por que foi rejeitada:* Duplicaria em outra linguagem a lógica já testada de RRF, normalização de
    tokens FTS5, diversificação por ficha e montagem de prompt (PMS-005 e PMS-006), criando duas fontes
    da verdade para o mesmo comportamento. Desde 28-Ago-2026 o FastAPI é suportado oficialmente em Python
    Workers via `workers.asgi`, então o custo de manter a borda em Python é um adaptador de poucas linhas.

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
* **Credenciais Não Interativas e Escopo Fechado:** Antes de despachar qualquer subcomando, a CLI carrega
  **apenas** as variáveis de deploy de um allow-list explícito (`CLOUDFLARE_API_TOKEN`,
  `CLOUDFLARE_ACCOUNT_ID` e `MBFT_API_URL`) a partir do `.env` da raiz, dispensando `wrangler login` em
  execução automatizada; variáveis já definidas no shell têm precedência e nunca são sobrescritas. A lista
  é fechada de propósito: despejar o `.env` inteiro no processo vazaria segredos de outras etapas (por
  exemplo `GEMINI_API_KEY`) para o Wrangler e para todo subprocesso, e ainda tornaria o resultado de um
  teste dependente da ordem de execução de outro.
* **Projeto Pages Idempotente:** O subcomando `site` garante a existência do projeto Cloudflare Pages
  (criando-o com `--production-branch=main` quando ausente e tratando o erro `already exists` como
  sucesso) antes de publicar os assets de `data/processed/site`.
* **Invocação do Wrangler no Windows:** `npx` é um script `.cmd`, que o `CreateProcess` não inicia
  diretamente (`WinError 2`). Quando o resolvedor encontra um `.cmd`/`.bat`, o comando é entregue como
  texto único ao `cmd.exe`, preservando as aspas dos caminhos com espaço. A saída do Wrangler é sempre
  lida como UTF-8 (com substituição de caracteres inválidos), evitando `UnicodeDecodeError` no console
  de código legado do Windows.
