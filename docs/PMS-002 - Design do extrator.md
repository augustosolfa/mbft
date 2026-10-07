---
PMS: 002
Título: Design do Extrator do Manual Brasileiro de Fiscalização de Trânsito
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 06-Out-2026
Requer: PMS-001
Substitui: Nenhum
---

# PMS-002: Design do Extrator do MBFT

## 1. Contexto e Escopo

O Manual Brasileiro de Fiscalização de Trânsito (MBFT) é aprovado por Resolução do CONTRAN em arquivo PDF consolidado de 826 páginas. O documento divide-se em duas macroestruturas: a **Parte Geral** (páginas 1 a 31), em texto normativo corrido, e as **Fichas de Fiscalização** (páginas 32 a 826), que agrupam 404 fichas tabulares com procedimentos operacionais.

Dada a complexidade do documento — onde aproximadamente 67% das fichas se estendem por duas ou mais páginas consecutivas (atingindo até 6 páginas em casos como a ficha 683-11) —, abordagens ingênuas de extração textual falham em manter a continuidade e hierarquia dos campos.

Este documento especifica o **Extrator** (Etapa 1 do PMS-001), processo *offline/batch* em Python baseado em pipeline híbrido `pypdfium2` (varredura vetorial rápida e colunas) e `docling` (Parte Geral e tabelas complexas sob demanda), responsável por decompor o PDF oficial em:
1. Texto da Parte Geral em Markdown;
2. Lista estruturada de Fichas de Enquadramento em formato JSON;
3. Imagens e diagramas operacionais extraídos diretamente dos objetos gráficos nativos do PDF em formato PNG.

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Extrair e transcrever a Parte Geral (páginas 1 a 31) em Markdown estruturado, preservando níveis de cabeçalho e tabelas institucionais.
  * Segmentar as fichas de fiscalização delimitando os limites de cada enquadramento a partir de âncoras de código aplicadas exclusivamente ao bloco de cabeçalho (`^\d{3}-\d{2}$` sobre o campo de código).
  * Recompor a continuidade de fichas multipágina (*multi-page stitching*), unificando seções fracionadas (*Quando Autuar*, *Definições e Procedimentos*, etc.) em uma entidade lógica única.
  * Estruturar e validar os atributos de cada ficha sob contrato de dados estrito via Pydantic.
  * Reconstruir a seção de *Informações Complementares* em HTML semântico sanitizado, preservando tabelas normativas e notas técnicas.
  * Extrair ilustrações, diagramas de posicionamento e placas presentes nas fichas, extraindo os bitmaps nativos do PDF em PNG referenciados no JSON.
  * Viabilizar alto desempenho com execução híbrida (`pypdfium2` em CPU para extração vetorial e aceleração CUDA/GPU no Docling para tabelas complexas e Parte Geral).

* **Não Objetivos (Non-Goals):**
  * Não é meta gerar vetores de busca (*embeddings*) ou normalizar entidades jurídicas/artigos do CTB (escopo atribuído ao Enriquecedor / PMS-003).
  * Não é meta persistir os dados em banco relacional ou em banco vetorial (escopo da Carga / PMS-004).
  * Não é meta operar como serviço síncrono ou API em tempo real; trata-se de rotina exclusivamente em lote (*offline batch*).

---

## 3. Design da Solução

### Pipeline de Processamento
O extrator atua de ponta a ponta sobre o PDF em pipeline sequencial:

```
[ PDF MBFT (826 págs) ]
         │
         ├─── (pp. 1-31)  ──> [ Parser Documental Docling ] ──> mbft_parte_geral.md
         │
         └─── (pp. 32-826) ─> [ Extrator Vetorial pypdfium2 ] (fatiamento e colunas)
                                    │
                                    ▼
                         [ Multi-page Stitcher ] (Costura de Estados & Âncoras)
                                    │
                                    ▼
                      [ Gerador de HTML Semântico ] (Informações Complementares; Docling CUDA sob demanda p/ tabelas)
                                    │
                                    ▼
                         [ Extrator de Imagens Nativas ] (bitmaps -> imagens/ficha{cod}_{idx}.png)
                                    │
                                    ▼
                          [ Validador Pydantic ]
                                    │
                                    └──> fichas_mbft.json
```

### Estratégia de Parsing e Costura Multipágina
1. **Parte Geral:** Processamento linear das páginas 1 a 31 via representação semântica do Docling, emitindo Markdown canônico com formatação de listas e tabelas preservada.
2. **Segmentação e Stitching de Fichas:** O parser percorre as páginas 32 a 826 mantendo uma máquina de estados:
   * A detecção de um código de infração validado exclusivamente no campo de código do bloco de cabeçalho (`^\d{3}-\d{2}$`) inicializa uma nova ficha. Se o código for idêntico ao da ficha ativa (cabeçalho repetido em quebra de página), é tratado como continuidade da mesma ficha.
   * Quando uma página não contém novo código de enquadramento em cabeçalho, seus blocos de layout são tratados como extensão da ficha ativa. Listas ordenadas e parágrafos quebrados pela transição de página são concatenados e higienizados.
3. **Extração de Imagens Nativas:** Os objetos de imagem (bitmaps) embutidos nas páginas das fichas são extraídos diretamente do PDF e gravados em PNG no diretório local (`imagens/ficha{cod}_{idx}.png`), com caminho relativo registrado no JSON. Não há rasterização de regiões vetoriais.
4. **HTML Semântico:** A seção de *Informações Complementares* contém notas e quadros que não cabem em texto puro; seu conteúdo é compilado em tags HTML higienizadas (`<p>`, `<strong>`, `<table>`, `<ul>`).
5. **Configuração do Pipeline Docling e OCR:** Como o PDF oficial possui camada textual vetorial nativa e de alta qualidade, o `PdfPipelineOptions` é configurado explicitamente com `do_ocr = False` para maximizar o desempenho e evitar degradação de caracteres jurídicos (`§`, incisos). A execução de OCR é reservada estritamente como mecanismo de contingência (*fallback*) caso alguma página pontual não apresente camada de texto extraível.

### Contrato de Dados e Guardrail de Saída (`mbft-core`)

O contrato de dados das fichas reside no pacote neutro compartilhado `packages/core` (`mbft-core`), servindo como guardrail estrito de validação da saída do Extrator e contrato de entrada do Enriquecedor (PMS-003), sem acoplar os pipelines consumidores às dependências pesadas de PDF/visão computacional.

A fim de evitar a defasagem de documentação (*document drift*), os esquemas Pydantic brutos não são transcritos neste documento. Eles podem ser encontrados em sua fonte canônica de verdade: `packages/core/src/mbft_core/models/extracao.py`.

Em suma, o modelo `Ficha` extrai e consolida:
- **Identificadores**: `id` e `codigo_enquadramento` (validados para manter consistência absoluta).
- **Tipificação**: `tipificacao_resumida`, `tipificacao_enquadramento`, e `amparo_legal`.
- **Atributos Punitivos/Administrativos originais**: textos literais sobre gravidade, penalidade, medida administrativa, infrator e pontuação.
- **Campos Normativos (Markdown e listas)**: `quando_autuar`, `quando_nao_autuar`, `definicoes_procedimentos` e `exemplos_observacoes_ait` (modelados como `CampoNormativo`, que armazena tanto a renderização do texto corrido quanto os itens fragmentados).
- **Dados Ricos e Rastros Visuais**: `informacoes_complementares` (em HTML semântico com recriação de tabelas e injeção inline de imagens) e a lista de `imagens` associadas com seus respectivos `paginas` do PDF original.

Uma rotina de validação acoplada inferirá automaticamente a *flag* `competencia_alterada_lei_14599` sempre que detectar inconsistências no campo de competência causadas pelas lacunas de revisão no PDF original.


---

## 4. Alternativas Consideradas

* **Parsers Textuais Lineares (`pypdf` / `pdfplumber`):** Descartados por extraírem o texto em ordem de fluxo vetorial bruto, quebrando a correlação geométrica de tabelas e falhando na reconstituição de blocos fracionados por quebras de página. Também não oferecem suporte integrado à segmentação e extração de imagens e diagramas.
* **OCR Integral com Tesseract:** Descartado devido ao alto custo computacional sobre 826 páginas e alta incidência de degradação em caracteres jurídicos especiais (`§`, incisos e alíneas) em um PDF que já possui camada textual vetorial nativa.

---

## 5. Preocupações Transversais

* **Tolerância a Anomalias e Lacunas Normativas:** O extrator tolera inconsistências formais presentes no texto oficial do MBFT, como fichas em que o campo de competência foi deixado em branco em virtude das mudanças promovidas pela Lei nº 14.599/2023. O schema aceita strings vazias para esse campo sem abortar o processamento e marca automaticamente `competencia_alterada_lei_14599 = True` quando o rótulo/campo de competência do cabeçalho citar a Lei nº 14.599/23 ou quando o campo for vazio, delegando correções e atribuições conceituais detalhadas ao Enriquecedor (PMS-003).
* **Gerenciamento de Memória e Recursos:** O pipeline realiza a inferência dos modelos do Docling com aceleração CUDA. Os bitmaps extraídos são gravados em PNG imediatamente e não retidos em memória, prevenindo saturação de RAM/VRAM durante a varredura do lote.
