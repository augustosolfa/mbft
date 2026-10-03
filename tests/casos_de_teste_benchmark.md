# Casos de Teste Benchmark e Gabarito Visual de Validação

Este documento serve como referência e **gabarito (ground truth)** para testes de fidelidade de extração do pipeline (Docling + costura geométrica e fatiamento). As imagens renderizadas de referência estão armazenadas em `tests/benchmark_renders/`.

---

## Caso 1: Ficha `563-00` (Páginas 264 e 265)
* **Tipificação Resumida**: Parar na área de cruzamento de vias.
* **Amparo Legal**: Art. 182, VII.
* **Gravidade**: Média | **Penalidade**: Multa | **Medida Administrativa**: Não | **Crime**: NÃO
* **Infrator**: Condutor | **Competência**: Órgão ou Entidade de Trânsito Municipal e Rodoviário | **Pontuação**: 4 | **Constatação**: Possível sem abordagem.

### Desafios Críticos de Validação:
1. **Costura da Coluna "Quando Autuar"**:
   - O item `5` começa no rodapé da **página 264**:
     > `5. Veículo que passa pela linha de retenção na fase do verde ou do amarelo, fica imobilizado sobre a área de conflito e, tendo visão do foco`
   - E continua no topo da coluna da **página 265**:
     > `semafórico no momento da mudança para a fase vermelha, continua na marcha e completa o movimento.`
   - **Gabarito**: O extrator deve concatenar e recompor o item `5` como uma única sentença contínua.
2. **Informações Complementares**:
   - `1. A autuação independe da existência de sinalização.`
   - `2. Desenho ilustrativo:`
   - Contém **2 ilustrações esquemáticas de cruzamento** (com carros vermelhos em área amarela quadriculada de conflito e marcação viária).
   - **Gabarito**: Extrair as ilustrações para `imagens/ficha563-00_1.png` e `imagens/ficha563-00_2.png` (ou montagem única 300 DPI) e embutir tags `<img ...>` no HTML.

---

## Caso 2: Ficha `599-10` (Páginas 376 e 377)
* **Tipificação Resumida**: Executar operação de retorno em locais proibidos pela sinalização.
* **Amparo Legal**: Art. 206, I.
* **Gravidade**: Gravíssima | **Penalidade**: Multa | **Medida Administrativa**: Não | **Crime**: NÃO
* **Infrator**: Condutor | **Competência**: Órgão ou Entidade de Trânsito Estadual, Municipal e Rodoviário | **Pontuação**: 7 | **Constatação**: Possível sem abordagem.

### Desafios Críticos de Validação:
1. **Informações Complementares na Página 377 (Tabelas com Imagens e Texto)**:
   - **Seção 1**: `1. Imagens Ilustrativas:`
     - Tabela de 1 linha x 2 colunas.
     - Coluna 1: Imagem da **Placa R-5a** + Legenda "Placa R-5a".
     - Coluna 2: Imagem da **Placa R-5b** + Legenda "Placa R-5b".
   - **Seção 2**: `2. Linha de Divisão de Fluxos Opostos-LFO:`
     - Tabela de 1 linha x 2 colunas.
     - Coluna 1: Subtítulo `Linha Simples Contínua (LFO-1):`, diagrama esquemático com detalhe circular ampliado e texto explicativo (`A LFO-1 divide fluxos opostos...`).
     - Coluna 2: Subtítulo `Linha Dupla Contínua (LFO-3):`, diagrama esquemático com detalhe circular ampliado e texto explicativo (`A LFO-3 divide fluxos opostos...`).
   - **Seção 3**: `3. As placas R-4a e R-4b NÃO PROÍBEM o retorno:`
     - Tabela de 1 linha x 2 colunas.
     - Coluna 1: Imagem da **Placa R-4a** + Legenda "Placa R-4a / Proibido Virar à Esquerda".
     - Coluna 2: Imagem da **Placa R-4b** + Legenda "Placa R-4b / Proibido Virar à Direita".
   - **Gabarito**: O HTML de `informacoes_complementares` deve conter as tabelas `<table>` preservando as células com suas respectivas imagens `<img src="imagens/ficha599-10_X.png">` e textos explicativos.

---

## Caso 3: Ficha `683-11` (Páginas 628 a 633 - 6 Páginas!)
* **Tipificação Resumida**: Transitar com o veículo com excesso de peso PBT/PBTC.
* **Código do Enquadramento**: `683-11` (id da ficha)
* **Amparo Legal**: Art. 231, V.
* **Gravidade**: Média | **Penalidade**: Multa acrescida a cada duzentos quilogramas... | **Medida Administrativa**: Retenção do veículo e transbordo...
* **Infrator**: Embarcador/Transportador | **Competência**: Órgão ou Entidade de Trânsito Municipal e Rodoviário.
* **Pontuação**: `4* (vide item 25 das Definições e Procedimentos)` | **Constatação**: Mediante abordagem.

### Desafios Críticos de Validação:
1. **Extensão Multipágina (6 páginas consecutivas de 628 a 633)**:
   - A ficha inicia na página 628 e a próxima ficha (`683-12`) só começa na página 634. O fatiador deve mapear `paginas = [628, 629, 630, 631, 632, 633]`.
2. **Coluna "Definições e Procedimentos" Gigante (Páginas 628 a 632)**:
   - Contém **27 itens enumerados** que se estendem continuamente ao longo de 5 páginas.
   - Pág 628: itens 1, 2, 3, 4 (item 4 quebra no fim: `peso máximo que o veículo transmite ao pavimento,`).
   - Pág 629: continuação do item 4 (`constituído da soma da tara mais a lotação.`), itens 5, 6, 7, 8, 9, 10, 11 (item 11 quebra no fim).
   - Pág 630: continuação do item 11, itens 12, 13, 14, 15, 16, 17 (item 17 quebra no fim).
   - Pág 631: continuação do item 17, itens 18, 19, 20, 21, 22, 23, 24.
   - Pág 632: continuação do item 24, itens 25, 26, 27.
   - **Gabarito**: Todos os 27 itens devem ser recompostos e alinhados perfeitamente no objeto `definicoes_procedimentos`.
3. **Colunas "Quando Autuar" e "Quando NÃO Autuar"**:
   - "Quando Autuar": itens 1 a 8 fluindo entre páginas 628 e 629.
   - "Quando NÃO Autuar": itens 1 a 6 fluindo entre páginas 628 e 629.
4. **Informações Complementares (Páginas 632 e 633)**:
   - **Página 632**: Tabela de identificação de infrator da Resolução CONTRAN nº 547/2015 (matriz com colunas: Possibilidades, Excesso PBT/PBTC, Excesso Eixos, Excesso Simultâneo).
   - **Página 633**:
     - Desenho ilustrativo com a **Placa R-14 (10 t - Peso Bruto Total Máximo Permitido)** e alíneas explicativas (a, b, c, d).
     - Seção 3: Resolução Contran nº 882/2021.
     - Seção 4: Regras para Cálculo do Valor da Multa de Excesso de Peso (itens 4.1 e 4.2 com alíneas de `a` até `f` com valores em Reais).
