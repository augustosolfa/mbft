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

### 3.2. Páginas 32 até o final - Fichas de Fiscalização Estruturadas
- **Natureza**: Fichas individuais padronizadas de enquadramento de infrações.
- **Identificador Único (`id`)**: O campo `Código do Enquadramento` (ex.: `"768-42"`).
- **Desafio de Paginação e Colunas**:
  - Múltiplas fichas estendem-se por 2 ou mais páginas.
  - Colunas normativas paralelas fluem entre as quebras de página.
  - **Atenção crítica**: Não misturar texto de colunas diferentes. Aplicar costura geométrica contínua por coluna/canal (técnica derivada de `extrair_mbft_old.py`).
- **Arquivo de Saída**: `fichas_mbft.json` (array JSON contendo todas as fichas como objetos estruturados).

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

1. **Formato HTML**: O campo deve ser serializado em HTML limpo (`<p>`, `<table>`, `<tr>`, `<td>`, `<th>`, `<ul>`, `<li>`, `<img>`).
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

- **`cli.py`**: Ponto de entrada CLI (subcomandos `geral`, `fichas`, `tudo` e opções `--range`, `--force`).
- **`models.py`**: Modelos de dados e esquemas de validação (Pydantic).
- **`parte_geral.py`**: Pipeline de extração das páginas 1 a 31 para Markdown.
- **`fatiador.py`**: Mapeamento de início/fim e paginação de cada ficha via coordenadas vetoriais.
- **`stitching.py`**: Algoritmo de canais de colunas e costura contínua entre páginas subsequentes.
- **`docling_extractor.py`**: Configuração e execução do Docling com aceleração GPU (CUDA).
- **`html_builder.py`**: Montador e formatador de HTML semântico e exportador de imagens 300 DPI.
- **`auditoria.py`**: Geração do relatório `relatorio_extracao.md` com estatísticas e alertas.

---

## 7. Checkpointing e Resiliência

1. **Persistência de Progresso**: Checkpoints salvos em `.cache_extracao/` por ficha/página.
2. **Retomada Segura**: Em caso de interrupção ou reexecução, fichas já concluídas não precisam ser reprocessadas a menos que `--force` seja especificado.
3. **Validação Piloto**: Testes iniciais sempre executados em faixas pequenas (ex.: páginas 32 a 37) para homologação visual antes da execução completa.
