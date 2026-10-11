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

Para garantir portabilidade e alinhamento com a arquitetura de borda (Cloudflare Workers via Pyodide), o Gerador é desenhado como um submódulo interno (`mbft_api.gerador` em `apps/api/src/mbft_api/gerador/`), desacoplado da camada de roteamento HTTP (`mbft_api.routers`) por contratos explícitos.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Desenvolver o submódulo `mbft_api.gerador` como um componente Python assíncrono e agnóstico de infraestrutura, integrado diretamente ao pacote `apps/api`.
  * Definir contratos rígidos (Interfaces/Protocols) para injeção de dependência do motor LLM, permitindo rodar tanto modelos na borda (Workers AI / Fetch nativo) quanto APIs externas em desenvolvimento local (Gemini).
  * Construir o _System Prompt_ definitivo focado em "Strict RAG" (Zero Alucinação), obrigando o modelo a responder estritamente com base no contexto fornecido.
  * Manter o fluxo _Stateless_ (One-Shot), respondendo perguntas isoladas sem estado ou histórico de conversação.

* **Não Objetivos (Non-Goals):**
  * **Não é meta** acoplar a lógica de prompts e orquestração LLM diretamente às rotas FastAPI (que residem em `mbft_api.routers` conforme a PMS-008).
  * **Não é meta** implementar estratégias de reescrita ou expansão da pergunta do usuário (Query Rewrite) nesta primeira versão. O foco é latência mínima na borda.
  * **Não é meta** implementar histórico de conversação (memória contínua).

---

## 3. Design da Solução

O submódulo `mbft_api.gerador` compartilha a filosofia do Recuperador (`mbft_api.recuperador`): operar dentro do **Monólito Modular** de `apps/api`, puramente tipado e focado em injeção de dependências.

### 3.1. Injeção de Dependência e Isolamento para Pyodide

Para que o código rode nativamente no Cloudflare Workers sem travamentos de pacotes C ou bibliotecas incompatíveis com WebAssembly (e seja facilmente testável localmente), o núcleo do gerador (`interfaces.py`, `orquestrador.py`, `prompts.py` e `__init__.py`) não importa nenhum SDK externo no nível superior.

A classe principal `OrquestradorGeracao` exige a implementação da interface `ILLMClient`:

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

Desta forma, os adaptadores ficam estritamente isolados conforme o ambiente:
* **Ambiente de Borda (`mbft_api.gerador.cloudflare_adapters.WorkersAILLMClient`):** Consumo via binding nativo (`env.AI.run(...)`) do Cloudflare Workers AI, parametrizado pela variável `CF_LLM_MODEL` em `wrangler.jsonc` (com padrão `@cf/meta/llama-3.1-8b-instruct-fp8-fast`) e higienização automática de eventuais blocos `<think>...</think>` caso um modelo de raciocínio (como DeepSeek R1) seja configurado.
* **Ambiente Local (`mbft_api.gerador.local_adapters.GeminiLLMClient`):** Utiliza o SDK `google-genai` (declarado apenas no grupo `[dependency-groups] dev` de `apps/api/pyproject.toml`) e é importado exclusivamente sob demanda (`lazy import`) fora do runtime `emscripten`, evitando contaminar o bundle de produção do Worker. O provedor ativo pode ser sobrescrito via variável de ambiente `LLM_PROVIDER`.

### 3.2. Estratégia de "Strict RAG" e Prevenção de Alucinação

O modelo operará sob regras draconianas para prevenir desvios do Manual Brasileiro de Fiscalização de Trânsito (MBFT). Como modelos menores disponíveis na borda sofrem consideravelmente com instruções negativas complexas em português (ignorando recusas padronizadas, confundindo termos parecidos e adivinhando com base no pré-treino do CTB), a arquitetura parametriza o modelo via `CF_LLM_MODEL` na Cloudflare (padrão `@cf/meta/llama-3.1-8b-instruct-fp8-fast`, suportando troca transparente para modelos como DeepSeek R1 com limpeza de `<think>...</think>`) e **Gemini Flash-Lite** em desenvolvimento local.

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
* **Pacote Separado no Workspace (`packages/gerador`) vs. Submódulo Interno (`mbft_api.gerador`):** Rejeitada a separação em pacote de workspace distinto para evitar dependências locais (`{ workspace = true }`) e dependências transitivas pesadas (`google-genai`) no manifesto de produção de `apps/api/pyproject.toml`. A consolidação em `apps/api/src/mbft_api/gerador/` mantém o contrato desacoplado e simplifica o deploy no Cloudflare Workers.
* **Expansão de Consulta (Query Rewrite):** Rejeitado inicialmente para preservar latência e reduzir custos. A pergunta original do usuário irá diretamente para o fluxo. Se a precisão provar-se baixa em testes empíricos posteriores, uma etapa de reescrita leve poderá ser adicionada.

---

## 5. Preocupações Transversais

* **Segurança de Borda e Rate Limiting:** Embora o controle de fila e autenticação resida na camada da API (PMS-008), o Gerador é desenhado para repassar rapidamente falhas de *Timeout* ou esgotamento de quota de LLM.
* **Tamanho do Contexto (Context Window):** O Gerador implementa uma limitação sobre a quantidade de tokens gerados (`max_tokens=1024`) para garantir que o modelo processe a requisição sem exceder os limites estritos de tempo de execução da arquitetura Workers (Timeout).

