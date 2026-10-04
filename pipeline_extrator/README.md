# Pipeline Extrator MBFT

Módulo responsável pela extração estruturada de alta fidelidade do **Manual Brasileiro de Fiscalização de Trânsito (MBFT)** a partir do PDF oficial.

---

## 1. Visão Geral da Arquitetura de Extração

O pipeline extrai duas partes principais do documento:

1. **Parte Geral / Normativa (Páginas 1 a 31)**:
   - Disposições preliminares, conceitos gerais e resoluções do CONTRAN.
   - Conversão com remoção de ruídos de cabeçalhos/rodapés e preservação de tabelas e hierarquia semântica (`#`, `##`, `###`).
   - Marcadores discretos de página (ex.: `<!-- Página X -->`).
   - Saída padrão: `data/processed/mbft_parte_geral.md`.

2. **Fichas de Fiscalização Estruturadas (Páginas 32 até 826)**:
   - 402 fichas de fiscalização com início demarcado por `Código do Enquadramento: <código>`.
   - **Costura Geométrica de Colunas**: Tratamento de fichas multipáginas (até 6 páginas consecutivas, ex.: Ficha 683-11) preservando o fluxo paralelo dos canais normativos sem intercalação indevida de texto.
   - **Normalização Textual**: Junção de quebras duras de linha e des-hifenização inteligente de palavras quebradas (`cruzamen-` + `to` -> `cruzamento`).
   - Saída padrão: `data/processed/fichas_mbft.json` (e opcionalmente `data/processed/fichas/ficha_<id>.json`).

---

## 2. Tecnologias e Aceleração por Hardware

- **Python 3.14**: Execução gerenciada via `uv`.
- **PyTorch (CUDA 13.2)**: Aceleração GPU para inferência de modelos de layout e OCR.
- **Docling**: Extração semântica com `AcceleratorOptions(device="cuda")` com fallback inteligente para extração vetorial direta via `pypdfium2`.
- **ProcessPoolExecutor**: Execução paralela de extração de fichas multipáginas com 4 workers paralelos e carregamento *lazy* de modelos.

---

## 3. Modelo de Dados JSON da Ficha

Cada ficha gerada possui o seguinte esquema:

| Campo | Tipo | Descrição |
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
| `infrator` | `string` | Condutor, Proprietário, etc. |
| `competencia` | `string` | Órgão ou entidade executiva competente |
| `competencia_alterada_lei_14599` | `boolean` | `true` se competência alterada pela Lei 14.599/23 |
| `pontuacao` | `string` | Pontuação prevista na CNH |
| `constatacao_infracao` | `string` | Forma de constatação (com/sem abordagem) |
| `quando_autuar` | `object` | `{ "texto": str, "itens": list[str] }` |
| `quando_nao_autuar` | `object` | `{ "texto": str, "itens": list[str] }` |
| `definicoes_procedimentos` | `object` | `{ "texto": str, "itens": list[str] }` |
| `exemplos_observacoes_ait` | `object` | `{ "texto": str, "itens": list[str] }` |
| `informacoes_complementares` | `string` (HTML) | HTML semântico com tabelas em 2 colunas e imagens integradas |
| `paginas` | `list[int]` | Lista de números de página no PDF |
| `imagens` | `list[str]` | Caminhos relativos das imagens geradas |

---

## 4. Extração e Renderização de Imagens (Híbrido 300 DPI)

- Imagens nativas embutidas no PDF são extraídas diretamente dos fluxos binários de imagem do PDF.
- Desenhos e diagramas vetoriais (ex.: esquemas de cruzamento, sinalizações) são renderizados a **300 DPI** a partir de seus *bounding boxes*.
- Todas as imagens são salvas em `data/processed/imagens/` com o padrão de nomenclatura `ficha<codigo_enquadramento>_<indice>.png`.

---

## 5. Uso da Linha de Comando (CLI)

Executar a partir da raiz do monorepo:

```bash
# Extração da Parte Geral
uv run --package mbft-extrator python pipeline_extrator/extrair.py geral

# Extração de intervalo de páginas ou fichas
uv run --package mbft-extrator python pipeline_extrator/extrair.py fichas --range 32-37

# Extração completa com fichas individuais
uv run --package mbft-extrator python pipeline_extrator/extrair.py tudo --salvar-individuais

# Auditoria regressiva entre versões de extração
uv run --package mbft-extrator python pipeline_extrator/comparar_versoes.py
```

---

## 6. Estrutura do Código-Fonte (`src/mbft_extrator/`)

- **`cli.py`**: Ponto de entrada CLI e orquestração de workers paralelos.
- **`models.py`**: Modelos de dados e validações Pydantic.
- **`parte_geral.py`**: Pipeline das páginas 1 a 31 para Markdown.
- **`fatiador.py`**: Detecção e mapeamento geométrico das fichas no PDF.
- **`stitching.py`**: Algoritmo de canais de colunas e costura entre páginas consecutivas.
- **`docling_extractor.py`**: Integração com Docling e aceleração CUDA.
- **`html_builder.py`**: Montador de HTML semântico em 2 colunas e exportador de imagens a 300 DPI.
- **`auditoria.py`**: Validador e gerador do `relatorio_extracao.md`.
