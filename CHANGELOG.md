# Changelog

Todas as mudanças relevantes do MBFT são documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [0.3.0] - 2026-10-12

Primeiro release do sistema publicado como aplicação integrada.

### Adicionado

- CLI unificada `mbft` para executar pipelines, desenvolvimento local, testes e
  deploy.
- Portal estático de consulta das fichas do MBFT, servido junto com a API no
  Worker `mbft`.
- API FastAPI com chat RAG, busca híbrida FTS5/RRF, ticketizador e geração com
  Gemini.
- Cache exato, telemetria do RAG, proteção contra prompt injection e retries no
  cliente Gemini.
- Provisionamento, exportação e deploy na Cloudflare, incluindo D1, Vectorize
  e domínio customizado.
- Rate limit por identidade e integração com Cloudflare Access.
- Painel administrativo e API administrativa com controle de acesso.
- Documentação arquitetural nas PMS e testes de governança, CLI e pipelines.

### Alterado

- Site e API foram consolidados em um único Worker para publicação na mesma
  origem.
- A arquitetura foi reorganizada como monorepo `uv`, com contratos canônicos
  compartilhados entre os pacotes.
- A Parte Geral do MBFT passou a integrar os pipelines, a API e o site.

## [0.2.0] - 2026-10-06

Marco técnico da extração estruturada do manual, conforme registrado pela tag
`v0.2.0-extracao-concluida`.

### Adicionado

- Extrator modular com Docling, OCR, processamento CUDA, costura de colunas e
  renderização de imagens a 300 DPI.
- Extração consolidada das 404 fichas de fiscalização do manual.
- Enriquecimento determinístico, parsing geométrico de cabeçalhos e vocabulário
  expandido.
- Indexação com embeddings densos e recuperação híbrida FTS5/RRF.
- Contratos Pydantic compartilhados e arquitetura documentada nas PMS-001 a
  PMS-003.

### Corrigido

- Fidelidade geométrica, recortes de imagens e campos opcionais da extração.
- Tratamento de tabelas em duas colunas e alinhamento espacial das informações
  complementares.

## [0.1.0] - 2026-10-03

Primeira base funcional do projeto, reconstruída a partir dos commits iniciais
do repositório.

### Adicionado

- Estrutura inicial do projeto e ambiente de desenvolvimento.
- Casos de teste de benchmark, especificações de extração e renderizações
  visuais.
- Primeira implementação modular do extrator MBFT e da extração v1.

### Documentado

- Regras de projeto, convenções de agentes e governança inicial.

[0.3.0]: https://github.com/augustosolfa/mbft/releases/tag/v0.3.0
[0.2.0]: https://github.com/augustosolfa/mbft/releases/tag/v0.2.0
[0.1.0]: https://github.com/augustosolfa/mbft/releases/tag/v0.1.0
