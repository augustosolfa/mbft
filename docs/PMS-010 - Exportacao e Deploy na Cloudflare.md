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
3. Publicação do site estático junto do Worker único `mbft`, via Workers Static Assets, no deploy
   transversal (dados + Worker que reúne a API FastAPI e os assets).

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
    dados (`data`) e deploy do Worker único `mbft` (`api`), que publica a API FastAPI e o portal estático.
  * Resolver o hostname de produção por uma precedência explícita (`--hostname` > `MBFT_HOSTNAME` >
    nenhum), declarando um Custom Domain para `<hostname>` sem exigir a repetição do domínio no comando.

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
[ mbft-ssg ]       ──> data/processed/site/  ──┐
                                               ├──> [ mbft-deploy api ] ───────────────────────────> Worker único `mbft`
[ mbft-api ]       ──> apps/api/  ─────────────┘                                                       (Static Assets + FastAPI)
```

O subcomando `api` publica o Worker único `mbft`, que reúne o FastAPI (PMS-008) e os assets estáticos
do SSG (PMS-007). O site deixa de ser um projeto Cloudflare Pages separado: o `wrangler deploy` do
Worker também publica `data/processed/site/` como *Static Assets*.

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

* **Manifesto incremental no D1:** O `mbft-deploy` mantém a tabela operacional `deploy_manifest` em uma
  migração própria, separada do `apps/api/schema.sql`. Há um registro independente para `d1_schema`,
  `d1_content` e `vectorize`, identificado por `(resource_type, resource_name)` e pelo SHA-256 do
  artefato local. A migração usa `CREATE TABLE IF NOT EXISTS`; portanto, tabela ou registros ausentes
  caracterizam bootstrap e fazem a carga necessária, sem erro.
* **Estados e recarga explícita:** Um recurso só pode ser ignorado quando seu hash coincide e o estado é
  `ready`. O fluxo grava `pending` antes de iniciar, `ready` após sucesso e `failed` com a mensagem do
  erro quando uma operação falha. Como D1 e Vectorize não compartilham transação, cada recurso tem seu
  próprio ciclo de confirmação. `data --force` e `tudo --force` ignoram os hashes e repetem a sincronização.

### 3.3. Origem Única do Frontend (`config.js`) e CORS
* A pipeline `mbft-ssg` (PMS-007) gera um arquivo neutro `data/processed/site/config.js` com
  `window.MBFT_CONFIG = { apiBaseUrl: "" }`; o `mbft-deploy` não o sobrescreve mais.
* Como o site e a API passam a ser servidos pelo mesmo Worker, o frontend opera em **origem única**:
  em produção, `apiBaseUrl` vazio resolve para a própria origem e as chamadas usam o prefixo externo
  `/api` (`/api/busca/`, `/api/chat/`). Em desenvolvimento local, o frontend continua apontando para
  `http://127.0.0.1:8000` sem prefixo.
* Na `mbft-api` (PMS-008), o middleware `EnvAwareCORSMiddleware` combina dinamicamente as portas
  locais de desenvolvimento com a variável `CORS_ORIGINS` declarada no ambiente ou em `wrangler.jsonc`.
  A origem do antigo Pages (`https://mbft-site.pages.dev`) foi removida por ser obsoleta.

### 3.4. Worker Único, Static Assets e Resolução de Hostname
* O Worker `mbft` configura `assets.directory` apontando diretamente para `data/processed/site`
  (relativo a `apps/api/wrangler.jsonc`), sem duplicar o artefato canônico do SSG em `apps/api/public/`.
* O roteamento é *assets-first*: arquivos existentes são servidos diretamente e apenas caminhos sem
  asset executam o FastAPI. `assets.run_worker_first = ["/api/*"]` garante que as chamadas de API sob
  `/api` tenham prioridade sem obrigar toda navegação a atravessar o Worker.
* `assets.not_found_handling = "404-page"` faz com que navegações sem asset recebam o `404.html` gerado
  pelo SSG, evitando invocação desnecessária do Worker.
* **Prefixo externo único:** `API_PREFIX = "/api"` é declarado no adapter ASGI
  (`mbft_api.asgi_prefix`) e alimenta tanto a normalização das requisições quanto a regra
  `assets.run_worker_first` do manifesto (`RUN_WORKER_FIRST_PATTERNS`). O `mbft-deploy` valida que o
  manifesto espelha essa constante, impedindo divergência entre o edge e a aplicação. Os routers do
  FastAPI permanecem declarados sem prefixo (`/busca/`, `/chat/`, `/health/`); o adapter remove apenas
  o `/api` externo, preservando também os caminhos sem prefixo.
* **Resolução de hostname:** a precedência é `--hostname` explícito > `MBFT_HOSTNAME` > nenhum
  hostname. Havendo hostname, o deploy declara automaticamente um Custom Domain para `<hostname>` **e
  desativa o `workers_dev`** (para não expor o Worker em `<worker>.<conta>.workers.dev`); sem hostname,
  o `workers_dev` permanece habilitado como único endereço. Como o Wrangler não oferece flag de CLI
  para alternar `workers_dev` — e a declaração do Custom Domain pertence ao arquivo de configuração —,
  o `mbft-deploy` grava um manifesto efêmero ao lado de `wrangler.jsonc` (preservando o
  `assets.directory` relativo) com o valor coerente com o alvo, injeta automaticamente as variáveis
  seguras de ambiente (`ADMIN_EMAIL`, `RATE_LIMIT_SALT` e credenciais do Cloudflare Access), o passa via
  `--config` e o remove em seguida. O domínio e o e-mail de admin nunca são versionados: o `.env` é ignorado
  pelo Git e o `.env.example` contém apenas placeholders.

---

## 4. Alternativas Consideradas

* **Alternativa 1: Manter os exportadores e comandos Wrangler dentro das pipelines (`pipelines/indexador`).**
  * *Por que foi rejeitada:* Poluía a pipeline de indexação com responsabilidades de transporte e
    infraestrutura de nuvem (`deploy.py` e flag `--deploy`), violando o princípio de que cada
    pipeline deve apenas produzir os dados canônicos da sua etapa.
* **Alternativa 2: Alocar os scripts de deploy dentro de `apps/api/`.**
  * *Por que foi rejeitada:* O processo de deploy é transversal ao monorepo (envolve dados do
    `indexador`, os assets estáticos do `ssg` e o Worker da `api`). Colocar
    essa orquestração dentro de `apps/api` inverteria a hierarquia de responsabilidades e misturaria
    ferramentas locais de build/CLI com o diretório empacotado pelo Pyodide para o Cloudflare Workers.
* **Alternativa 3: Vendorizar `python_modules/` nativamente no Windows, sem WSL2.**
  * *Por que foi rejeitada:* O `uv` do Windows não consegue consultar o interpretador Pyodide: o launcher
    executa sob Node e o sistema de arquivos virtual do Pyodide não resolve o caminho `C://...` que o
    `uv` injeta no `sys.path`, resultando em `ModuleNotFoundError: No module named 'python'` (reproduzido
    tanto no `uv` 0.12.17 quanto no 0.13.0). Contornar fixando a plataforma (`--python-platform
    wasm32-pyodide2025`) também não serve: as wheels do alvo real (`pyemscripten_2026_0_wasm32`) não casam
    com as tags expostas pelo `uv`, o que deixa `pydantic-core` sem wheel e quebra a resolução. Restou
    executar essa única etapa em ambiente POSIX (WSL2), mantendo o deploy do Worker nativo no Windows.
* **Alternativa 4: Servir o Worker sem FastAPI, reescrevendo a borda em JavaScript.**
  * *Por que foi rejeitada:* Duplicaria em outra linguagem a lógica já testada de RRF, normalização de
    tokens FTS5, diversificação por ficha e montagem de prompt (PMS-005 e PMS-006), criando duas fontes
    da verdade para o mesmo comportamento. Desde 28-Ago-2026 o FastAPI é suportado oficialmente em Python
    Workers via `workers.asgi`, então o custo de manter a borda em Python é um adaptador de poucas linhas.
* **Alternativa 5: Manter o site em Cloudflare Pages separado e publicar apenas a API no Worker.**
  * *Por que foi superada:* Dois projetos e dois domínios forçavam a injeção da URL da API em `config.js`
    no deploy, o cadastro da origem do Pages em `CORS_ORIGINS` e a manutenção de dois fluxos de
    publicação. Um Worker único com Workers Static Assets serve site e API na mesma origem, elimina a
    injeção de configuração de ambiente e preserva o roteamento *assets-first* (o HTML continua sendo
    servido pelo edge, sem custo de invocação do Worker).

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
  `CLOUDFLARE_ACCOUNT_ID` e `MBFT_HOSTNAME`) a partir do `.env` da raiz, dispensando `wrangler login` em
  execução automatizada; variáveis já definidas no shell têm precedência e nunca são sobrescritas. A lista
  é fechada de propósito: despejar o `.env` inteiro no processo vazaria segredos de outras etapas (por
  exemplo `GEMINI_API_KEY`) para o Wrangler e para todo subprocesso, e ainda tornaria o resultado de um
  teste dependente da ordem de execução de outro.
* **Roteamento Assets-First, 404 Estático e Prefixo Único:** O Worker prioriza os assets estáticos e só
  invoca o FastAPI para caminhos declarados em `assets.run_worker_first` (`/api/*`) ou para requisições
  programáticas sem asset correspondente; navegações sem asset recebem o `404.html` do SSG
  (`not_found_handling = "404-page"`). O prefixo `/api` é uma constante de código consumida tanto pelo
  adapter ASGI quanto pela geração/validação de `assets.run_worker_first`, e o `mbft-deploy` falha se o
  manifesto divergir — evitando que edge e aplicação aceitem caminhos diferentes.
* **Custom Domain fora do Versionamento e Remoção Manual:** O hostname de produção nunca é gravado no
  manifesto versionado: a CLI o resolve por `--hostname` > `MBFT_HOSTNAME` (lendo apenas essa chave do
  `.env`) e valida valores malformados. Durante o deploy, o manifesto efêmero declara o hostname como
  Custom Domain (`routes[].custom_domain = true`) e desativa `workers_dev`, permitindo `--dry-run` para
  inspecionar a configuração final. A migração não exclui
  automaticamente o projeto Pages `mbft-site` nem o Worker `mbft-api`; essa limpeza é uma operação
  manual, executada apenas após confirmar que o Worker único responde corretamente.
* **Invocação do Wrangler no Windows:** `npx` é um script `.cmd`, que o `CreateProcess` não inicia
  diretamente (`WinError 2`). Quando o resolvedor encontra um `.cmd`/`.bat`, o comando é entregue como
  texto único ao `cmd.exe`, preservando as aspas dos caminhos com espaço. A saída do Wrangler é sempre
  lida como UTF-8 (com substituição de caracteres inválidos), evitando `UnicodeDecodeError` no console
  de código legado do Windows.
