---
PMS: 008
Título: API Gateway (FastAPI) e Gerenciamento de Fila Global (Ticketizador)
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rejeitado
Tipo: Trilha de Arquitetura e Engenharia (Engineering Track)
Criado: 08-Out-2026
Requer: PMS-005, PMS-006, PMS-007
Substitui: Nenhum
---

# PMS-008: API Gateway e Gerenciamento de Fila Global (Ticketizador)

> **Decisão de Arquitetura (Descontinuação):** O mecanismo de fila serial via D1 (`fila_global`), invalidação por KV (`KV_TICKETS`) e emissão de ingressos JWT foi descontinuado e rejeitado. A mitigação de bots e contenção de concorrência foi delegada nativamente à infraestrutura de borda da Cloudflare (WAF Custom Rules, Rate Limiting e Bot Management), eliminando latência de I/O e custo computacional dentro do Worker Pyodide.

## 1. Contexto e Escopo

Com o sistema de Recuperação (RAG) e a Geração (LLM) desenhados, e com as páginas estáticas pré-processadas (PMS-007), o MBFT necessita de um ponto de entrada unificado: uma API hospedada no **Cloudflare Workers**. 

Dado que o uso de modelos de IA (Workers AI ou Gemini) implica custo por token, precisamos de um mecanismo draconiano de "limite de taxa global" para o consumo do LLM, formatado como um "Ticketizador" (uma fila em que no máximo 1 requisição global de chat seja processada por minuto, protegendo a carteira do mantenedor).

Esta PMS formaliza o uso do **FastAPI** rodando sobre o Pyodide (Python no Cloudflare Workers) e detalha o design do banco transacional para a fila.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Fornecer um *entrypoint* HTTP unificado em **FastAPI** sobre o runtime Python (Pyodide) do Cloudflare Workers (`apps/api`), expondo documentação OpenAPI (`/docs`) e validação via Pydantic.
  * Implementar um limitador de taxa global determinístico (**Ticketizador**) apoiado pelo Cloudflare D1 (`fila_global`), garantindo o teto máximo de 1 requisição pública de chat por minuto.
  * Emitir e validar tickets JWT assinados (`TicketService`) com verificação *stateless* na rota `/chat` e proteção anti-replay via Cloudflare KV (`KV_TICKETS`).
  * Suportar vias expressas de prioridade (`priority_token`) para testes e administração sem bloquear o fluxo de homologação.

* **Não Objetivos (Non-Goals):**
  * Não é meta implementar autenticação de sessão ou cadastro de usuários finais; o controle de acesso público baseia-se exclusivamente em tickets temporais efêmeros.
  * Não é meta manter conexões persistentes (WebSockets) para fila de espera; o cliente aguarda o *timestamp* do ticket localmente (`LocalStorage`) e consulta a rota `/chat` no horário agendado.
  * Não é meta acoplar pacotes locais de workspace como dependências de produção de `apps/api/pyproject.toml`, preservando compatibilidade estrita com o bundler Pyodide do Cloudflare Workers.

---

## 3. Design da Solução

### 3.1. Framework, Runtime e Topologia de Monólito Modular
* O *entrypoint* do Cloudflare Workers (`apps/api`) utiliza **FastAPI**, servido no runtime Python (Pyodide) do Workers pelo servidor ASGI embutido no SDK do runtime (`from workers import asgi`). O adaptador vive em `apps/api/src/entry.py` (`Default = asgi.entrypoint(app)`) e o `main` do `wrangler.jsonc` aponta para ele.
* O adaptador é um módulo de topo, separado do pacote, porque o bundler do Workers carrega o arquivo de `main` como módulo raiz: imports relativos (`from .routers import ...`) não possuem pacote-pai nesse contexto e falham na validação de deploy. O app FastAPI permanece em `mbft_api.main` para uso local via `uvicorn`.
* O bundler **não** resolve as dependências do `pyproject.toml` no momento do upload. As dependências precisam estar vendorizadas em `apps/api/python_modules/`, produzidas por `pywrangler sync` (pacote `workers-py`) a partir do lockfile `apps/api/pylock.toml`. O upload é validado pela Cloudflare, que executa o módulo de entrada e seus imports — um import ausente reprova o deploy com erro `10021`.
* A `compatibility_date` de `apps/api/wrangler.jsonc` é o que fixa o runtime: datas a partir de 08-Set-2026 ativam o **Python 3.14** por padrão (flag `python_workers_314`), o que mantém o `requires-python = ">=3.14"` de `apps/api/pyproject.toml` coerente com o Worker — ele não deve ser ajustado para baixo como forma de contornar falhas de bundling.
* Ganhamos documentação automática `/docs` (Swagger) e validação de payload com Pydantic de forma fluida.
* Para compatibilidade total com o bundler do Cloudflare Workers (que exige dependências PyPI puras em `[project].dependencies` sem pacotes locais de workspace), o pacote `mbft-api` consolida toda a inteligência de borda em uma topologia interna unificada:
  * `mbft_api.routers`: Rotas HTTP (`/health`, `/busca`, `/ticket`, `/chat`).
  * `mbft_api.dependencies`: Provedores de Injeção de Dependência por requisição via `Depends()` (`get_buscador`, `get_gerador`), detectando automaticamente os bindings em `request.scope["env"]` no Cloudflare Workers (`DB`, `VECTORIZE`, `AI`) com fallback para o cache de `app.state` no modo local e suporte a override do provedor LLM via `LLM_PROVIDER`.
  * `mbft_api.recuperador`: Motor de Busca Híbrida RRF e adaptadores locais/Cloudflare (PMS-005).
  * `mbft_api.gerador`: Orquestrador de geração Strict RAG, templates de prompt e adaptadores de LLM (PMS-006).
  * `mbft_api.security`: Emissão, assinatura e validação de Tickets JWT (`TicketService`) com proteção anti-replay via KV (`jti`).
  * `mbft_api.database`: Repositório transacional da fila global (`D1FilaRepository` na nuvem e `SqliteFilaRepository` local).
* O `apps/api/pyproject.toml` declara apenas `fastapi` e `pyjwt` como dependências de produção, isolando pacotes de desenvolvimento e execução local (`uvicorn`, `google-genai`, `pytest`, `python-dotenv`) em `[dependency-groups] dev`.

### 3.2. O "Ticketizador" e a Fila Global (Rate Limiter)
Em vez do tradicional balde furado (Token Bucket), adotamos uma lógica de **Fila Indiana Global**.

1. A rota `/ticket` é o ponto de entrada para quem quer perguntar à IA.
2. Usaremos o banco **Cloudflare D1** (SQLite) com uma tabela de controle: `fila_global` (de linha única).
3. Ao solicitar um ticket, um `UPDATE` atômico ajusta a data `next_available` para `max(now(), next_available) + 1 minuto`. O usuário recebe um token JWT assinado criptograficamente contendo a data/hora exata em que seu ticket se torna válido.
4. Ao chamar a rota `/chat`, o ticket é decodificado (stateless) e seu identificador único (`jti`) é verificado/consumido no Cloudflare KV (`KV_TICKETS`) quando disponível. Se a hora atual for menor que a do ticket, a API recusa com `429 Too Many Requests` avisando o tempo restante.

### 3.3. Vias Expressas (VIP / Prioridades)
Para evitar que a cota global bloqueie usos em apresentação, especialização ou familiares, o Ticketizador aceitará um parâmetro/header de autenticação especial (`priority_token`).
As senhas de privilégio serão configuradas via **Segredos de Ambiente** no painel da Cloudflare (ex: `TOKEN_ADMIN`, `TOKEN_TESTES`).

* **Fluxo Padrão:** +60 segundos de espera na Fila Global.
* **Fluxo Especial/Testes (`TOKEN_TESTES`):** Ticket com +10 segundos de espera.
* **Fluxo Admin (`TOKEN_ADMIN`):** Ticket imediato (fura-fila).

### 3.4. Especificação das Rotas da API

| Método | Rota | Descrição | Integração |
|---|---|---|---|
| `GET` | `/health` | Checagem de vivacidade da API. | N/A |
| `GET` | `/busca` | Executa RAG Híbrido. Retorna JSON com excertos e os `links` para os HTMLs estáticos (`/fichas/XXX.html`) gerados no PMS-007. | `mbft_api.recuperador` e Cloudflare D1/Vectorize |
| `POST`| `/ticket` | Insere o usuário na Fila Global e devolve um Ticket JWT com um "timestamp de embarque". Aceita `priority_token`. | D1 (`fila_global`) |
| `POST`| `/chat` | Recebe a pergunta e o Ticket JWT. Só libera para o `mbft_api.gerador` se o ticket for válido e a hora de embarque tiver chegado. | `mbft_api.recuperador`, `mbft_api.gerador` e KV (`KV_TICKETS`) |

### 3.5. Estrutura do Banco (Migração D1 Necessária)

O schema consolidado em `apps/api/schema.sql` declara a tabela virtual FTS5 de busca textual (`D1RelationalDB`) e a tabela de histórico e cache exato (`HistoricoRepository`):

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS fts_chunks USING fts5(
    id UNINDEXED,
    codigo,
    artigo,
    secao,
    texto_contextualizado,
    tokenize="unicode61 remove_diacritics 1"
);

CREATE TABLE IF NOT EXISTS historico_consultas (
    id TEXT PRIMARY KEY,
    query_hash TEXT NOT NULL,
    pergunta TEXT NOT NULL,
    busca_resultados_json TEXT NOT NULL,
    prompt_completo TEXT NOT NULL,
    resposta TEXT NOT NULL,
    from_cache INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_consultas_query_hash ON historico_consultas (query_hash);
```

---

## 4. Alternativas Consideradas

* **Fila Indiana Global na Aplicação (D1 `fila_global` + KV `KV_TICKETS` + JWT):**
  * *Por que foi rejeitada:* O mecanismo de fila serial via D1 (`fila_global`), invalidação por KV (`KV_TICKETS`) e emissão de ingressos JWT foi descontinuado e rejeitado. A mitigação de bots e contenção de concorrência foi delegada nativamente à infraestrutura de borda da Cloudflare (WAF Custom Rules, Rate Limiting e Bot Management), eliminando latência de I/O e custo computacional dentro do Worker Pyodide.
* **Rate Limiting por Token Bucket tradicional (por IP/usuário):**
  * *Por que foi rejeitada:* Limites por IP não impedem que picos simultâneos de usuários legítimos disparem dezenas de chamadas concorrentes ao LLM no mesmo minuto. A Fila Indiana Global garante matematicamente o teto máximo de 1 requisição pública por minuto, tornando o custo financeiro previsível.
* **Validação Stateful do Ticket no Banco D1 a cada chamada `/chat`:**
  * *Por que foi rejeitada:* Consultar o D1 em toda tentativa prematura de `/chat` geraria leituras desnecessárias sob *polling* do cliente. A validação *stateless* via assinatura HMAC (JWT) barra chamadas adiantadas na borda sem tocar no banco relacional, reservando o KV (`KV_TICKETS`) apenas para o consumo definitivo do `jti`.

---

## 5. Preocupações Transversais

* **Prevenção de Esgotamento de Fila (Cloudflare WAF):**
  Para impedir que um usuário mal-intencionado peça inúmeros tickets em loop (empurrando a fila global horas para o futuro), a rota `/ticket` é protegida pelo **Cloudflare WAF — Rate Limiting**, bloqueando requisições excessivas (ex.: máximo de 1 por minuto por IP) antes que alcancem o Worker ou gerem leituras/escritas no D1. No cliente, o ticket é persistido no `LocalStorage` do navegador.
* **Blindagem de API (Limites de Caracteres e CORS Estrito):**
  * **Validação de Tamanho (FastAPI Query):** A rota `/busca` limita estritamente `q` a **200 caracteres**, e a rota `/chat` limita `pergunta` a **500 caracteres**. Textos fora desse escopo são rejeitados instantaneamente na borda sem acionar modelos, poupando tokens e mitigando *Prompt Injection* ou payloads abusivos.
  * **Política CORS Estrita:** O `CORSMiddleware` rejeita o curinga `allow_origins=["*"]`, aceitando requisições exclusivamente dos domínios oficiais e de ambientes locais (`localhost`).
* **Previsibilidade de Custo e Integração Frontend:**
  O teto de 1 requisição por minuto na camada pública elimina surpresas de faturamento de tokens, a validação *stateless* do JWT reduz o consumo do D1, e a entrega direta dos links estáticos `/fichas/XXX.html` permite que o frontend opere sem estado adicional.
