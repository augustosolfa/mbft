# MBFT - Manual Brasileiro de Fiscalização de Trânsito

**Consulta inteligente, busca híbrida e extração estruturada para as normas de fiscalização de trânsito brasileiras.**

O Manual Brasileiro de Fiscalização de Trânsito (MBFT — Resolução CONTRAN nº 985/2022 e alterações posteriores) é um documento extenso e complexo, cuja versão original em PDF dificulta buscas rápidas e cruzamento de informações no dia a dia. Este monorepo resolve esse problema automatizando a ingestão e estruturação das 402 fichas de fiscalização do manual, disponibilizando os dados por meio de um portal estático de consulta rápida e de um assistente inteligente baseado em RAG (*Retrieval-Augmented Generation*). Suas principais funcionalidades incluem extração de PDF acelerada por GPU, enriquecimento semântico, indexação híbrida (busca textual FTS5 + vetorial densa), geração de páginas estáticas e uma API com fila global de atendimento.

---

## Tabela de conteúdos

- [Tecnologias utilizadas](#tecnologias-utilizadas)
- [Uso de inteligência artificial](#uso-de-inteligência-artificial)
- [Pré-requisitos](#pré-requisitos)
- [Estrutura do Repositório](#️-estrutura-do-repositório)
- [Instalação](#instalação)
- [Como Executar (CLI Unificada `mbft`)](#-como-executar-cli-unificada-mbft)
- [Limitações e próximos passos](#limitações-e-próximos-passos)
- [Licença](#licença)

---

## Tecnologias utilizadas

- **Python 3.14** e **uv** para desenvolvimento, gerenciamento de dependências
  e execução do workspace.
- **FastAPI**, **Pydantic** e **Uvicorn** para os contratos e a API local.
- **Docling**, OCR e **PyTorch com CUDA** para extração e processamento
  acelerado do PDF.
- **sentence-transformers** e o modelo **BAAI/bge-m3** para geração de
  embeddings densos.
- **Jinja2** para geração do site estático e **SQLite/FTS5** para busca textual
  local.
- **Cloudflare Workers**, **D1**, **Vectorize**, **Workers AI** e **Wrangler**
  para hospedagem, persistência, busca vetorial e deploy.
- **pytest** e **pytest-asyncio** para testes unitários, de integração e
  governança documental.

## Uso de inteligência artificial

As ferramentas de inteligência artificial foram utilizadas como apoio ao
desenvolvimento, com revisão e validação dos resultados no código e nos testes:

- **Antigravity com Gemini**: geração principal de código e testes.
- **GitHub Copilot**, utilizando **GPT Luna** e **DeepSeek Flash**: assistência
  complementar na implementação e revisão.
- **Claude Sonnet**, utilizado via web: planejamento e organização das etapas
  do projeto.

Essas ferramentas apoiaram o processo de desenvolvimento, mas não substituem
os testes automatizados, a revisão técnica nem a validação dos resultados.

---

## Pré-requisitos

- Linux ou WSL2; o fluxo de extração e geração de embeddings foi projetado
  para uso com GPU NVIDIA.
- Python 3.14 ou superior e [uv](https://docs.astral.sh/uv/).
- CUDA compatível com a versão do PyTorch instalada pelo projeto para executar
  os pipelines de extração e indexação completos. Os testes rápidos podem ser
  executados sem GPU.
- O arquivo-fonte `data/raw/mbft.pdf`, obtido de forma autorizada, para
  executar a extração. Esse arquivo não é versionado pelo Git.
- Para desenvolvimento local do chat, uma chave `GEMINI_API_KEY` (ou
  `GOOGLE_API_KEY`) válida.
- Para provisionamento e deploy, uma conta Cloudflare com acesso a D1,
  Vectorize e Workers, além de `CLOUDFLARE_API_TOKEN` e
  `CLOUDFLARE_ACCOUNT_ID`.

As credenciais e demais variáveis opcionais estão descritas em
[`.env.example`](./.env.example). Não versione chaves, tokens ou outros
segredos.

---

## 🏗️ Estrutura do Repositório

- **`data/raw/`**: Documento fonte original (`mbft.pdf`).
- **`data/processed/`**: Dados finais consolidados por etapa:
  - **`extrator/`**: `fichas_mbft.json` (402 fichas de fiscalização), `mbft_parte_geral.md` e `imagens/` (300 DPI).
  - **`enriquecedor/`**: `fichas_enriquecidas.json` com metadados normativos e vocabulário expandido.
  - **`indexador/`**: `embeddings_mbft.jsonl` com chunks contextualizados e vetores densos (`BAAI/bge-m3`).
  - **`site/`**: Páginas estáticas HTML geradas para consulta rápida (`/fichas/XXX.html`, `index.html`, `lista.html`, `chat.html`, `404.html`, `config.js`), publicadas como *Static Assets* pelo Worker único `mbft`.
  - **`deploy/`**: `fts_chunks.sql` exportado para carga na tabela virtual FTS5 do Cloudflare D1.
- **`pipelines/`**:
  - **`core/` (`mbft-core`)**: Modelos de domínio e contratos Pydantic compartilhados entre os pipelines (PMS-009).
  - **`extrator/` (`mbft-extrator`)**: Ingestão do PDF, OCR, costura geométrica de colunas e serialização com aceleração CUDA (PMS-002).
  - **`enriquecedor/` (`mbft-enriquecedor`)**: Enriquecimento determinístico e semântico das fichas (PMS-003).
  - **`indexador/` (`mbft-indexador`)**: Geração de chunks e embeddings densos a partir das fichas enriquecidas (PMS-004).
  - **`ssg/` (`mbft-ssg`)**: Gerador de site estático HTML via Jinja2 (PMS-007).
- **`apps/api/` (`mbft-api`)**: Worker único `mbft` (Cloudflare Workers/Pyodide) que serve, na mesma origem, os assets estáticos do SSG e a API Gateway FastAPI, consolidando o **Ticketizador** de fila global (PMS-008), o **Recuperador** de busca híbrida RRF (`mbft_api.recuperador`, PMS-005) e o **Gerador** Strict RAG (`mbft_api.gerador`, PMS-006).
- **`deploy/` (`mbft-deploy`)**: Exportadores de dados para nuvem (`fts_chunks.sql`), provisionamento e automação de deploy do Worker único (API + Static Assets) na Cloudflare via Wrangler (PMS-010).
- **`docs/`**: Propostas de Melhoria do Sistema (PMS) documentando todas as decisões de arquitetura (visão geral do mecanismo RAG na `PMS-001` e template na `PMS-000`).

---

## Instalação

1. **Clone o repositório e acesse o diretório do projeto:**
   ```bash
   git clone https://github.com/augustosolfa/mbft.git
   cd mbft
   ```

2. **Instale e sincronize as dependências do workspace via `uv`:**
   ```bash
   uv sync
   ```

3. **Configure as variáveis de ambiente:**

   Crie um arquivo `.env` na raiz do projeto, ignorado pelo Git, tomando
   [`.env.example`](./.env.example) como base:

   ```bash
   cp .env.example .env
   ```

   Edite o arquivo `.env` e preencha as credenciais necessárias, como
   `GEMINI_API_KEY` para o gerador LLM local e, caso vá realizar deploy,
   `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` e `MBFT_HOSTNAME`.

4. **Adicione o documento-fonte (apenas se for rodar o pipeline de extração):**

   Coloque o arquivo original autorizado do manual em `data/raw/mbft.pdf`.

---

## 🚀 Como Executar (CLI Unificada `mbft`)

Este projeto utiliza o gerenciador de pacotes **`uv`** e centraliza todas as operações no executável **`mbft`**.

### 1. Pipelines de Dados (`mbft pipeline`)

```bash
# Executar todas as 4 etapas em sequência (extrator -> enriquecedor -> indexador -> ssg)
uv run mbft pipeline tudo

# Ou executar apenas uma etapa específica
uv run mbft pipeline extrator
uv run mbft pipeline enriquecedor
uv run mbft pipeline indexador
uv run mbft pipeline ssg
```

### 2. Ambiente de Desenvolvimento Local (`mbft dev`)

O comando carrega automaticamente o arquivo `.env` da raiz do monorepo (quando presente),
sem sobrescrever variáveis já exportadas no shell — é assim que `GEMINI_API_KEY` chega ao
Gerador LLM local. O mesmo arquivo pode definir `MBFT_HOSTNAME` para o deploy.

```bash
# Subir API FastAPI (porta 8000) + Site Estático (porta 3000) simultaneamente
uv run mbft dev

# Ou subir apenas um dos serviços
uv run mbft dev api
uv run mbft dev site
```

Com os serviços locais em execução, você pode interagir com a aplicação pelos
seguintes meios:

- **Portal estático e chat web:** acesse `http://localhost:3000` no navegador.
- **API local e documentação interativa (Swagger):** acesse
  `http://localhost:8000/docs`.

**Exemplo de requisição HTTP via `curl`:**

```bash
# Verificar o status da API local
curl -X GET "http://localhost:8000/health/" -H "Accept: application/json"
```

No Worker publicado, o mesmo endpoint fica disponível com o prefixo externo
`/api`:

```bash
curl -X GET "https://SEU_HOSTNAME/api/health/" -H "Accept: application/json"
```

### 3. Testes, Governança e Benchmarks (`mbft testes`)

```bash
# Suíte rápida (testes unitários de todos os pacotes + governança documental, sem GPU)
uv run mbft testes

# Suíte completa (inclui integração vetorial densa na GPU com BAAI/bge-m3)
uv run mbft testes tudo

# Apenas auditoria de governança documental (PMS / README / pyproject.toml)
uv run mbft testes governanca

# Benchmarks e auditorias específicas
uv run mbft testes recall
uv run mbft testes diff-extracao
uv run mbft testes gerador
```

### 4. Exportação e Deploy na Cloudflare (`mbft deploy`)

```bash
# Provisionar recursos na Cloudflare (D1 e Vectorize) e atualizar wrangler.jsonc
uv run mbft deploy provision

# Exportar SQL FTS5 e publicar Dados (D1/Vectorize) + Worker único `mbft` (API + site estático)
uv run mbft deploy tudo

# Opcional: configurar um Custom Domain (ou definir MBFT_HOSTNAME no .env da raiz)
uv run mbft deploy tudo --hostname mbft.seu-dominio.com
```

## Limitações e próximos passos

- A extração completa e a geração local de embeddings dependem de GPU NVIDIA
  e CUDA; ambientes sem GPU ficam limitados aos testes rápidos ou aos
  artefatos já processados.
- O chat local depende da disponibilidade e das credenciais da API Gemini. O
  deploy em produção depende dos serviços Cloudflare configurados (D1,
  Vectorize, Workers AI e Workers).
- O acesso administrativo depende de Cloudflare Access e de `ADMIN_EMAIL`;
  visitantes anônimos são submetidos às cotas e ao rate limit configurados.
  Isso não substitui uma política de autenticação e autorização adequada para
  novos ambientes de produção.
- A busca atual combina recuperação vetorial e FTS5, mas ainda pode evoluir
  com filtros avançados por código da ficha, órgão, categoria, período e
  outros metadados normativos.
- Próximos passos incluem reduzir a dependência de hardware local, ampliar a
  observabilidade do pipeline e do RAG, documentar políticas operacionais de
  produção e expandir a cobertura de testes de integração e carga.

## Licença

Este projeto é distribuído sob a [Licença MIT](./LICENSE). A licença permite
usar, copiar, modificar e distribuir o código, desde que os avisos de
copyright e de licença sejam preservados. Consulte o texto completo em
[`LICENSE`](./LICENSE) e a descrição oficial da licença na
[Open Source Initiative](https://opensource.org/license/mit/).

Consulte [GEMINI.md](./GEMINI.md) e os guias operacionais de cada módulo ([core](./pipelines/core/README.md), [extrator](./pipelines/extrator/README.md), [enriquecedor](./pipelines/enriquecedor/README.md), [indexador](./pipelines/indexador/README.md), [ssg](./pipelines/ssg/README.md), [api](./apps/api/README.md) e [deploy](./deploy/README.md)) para detalhes técnicos e opções avançadas.
