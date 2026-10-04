# MBFT - Manual Brasileiro de Fiscalização de Trânsito

Monorepo para processamento, extração de dados estruturados e aplicações inteligentes baseadas no Manual Brasileiro de Fiscalização de Trânsito (**MBFT** - Resolução CONTRAN nº 985/2022 e alterações posteriores).

---

## 🏗️ Estrutura do Repositório

- **`data/raw/`**: Documento fonte original (`mbft.pdf`).
- **`data/processed/`**: Dados finais consolidados:
  - `fichas_mbft.json`: Base estruturada contendo as 402 fichas de fiscalização com metadados, regras e conteúdo normativo.
  - `mbft_parte_geral.md`: Transcrição semântica da parte geral (páginas 1 a 31).
  - `imagens/`: Ilustrações, placas de sinalização e diagramas de trânsito em alta definição (300 DPI).
- **`pipeline_extrator/`**: Módulo em Python responsável pela ingestão, OCR, costura geométrica de colunas e serialização com aceleração CUDA.

---

## 🚀 Como Executar

Este projeto utiliza o gerenciador de pacotes **`uv`**.

### Instalação de Dependências

```bash
uv sync
```

### Execução do Extrator

A partir da raiz do monorepo:

```bash
# Executar extração da parte geral
uv run --package mbft-extrator python pipeline_extrator/extrair.py geral

# Executar extração das fichas estruturadas
uv run --package mbft-extrator python pipeline_extrator/extrair.py fichas

# Executar pipeline completo
uv run --package mbft-extrator python pipeline_extrator/extrair.py tudo
```

Consulte [pipeline_extrator/README.md](file:///d:/dev/mbft%20-%20extrator/pipeline_extrator/README.md) para detalhes técnicos da arquitetura do extrator.
