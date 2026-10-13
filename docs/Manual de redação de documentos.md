# Manual de Redação de Documentos e Mensagens de Commit

Este manual estabelece as diretrizes, boas práticas e padrões para a elaboração de documentação técnica e redação de mensagens de commit no projeto **MBFT (Manual Brasileiro de Fiscalização de Trânsito)**. Seu objetivo é servir como guia prático para desenvolvedores e agentes de IA, garantindo clareza, concisão e manutenção sustentável da documentação do ecossistema.

---

## 1. Princípios Fundamentais para Projetos Enxutos

Em projetos pequenos a médios (ou monorepos enxutos), o excesso de documentação desatualizada é tão prejudicial quanto a ausência de documentação. A documentação deve ser tratada como código: testável, viva e mantida com o mínimo de fricção possível.

1. **Princípio DRY (*Don't Repeat Yourself*) na Documentação**:
   - Cada informação deve possuir uma única fonte da verdade (*Single Source of Truth*).
   - Não duplique explicações arquiteturais nos READMEs nem cole trechos de código operacionais dentro das Propostas de Melhoria do Sistema (PMS).
2. **Documentação Direta e Orientada ao Leitor**:
   - Assuma que o leitor possui conhecimento técnico básico de engenharia de software e da linguagem do projeto (Python/TypeScript).
   - Vá direto ao ponto: evite introduções prolixas, firulas mercadológicas ou justificativas genéricas (ex.: "este projeto foi feito para facilitar...").
3. **Código Autoexplicativo vs. Documentação de Intenção**:
   - O código-fonte diz **o que** e **como** o sistema faz.
   - A documentação deve focar em **por que** foi feito dessa forma, quais restrições moldaram a decisão e **como operar** a solução.
4. **Princípio do Menor Esforço de Manutenção**:
   - Dê preferência a tabelas, diagramas conceituais simples em texto/Mermaid e listas tópicas em vez de parágrafos extensos.
   - Documentos mais curtos e estruturados são lidos e mantidos com maior frequência.

---

## 2. Taxonomia da Documentação no Monorepo MBFT

A documentação do ecossistema MBFT é estruturada em camadas bem definidas para evitar sobreposição de responsabilidades.

### 2.1. README Principal (`/README.md`)
* **Papel**: Vitrine do repositório e *Quickstart* global.
* **O que DEVE conter**:
  - Visão geral sucinta do propósito do projeto MBFT.
  - Diagrama de alto nível do repositório ou mapa dos diretórios principais.
  - Comandos rápidos de ponta a ponta (`uv sync`, `uv run mbft pipeline tudo`, `uv run mbft dev`).
  - Links de navegação para os guias dos subpacotes e documentos de arquitetura.
* **O que NÃO DEVE conter**:
  - Detalhamento de flags secundárias de CLI por subpacote.
  - Razões e discussões teóricas sobre escolhas de algoritmos.
  - Estrutura interna de arquivos do código fonte (`src/`).

### 2.2. Guia do Pacote (`pipelines/*/README.md`, `apps/*/README.md`, `deploy/README.md`)
* **Papel**: *Developer Guide* e *Runbook* operacional do componente.
* **O que DEVE conter**:
  - Referência expressa à PMS correspondente no cabeçalho (ex.: `Referência Arquitetural: PMS-002`).
  - Guia de execução rápida e opções de CLI específicas do pacote.
  - Entradas e saídas de dados esperadas (arquivos em `data/processed/`).
  - Variáveis de ambiente exigidas.
  - Comandos para testes unitários, de integração ou benchmarks do pacote.
* **O que NÃO DEVE conter**:
  - Histórico de alternativas descartadas ou fundamentação teórica longa (deve ficar na PMS).
  - Duplicação de diagramas ou conceitos genéricos de outros componentes.

### 2.3. Propostas de Melhoria do Sistema (`docs/PMS-NNN - *.md`)
* **Papel**: Documento de Design Arquitetural (*Design Doc* / RFC).
* **O que DEVE conter**:
  - Formato estrito definido pelo modelo `docs/PMS-000 - Template de PMS.md`.
  - **Contexto e Escopo**: Cenário técnico sucinto sem jargões de negócio desnecessários.
  - **Objetivos e Não Objetivos**: Metas precisas e delimitação clara do que foi deixado de fora intencionalmente.
  - **Design da Solução**: Diagramas conceituais, contratos de interface (APIs), estruturas de dados e fluxo de informação.
  - **Alternativas Consideradas**: Soluções rejeitadas e a justificativa técnica dos *trade-offs*.
  - **Preocupações Transversais**: Segurança, limites de memória/CPU, observabilidade e contenção de falhas.
* **O que NÃO DEVE conter**:
  - Comandos de instalação, execução de CLI ou receitas de deploy.
  - Trechos de código brutos que possam ficar obsoletos com refatorações simples.

### 2.4. Regras e Instruções de Agentes (`.agents/rules/*.md`, `GEMINI.md`)
* **Papel**: Diretrizes operacionais e restrições para agentes de IA e desenvolvedores.
* **O que DEVE conter**:
  - Invariantes técnicas invioláveis (ex.: não alterar `data/raw/mbft.pdf`).
  - Padrões de ambiente (`uv`, Python 3.14, CUDA).
  - Regras automáticas e acionadores de governança (*triggers* de glob/arquivos).

---

## 3. Diretrizes de Redação Técnica e Formatação Markdown

1. **Codificação e Invariantes do Git**:
   - Todos os arquivos Markdown devem ser salvos em **UTF-8 sem BOM** (*Byte Order Mark*).
   - Use quebras de linha padrão do Unix (`LF`).
2. **Links e Referências Cruzadas**:
   - **Proibido o uso de caminhos absolutos locais** (ex.: `file:///C:/...` ou `/Users/...`).
   - Todos os links para arquivos do repositório devem ser **relativos** (ex.: `[PMS-002](../docs/PMS-002%20-%20Design%20do%20extrator.md)` ou `./docs/PMS-001...`).
3. **Padrão de Frontmatter YAML**:
   - Os documentos em `docs/PMS-*.md` e regras em `.agents/rules/*.md` devem seguir estritamente o frontmatter especificado em seus respectivos templates/contratos.
   - As chaves do frontmatter não podem ser duplicadas e os valores devem respeitar os padrões regex definidos no projeto.
4. **Tom e Estilo da Linguagem**:
   - Utilize a norma culta da língua portuguesa (PT-BR) com terminologia técnica consolidada em inglês mantida em itálico ou formato de código quando aplicável (ex.: *chunking*, *embeddings*, *runtime*, *frontmatter*).
   - Prefira frases na ordem direta e no modo indicativo ou imperativo neutro ("Execute o comando...", "A API recebe...", "O extrator processa...").

---

## 4. Guia Prático para Redação do Texto de Commits

A mensagem de commit é um documento de histórico e auditoria do projeto. Seu propósito principal não é repetir o que o *diff* do Git já mostra (quais linhas mudaram), mas sim registrar **o contexto, o motivo da mudança e o raciocínio da decisão**.

### 4.1. O que Colocar na Mensagem de Commit

* **O "Porquê" da alteração**: Qual problema estava ocorrendo? Qual requisito ou restrição motivou a alteração?
* **O Impacto e a Solução Adotada**: De forma sucinta, qual foi a estratégia utilizada para resolver o problema.
* **Resposta a Casos de Borda**: Se a alteração trata um comportamento atípico, explique brevemente qual é esse caso.
* **Decisões Não Óbvias**: Se você escolheu uma abordagem menos comum para evitar um bug conhecido ou limitação de biblioteca, registre isso na mensagem.

### 4.2. O que NÃO Precisa Colocar

* **Repetição do Diff**: Não liste arquivos alterados nem descreva linha por linha ("alterei a linha 42 do arquivo X para Y"). O Git já faz isso automaticamente.
* **Comentários Óbvios ou Vazios**: Evite frases genéricas como "corrigindo bugs", "ajustes no código", "atualizando documentação" ou "melhorias gerais".
* **Detalhes Operacionais irrelevantes**: Não inclua comandos temporários que você rodou no seu terminal durante o desenvolvimento.

### 4.3. Como Escolher o que Vai no Título vs. no Corpo do Commit

1. **Linha do Título (Assunto / First Line)**:
   - Siga a estrutura: `<tipo>(<escopo opcional>): <resumo do que foi feito>` (em português).
   - **O que vai**: O resumo de maior impacto. Exemplo: `fix(extrator): corrigir estouro de memória em PDFs com tabelas aninhadas`.
   - Deve ter no máximo 50 a 72 caracteres, escrita no imperativo/infinitivo direto, sem ponto final no fim.
2. **Linha em Branco**: Sempre insira uma linha em branco entre o título e o corpo do commit.
3. **Corpo do Commit (Body)**:
   - **Quando usar**: Utilize o corpo sempre que a alteração envolver lógica de negócio, correção de bugs não triviais, refatoração de arquitetura ou decisões de design. Commits simples de *typos* ou adição de um arquivo isolado podem dispensar o corpo.
   - **O que vai no corpo**:
     - **Contexto**: O que motivou a mudança.
     - **Solução**: Como o problema foi abordado de forma conceitual.
     - **Efeitos Colaterais/Notas**: Qualquer atenção necessária para quem for ler o histórico no futuro.

### 4.4. Exemplos Práticos no Contexto do MBFT

#### ❌ Exemplo Ruim (Pouco informativo, repete o diff):
```text
fix: ajustado extrator.py

Mudei a linha 102 do extrator.py para usar timeout de 30 segundos e adicionei import os.
```

#### 🟢 Exemplo Bom (Focado no motivo, contexto e decisão):
```text
fix(extrator): aplicar timeout no OCR de tabelas complexas

Páginas contendo tabelas com múltiplos aninhamentos causavam travamento
indefinido no motor de OCR Docling sob GPU.

Para evitar o bloqueio dos pipelines batch em execução contínua, definimos
um limite rígido de 30s por página. Caso o tempo seja excedido, o extrator
registra um aviso e prossegue para a aproximação via texto bruto.
```

#### 🟢 Exemplo Bom para Documentação:
```text
docs: criar manual de redação de documentos e convenções de commit

Adiciona guia centralizado em docs/Manual de redação de documentos.md
estabelecendo a taxonomia da documentação do monorepo, regras de DRY entre
READMEs/PMSs, e diretrizes para redação técnica e mensagens de commit.
```

---

## 5. Ciclo de Vida da Documentação e o Dever de Emenda

1. **Fonte da Verdade Sem Petrificação**:
   - As PMSs são a fonte da verdade arquitetural. O código não deve contradizê-las silenciosamente.
   - Entretanto, **nenhuma PMS é imutável**. Se durante a implementação você identificar que uma especificação da PMS é ineficiente ou inviável, você deve **atualizar a PMS junto com o código**, documentando a alteração na seção de *Alternativas Consideradas*.
2. **Atualização Atômica**:
   - Alterações de código que modifiquem comandos CLI, novas rotas da API ou novos parâmetros de configuração **devem incluir a atualização dos respectivos `README.md` no mesmo commit ou PR**.
3. **Auditoria Automatizada via Pytest**:
   - A integridade da documentação (referências cruzadas, ausência de BOM, presença de README nos pacotes, frontmatter correto) é verificada automaticamente pelo teste de governança.
   - Sempre valide suas alterações na documentação executando:
     ```bash
     uv run pytest tests/test_governanca_docs.py
     ```

---

## 6. Recomendações para Redação e Revisão da Documentação Existente

Com base na auditoria da documentação atual do repositório MBFT, destacam-se as seguintes recomendações práticas para revisões e redações futuras:

1. **Consistência nos Nomes e Cabeçalhos das PMSs**:
   - Certifique-se de que o título H1 do arquivo PMS corresponda exatamente ao campo `PMS` do frontmatter e ao nome do arquivo físico (ex.: `PMS-001` no arquivo `docs/PMS-001 - Mecanismo RAG...md`).
   - Mantenha a tabela de seções rigorosamente alinhada ao Anexo A do `PMS-000`.

2. **READMEs de Pacotes Pipelines e Apps**:
   - **Ponto Positivo Atual**: Os READMEs de `pipelines/core`, `pipelines/extrator`, `pipelines/enriquecedor`, `pipelines/indexador`, `pipelines/ssg`, `apps/api` e `deploy` referenciam corretamente suas PMSs no topo e possuem estrutura concisa.
   - **Recomendação**: Ao adicionar novas CLI flags nos pacotes (por exemplo, no `mbft-extrator` ou `mbft-indexador`), certifique-se de registrar o exemplo de uso direto no `README.md` do pacote e manter o `README.md` raiz apenas com o comando de alto nível (`uv run mbft pipeline ...`).

3. **Invariantes do Frontmatter e Regras de Agentes**:
   - As regras em `.agents/rules/` devem continuar usando o formato de string separada por vírgulas no campo `globs` (ex.: `globs: "docs/**, **/README.md"`), evitando sintaxe de lista YAML entre colchetes, para compatibilidade com o parser do projeto.

4. **Preservação de Dados de Referência**:
   - Lembre-se de que arquivos de documentação nunca devem sugerir a modificação ou substituição do PDF fonte original em `data/raw/mbft.pdf`.

5. **Clareza nos Diagramas ASCII/Mermaid**:
   - Ao desenhar fluxos de dados nas PMSs (como no `PMS-001` ou `PMS-008`), utilize notações ASCII ou Mermaid claras e diretas, facilitando a leitura tanto por humanos quanto por LLMs em terminais de texto.
