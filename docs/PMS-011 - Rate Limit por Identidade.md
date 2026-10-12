---
PMS: 011
Título: Rate Limit por Identidade (IP ou Cloudflare Access) sobre D1
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Ativo
Tipo: Trilha de Arquitetura e Engenharia (Engineering Track)
Criado: 12-Out-2026
Requer: PMS-005, PMS-006, PMS-008
Substitui: Nenhum
---

# PMS-011: Rate Limit por Identidade (IP ou Cloudflare Access) sobre D1

## 1. Contexto e Escopo

`/api/busca` aciona Vectorize, Workers AI (embedding) e D1; `/api/chat` aciona ainda o LLM, com custo por token. O PMS-008 delegou a contenção ao WAF da Cloudflare, mas o WAF não expressa cotas por usuário em janela de 24 h nem distingue visitantes autenticados pelo Cloudflare Access. Este documento especifica um limitador na aplicação (D1), complementar ao WAF.

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Limitar `busca` e `chat` por identidade: intervalo mínimo entre chamadas e cota em janela deslizante de 24 h.
  * Dar cotas maiores a usuários autenticados no Cloudflare Access, sem confiar em headers forjáveis.
  * Não gastar cota diária de LLM em respostas servidas pelo cache exato.
* **Não Objetivos (Non-Goals):**
  * Não é meta substituir o WAF/Bot Management nem conter picos globais de concorrência.
  * Não é meta autenticar usuários: o Access continua sendo o único provedor de login.
  * Não é meta oferecer limpeza exata por Cron Trigger.

## 3. Design da Solução

* **Identidade:** usuário logado é identificado pelo e-mail do JWT do Access (`Cf-Access-Jwt-Assertion` ou cookie `CF_Authorization`), validado localmente (RS256, `iss`, `aud`, `exp`) com as chaves de `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`. Demais requisições usam `cf-connecting-ip` (IPv6 reduzido a /64). Identidades são gravadas como HMAC-SHA256 com o secret `RATE_LIMIT_SALT`.
* **Armazenamento:** tabela `rate_limit_eventos` (`identidade`, `recurso`, `criado_em`, `conta_cota`) no D1 existente. Uma única instrução `INSERT ... SELECT ... WHERE` verifica o intervalo e a cota e grava o evento de forma atômica; só quando bloqueia há consultas extras para calcular `Retry-After`.
* **Limites** (`mbft_api.rate_limit.LIMITES`, fonte única): anônimo — busca 1/30 s e 15/dia, chat 1/30 s e 1/dia; logado — busca 1/10 s e 60/dia, chat 1/30 s e 5/dia. Janelas de `busca` e `chat` são independentes. Cache HIT no chat respeita o intervalo mas não consome a cota diária.
* **Contrato HTTP:** excedido → `429` com `Retry-After` (segundos) e mensagem em português; falha do limitador → `503`.
* **Limpeza:** `DELETE` de eventos com mais de 25 h, disparado de forma oportunista (no máximo a cada 10 min por isolate).

## 4. Alternativas Consideradas

* **Somente WAF Rate Limiting:** rejeitada como solução única; não conta por e-mail nem em janela de 24 h. Permanece como primeira barreira.
* **`ctx.access.getIdentity()`:** rejeitada; Workers com Static Assets não recebem `ctx.access` (router interno) e o contrato em Python Workers é indocumentado.
* **Confiar em `Cf-Access-Authenticated-User-Email`:** rejeitada; fora de um app Access o cliente forja o header e obtém a cota maior.
* **KV / Durable Objects como contador:** rejeitadas; KV é eventualmente consistente e DO adiciona um componente novo. O D1 já está no caminho da requisição.
* **Cron Trigger para limpeza:** adiada; o entrypoint é um ASGI sem handler `scheduled`, e a limpeza oportunista basta.

## 5. Preocupações Transversais

* **Privacidade (LGPD):** nem IP nem e-mail ficam em claro; o sal é secret e os eventos são apagados após 25 h. Logs registram apenas tipo, recurso e resultado.
* **Disponibilidade vs. custo:** o limitador falha fechado (503) se o D1 falhar; é um site experimental e o custo financeiro é a preocupação dominante.
* **Limitações conhecidas:** NAT/CGNAT compartilha cota entre pessoas; atacante com muitos IPs distintos escapa do limite por IP (cobrir com WAF); chamadas que caem no short-circuit de relevância consomem cota por passarem pelo Vectorize.
