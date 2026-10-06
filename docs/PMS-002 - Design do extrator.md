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

O Manual Brasileiro de Fiscalização de Trânsito (MBFT) é homologado pelo CONTRAN em arquivo PDF consolidado de 826 páginas. O documento divide-se em duas macroestruturas: a **Parte Geral** (páginas 1 a 31), em texto normativo corrido, e as **Fichas de Fiscalização** (páginas 32 a 826), que agrupam 404 fichas tabulares com procedimentos operacionais.

Dada a complexidade do documento — onde aproximadamente 67% das fichas se estendem por duas ou mais páginas consecutivas (atingindo até 6 páginas em casos como a ficha 683-11) —, abordagens ingênuas de extração textual falham em manter a continuidade e hierarquia dos campos.

Este documento especifica o **Extrator** (Etapa 1 do PMS-001), processo *offline/batch* em Python baseado na biblioteca `docling`, responsável por decompor o PDF oficial em:
1. Texto da Parte Geral em Markdown;
2. Lista estruturada de Fichas de Enquadramento em formato JSON;
3. Imagens e diagramas operacionais recortados em alta resolução (300 DPI).

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Extrair e transcrever a Parte Geral (páginas 1 a 31) em Markdown estruturado, preservando níveis de cabeçalho e tabelas institucionais.
  * Segmentar as fichas de fiscalização delimitando os limites de cada enquadramento a partir de âncoras de código aplicadas exclusivamente ao bloco de cabeçalho (`^\d{3}-\d{2}$` sobre o campo de código).
  * Recompor a continuidade de fichas multipágina (*multi-page stitching*), unificando seções fracionadas (*Quando Autuar*, *Definições e Procedimentos*, etc.) em uma entidade lógica única.
  * Estruturar e validar os atributos de cada ficha sob contrato de dados estrito via Pydantic.
  * Reconstruir a seção de *Informações Complementares* em HTML semântico sanitizado, preservando tabelas normativas e notas técnicas.
  * Extrair ilustrações, diagramas de posicionamento e placas presentes nas fichas, renderizando-os em PNG a 300 DPI referenciados no JSON.
  * Viabilizar o processamento do lote completo por meio de aceleração de visão computacional em GPU (CUDA).

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
         └─── (pp. 32-826) ─> [ Docling Layout Engine (CUDA) ]
                                    │
                                    ▼
                         [ Multi-page Stitcher ] (Costura de Estados & Âncoras)
                                    │
                                    ▼
                      [ Gerador de HTML Semântico ] (Informações Complementares)
                                    │
                                    ▼
                         [ Renderizador 300 DPI ] (Recorte BBox -> imagens/ficha{cod}_{idx}.png)
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
3. **Extração Gráfica a 300 DPI:** Regiões classificadas como ilustrações/figuras têm suas coordenadas de Bounding Box capturadas e rasterizadas a 300 DPI com margem de segurança de 5 pixels, sendo gravadas em diretório local (`imagens/ficha{cod}_{idx}.png`).
4. **HTML Semântico:** A seção de *Informações Complementares* contém notas e quadros que não cabem em texto puro; seu conteúdo é compilado em tags HTML higienizadas (`<p>`, `<strong>`, `<table>`, `<ul>`).
5. **Configuração do Pipeline Docling e OCR:** Como o PDF oficial possui camada textual vetorial nativa e de alta qualidade, o `PdfPipelineOptions` é configurado explicitamente com `do_ocr = False` para maximizar o desempenho e evitar degradação de caracteres jurídicos (`§`, incisos). A execução de OCR é reservada estritamente como mecanismo de contingência (*fallback*) caso alguma página pontual não apresente camada de texto extraível.

### Contrato de Dados (Pydantic Schema)

```python
from typing import List
from pydantic import BaseModel, Field, field_validator, model_validator

class BlocoItemizado(BaseModel):
    texto: str = Field(..., description="Texto integral concatenado")
    itens: List[str] = Field(default_factory=list, description="Lista de itens numerados extraídos")

class FichaEnquadramento(BaseModel):
    id: str = Field(..., description="Identificador único (ex.: 751-01)")
    codigo_enquadramento: str
    tipificacao_resumida: str
    amparo_legal: str
    tipificacao_enquadramento: str
    gravidade: str
    penalidade: str
    medida_administrativa: str
    pode_configurar_crime_transito: str
    infrator: str
    competencia: str = Field(default="", description="Pode ser vazia devido a alterações normativas")
    competencia_alterada_lei_14599: bool = False
    pontuacao: str
    constatacao_infracao: str
    quando_autuar: BlocoItemizado
    quando_nao_autuar: BlocoItemizado
    definicoes_procedimentos: BlocoItemizado
    exemplos_observacoes_ait: BlocoItemizado
    informacoes_complementares: str = Field(default="", description="HTML semântico higienizado")
    paginas: List[int]
    imagens: List[str] = Field(default_factory=list, description="Caminhos locais dos recortes em 300 DPI")

    @field_validator("codigo_enquadramento")
    @classmethod
    def validar_consistencia_id(cls, v: str, info) -> str:
        id_val = info.data.get("id")
        if id_val and v != id_val:
            raise ValueError(f"codigo_enquadramento ('{v}') deve ser idêntico ao id ('{id_val}')")
        return v

    @model_validator(mode="after")
    def inferir_competencia_lei_14599(self) -> "FichaEnquadramento":
        if not self.competencia.strip():
            self.competencia_alterada_lei_14599 = True
        return self
```

---

## 4. Alternativas Consideradas

* **Parsers Textuais Lineares (`pypdf` / `pdfplumber`):** Descartados por extraírem o texto em ordem de fluxo vetorial bruto, quebrando a correlação geométrica de tabelas e falhando na reconstituição de blocos fracionados por quebras de página. Também não oferecem suporte integrado à segmentação e rasterização de diagramas em alta resolução.
* **OCR Integral com Tesseract:** Descartado devido ao alto custo computacional sobre 826 páginas e alta incidência de degradação em caracteres jurídicos especiais (`§`, incisos e alíneas) em um PDF que já possui camada textual vetorial nativa.

---

## 5. Preocupações Transversais

* **Tolerância a Anomalias e Lacunas Normativas:** O extrator tolera inconsistências formais presentes no texto oficial do MBFT, como fichas em que o campo de competência foi deixado em branco em virtude das mudanças promovidas pela Lei nº 14.599/2023. O schema aceita strings vazias para esse campo sem abortar o processamento e marca automaticamente `competencia_alterada_lei_14599 = True` quando o campo for vazio, delegando correções e atribuições conceituais detalhadas ao Enriquecedor (PMS-003).
* **Gerenciamento de Memória e Recursos:** O pipeline realiza a inferência dos modelos de layout com aceleração CUDA em precisão reduzida (`fp16`). Os buffers de renderização gráfica a 300 DPI são liberados da memória imediatamente após a gravação dos arquivos PNG em disco, prevenindo saturação de RAM/VRAM durante a varredura do lote.