---
PMS: 001
Título: Mecânismo RAG do Manual Brasileiro de Fiscalização de Trânsito
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 06-Out-2026
Requer: Nenhum
Substitui: Nenhum
---

# PMS-001: Mecânismo RAG do Manual Brasileiro de Fiscalização de Trânsito

## 1. Contexto e Escopo
O Manual Brasileiro de Fiscalização de Trânsito (MBFT) é um documento oficial, aprovado por Resolução do CONTRAN (Conselho Nacional de Trânsito), destinado a *"autoridades de trânsito, seus agentes e órgãos de julgamento de 1ª e 2ª instâncias"*. [^mbft]
É disponibilizado apenas em formato PDF, tornando difícil a leitura em dispositivos com tela pequena, e permitindo apenas a busca textual exata.
Este documento apresenta a visão geral do mecânismo proposto, com a descrição dos módulos sendo objeto de Propostas de Melhoria do Sistema específicos.

[^mbft]: [Manual Brasileiro de Fiscalização de Trânsito.](https://www.gov.br/transportes/pt-br/assuntos/transito/conteudo-contran/resolucoes/mbvt20222.pdf)


---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Extrair o conteúdo do MBFT de maneira estruturada
  * Permitir busca semântica
  * Gerar respostas coerentes e textuais limitadas à informação presente no manual
  * Apresentar os enquadramentos em formato web
  * Fornecer interface web para entrada da busca textual do usuário

* **Não Objetivos (Non-Goals):**
  * Não é meta aplicar jurisprudência que modifique o entendimento
  * Não é meta tipificar o caso concreto em determinado enquadramento


---

## 3. Design da Solução

### Etapas / módulos
O mecânismo divide-se em 4 etapas: Extrator, Enriquecedor, Carga, Recuperador e Gerador.

1. **Extrator**: recebe o arquivo PDF oficial do MBFT e retorna o texto da parte geral e uma lista em json com os campos das fichas de enquadramento, além das imagens associadas.
2. **Enriquecedor**: normaliza os campos de dados categóricos. Gera novos campos com base em dados extraídos dos campos de texto livre (enquadramentos correla-tos, por exemplo).
3. **Carga**: salva os enquadramentos no banco SQL. Gera embeddings e os salva junto com referência aos enquadramentos no banco vetorizado.
4. **Recuperador**: recebe a busca textual do usuário, transforma em embedding, consulta no banco vetorial e retorna os dados dos enquadramentos encontrados.
5. **Gerador**: utiliza uma LLM para enviar a pergunta do usuário, a informação obtida pelo recuperador e um prompt direcionador para gerar a resposta a ser encaminhada ao usuário.


As etapas 1, 2 e 3 são executadas apenas uma vez a cada atualização do MBFT.
As etapas 4 e 5 serão fornecidas por meio de API REST.

### Front End
Página web estática simples para consumo da API do sistema.

---

## 4. Alternativas Consideradas

* Foi considerado o uso do FTS5 (Full-Text Search 5) embutido no SQLite ao invés de embeddings, mas com isto se perderia a busca por sinônimos. O custo atual do embeddings não justifica tal perda de precisão.


---

## 5. Preocupações Transversais

* A geração de respostas com o uso de LLM ainda é cara para grandes volumes de acessos. O acesso constante de bots de indexação e treinamento de modelos de LLM piorou a situação. Terão que ser inseridos mecanismos que reaproveitem respostas anteriores, além de limites de custos por período.
