---
PMS: NNN
Título: <Título da Proposta>
Autor: <NOME DO AUTOR> <seu.email@dominio.com>
Status: <Rascunho>
Tipo: Trilha de Padronização (Standards Track)
Criado: <DD-Mmm-AAAA> (ex.: 08-Out-2026)
Requer: <Nenhum | PMS-NNN>
Substitui: <Nenhum | PMS-NNN>
---

# PMS-NNN: <Título da Proposta>

> Modelo reutilizável. Substitua todos os campos entre < e > e os exemplos fictícios antes de
> propor qualquer implementação.
## 1. Contexto e Escopo
### O que deve ser colocado aqui (Documento de Design do Google)
Forneça um panorama objetivo e sucinto do cenário tecnológico onde o novo sistema será inserido e
o que está sendo construído. Não trate como documento de requisitos de negócio; limite-se aos fatos
técnicos de base e assuma que o leitor possui conhecimento prévio de engenharia, linkando
documentações detalhadas sempre que necessário. Mantenha o texto estritamente conciso e objetivo.
### Exemplo ilustrativo — fictício (Calculadora Científica)
O módulo de operações da calculadora atualmente avalia expressões matemáticas concatenando strings
diretamente na função interna de execução do runtime. Esse arranjo acarreta inconsistências severas
de precisão em ponto flutuante IEEE 754 e impossibilita o suporte robusto a operadores unários e
funções trigonométricas compostas (ex.: `sin(cos(x))`). Este documento especifica o novo núcleo de
cálculo (Core Engine), baseado em análise léxica formal, geração de Abstract Syntax Tree (AST) e
suporte nativo a precisão decimal arbitrária para operações científicas.

---
## 2. Objetivos e Não Objetivos
### O que deve ser colocado aqui (Documento de Design do Google)
Uma lista enxuta de tópicos (*bullet points*) definindo com precisão cirúrgica o que o sistema
resolverá (*Objetivos*) e o que ele deliberadamente optou por não resolver (*Não Objetivos*). Não
objetivos não são metas negadas óbvias (como "não deve travar"), mas sim funcionalidades e
requisitos legítimos que poderiam ser atendidos, mas foram conscientemente deixados de fora para
limitar complexidade e focar no propósito central.
### Exemplo ilustrativo — fictício (Calculadora Científica)
* **Objetivos (Goals):**
  * Avaliar expressões aritméticas e trigonométricas respeitando precedência formal (PEMDAS/BODMAS).
  * Suportar precisão decimal configurável de até 128 bits via tipos de precisão arbitrária.
  * Manter retrocompatibilidade com o formato de entrada da API básica de cálculo aritmético v1.
* **Não Objetivos (Non-Goals):**
  * Não é meta resolver cálculo simbólico analítico (como derivadas simbólicas ou simplificação
    algébrica de polinômios).
  * Não é meta implementar renderização gráfica de funções ($f(x)$) em canvas nesta versão do motor.
  * Não é meta fornecer suporte imediato a operações matriciais ou números complexos (postergado
    para revisões futuras).

---
## 3. Design da Solução
### O que deve ser colocado aqui (Documento de Design do Google)
O núcleo da solução técnica. Deve iniciar por uma visão geral (geralmente acompanhada de um
diagrama de contexto do sistema) e aprofundar-se nos contratos de interface (APIs) e estruturas de
armazenamento/dados, evitando colar código bruto de schemas que fiquem desatualizados facilmente. O
texto deve justificar por que essa arquitetura satisfaz as metas definidas, limitando pseudo-código
a casos de algoritmos inéditos ou altamente complexos.
### Exemplo ilustrativo — fictício (Calculadora Científica)
O motor divide-se em três etapas: **Tokenizer**, **Parser (Shunting-Yard)** e **Evaluator (Visitor
Pattern sobre AST)**.
Fluxo de dados:
`Entrada (String) ──> [ Tokenizer ] ──> [ Parser (AST) ] ──> [ Evaluator ] ──> Resultado Decimal`
* **Interface Pública:** A classe de entrada aceita um payload estruturado com expressão e precisão:
  - Assinatura: `evaluate(expression: str, precision: int = 34) -> Decimal`
  - Comportamento: Recebe a expressão textual sanitizada e retorna o valor com precisão controlada.
* **Gramática e Precedência:** Operadores unários (`-`, `+`) têm precedência superior a produtos.
  Chamadas funcionais (`sin`, `log`) operam como nós de argumento único, associativos à direita.
* **Camada de Compatibilidade:** Chamadas para o endpoint legado `compute(a, b, op)` são traduzidas
  por uma fachada (*facade*) para o formato textual `"a op b"` e repassadas ao novo motor.

---
## 4. Alternativas Consideradas
### O que deve ser colocado aqui (Documento de Design do Google)
Uma listagem das arquiteturas e soluções alternativas plausíveis que poderiam ter alcançado
objetivos semelhantes, mas foram descartadas. Esta seção é crítica porque expõe com transparência os
trade-offs considerados, registrando por que o caminho escolhido supera as alternativas diante das
restrições e metas do projeto.
### Exemplo ilustrativo — fictício (Calculadora Científica)
* **Alternativa 1: Uso da função interna de execução dinâmica (`eval` com sandbox).**
  * *Por que foi rejeitada:* Embora eliminasse a necessidade de construir um parser próprio, o custo
    de sanitização contra injeção de código e a impossibilidade de controlar a precisão de
    arredondamento em baixo nível introduziram riscos inaceitáveis de segurança e integridade.
* **Alternativa 2: Avaliação direta via Notação Polonesa Reversa (RPN) linear sem AST.**
  * *Por que foi rejeitada:* Avaliar a pilha RPN diretamente economizaria ciclos de CPU e memória em
    expressões simples, mas inviabilizaria inspeções semânticas futuras, otimizações de nós de
    subexpressões repetidas e a expansão planejada para resolução de equações algébricas.

---
## 5. Preocupações Transversais
### O que deve ser colocado aqui (Documento de Design do Google)
Tratamento das preocupações transversais de engenharia que afetam a robustez do sistema, tais como
segurança, privacidade, observabilidade (logs, métricas, rastreamento), contenção de falhas e
consumo de recursos. Demonstra como o design mitiga impactos sistêmicos de forma preventiva.
### Exemplo ilustrativo — fictício (Calculadora Científica)
* **Segurança e Proteção contra DoS Algorítmico:**
  * O tamanho da string de entrada é limitado a 2.048 caracteres para mitigar estouro de memória.
  * A profundidade máxima da AST é restrita a 50 níveis para prevenir estouro de pilha (*stack
    overflow*) por recursão aninhada maliciosa (ex.: `((((...))))`).
  * Timeout rígido de execução de 250ms por cálculo no *Evaluator* para barrar expressões lentas.
* **Observabilidade e Métricas:**
  * Emissão de métricas em tempo de execução via contadores (`syntax_errors_total`) e histogramas
    (`evaluation_latency_seconds`).
  * Nenhuma entrada de expressão é logada com identificadores de usuário ou sessão, cumprindo
    isolamento de dados de usuário.

---
## Anexo A — Mapa de Seções
| Seção deste template | Seção do Google Design Doc | Seções da PEP englobadas |
|---|---|---|
| 1. Contexto e Escopo | Contexto e Escopo | Resumo, Motivação, Notas de Rodapé |
| 2. Objetivos e Não Objetivos | Objetivos e Não Objetivos | Motivação, Compatibilidade, Questões |
| 3. Design da Solução | Design da Solução | Especificação, Justificativa, Implementação etc. |
| 4. Alternativas Consideradas | Alternativas Consideradas | Ideias Rejeitadas, Justificativa |
| 5. Preocupações Transversais | Preocupações Transversais | Segurança, Compatibilidade Retroativa |

---
## Anexo B — Chaves Canônicas do Frontmatter
| Chave | Padrão (Regex) | Descrição |
|---|---|---|
| PMS | `^\d{3}$` | Identificador numérico de 3 dígitos (`001`, `002`, ...) ou `NNN` no template |
| Título | `^[^<>]+$` | Título descritivo da proposta sem placeholders |
| Autor | `^.+ <[^@\s]+@[^@\s]+\.[^@\s]+>$` | Nome completo e e-mail (`Nome <email@dominio>`) |
| Status | `^(Rascunho\|Ativo\|Aceito\|Substituído\|Rejeitado)$` | Estado do documento no ciclo de vida |
| Tipo | `^Trilha de .+ \(.+ Track\)$` | Categoria da proposta (ex.: `Trilha de Padronização (Standards Track)`) |
| Criado | `^\d{2}-[A-Z][a-z]{2}-\d{4}$` | Data de criação no formato `DD-Mmm-AAAA` |
| Requer | `^(Nenhum\|PMS-\d{3}(,\s*PMS-\d{3})*)$` | Lista de dependências (`PMS-NNN`) ou `Nenhum` |
| Substitui | `^(Nenhum\|PMS-\d{3}(,\s*PMS-\d{3})*)$` | Documento substituído (`PMS-NNN`) ou `Nenhum` |