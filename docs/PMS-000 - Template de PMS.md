> **INSTRUÇÃO PARA AGENTES — NÃO IMPLEMENTAR**
>
> Este arquivo é **somente um template reutilizável** de documento SEP. Ele não
> descreve uma demanda de desenvolvimento e não deve ser interpretado como um
> pedido para criar código, funcionalidades ou um produto.
>
> O conteúdo sobre uma **calculadora** abaixo é apenas texto de exemplo para
> preencher a estrutura do template. **Não criar, alterar ou executar uma
> calculadora** com base neste arquivo. Ao usar este template, substitua os
> exemplos pelos requisitos reais do projeto antes de propor qualquer
> implementação.

Modelo de Proposta de Melhoria do Sistema (System Enhancement Proposal)

---
PMS: 001
Título: Motor de Avaliação Simbólica e Expressões Matemáticas
Autor: Seu Nome <seu.email@dominio.com>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 06-Oct-2026
Requer: Nenhum
Substitui: Nenhum
---

# SEP-001: Motor de Avaliação Simbólica e Expressões Matemáticas

## 1. Contexto e Escopo

### O que deve ser colocado aqui (Documento de Design do Google)
Forneça um panorama objetivo e sucinto do cenário tecnológico onde o novo sistema será inserido e o que está sendo construído. Não trate como documento de requisitos de negócio; limite-se aos fatos técnicos de base e assuma que o leitor possui conhecimento prévio de engenharia, linkando documentações detalhadas sempre que necessário. Mantenha o texto estritamente conciso e objetivo.

### Seções da PEP englobadas
* **Resumo (Abstract)** (visão executiva concisa de cerca de 200 palavras resumindo o problema técnico abordado e o escopo da solução proposta).
* **Motivação (Motivation)** (diagnóstico do status quo e deficiências da arquitetura/linguagem atual que tornam o cenário vigente inadequado).
* **Notas de Rodapé (Footnotes)** (links de background, referências técnicas, papers de algoritmos e documentações de suporte preexistentes).

### Exemplo (Calculadora Científica)
O módulo de operações da calculadora atualmente avalia expressões matemáticas concatenando strings diretamente na função interna de execução do runtime. Esse arranjo acarreta inconsistências severas de precisão em ponto flutuante IEEE 754 e impossibilita o suporte robusto a operadores unários e funções trigonométricas compostas (ex.: `sin(cos(x))`). Este documento especifica o novo núcleo de cálculo (Core Engine), baseado em análise léxica formal, geração de Abstract Syntax Tree (AST) e suporte nativo a precisão decimal arbitrária para operações científicas.

---

## 2. Objetivos e Não Objetivos

### O que deve ser colocado aqui (Documento de Design do Google)
Uma lista enxuta de tópicos (*bullet points*) definindo com precisão cirúrgica o que o sistema resolverá (*Objetivos*) e o que ele deliberadamente optou por não resolver (*Não Objetivos*). Não objetivos não são metas negadas óbvias (como "não deve travar"), mas sim funcionalidades e requisitos legítimos que poderiam ser atendidos, mas foram conscientemente deixados de fora para limitar complexidade e focar no propósito central.

### Seções da PEP englobadas
* **Motivação (Motivation)** (definição dos objetivos positivos, metas funcionais diretas e ganhos estruturais esperados).
* **Compatibilidade Retroativa (Backwards Compatibility)** (garantias de compatibilidade legada tratadas como metas formais ou, inversamente, quebras aceitas registradas explicitamente como não objetivos).
* **Questões em Aberto (Open Issues)** (fronteiras temporárias de escopo, registrando pontos ainda não decididos que ficam explicitamente fora da entrega imediata).

### Exemplo (Calculadora Científica)
* **Objetivos (Goals):**
  * Avaliar expressões aritméticas e trigonométricas respeitando precedência matemática formal (PEMDAS/BODMAS).
  * Suportar precisão decimal configurável de até 128 bits via tipos de precisão arbitrária.
  * Manter retrocompatibilidade com o formato de entrada da API básica de cálculo aritmético v1.
* **Não Objetivos (Non-Goals):**
  * Não é meta resolver cálculo simbólico analítico (como derivadas simbólicas ou simplificação algébrica de polinômios).
  * Não é meta implementar renderização gráfica de funções ($f(x)$) em canvas nesta versão do motor.
  * Não é meta fornecer suporte imediato a operações matriciais ou números complexos (postergado para revisões futuras).

---

## 3. Design da Solução

### O que deve ser colocado aqui (Documento de Design do Google)
O núcleo da solução técnica. Deve iniciar por uma visão geral (geralmente acompanhada de um diagrama de contexto do sistema) e aprofundar-se nos contratos de interface (APIs) e estruturas de armazenamento/dados, evitando colar código bruto de schemas que fiquem desatualizados facilmente. O texto deve justificar por que essa arquitetura satisfaz as metas definidas, limitando pseudo-código a casos de algoritmos inéditos ou altamente complexos.

### Seções da PEP englobadas
* **Especificação (Specification)** (contratos formais de API, estruturas de dados centrais, sintaxe, gramática e semântica das novas interfaces).
* **Justificativa (Rationale)** (justificativa técnica interna para a escolha dos algoritmos, tipos de dados e padrões adotados nesta arquitetura).
* **Implementação de Referência (Reference Implementation)** (links para provas de conceito funcionais, protótipos em branches ou diretrizes práticas para a codificação).
* **Compatibilidade Retroativa (Backwards Compatibility)** (camadas de adaptação operacional, flags de transição e fallbacks que mantêm chamadas legadas funcionais).
* **Como Ensinar Isso (How to Teach This)** (modelo mental de uso para outros desenvolvedores, incluindo exemplos de integração com a API e tratamento de erros).

### Exemplo (Calculadora Científica)
O motor divide-se em três etapas: **Tokenizer**, **Parser (Shunting-Yard)** e **Evaluator (Visitor Pattern sobre AST)**.

Fluxo de dados:
`Entrada (String) ──> [ Tokenizer ] ──> [ Parser (AST) ] ──> [ Evaluator ] ──> Resultado Decimal`

* **Interface Pública:**
  A classe de entrada aceita um payload estruturado com expressão e precisão opcional:
  - Assinatura: `evaluate(expression: str, precision: int = 34) -> Decimal`
  - Comportamento: Recebe a expressão textual sanitizada e retorna o valor com precisão numérica controlada.
* **Gramática e Precedência:**
  Operadores unários (`-`, `+`) possuem precedência superior a multiplicações. Chamadas funcionais (`sin`, `log`) operam como nós de argumento único, garantindo associatividade à direita.
* **Camada de Compatibilidade:**
  Chamadas para o endpoint legado `compute(a, b, op)` serão interceptadas por uma fachada (*facade*) que traduz os parâmetros para o formato textual `"a op b"` e repassa ao novo motor sem quebrar clientes legados.

---

## 4. Alternativas Consideradas

### O que deve ser colocado aqui (Documento de Design do Google)
Uma listagem das arquiteturas e soluções alternativas plausíveis que poderiam ter alcançado objetivos semelhantes, mas foram descartadas. Esta seção é crítica porque expõe com transparência os trade-offs considerados, registrando por que o caminho escolhido supera as alternativas diante das restrições e metas do projeto.

### Seções da PEP englobadas
* **Ideias Rejeitadas (Rejected Ideas)** (designs, tecnologias ou abordagens arquiteturais descartadas durante a concepção, explicitando os motivos da rejeição).
* **Justificativa (Rationale)** (análise comparativa explícita de trade-offs de desempenho, manutenibilidade, segurança e complexidade entre o design escolhido e as alternativas descartadas).

### Exemplo (Calculadora Científica)
* **Alternativa 1: Uso da função interna de execução dinâmica (`eval` com sandbox).**
  * *Por que foi rejeitada:* Embora eliminasse a necessidade de construir um parser próprio, o custo de sanitização contra injeção de código e a impossibilidade de controlar a precisão de arredondamento em baixo nível introduziram riscos inaceitáveis de segurança e integridade numérica.
* **Alternativa 2: Avaliação direta via Notação Polonesa Reversa (RPN) linear sem construção de AST.**
  * *Por que foi rejeitada:* Avaliar a pilha RPN diretamente economizaria ciclos de CPU e memória em expressões simples, mas inviabilizaria inspeções semânticas futuras, otimizações de nós de subexpressões repetidas e a expansão planejada para resolução de equações algébricas.

---

## 5. Preocupações Transversais

### O que deve ser colocado aqui (Documento de Design do Google)
Tratamento das preocupações transversais de engenharia que afetam a robustez do sistema, tais como segurança, privacidade, observabilidade (logs, métricas, rastreamento), contenção de falhas e consumo de recursos. Demonstra como o design mitiga impactos sistêmicos de forma preventiva.

### Seções da PEP englobadas
* **Implicações de Segurança (Security Implications)** (análise de superfícies de ataque, vetores de vulnerabilidade, exaustão de recursos computacionais e medidas preventivas).
* **Compatibilidade Retroativa (Backwards Compatibility)** (análise de blast radius e impacto colateral da mudança na estabilidade e confiabilidade do ecossistema dependente).

### Exemplo (Calculadora Científica)
* **Segurança e Proteção contra DoS Algorítmico:**
  * O tamanho da string de entrada é limitado a 2.048 caracteres para mitigar estouro de memória na tokenização.
  * A profundidade máxima da AST é restrita a 50 níveis para prevenir estouro de pilha (*stack overflow*) por recursão aninhada maliciosa (ex.: `((((...))))`).
  * Timeout rígido de execução de 250ms por cálculo no *Evaluator* para barrar expressões propositalmente lentas.
* **Observabilidade e Métricas:**
  * Emissão de métricas em tempo de execução via contadores (`syntax_errors_total`) e histogramas (`evaluation_latency_seconds`).
  * Nenhuma entrada de expressão é logada com identificadores de usuário ou sessão, cumprindo isolamento de dados de usuário.