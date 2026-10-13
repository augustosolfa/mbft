# Pipeline Gerador de Site Estático (`mbft-ssg`)

Módulo de processamento em lote (*batch*) responsável pela compilação estática (*Static Site Generation* — SSG) das fichas de enquadramento, índice filtrável e interfaces de consulta do **Manual Brasileiro de Fiscalização de Trânsito (MBFT)** em páginas HTML pré-renderizadas, publicadas como *Static Assets* pelo Worker único `mbft` (PMS-010).

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação completa de arquitetura, decisões de design e trade-offs, consulte a **PMS-007** em `docs/PMS-007 - Site Estático (SSG).md` e a **PMS-008** em `docs/PMS-008 - API e Ticketizador.md`.
> Para o contrato de dados consumido por este pipeline (`FichaEnriquecida`), consulte a **PMS-009** e o pacote **`mbft-core`** em `pipelines/core/README.md`.

---

## 1. Responsabilidades do Módulo

1. **Validação de Contrato e Integridade**:
   - Consome o artefato consolidado do Enriquecedor e valida estritamente cada registro contra o modelo Pydantic `FichaEnriquecida` (`mbft-core`).
   - Garante a unicidade dos identificadores (`ficha.id`), interrompendo o *build* imediatamente caso seja detectada qualquer colisão de rota/arquivo HTML.
2. **Geração das Páginas Individuais de Enquadramento (`fichas/{id}.html`)**:
   - Renderiza cada ficha com *badges* visuais de gravidade, pontuação, penalidades, infratores e medidas administrativas.
   - Estrutura em listas os itens normativos atômicos (*Quando Autuar*, *Quando NÃO Autuar*, *Definições e Procedimentos* e *Exemplos e Observações de AIT*).
   - Injeta de forma controlada o bloco `informacoes_complementares_html` (preservando tabelas normativas extraídas) e vincula as ilustrações correspondentes.
3. **Listagem Completa com Filtragem Client-Side (`lista.html`)**:
   - Embute metadados normalizados diretamente nas linhas da tabela HTML via atributos `data-*` (`data-gravidade`, `data-infratores`, `data-crime`, `data-suspensiva`).
   - Executa filtragem multi-critério instantânea (lógica `AND` combinando busca textual, gravidade, infrator, crime de trânsito e pontuação suspensiva) em **Vanilla JS** direto no DOM do navegador, com **custo zero** de requisições de nuvem/API.
4. **Portal de Busca Vetorial e Oráculo IA (`index.html` e `chat.html`)**:
   - Disponibiliza o portal estático de entrada integrado à rota `/busca` da API RAG e a interface do assistente (**Oráculo MBFT**), que implementa o fluxo visual de fila global (`/ticket` com *countdown* e suporte a `priority-token` + `/chat`).
5. **Empacotamento de Ativos Visuais**:
   - Copia o acervo de ilustrações e placas de sinalização em alta definição (300 DPI) extraídas do PDF para o diretório final de publicação.
6. **Módulo da Parte Geral (`parte-geral/`)**:
   - Gera o índice (`parte-geral/index.html`) com o sumário completo de seções e a tabela do glossário oficial de siglas.
   - Gera páginas dedicadas para cada seção temática (`parte-geral/{slug}.html`, ex.: `pg_8_1.html`), com breadcrumbs, paginação sequencial e fichas de enquadramento vinculadas.
   - Injeta nas fichas os links de medida administrativa apontando para `../parte-geral/{slug}.html` e os enquadramentos correlatos.

---

## 2. Entradas e Saídas

- **Entradas**:
  - `data/processed/enriquecedor/fichas_enriquecidas.json`: Base consolidada e normalizada pelo módulo `mbft-enriquecedor`.
  - `data/processed/enriquecedor/parte_geral_enriquecida.json`: Parte Geral curada (opcional; auto-detectada quando presente) para gerar o índice e as páginas de seção em `parte-geral/`, além das âncoras de medida administrativa nas fichas.
  - `data/processed/extrator/imagens/`: Diretório de imagens e recortes vetoriais/bitmaps gerados pelo módulo `mbft-extrator`.
- **Saída (`data/processed/site/`)**:
  - Diretório autocontido pronto para publicação estática, seguindo a topologia abaixo:

```text
data/processed/site/
├── index.html                 # Portal principal com busca vetorial integrada à API (/busca)
├── lista.html                 # Tabela completa de infrações com filtro multi-critério em Vanilla JS
├── chat.html                  # Interface do Oráculo MBFT integrada ao Ticketizador (/ticket e /chat)
├── 404.html                   # Página de erro 404 consumida por assets.not_found_handling do Worker (PMS-010)
├── admin.html                 # Alias do painel administrativo
├── admin/
│   └── index.html             # Painel administrativo de inspeção do banco D1/SQLite (/admin)
├── config.js                  # Configuração neutra de runtime (window.MBFT_CONFIG.apiBaseUrl)
├── imagens/                   # Cópia das ilustrações e placas de sinalização (300 DPI)
├── parte-geral/               # Subdiretório modular da Parte Geral
│   ├── index.html             # Índice com listagem de seções, contadores e glossário
│   ├── pg_1_2.html            # Páginas individuais por seção normativa ({slug}.html)
│   └── ...
└── fichas/
    ├── 501-00.html            # Página individual da ficha (/fichas/{id}.html)
    └── ...
```

---

## 3. Execução e Preview Local

### 3.1. Geração do Build Estático

Execute os comandos a partir da raiz do monorepo via **`uv`**:

```bash
# Execução direta via entrypoint CLI registrado no workspace
uv run mbft-ssg

# Alternativa via execução direta do módulo Python
uv run python -m mbft_ssg.builder
```

A função `run_build()` em `mbft_ssg.builder` também aceita parâmetros opcionais (`fichas_json`, `templates_dir`, `output_dir`, `imagens_src`) para execuções customizadas ou testes automatizados.

### 3.2. Servidor de Preview Local

Para inspecionar o site estático gerado no navegador:

```bash
# Serve o diretório de saída na porta 3000
uv run python -m http.server 3000 -d data/processed/site
```

Acesse `http://localhost:3000` (ou `http://127.0.0.1:3000`).

> **Integração com a API em Ambiente Local**:
> Os templates `index.html` e `chat.html` detectam automaticamente quando estão sendo servidos a partir de `localhost` ou `127.0.0.1` e direcionam as chamadas de `/busca` e `/chat` para `http://127.0.0.1:8000` (sem prefixo). Em produção, o frontend usa a mesma origem sob o prefixo externo `/api` (`/api/busca/`, `/api/chat/`), roteado para o Worker por `assets.run_worker_first` (PMS-010).
> Enquanto a página `lista.html` e todas as páginas em `fichas/*.html` funcionam de maneira 100% offline, certifique-se de que o servidor da API (`apps/api`) esteja ativo na porta `8000` caso queira testar a busca semântica ou o chat localmente.

---

## 4. Tecnologias e Estrutura do Código-Fonte (`src/mbft_ssg/`)

### Stack Técnica
- **Python 3.14**: Execução gerenciada via `uv` workspace.
- **Jinja2**: Motor de templates com `select_autoescape(["html", "xml"])` habilitado por padrão.
- **`mbft-core` (Pydantic v2)**: Validação de dados e tipagem estrita dos modelos e enumerações do domínio.
- **Pico.css v2 (via CDN) + Vanilla JS**: Estilização responsiva minimalista (*classless*/semântica) e interatividade no cliente sem dependência de *bundlers* ou Node.js.

### Organização dos Arquivos
- **`builder.py`**: Orquestrador do pipeline SSG (`run_build`), responsável pela limpeza do diretório de destino, cópia de imagens, validação Pydantic, verificação de colisões de ID e renderização dos templates Jinja2.
- **`templates/base.html`**: Layout base compartilhado pelas páginas de conteúdo normativo, carregando o Pico.css (*classless*) e definindo os estilos de *badges* de gravidade.
- **`templates/ficha.html`**: Template individual de cada ficha de enquadramento (`/fichas/{id}.html`).
- **`templates/parte_geral_index.html`**: Template do índice da Parte Geral (`/parte-geral/index.html`) com o sumário navegável de seções e tabela do glossário.
- **`templates/parte_geral_secao.html`**: Template individual de seção da Parte Geral (`/parte-geral/{slug}.html`) com breadcrumbs, paginação sequencial e fichas vinculadas.
- **`templates/lista.html`**: Template da tabela completa de infrações com atributos `data-*` e script de filtragem client-side.
- **`templates/index.html`**: Portal inicial com formulário de busca semântica conectado à API e atalhos de navegação.
- **`templates/chat.html`**: Interface do Oráculo MBFT com suporte a fila global (Ticketizador), barra de progresso de espera e envio de token de prioridade (`priority-token`).
