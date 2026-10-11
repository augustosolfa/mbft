---
trigger: glob
globs: "apps/api/**"
description: "Restrições de runtime Pyodide / Cloudflare Workers para o pacote mbft-api"
---

# Guardrails de Runtime e Dependências — `apps/api` (`mbft-api`)

O pacote `apps/api` é executado na borda sobre o runtime Python do **Cloudflare Workers (Pyodide)** (consulte `PMS-005`, `PMS-006` e `PMS-008`):

1. **Dependências Estritas de Produção**:
   - O bloco `[project].dependencies` em `apps/api/pyproject.toml` deve conter **apenas `fastapi` e `pyjwt`**.
   - **Nunca adicione** dependências de outros pacotes do workspace (`mbft-core`, etc.) nem bibliotecas com extensões nativas C/Rust não suportadas pelo bundler Pyodide nas dependências de produção.
2. **Dependências de Desenvolvimento e Testes Locais**:
   - Pacotes usados apenas para execução local, testes ou scripts de validação (como `uvicorn`, `pytest`, `google-genai`) devem ficar estritamente em `[dependency-groups].dev`.
