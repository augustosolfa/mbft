---
PMS: 008
Título: API Gateway (FastAPI) e Gerenciamento de Fila Global (Ticketizador)
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Arquitetura e Engenharia (Engineering Track)
Criado: 08-Out-2026
Requer: PMS-005, PMS-006, PMS-007
Substitui: Nenhum
---

# PMS-008: API Gateway e Gerenciamento de Fila Global (Ticketizador)

## 1. Contexto e Escopo

Com o sistema de Recuperação (RAG) e a Geração (LLM) desenhados, e com as páginas estáticas pré-processadas (PMS-007), o MBFT necessita de um ponto de entrada unificado: uma API hospedada no **Cloudflare Workers**. 

Dado que o uso de modelos de IA (Workers AI ou Gemini) implica custo por token, precisamos de um mecanismo draconiano de "limite de taxa global" para o consumo do LLM, formatado como um "Ticketizador" (uma fila em que no máximo 1 requisição global de chat seja processada por minuto, protegendo a carteira do mantenedor).

Esta PMS formaliza o uso do **FastAPI** rodando sobre o Pyodide (Python no Cloudflare Workers) e detalha o design do banco transacional para a fila.

---

## 2. Decisões Arquiteturais

### 2.1. Framework, Runtime e Topologia de Monólito Modular
* O *entrypoint* do Cloudflare Workers (`apps/api`) utiliza **FastAPI**, servido nativamente no runtime Python (Pyodide) do Workers.
* Ganhamos documentação automática `/docs` (Swagger) e validação de payload com Pydantic de forma fluida.
* Para compatibilidade total com o bundler do Cloudflare Workers (que exige dependências PyPI puras em `[project].dependencies` sem pacotes locais de workspace), o pacote `mbft-api` consolida toda a inteligência de borda em uma topologia interna unificada:
  * `mbft_api.routers`: Rotas HTTP (`/health`, `/busca`, `/ticket`, `/chat`).
  * `mbft_api.recuperador`: Motor de Busca Híbrida RRF (PMS-005).
  * `mbft_api.gerador`: Orquestrador de geração Strict RAG e templates de prompt (PMS-006).
  * `mbft_api.security`: Emissão, assinatura e validação de Tickets JWT (`TicketService`) com proteção anti-replay via KV (`jti`).
  * `mbft_api.database`: Repositório transacional da fila global (`D1FilaRepository` na nuvem e `SqliteFilaRepository` local).
* O `apps/api/pyproject.toml` declara apenas `fastapi` e `pyjwt` como dependências de produção, isolando pacotes de desenvolvimento e execução local (`uvicorn`, `google-genai`, `pytest`, `python-dotenv`) em `[dependency-groups] dev`.

### 2.2. O "Ticketizador" e a Fila Global (Rate Limiter)
Em vez do tradicional balde furado (Token Bucket), adotamos uma lógica de **Fila Indiana Global**.

1. A rota `/ticket` é o ponto de entrada para quem quer perguntar à IA.
2. Usaremos o banco **Cloudflare D1** (SQLite) com uma tabela de controle: `fila_global` (de linha única).
3. Ao solicitar um ticket, um `UPDATE` atômico ajusta a data `next_available` para `max(now(), next_available) + 1 minuto`. O usuário recebe um token JWT assinado criptograficamente contendo a data/hora exata em que seu ticket se torna válido.
4. Ao chamar a rota `/chat`, o ticket é decodificado (stateless) e seu identificador único (`jti`) é verificado/consumido no Cloudflare KV (`KV_TICKETS`) quando disponível. Se a hora atual for menor que a do ticket, a API recusa com `429 Too Many Requests` avisando o tempo restante. 

### 2.3. Prevenção de Esgotamento de Fila (WAF)
Para impedir que um usuário mal-intencionado peça inúmeros tickets em loop (empurrando a fila global horas para o futuro), a rota `/ticket` será protegida nativamente pelo **Cloudflare WAF (Web Application Firewall) - Rate Limiting**.
Uma regra bloqueará requisições excessivas (ex: máximo de 1 por minuto) vindas do mesmo IP antes mesmo que elas alcancem o Worker ou faturem leitura no banco D1, garantindo custo zero contra abusos. No lado do cliente, o ticket será persistido no `LocalStorage` do navegador.

### 2.4. Blindagem de API: Limites de Caracteres e CORS
Além do rate limiting, a API possui salvaguardas rigorosas contra *Prompt Injection* e abuso de infraestrutura:
* **Validação de Tamanho (FastAPI Query):** A rota de `/busca` limita estritamente `q` a **200 caracteres**, e a rota de `/chat` limita `pergunta` a **500 caracteres**. Textos fora desse escopo são rejeitados instantaneamente no *Edge* sem acionar modelos, poupando tokens e barrando *payloads* gigantes ou ataques DDoS de strings enormes.
* **Política CORS Estrita:** A configuração do `CORSMiddleware` abandonou o curinga `allow_origins=["*"]`. A API aceita requisições exclusivamente dos domínios oficiais (ex: `https://mbft.exemplo.com`) e ambientes locais (`localhost`). Isso inviabiliza que desenvolvedores terceiros embutam o frontend do MBFT em seus sites para sugar nossa fila ou conta da IA.

### 2.5. Vias Expressas (VIP / Prioridades)
Para evitar que a cota global bloqueie usos em apresentação, especialização ou familiares, o Ticketizador aceitará um parâmetro/header de autenticação especial (`priority_token`).
As senhas de privilégio serão configuradas via **Segredos de Ambiente** no painel da Cloudflare (ex: `TOKEN_ADMIN`, `TOKEN_TESTES`).

* **Fluxo Padrão:** +60 segundos de espera na Fila Global.
* **Fluxo Especial/Testes (`TOKEN_TESTES`):** Ticket com +10 segundos de espera.
* **Fluxo Admin (`TOKEN_ADMIN`):** Ticket imediato (fura-fila).

---

## 3. Especificação das Rotas da API

| Método | Rota | Descrição | Integração |
|---|---|---|---|
| `GET` | `/health` | Checagem de vivacidade da API. | N/A |
| `GET` | `/busca` | Executa RAG Híbrido. Retorna JSON com excertos e os `links` para os HTMLs estáticos (`/fichas/XXX.html`) gerados no PMS-007. | `mbft_api.recuperador` e Cloudflare D1/Vectorize |
| `POST`| `/ticket` | Insere o usuário na Fila Global e devolve um Ticket JWT com um "timestamp de embarque". Aceita `priority_token`. | D1 (`fila_global`) |
| `POST`| `/chat` | Recebe a pergunta e o Ticket JWT. Só libera para o `mbft_api.gerador` se o ticket for válido e a hora de embarque tiver chegado. | `mbft_api.recuperador`, `mbft_api.gerador` e KV (`KV_TICKETS`) |

---

## 4. Estrutura do Banco (Migração D1 Necessária)

Será necessário criar a tabela transacional de fila:

```sql
CREATE TABLE fila_global (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    next_available DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO fila_global (id) VALUES (1);
```

---

## 5. Benefícios da Abordagem

1. **Custo Controlado:** É matematicamente impossível gastar mais tokens do que 1 requisição por minuto na camada pública.
2. **Stateless no Chat:** A rota de chat não bate no banco de dados para validar o ticket, reduzindo faturamento do D1 (basta checar a assinatura HMAC do ticket).
3. **Frontend Amigável:** O RAG entrega direto os links estáticos `/fichas/`, permitindo que a SPA do site seja leve e burra (basta colocar a URL em um `<iframe src="...">` ou num link `<a href>`).
