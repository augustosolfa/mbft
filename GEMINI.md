# Diretrizes e Instruções do Projeto - Extrator MBFT

Este documento define os padrões de desenvolvimento, ferramentas, regras estritas, arquitetura do pipeline e modelagem de dados para a extração do Manual Brasileiro de Fiscalização de Trânsito (**MBFT**).

---

## 1. Ambiente, Ferramentas e Padrões de Execução

- **Gerenciador de Pacotes**: Usar SEMPRE `uv` (`uv venv`, `uv pip`, `uv add`, `uv run`, `uv sync`).
- **Gerenciamento de Projeto e Dependências**: Centralizado exclusivamente no `pyproject.toml`.
- **Versão do Python**: Python 3.14 (testado e homologado com CPython 3.14.6).
- **Ambiente Virtual**: SEMPRE utilizar ambiente virtual (`.venv`), inicializado e mantido via `uv`.
- **Aceleração de Hardware (GPU / CUDA)**:
  - O PyTorch é instalado a partir do índice oficial CUDA 13.2 (`https://download.pytorch.org/whl/cu132`) com `explicit = true`.
  - O Docling utiliza automaticamente `AcceleratorOptions(device="cuda")` com a GPU instalada (NVIDIA GeForce RTX 4070).

---

## 2. Regras Estritas de Integridade de Arquivos

- **`mbft.pdf`**: Arquivo fonte bruto original. **NUNCA DEVE SER MODIFICADO OU SOBRESCRITO**.
- **`extrair_mbft_old.py`**: Arquivo de referência histórica. **NUNCA DEVE SER MODIFICADO**. Serve como fonte de consulta para reutilizar heurísticas (ex.: lógica de canais geométricos de colunas e costura entre páginas).

---

## 3. Divisão do Documento e Arquitetura de Extração

### 3.1. Páginas 1 a 31 (inclusive) - Parte Geral / Normativa
- **Natureza**: Disposições preliminares, conceitos gerais e resoluções do CONTRAN.
- **Processamento**: Conversão com remoção de ruídos de cabeçalhos/rodapés e preservação de tabelas e hierarquia semântica de títulos (`#`, `##`, `###`).
- **Anotações de Página**: Inclusão de marcadores discretos (ex.: `<!-- Página X -->`).
- **Arquivo de Saída**: `mbft_parte_geral.md`.

### 3.2. Páginas 32 até o final (pág. 826) - Fichas de Fiscalização Estruturadas
- **Total de Fichas Mapeadas**: 402 fichas individuais.
- **Mapeamento de Início de Ficha**: Cada ficha começa em uma página própria identificada pelo cabeçalho `Código do Enquadramento: <código>`. Nenhuma página contém o início de mais de uma ficha.
- **Identificador Único (`id`)**: O campo `Código do Enquadramento` (ex.: `"768-42"`).
- **Desafio de Paginação e Colunas**:
  - Múltiplas fichas estendem-se por 2 a 6 páginas consecutivas (ex.: Ficha 683-11 ocupa 6 páginas, da 628 à 633).
  - Colunas normativas paralelas fluem entre as quebras de página.
  - **Atenção crítica**: Não misturar texto de colunas diferentes. Aplicar costura geométrica contínua por coluna/canal (técnica derivada de `extrair_mbft_old.py`).
  - **Normalização Textual**: Quebras duras de linha dentro de parágrafos/itens devem ser convertidas em espaços e palavras quebradas por hífen no fim da linha devem ser reunificadas (ex.: `cruzamen-` + `to` -> `cruzamento`).
- **Arquivos de Saída**:
  - Consolidado principal: `fichas_mbft.json` (com indentação `indent=2`).
  - Opção na CLI `--salvar-individuais`: exporta também `fichas/ficha_<id>.json`.

---

## 4. Estrutura de Campos e Modelagem do JSON

Cada ficha no arquivo `fichas_mbft.json` conterá a seguinte estrutura padronizada:

| Campo | Tipo no JSON | Descrição / Regra de Formatação |
| :--- | :--- | :--- |
| `id` | `string` | Mesmo valor de `codigo_enquadramento` (ex.: `"768-42"`) |
| `tipificacao_resumida` | `string` | Título / tipificação resumida da infração |
| `codigo_enquadramento` | `string` | Código de enquadramento da infração |
| `amparo_legal` | `string` | Artigo e inciso do CTB |
| `tipificacao_enquadramento` | `string` | Descrição completa do enquadramento legal |
| `gravidade` | `string` | Leve, Média, Grave ou Gravíssima |
| `penalidade` | `string` | Penalidade prevista (ex.: Multa) |
| `medida_administrativa` | `string` | Medida cabível (ex.: Retenção do veículo) |
| `pode_configurar_crime_transito` | `string` | Indicação de crime de trânsito |
| `infrator` | `string` | Condutor, Proprietário, Pessoa Física/Jurídica, etc. |
| `competencia` | `string` | Órgão ou entidade executiva de trânsito competente |
| `competencia_alterada_lei_14599` | `boolean` | `true` se a competência foi alterada pela Lei n. 14.599/23, senão `false` |
| `pontuacao` | `string` | Pontos a computar na CNH |
| `constatacao_infracao` | `string` | Com abordagem, Sem abordagem, etc. |
| `quando_autuar` | `object` | `{ "texto": str, "itens": list[str] }` |
| `quando_nao_autuar` | `object` | `{ "texto": str, "itens": list[str] }` |
| `definicoes_procedimentos` | `object` | `{ "texto": str, "itens": list[str] }` |
| `exemplos_observacoes_ait` | `object` | `{ "texto": str, "itens": list[str] }` |
| `informacoes_complementares` | `string` (HTML) | Conteúdo semântico em HTML simples (`<p>`, `<table>`, `<img>`) |
| `paginas` | `list[int]` | Números das páginas do PDF de onde a ficha foi extraída |
| `imagens` | `list[str]` | Caminhos relativos das imagens extraídas para esta ficha |

---

## 5. Tratamento de "Informações Complementares" e Imagens

1. **Formato HTML Semântico**: Serialização em HTML limpo (`<table>`, `<tr>`, `<td>`, `<img>`, `<p>`) sem estilos inline intrusivos, garantindo portabilidade para qualquer visualizador.
2. **Estratégia de Extração de Imagens (Híbrido Inteligente)**:
   - Fotos e imagens raster nativas são extraídas diretamente dos fluxos do PDF.
   - Diagramas vetoriais, ilustrações compostas (placas, sinalizações com vetores) e tabelas com ilustrações são renderizados a partir de seu *bounding box* a **300 DPI**, garantindo 100% de legibilidade visual.
3. **Diretório e Nomenclatura das Imagens**:
   - Salvas na pasta `imagens/`.
   - Nome das imagens: `ficha<codigo_enquadramento>_<indice>.png` (ex.: `imagens/ficha768-42_1.png`).
   - Tags `<img src="imagens/ficha768-42_1.png" alt="..." />` integradas no HTML do campo.

---

## 6. Arquitetura Modular do Código (`src/mbft_extrator/`)

O código-fonte deve ser organizado com responsabilidades bem definidas:

- **`cli.py`**: Ponto de entrada CLI (subcomandos `geral`, `fichas`, `tudo` e opções `--range`, `--salvar-individuais`, `--force`).
- **`models.py`**: Modelos de dados e esquemas de validação (Pydantic).
- **`parte_geral.py`**: Pipeline de extração das páginas 1 a 31 para Markdown.
- **`fatiador.py`**: Mapeamento de início/fim e paginação de cada ficha via coordenadas vetoriais.
- **`stitching.py`**: Algoritmo de canais de colunas e costura contínua entre páginas subsequentes com normalização de quebras e hifens.
- **`docling_extractor.py`**: Configuração e execução do Docling com aceleração GPU (CUDA).
- **`html_builder.py`**: Montador e formatador de HTML semântico e exportador de imagens 300 DPI.
- **`auditoria.py`**: Geração do relatório `relatorio_extracao.md` com estatísticas e alertas.

---

## 7. Checkpointing e Casos de Teste Benchmark

1. **Persistência de Progresso**: Checkpoints salvos em `.cache_extracao/` por ficha/página.
2. **Retomada Segura**: Em caso de interrupção ou reexecução, fichas já concluídas não precisam ser reprocessadas a menos que `--force` seja especificado.
3. **Gabarito Visual e Casos Canônicos de Validação**:
   - Documentados detalhadamente em [tests/casos_de_teste_benchmark.md](file:///d:/dev/mbft%20-%20extrator/tests/casos_de_teste_benchmark.md) com imagens em `tests/benchmark_renders/`:
     - **Ficha 563-00 (págs. 264-265)**: Quebra e costura de coluna no item 5 de "Quando Autuar" e 2 esquemas gráficos de cruzamento.
     - **Ficha 599-10 (págs. 376-377)**: 3 tabelas com placas R-5a/R-5b/R-4a/R-4b e diagramas de linhas de fluxo LFO com ilustrações e textos explicativos embutidos.
     - **Ficha 683-11 (págs. 628-633 - 6 páginas)**: Coluna gigante de "Definições e Procedimentos" com 27 itens ao longo de 5 páginas consecutivas, matriz da Resolução 547 e placa R-14.
