---
PMS: 006
Título: Design do Gerador RAG (LLM) do MBFT
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 07-Out-2026
Requer: PMS-001, PMS-005
Substitui: Nenhum
---

# PMS-006: Design do Gerador RAG (LLM) do MBFT

## 1. Contexto e Escopo

O **Gerador** é o módulo final do pipeline do mecanismo RAG (Retrieval-Augmented Generation) descrito na PMS-001. A sua responsabilidade é receber a pergunta original do usuário, consolidá-la com o contexto estruturado fornecido pelo Recuperador (PMS-005) e orquestrar a chamada a um Modelo de Linguagem Grande (LLM) para redigir a resposta final.

Para garantir portabilidade e alinhamento com a arquitetura de borda (Cloudflare Workers via Pyodide), o Gerador será desenhado como uma biblioteca embutida (`mbft-gerador`), separada da futura camada de roteamento HTTP (API).

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Desenvolver a biblioteca `mbft-gerador` como um pacote Python assíncrono e agnóstico de infraestrutura.
  * Definir contratos rígidos (Interfaces/Protocols) para injeção de dependência do motor LLM, permitindo rodar tanto modelos na borda (Workers AI) quanto APIs externas (OpenAI, Gemini).
  * Construir o _System Prompt_ definitivo focado em "Strict RAG" (Zero Alucinação), obrigando o modelo a responder estritamente com base no contexto fornecido.
  * Manter o fluxo _Stateless_ (One-Shot), respondendo perguntas isoladas sem estado ou histórico de conversação.

* **Não Objetivos (Non-Goals):**
  * **Não é meta** desenhar ou implementar o servidor web / API FastAPI neste documento. A orquestração HTTP será abordada em uma PMS futura.
  * **Não é meta** implementar estratégias de reescrita ou expansão da pergunta do usuário (Query Rewrite) nesta primeira versão. O foco é latência mínima na borda.
  * **Não é meta** implementar histórico de conversação (memória contínua).

---

## 3. Design da Solução

O pacote `mbft-gerador` compartilhará a filosofia do Recuperador: ser um monólito modular, puramente tipado e focado em injeção de dependências.

### 3.1. Injeção de Dependência (Abstração Híbrida)

Para que o código rode nativamente no Cloudflare Workers sem travamentos de pacotes C (e seja facilmente testável localmente), a dependência do LLM não será baseada em SDKs pesados (`openai`, `google-generativeai`).

A classe principal `OrquestradorGeracao` exigirá a implementação da interface `ILLMClient`:

```python
from typing import Protocol

class ILLMClient(Protocol):
    async def gerar_resposta(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Gera a resposta do LLM com base nos prompts fornecidos."""
        ...
```

Desta forma, criaremos adaptadores enxutos, respeitando as restrições do ecossistema Pyodide (ausência de sockets POSIX tradicionais):
* `CloudflareAIClient`: Para consumo do binding nativo injetado no ambiente (`env.AI.run(...)`) ou abstrações diretas sobre a API `fetch` nativa do JavaScript/V8. O modelo eleito para a geração será o **DeepSeek flash**, hospedado via Cloudflare, balanceando custo e capacidade instrucional.
* `MockLLMClient` / `HTTPClient`: O uso de bibliotecas baseadas em asyncio/sockets como `httpx` será restrito ao ambiente local e testes unitários (ou envelopados via bridge JS para chamadas externas).

### 3.2. Estratégia de "Strict RAG" e Prevenção de Alucinação

O modelo operará sob regras draconianas para prevenir desvios do Manual Brasileiro de Fiscalização de Trânsito (MBFT). Como modelos menores disponíveis na borda (Llama 3 8B, Qwen, Mistral) sofrem consideravelmente com instruções negativas complexas em português (ignorando recusas padronizadas, confundindo termos parecidos e adivinhando com base no pré-treino do CTB), a arquitetura adotará o modelo **DeepSeek flash** hospedado na Cloudflare. Este possui capacidade superior de aderência estrita às restrições do RAG. 

**Regras do System Prompt:**
1. O LLM atua apenas como um sumarizador e tradutor de linguagem natural, nunca como legislador ou juiz.
2. Toda afirmação deve estar ancorada nos trechos do contexto fornecido (Fichas de Enquadramento e Regras Gerais).
3. Se a informação necessária para responder a pergunta não constar no contexto fornecido, o modelo **deve** admitir que não possui a informação, usando uma frase padronizada (ex: *"Não encontrei informações suficientes no contexto do MBFT para responder a esta pergunta."*). É estritamente proibido utilizar conhecimento prévio ou externo sobre o Código de Trânsito Brasileiro.

### 3.3. Construção do Prompt

O módulo será responsável por transformar as estruturas de dados retornadas pelo Recuperador (Fichas e trechos normativos) em texto puro formatado de maneira ótima para consumo pelo LLM (normalmente em Markdown ou YAML estruturado). 

O fluxo de dados será _Stateless_: o usuário fornece a pergunta -> o gerador formata e anexa o contexto -> o LLM responde -> o ciclo se encerra.

---

## 4. Alternativas Consideradas

* **Uso de LangChain / LlamaIndex para a Geração:** Rejeitado pelo mesmo motivo da PMS-005. Frameworks densos quebram facilmente em ambientes como Pyodide/Cloudflare Workers e introduzem latência de inicialização (Cold Start).
* **Expansão de Consulta (Query Rewrite):** Rejeitado inicialmente para preservar latência e reduzir custos. A pergunta original do usuário irá diretamente para o fluxo. Se a precisão provar-se baixa em testes empíricos posteriores, uma etapa de reescrita leve poderá ser adicionada.

---

## 5. Preocupações Transversais

* **Segurança de Borda e Rate Limiting:** Embora a implementação HTTP não seja parte desta PMS, o Gerador será desenhado para repassar rapidamente falhas de *Timeout* ou esgotamento de quota de LLM.
* **Tamanho do Contexto (Context Window):** O Gerador deve implementar uma limitação rígida sobre a quantidade de caracteres/tokens injetada no `user_prompt` para garantir que o modelo processe a requisição sem exceder os limites estritos de tempo de CPU da arquitetura Workers (Timeout), além de respeitar os hiperparâmetros `max_tokens` definidos na requisição.
