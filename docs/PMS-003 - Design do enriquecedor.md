---
PMS: 003
Título: Design do Enriquecedor e Vetorizador do MBFT
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 06-Out-2026
Requer: PMS-001, PMS-002
Substitui: Nenhum
---

# PMS-003: Design do Enriquecedor e Vetorizador do MBFT

## 1. Contexto e Escopo

O Manual Brasileiro de Fiscalização de Trânsito (MBFT) é extraído na Etapa 1 (PMS-002), que entrega dois artefatos brutos fundamentais:
1. `data/processed/extrator/fichas_mbft.json`: 404 fichas de fiscalização com texto semântico e estruturação inicial;
2. `data/processed/extrator/mbft_parte_geral.md`: o texto integral das disposições gerais e normativas (páginas 1 a 31 do PDF oficial).

Embora o Extrator preserve a integridade geométrica e textual do documento original, os dados resultantes ainda apresentam características de texto livre não normalizado, variações sintáticas de termos regulatórios e lacunas decorrentes de atualizações legais (como o campo de competência esvaziado nas fichas em decorrência da promulgação da Lei nº 14.599/2023). Além disso, os modelos de busca vetorial exigem segmentação (*chunking*) contextualizada e representações densas (*embeddings*) para viabilizar recuperação semântica de alta precisão.

Este documento especifica o **Enriquecedor** (Etapa 2 do PMS-001), pipeline *batch* em Python 3.14 gerenciado via `uv`, responsável por:
1. **Normalização Categórica**: Padronizar atributos regulatórios (gravidade, penalidade, medida administrativa, infrator, constatação, pontuação e crime) sob vocabulário controlado estrito (Enums);
2. **Resolução de Competência**: Resolver formalmente a competência das infrações afetadas pela Lei nº 14.599/2023 (Municipal, Estadual ou Concorrente) através de tabela canônica de referência normativa;
3. **Extração de Informação Determinística (IE)**: Identificar e estruturar menções a artigos/incisos do CTB, Resoluções do CONTRAN e códigos de enquadramentos correlatos citados nos campos textuais;
4. **Segmentação Semântica Contextualizada (Chunking)**: Fracionar as fichas por seções temáticas autônomas e a Parte Geral por blocos estruturados em Markdown, anexando metadados ricos e prefixos contextuais;
5. **Geração de Embeddings**: Calcular vetores densos (1024 dimensões) utilizando o modelo `BAAI/bge-m3` com aceleração por hardware (PyTorch CUDA em GPU NVIDIA GeForce RTX 4070), compatibilizado nativamente com o Cloudflare Workers AI (`@cf/baai/bge-m3`) para a futura etapa de busca em tempo de execução (PMS-005).

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Normalizar os atributos categóricos das 404 fichas para vocabulários controlados estritos, eliminando inconsistências ortográficas, plurais irregulares e pontuações espúrias.
  * Preservar os campos originais brutos (`*_original`) ao lado dos atributos normalizados para auditoria e rastreabilidade jurídica completa.
  * Resolver a atribuição de competência das fichas com campo em branco ou marcado como `competencia_alterada_lei_14599 = True`, categorizando-as deterministicamente como `MUNICIPAL`, `ESTADUAL` ou `CONCORRENTE`, com registro explícito da fonte normativa.
  * Extrair referências estruturadas ao Código de Trânsito Brasileiro (artigo, parágrafo, inciso, alínea), resoluções do CONTRAN e códigos correlatos (`\d{3}-\d{2}`) a partir dos blocos normativos (*Quando Autuar*, *Quando Não Autuar*, *Definições e Procedimentos* e *Informações Complementares*).
  * Gerar chunks semânticos autônomos com enriquecimento de cabeçalho (*chunk prefixing*) para as Fichas e segmentação hierárquica por cabeçalhos Markdown (512 a 800 tokens) para a Parte Geral.
  * Computar embeddings densos de 1024 dimensões via `BAAI/bge-m3` localmente via GPU CUDA, gravando os vetores em formato compacto e de alta performance Apache Parquet.
  * Fornecer pacote modular `pipelines/enriquecedor` integrado ao UV Workspace da raiz, com CLI própria (`mbft-enriquecedor`) e relatório automatizado de auditoria (`relatorio_enriquecimento.md`).

* **Não Objetivos (Non-Goals):**
  * Não é meta usar LLMs para inferência ou extração no enriquecimento; toda a extração de informação e normalização de atributos é estritamente determinística, baseada em regras, regex compiladas e tabelas de de-para, garantindo 100% de reprodutibilidade e zero custo operacional de chamadas de API.
  * Não é meta realizar a persistência em banco de dados relacional SQL ou no Cloudflare Vectorize (escopo estrito da Carga / PMS-004).
  * Não é meta responder perguntas ou expor endpoints HTTP em tempo real (escopo do Recuperador / PMS-005 e Gerador / PMS-006).

---

## 3. Design da Solução

### 3.1. Visão Geral do Pipeline de Enriquecimento

O módulo processa os artefatos da extração através de estágios modulares e desacoplados:

```
[ data/processed/extrator/ ]
   ├── fichas_mbft.json
   └── mbft_parte_geral.md
             │
             ▼
   [ 1. Normalizador de Vocabulário & Regras ]
        ├── Sanitização de Enums (Gravidade, Penalidade, Medidas, Infrator, etc.)
        └── Resolução de Competência (Tabela Canônica Lei nº 14.599/2023)
             │
             ▼
   [ 2. Extrator de Entidades & Relações (IE Determinístico) ]
        ├── Referências ao CTB (Art., §, Inc., Alínea)
        ├── Resoluções do CONTRAN
        └── Enquadramentos Correlatos (^\d{3}-\d{2}$)
             │
             ▼
   [ 3. Gerador de Chunks Semânticos Contextualizados ]
        ├── Chunks Temáticos de Fichas (Ementa, Quando Autuar, Quando Não Autuar, etc.)
        └── Chunks Hierárquicos da Parte Geral (Markdown Headers 512-800 tokens)
             │
             ▼
   [ 4. Vetorizador Batch CUDA (BAAI/bge-m3) ] ──> RTX 4070 (PyTorch CUDA 13.2)
             │
             ├───> data/processed/enriquecedor/fichas_enriquecidas.json
             ├───> data/processed/enriquecedor/chunks_parte_geral.json
             ├───> data/processed/enriquecedor/embeddings_mbft.parquet
             └───> data/processed/enriquecedor/relatorio_enriquecimento.md
```

---

### 3.2. Normalização Categórica e Vocabulário Controlado

Os dados extraídos do PDF trazem variações textuais que dificultam filtros facetados em bancos relacionais e consultas precisas. O enriquecedor converte esses dados em enumerações canônicas:

| Atributo Original | Valores Canônicos Normalizados (Enums) | Regras de Tratamento |
| :--- | :--- | :--- |
| `gravidade` | `LEVE`, `MEDIA`, `GRAVE`, `GRAVISSIMA`, `NAO_APLICAVEL` | Remoção de acentos e correspondência exata de tokens; "Não aplicável" para infrações de trânsito específicas (ex.: obras/eventos). |
| `penalidade` | `MULTA`, `ADVERTENCIA_POR_ESCRITO`, `SUSPENSAO_DIREITO_DIRIGIR`, `CASSAÇÃO_CNH`, `NAO_APLICAVEL` | Decomposição de listas em array de enums quando houver múltiplas penalidades previstas. |
| `medida_administrativa` | `RETENCAO_VEICULO`, `REMOCAO_VEICULO`, `RECOLHIMENTO_CNH`, `RECOLHIMENTO_CRLV`, `TRANSBORDO_CARGA`, `REALIZACAO_TESTE_ALCOOLEMIA`, `NAO_APLICAVEL` | Normalização de variações redacionais do manual para conjunto fechado de medidas do CTB. |
| `pode_configurar_crime_transito` | `True` / `False` | Mapeamento direto de `"SIM"` / `"NÃO"`. |
| `infrator` | `CONDUTOR`, `PROPRIETARIO`, `CONDUTOR_OU_PROPRIETARIO`, `PESSOA_FISICA_OU_JURIDICA`, `EMBARCADOR`, `TRANSPORTADOR`, `PEDESTRE` | Unificação de termos compostos e plurais para valores canônicos. |
| `pontuacao` | `valor`: int (0, 3, 4, 5, 7); `especial_sem_pontos`: bool; `pontuacao_suspensiva`: bool | Infrações com suspensão direta (ex.: Art. 165) ou cometidas por pessoa jurídica sem pontuação recebem flags dedicadas. |
| `constatacao_infracao` | `COM_ABORDAGEM`, `SEM_ABORDAGEM`, `MEDIANTE_ABORDAGEM_OU_NAO`, `VIDEOMONITORAMENTO` | Normalização de termos descritivos de abordagem do agente. |

---

### 3.3. Resolução da Competência e Lei nº 14.599/2023

A Lei nº 14.599/2023 reestruturou substancialmente as competências de fiscalização entre órgãos municipais e estaduais (alterando os artigos 22 e 24 do CTB). No arquivo oficial do MBFT, as fichas afetadas por essa alteração tiveram o campo preenchido com avisos genéricos ou mantido em branco.

O Enriquecedor resolve essa questão por meio de uma **Tabela Canônica de Competência Normativa**:
1. O texto original é mantido no campo `competencia_original` (preservando literalidade histórica do PDF);
2. A competência efetiva é atribuída ao campo `competencia_normalizada`:
   - `MUNICIPAL`: Infrações privativas do órgão executivo municipal de trânsito;
   - `ESTADUAL`: Infrações privativas do órgão rodoviário ou estadual (ex.: fiscalização documental e condutor);
   - `CONCORRENTE`: Infrações de competência compartilhada e fiscalização mútua (a grande maioria das infrações de circulação e operacionais pós-Lei 14.599/2023);
3. O campo `competencia_fonte` registra a proveniência do dado:
   - `MBFT_ORIGINAL`: Quando o manual já continha a definição explícita sem conflito;
   - `RESOLUCAO_LEI_14599`: Quando foi resolvida pela tabela de de-para normativa do módulo.

---

### 3.4. Extração de Informação Determinística (IE)

Para viabilizar consultas cruzadas, filtros no banco SQL e expansão de contexto sem depender de chamadas custosas a LLMs, o Enriquecedor executa parsers sintáticos com expressões regulares pré-compiladas sobre todos os campos de texto:

1. **Artigos do CTB**:
   - Padrão Regex: `(?:Art\.|Artigo)\s+(\d{1,3})(?:-([A-Z]))?(?:,\s*([§\dºª]+))?(?:,\s*inciso\s+([IVXLCDM]+|[a-z]+))?(?:,\s*alínea\s+['"]?([a-z])['"]?)?`
   - Saída Estruturada: Lista de objetos com `artigo`, `paragrafo`, `inciso` e `alinea`.
2. **Resoluções do CONTRAN**:
   - Padrão Regex: `(?:Resolução|Res\.)\s+(?:do\s+)?CONTRAN\s+n[ºo°]?\s*(\d+)(?:/(\d{2,4}))?`
   - Saída Estruturada: Lista de referências padronizadas (ex.: `CONTRAN 965/2022`).
3. **Enquadramentos Correlatos**:
   - Padrão Regex: `\b(\d{3}-\d{2})\b` (excluindo o próprio código da ficha ativa).
   - Identifica remissões a outras infrações nos textos de *Quando Autuar* e *Quando Não Autuar*.
4. **Palavras-chave e Termos Operacionais**:
   - Extração de vocabulário de equipamentos e medidas aferidas (ex.: "etilômetro", "radar", "balança", "tacógrafo", "decalque").

---

### 3.5. Granularidade de Segmentação Semântica (Chunking)

Para busca vetorial em RAG jurídico, chunks monolíticos por página diluem os trechos operacionais específicos, enquanto micro-chunks por linha perdem o contexto legal. Adota-se a **Granularidade por Seção Temática Contextualizada**:

#### A. Segmentação de Fichas de Enquadramento
Cada uma das 404 fichas é subdividida em chunks estruturados, onde cada chunk recebe um cabeçalho fixo (*prefixo contextual*) para ancorar a representação vetorial:

- **Prefixo de Contexto Padrão**:
  ```text
  [INFORMAÇÃO DA INFRAÇÃO]
  Código: {codigo_enquadramento} | Tipificação: {tipificacao_resumida}
  Amparo Legal: {amparo_legal} | Infrator: {infrator} | Gravidade: {gravidade} | Competência: {competencia}
  ```
- **Tipos de Chunks por Ficha**:
  1. `EMENTA`: Cabeçalho completo, amparo legal e enquadramento formal;
  2. `QUANDO_AUTUAR`: Prefixo + itens normativos de lavratura do auto;
  3. `QUANDO_NAO_AUTUAR`: Prefixo + exceções, tolerâncias e infrações subsidiárias;
  4. `DEFINICOES_PROCEDIMENTOS`: Prefixo + rotinas operacionais, regulamentações e medições;
  5. `EXEMPLOS_AIT`: Prefixo + textos padronizados para o campo de observações do auto de infração;
  6. `INFORMACOES_COMPLEMENTARES`: Prefixo + texto e tabelas de notas técnicas (se presentes).

#### B. Segmentação da Parte Geral (`mbft_parte_geral.md`)
O arquivo Markdown das páginas 1 a 31 é segmentado com base na árvore de títulos (`#`, `##`, `###`):
- Divisão semântica por seções com limite de 512 a 800 tokens;
- Rastreamento da hierarquia de tópicos (ex.: `Disposições Gerais > Competência de Fiscalização > Delegação`);
- Preservação da indicação de página original extraída do Extrator (ex.: `<!-- Página 12 -->`).

---

### 3.6. Geração de Embeddings (`BAAI/bge-m3`)

- **Modelo**: `BAAI/bge-m3` ([Chen et al., 2024](https://arxiv.org/abs/2402.03216)).
- **Dimensão Vetorial**: 1024 floats de 32 bits (normalizados em norma L2 para similaridade por cosseno).
- **Justificativa da Escolha**:
  - Suporte de ponta à língua portuguesa e a textos técnicos e jurídicos complexos;
  - Capacidade nativa de janelas de contexto de até 8192 tokens;
  - Execução batch local rápida via PyTorch CUDA na GPU local (NVIDIA RTX 4070, ~12 GB VRAM);
  - **Paridade direta com o Cloudflare Workers AI**: A Cloudflare disponibiliza o modelo `@cf/baai/bge-m3` em sua infraestrutura global na borda (*edge*), permitindo que a etapa síncrona do Recuperador (PMS-005) gere os embeddings das perguntas dos usuários sem divergência de espaço vetorial e com custo zero de API externa.

---

### 3.7. Contratos de Dados e Guardrails Compartilhados (`mbft-core`)

Todos os modelos e contratos de validação residem no pacote neutro compartilhado `packages/core` (`mbft-core`). O Enriquecedor consome a saída do Extrator (`Ficha`, `CampoNormativo`) como guardrail de entrada e produz seus artefatos estruturados e vetoriais (`FichaEnriquecida`, `ChunkPayload`, `ChunkMetadados`) a partir desse pacote central, servindo de guardrail de entrada para a Carga (PMS-004):

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class GravidadeEnum(str, Enum):
    LEVE = "LEVE"
    MEDIA = "MEDIA"
    GRAVE = "GRAVE"
    GRAVISSIMA = "GRAVISSIMA"
    NAO_APLICAVEL = "NAO_APLICAVEL"

class CompetenciaEnum(str, Enum):
    MUNICIPAL = "MUNICIPAL"
    ESTADUAL = "ESTADUAL"
    CONCORRENTE = "CONCORRENTE"

class CompetenciaFonteEnum(str, Enum):
    MBFT_ORIGINAL = "MBFT_ORIGINAL"
    RESOLUCAO_LEI_14599 = "RESOLUCAO_LEI_14599"

class ReferenciaCTB(BaseModel):
    artigo: str = Field(..., description="Número do artigo (ex.: '165', '230')")
    paragrafo: Optional[str] = Field(None, description="Parágrafo citado (ex.: '§ 1º', 'único')")
    inciso: Optional[str] = Field(None, description="Inciso em algarismo romano (ex.: 'V', 'VII')")
    alinea: Optional[str] = Field(None, description="Alínea citada (ex.: 'a', 'b')")

class FichaEnriquecida(BaseModel):
    id: str = Field(..., description="Código de enquadramento (ex.: '751-01')")
    tipificacao_resumida: str
    codigo_enquadramento: str
    amparo_legal: str
    tipificacao_enquadramento: str
    
    # Atributos brutos originais mantidos para auditoria
    gravidade_original: str
    penalidade_original: str
    medida_administrativa_original: str
    infrator_original: str
    competencia_original: str
    constatacao_infracao_original: str
    pontuacao_original: str
    
    # Atributos normalizados em vocabulário controlado
    gravidade: GravidadeEnum
    penalidades: List[str]
    medidas_administrativas: List[str]
    infratores: List[str]
    competencia: CompetenciaEnum
    competencia_fonte: CompetenciaFonteEnum
    competencia_alterada_lei_14599: bool
    crime_transito: bool
    pontuacao_valor: int = Field(default=0, description="0, 3, 4, 5 ou 7 pontos")
    pontuacao_suspensiva: bool = Field(default=False, description="True se gera suspensão direta da CNH")
    constatacao_infracao: List[str]
    
    # Informações Extraídas (IE)
    artigos_ctb: List[ReferenciaCTB] = Field(default_factory=list)
    resolucoes_contran: List[str] = Field(default_factory=list)
    enquadramentos_correlatos: List[str] = Field(default_factory=list)
    termos_chave: List[str] = Field(default_factory=list)
    
    # Textos canônicos e metadados
    quando_autuar_texto: str
    quando_nao_autuar_texto: str
    definicoes_procedimentos_texto: str
    exemplos_observacoes_ait_texto: str
    informacoes_complementares_html: str
    paginas: List[int]
    imagens: List[str]

class ChunkMetadados(BaseModel):
    chunk_id: str = Field(..., description="Identificador unívoco do chunk (ex.: '751-01_QUANDO_AUTUAR' ou 'PG_CAP_02_SEC_01')")
    tipo_documento: str = Field(..., description="'FICHA' ou 'PARTE_GERAL'")
    origem_id: str = Field(..., description="Código da ficha ou ID do capítulo da Parte Geral")
    secao: str = Field(..., description="Nome da seção temática")
    hierarquia_titulos: List[str] = Field(default_factory=list)
    paginas: List[int]
    artigos_ctb_associados: List[str] = Field(default_factory=list)
    competencia: Optional[str] = None

class ChunkPayload(BaseModel):
    metadados: ChunkMetadados
    texto_contextualizado: str = Field(..., description="Texto final entregue ao modelo de embedding")
    tokens_estimados: int
```

---

### 3.8. Formatos de Saída e Persistência Intermediária

Todos os artefatos são gravados no diretório `data/processed/enriquecedor/`:

1. `fichas_enriquecidas.json`: Array serializado das 404 fichas enriquecidas com o schema `FichaEnriquecida`.
2. `chunks_parte_geral.json`: Array serializado de chunks semânticos da Parte Geral com o schema `ChunkPayload`.
3. `embeddings_mbft.parquet`: Tabela colunar compacta contendo:
   - `chunk_id` (`string`, chave primária);
   - `origem_id` (`string`, chave estrangeira para a ficha ou Parte Geral);
   - `tipo_documento` (`string`);
   - `secao` (`string`);
   - `texto_contextualizado` (`string`);
   - `embedding` (`list<float32>`, dimensão fixa 1024).
4. `relatorio_enriquecimento.md`: Relatório executivo de auditoria detalhando estatísticas de normalização, distribuição de competências resolvidas, densidade de referências ao CTB e volumetria de vetores.

---

## 4. Alternativas Consideradas

* **Extração de Informação via LLM em Lote (Zero-shot / Few-shot):**
  * *Por que foi rejeitada:* O custo financeiro de APIs externas, a latência de rede e a imprevisibilidade de alucinação jurídica tornam o uso de LLMs desvantajoso para extração de dados normativos explícitos. O MBFT segue padrões redacionais sistemáticos, permitindo que analisadores léxicos e expressões regulares compiladas atinjam 100% de acurácia com custo marginal zero e auditabilidade absoluta.
* **Modelo de Embeddings `text-embedding-3-small` da OpenAI:**
  * *Por que foi rejeitado:* Embora ofereça alta qualidade semântica, introduz acoplamento estrito a uma API comercial proprietária e incorre em custos recorrentes tanto na etapa *batch* quanto em cada requisição de consulta no *runtime*. O modelo aberto `BAAI/bge-m3` atinge desempenho de recuperação comparável ou superior em textos jurídicos em português e já possui suporte de execução gratuita na infraestrutura do Cloudflare Workers AI.
* **Granularidade de Ficha Monolítica (1 vetor por ficha de fiscalização):**
  * *Por que foi rejeitada:* Fichas extensas (como a Ficha 683-11, com 6 páginas de texto) diluem conceitos específicos quando representadas em um único vetor médio de 1024 dimensões. Um usuário buscando uma regra excepcional de "Quando Não Autuar" teria baixa similaridade se o vetor fosse dominado pelo texto extenso de "Definições e Procedimentos".
* **Armazenamento de Vetores em JSON/JSONL Puro:**
  * *Por que foi rejeitado:* Armazenar dezenas de milhares de vetores de 1024 dimensões em strings JSON gera artefatos inflados (centenas de megabytes) e lentidão de I/O na etapa de Carga. O formato colunar Apache Parquet reduz o tamanho em disco em mais de 75% e permite leitura vetorizada instantânea no Python/Polars/PyArrow.

---

## 5. Preocupações Transversais

* **Auditabilidade e Segurança Jurídica:**
  * Nenhuma informação original do MBFT é descartada; os campos literais extraídos do PDF continuam acessíveis no JSON enriquecido com o sufixo `_original`.
  * As resoluções de competência decorrentes da Lei nº 14.599/2023 contêm registro explícito de auditoria (`competencia_fonte = RESOLUCAO_LEI_14599`), permitindo aos órgãos fiscalizadores distinguir entre o texto oficial do CONTRAN e a atualização legal posterior.
* **Desempenho e Eficiência de Recursos de Hardware:**
  * A geração de vetores utiliza PyTorch com aceleração CUDA 13.2 na GPU NVIDIA GeForce RTX 4070 em lotes de inferência controlados (*batch size* de 32 a 64 chunks), garantindo tempo total de vetorização do MBFT inferior a 2 minutos com ocupação moderada de VRAM (< 4 GB).
* **Idempotência e Reprodutibilidade:**
  * O pipeline de enriquecimento é estritamente puro e idempotente: dada a mesma entrada em `data/processed/extrator/`, a execução produzirá arquivos com hashes e vetores determinísticos idênticos.
