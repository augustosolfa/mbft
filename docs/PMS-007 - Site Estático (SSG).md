---
PMS: 007
Título: Geração de Site Estático (SSG) das Fichas do MBFT
Autor: José Augusto Solfa Campos Oliveira <augusto@solfa.net>
Status: Rascunho
Tipo: Trilha de Padronização (Standards Track)
Criado: 08-Out-2026
Requer: PMS-002, PMS-003
Substitui: Nenhum
---

# PMS-007: Geração de Site Estático (SSG) das Fichas do MBFT

## 1. Contexto e Escopo

Atualmente, o projeto possui as fichas do MBFT extraídas e enriquecidas em arquivos JSON brutos. Para que o usuário final possa consultar o manual sem onerar os limites de invocação (*requests/CPU*) do Cloudflare Workers, precisamos disponibilizar essas informações em um formato legível por humanos e indexável por motores de busca (SEO).

Esta PMS descreve a criação de um módulo de geração de site estático (SSG - *Static Site Generator*) puramente em Python. Ele transformará os dados estruturados em páginas HTML pré-renderizadas, prontas para hospedagem estática (ex: Cloudflare Pages).

---

## 2. Objetivos e Não Objetivos

* **Objetivos (Goals):**
  * Desenvolver um pipeline batch capaz de gerar uma página HTML para cada Ficha de Enquadramento.
  * Gerar uma página de índice (`index.html`) contendo a lista completa de infrações e regras gerais.
  * Utilizar `Jinja2` como motor de templates.
  * Embutir design minimalista e responsivo (usando CSS simples ou utilitário).
  * Criar URLs previsíveis que poderão ser referenciadas posteriormente pela API de busca (ex: `/fichas/518-51.html`).

* **Não Objetivos (Non-Goals):**
  * **Não é meta** desenhar a API de backend nem o front-end dinâmico de chat/busca neste momento (isso será abordado na PMS-008).
  * **Não é meta** usar frameworks pesados de frontend (como Next.js, Nuxt ou React) para as fichas, uma vez que o conteúdo normativo é essencialmente estático e imutável até a próxima Resolução do CONTRAN.

---

## 3. Design da Solução

### 3.1. Arquitetura do Módulo

O gerador será acomodado em um novo módulo no repositório: `pipelines/ssg` (ou `pipelines/site`). 
Como se trata de um processamento _batch_ e _offline_, ele se qualifica perfeitamente como um "pipeline".

* **Dependências Principais:** `jinja2`, `mbft-core` (para tipagem das fichas).
* **Entrada:** Arquivo consolidado `fichas_enriquecidas.json` (artefato do Enriquecedor).
* **Saída:** Diretório de *build* (ex: `data/processed/site/`) contendo os artefatos finais a serem subidos para o Cloudflare Pages.

### 3.2. Estrutura de URLs (Roteamento Estático)

Para facilitar a integração futura com o Recuperador/API, adotaremos a seguinte topologia de arquivos de saída:

```text
site/
├── index.html                 # Índice principal com listagem/tabela geral
├── css/                       # Estilos globais
└── fichas/
    ├── 518-51.html            # Rota /fichas/518-51.html
    ├── 518-52.html
    └── ...
```

### 3.3. Composição de Dados

O motor de *templates* consumirá as classes pydantic definidas em `mbft-core`. Campos tipicamente difíceis de visualizar no JSON bruto (como medidas administrativas, flags booleanas de recolhimento de CNH) serão transformados em seções visuais ("badges" ou painéis de destaque) na interface HTML.

---

## 4. Alternativas Consideradas

* **Uso de MkDocs ou Sphinx:** 
  * *Por que foi rejeitada:* Embora fantásticos para documentação escrita à mão, o MBFT é gerado puramente a partir de JSON estruturado (modelos Pydantic contendo campos enumerados, imagens recortadas, flags criminais). O uso cru do `Jinja2` permite controle absoluto sobre o HTML injetado por ficha e sobre a semântica da página, sem precisar hackear um sistema de plugins do MkDocs.

---

## 5. Preocupações Transversais

* **Imagens a 300 DPI:** O Extrator (PMS-002) gera imagens das placas associadas aos enquadramentos. O script SSG deverá garantir que o diretório de `imagens/` seja copiado (ou linkado) adequadamente para a pasta final de build (`site/assets/`), garantindo que a renderização ocorra corretamente em dispositivos móveis e de alta densidade de pixels.
* **Tamanho de Build e Cache:** Como são centenas de fichas (aprox. 500+ infrações catalogadas), o script de SSG rodará em fração de segundos graças ao Python, mas o tamanho final do diretório deverá ser avaliado para respeitar os limites de upload do provedor de hospedagem estática.
