# Diretrizes e Instruções do Projeto - MBFT Monorepo

Este documento define os padrões de desenvolvimento, governança de dados, regras estritas de integridade e arquitetura global do monorepo para o processamento e aplicações do Manual Brasileiro de Fiscalização de Trânsito (**MBFT**).

---

## 1. Ambiente, Ferramentas e Padrões de Execução

- **Gerenciador de Pacotes**: Usar SEMPRE `uv` (`uv run`, `uv sync`, `uv add`, `uv pip`) — nunca `pip` ou `python` diretamente.
- **Python e CUDA**: Python 3.14 com PyTorch acelerado via GPU/CUDA (preservar a configuração `explicit = true` do índice no `pyproject.toml` da raiz).

---

## 2. Regras Estritas de Integridade de Arquivos

- **`data/raw/mbft.pdf`**: Arquivo fonte bruto original (105 MB). **NUNCA DEVE SER MODIFICADO OU SOBRESCRITO**.

---

## 3. Estrutura Global do Monorepo

```text
mbft/
├── data/
│   ├── raw/                     # Dados brutos originais (mbft.pdf) - NUNCA ALTERAR
│   └── processed/               # Artefatos gerados por etapa (extrator, enriquecedor, indexador, site)
├── docs/                        # Propostas de Melhoria do Sistema (arquitetura geral RAG na PMS-001)
├── pipelines/                   # Pipelines batch (cada pacote possui README.md e PMS associada)
│   ├── core/                    # Contratos canônicos Pydantic v2 compartilhados (mbft-core)
│   ├── extrator/                # Extração estruturada do PDF via Docling/CUDA (mbft-extrator)
│   ├── enriquecedor/            # Enriquecimento determinístico e semântico (mbft-enriquecedor)
│   ├── indexador/               # Geração de chunks e embeddings densos (mbft-indexador)
│   └── ssg/                     # Gerador do portal estático HTML/Jinja2 (mbft-ssg)
├── apps/
│   └── api/                     # API Gateway, Ticketizador e Motor RAG (mbft-api)
└── tests/                       # Testes transversais e auditoria de governança (test_governanca_docs.py)
```

---

## 4. Padrões de Git e Conventional Commits

- Todas as mensagens de commit devem seguir rigorosamente o padrão **Conventional Commits** em português (ex.: `feat: ...`, `fix: ...`, `chore: ...`, `docs: ...`, `refactor: ...`, `perf: ...`).

---

## 5. Governança de Documentação (Separação de Responsabilidades)

Regras detalhadas em [`.agents/rules/governanca-docs.md`](./.agents/rules/governanca-docs.md):

- **Fronteira (`PMS` vs. `README`)**: Decisões arquiteturais, algorítmicas ou de contrato vão para `docs/PMS-NNN` (seguindo `docs/PMS-000 - Template de PMS.md`); operação, flags de CLI, testes e árvore `src/` vão para o `README.md` do pacote.
- **Dever de Emenda**: As PMSs são a fonte da verdade arquitetural, mas não são dogma — se barrarem um conserto de bug ou melhoria técnica, proponha a revisão da PMS (*Alternativas Consideradas*) junto com a alteração do código.
- **Invariantes e Validação (`pytest`)**: Todo pacote exige `README.md` (`readme = "README.md"`) referenciando sua `PMS-NNN`; ao alterar docs ou `pyproject.toml`, valide com `uv run pytest tests/test_governanca_docs.py`.

