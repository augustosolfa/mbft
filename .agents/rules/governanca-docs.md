---
trigger: glob
globs: "docs/**, **/README.md, **/pyproject.toml, GEMINI.md, AGENTS.md"
description: "Regras de governança documental, separação PMS vs README e dever de emenda"
---

# Governança de Documentação (Separação de Responsabilidades)

A documentação do monorepo é dividida por finalidade para evitar duplicação de fonte de verdade (DRY) e obsolescência:

| Tipo de Documento | Localização | Papel Arquitetural | O que DEVE conter | O que NÃO DEVE conter |
| :--- | :--- | :--- | :--- | :--- |
| **Apresentação Geral (`README.md`)** | `/README.md` | **Vitrine e Quickstart do Monorepo** | Visão geral do projeto, resumo das camadas e comandos rápidos de ponta a ponta (`uv sync` / `uv run`). | Flags exaustivas de CLI por pacote, árvore interna de `src/` ou racional de design (PMS). |
| **Proposta de Melhoria do Sistema (PMS)** | `docs/PMS-NNN - *.md` | **Design Doc / RFC** (Por que e Como foi desenhado) | Estrutura definida em `docs/PMS-000 - Template de PMS.md`. | Receituários operacionais de execução (runbooks de CLI, instalação ou `pytest`), planos de rollback ou árvores de arquivos internas que mudam sem alterar a arquitetura (citar restrições de CLI/runtime como premissa de design é permitido). |
| **Guia do Pacote (`README.md`)** | `pipelines/*/README.md` e `apps/*/README.md` | **Developer Guide / Runbook** (Como operar, testar e manter) | Comandos de execução (`uv run ...`), flags de CLI, execução de testes e benchmarks, variáveis de ambiente, entradas/saídas em `data/processed/` e estrutura atual de diretórios/módulos (`src/`). | Histórico de alternativas descartadas, justificativas teóricas longas de algoritmos ou duplicação de diagramas de concepção já registrados no PMS correspondente. |

## Critério de Fronteira (Decisão vs. Operação)

- **Vai para a `PMS`**: Tudo que define ou altera uma **decisão arquitetural, algorítmica ou de contrato** (o *porquê*, os invariantes técnicos e os *trade-offs*).
- **Vai para o `README.md`**: Tudo que descreve a **operação e estrutura física atual do código** (comandos CLI, testes e árvore `src/`). Refatorações internas que preservam a arquitetura atualizam apenas o `README.md`.

## Fonte da Verdade sem Petrificação (Dever de Emenda)

- As PMSs são a **fonte da verdade arquitetural** do sistema: o código nunca deve contradizer uma PMS silenciosamente.
- Contudo, **nenhuma PMS é dogma imutável**. Sempre que um agente ou desenvolvedor constatar que uma PMS está barrando um conserto de bug, ganho de qualidade ou melhoria técnica, ele **deve propor explicitamente a revisão da PMS em conjunto com a melhoria do código** (registrando na seção *Alternativas Consideradas* por que a abordagem anterior foi superada).

## Invariantes e Validação Automatizada (`pytest`)

- Todo pacote membro do workspace em `pipelines/*` e `apps/*` DEVE possuir `README.md` declarado em seu `pyproject.toml` (`readme = "README.md"`) e referenciar no cabeçalho o(s) seu(s) respectivo(s) `PMS-NNN`.
- Sempre que alterar documentos Markdown ou `pyproject.toml`, valide a conformidade estrutural executando:
  ```bash
  uv run pytest tests/test_governanca_docs.py
  ```
