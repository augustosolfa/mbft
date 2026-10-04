# Diretrizes e Instruções do Projeto - MBFT Monorepo

Este documento define os padrões de desenvolvimento, governança de dados, regras estritas de integridade e arquitetura global do monorepo para o processamento e aplicações do Manual Brasileiro de Fiscalização de Trânsito (**MBFT**).

---

## 1. Ambiente, Ferramentas e Padrões de Execução

- **Gerenciador de Pacotes e Workspaces**: Usar SEMPRE `uv` (`uv venv`, `uv pip`, `uv add`, `uv run`, `uv sync`).
- **Arquitetura Monorepo (UV Workspace)**:
  - O `pyproject.toml` da raiz gerencia o workspace (`[tool.uv.workspace]`).
  - Cada componente possui seu próprio subdiretório e `pyproject.toml` declarando dependências específicas.
- **Versão do Python**: Python 3.14 (testado e homologado com CPython 3.14.6).
- **Ambiente Virtual**: Compartilhado na raiz (`.venv`), mantido e sincronizado via `uv sync`.
- **Aceleração de Hardware (GPU / CUDA)**:
  - O PyTorch é instalado a partir do índice oficial CUDA 13.2 (`https://download.pytorch.org/whl/cu132`) com `explicit = true`.
  - O Docling utiliza automaticamente `AcceleratorOptions(device="cuda")` com a GPU instalada (NVIDIA GeForce RTX 4070).

---

## 2. Regras Estritas de Integridade de Arquivos

- **`data/raw/mbft.pdf`**: Arquivo fonte bruto original (105 MB). **NUNCA DEVE SER MODIFICADO OU SOBRESCRITO**.
- **`pipeline_extrator/extrair_mbft_old.py`**: Arquivo de referência histórica. **NUNCA DEVE SER MODIFICADO**. Serve como fonte de consulta para reutilizar heurísticas (ex.: lógica de canais geométricos de colunas e costura entre páginas).

---

## 3. Estrutura Global do Monorepo

```text
mbft/
├── .git/
├── .venv/
├── .gitignore                   # Exclusões do git (ignora data/raw/ e caches)
├── .python-version              # Python 3.14
├── AGENTS.md                    # Entrada de regras de agentes de IA
├── GEMINI.md                    # Governança e regras globais do monorepo
├── README.md                    # Apresentação geral do projeto
├── pyproject.toml               # Raiz do UV Workspace
│
├── data/
│   ├── raw/                     # Dados brutos originais (ex.: mbft.pdf)
│   └── processed/               # Dados tratados e artefatos consolidados
│       ├── fichas_mbft.json     # JSON canônico consolidado
│       ├── mbft_parte_geral.md  # Parte geral normativa em Markdown
│       ├── relatorio_extracao.md
│       ├── imagens/             # Imagens vetoriais e recortes (300 DPI)
│       ├── fichas/              # Fichas individuais JSON (opcional/ignorado no git)
│       └── backup_extracao_v1/  # Backups de segurança de extrações anteriores
│
└── pipeline_extrator/           # Módulo do Extrator Estruturado de Alta Fidelidade
    ├── pyproject.toml           # Dependências e scripts do pacote mbft-extrator
    ├── uv.lock
    ├── README.md                # Especificação técnica detalhada da extração
    ├── extrair.py               # Ponto de entrada CLI do extrator
    ├── extrair_mbft_old.py      # Referência histórica de extração (somente leitura)
    ├── comparar_versoes.py      # Script de auditoria regressiva v1 vs v2
    ├── .cache_extracao/         # Checkpoints intermediários de processamento
    ├── src/mbft_extrator/       # Código-fonte modular do extrator
    └── tests/                   # Casos de teste benchmark e renders visuais
```

---

## 4. Módulos do Sistema

### 4.1. `pipeline_extrator`
Responsável pela extração, fatiamento geométrico, costura de canais paralelos entre páginas, extração semântica via Docling CUDA, estruturação do JSON canônico e geração de HTML e imagens a 300 DPI.
- **Documentação Técnica Completa**: Consulte [pipeline_extrator/README.md](file:///d:/dev/mbft%20-%20extrator/pipeline_extrator/README.md).
- **Casos de Teste Benchmark**: Consulte [pipeline_extrator/tests/casos_de_teste_benchmark.md](file:///d:/dev/mbft%20-%20extrator/pipeline_extrator/tests/casos_de_teste_benchmark.md).

---

## 5. Padrões de Git e Conventional Commits

- Todas as mensagens de commit devem seguir rigorosamente o padrão **Conventional Commits** em português (ex.: `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `perf: ...`).
