# MBFT Enriquecedor (`mbft-enriquecedor`)

Módulo de processamento em lote (*batch*) responsável pelo enriquecimento semântico, normalização categórica sob vocabulário controlado e extração atômica de regras normativas das fichas do Manual Brasileiro de Fiscalização de Trânsito (**MBFT**).

> **Nota de Arquitetura**: Este arquivo é um guia operacional e de desenvolvimento (*Developer Guide*).
> Para a documentação completa de arquitetura, taxonomia normativa e decisões de design, consulte o Documento de Design **PMS-003** em `docs/PMS-003 - Design do enriquecedor.md`.
> Para os contratos de dados de entrada (`Ficha`) e saída (`FichaEnriquecida`), consulte a **PMS-009** e o pacote **`mbft-core`** em `pipelines/core/README.md`.

---

## 1. Responsabilidades do Módulo

1. **Normalização Categórica**:
   - Converte atributos brutos em enumerações estritas do domínio (`GravidadeEnum`, `PenalidadeEnum`, `MedidaAdministrativaEnum`, `InfratorEnum`, `ConstatacaoInfracaoEnum`).
   - Normalização e extração limpa de pontuação numérica (`pontuacao_valor`) e flags de nota de rodapé (`pontuacao_asterisco`, `pontuacao_suspensiva`).
   - Higienização e separação de vazamentos tabulares entre menções penais e categorias de infratores.
2. **Resolução de Competência**:
   - Mapeia as competências declaradas no texto (`MUNICIPAL`, `ESTADUAL`, `RODOVIARIO`).
   - Identifica casos anômalos com a fonte `NAO_RESOLVIDA`, marcando auditoria em `revisao_manual_necessaria`.
3. **Extração de Informação Determinística (IE)**:
   - Extrai referências canônicas a artigos e incisos do CTB (`ReferenciaCTB`).
   - Extrai menções formais a resoluções do CONTRAN.
   - Decompõe seções normativas (*Quando Autuar*, *Quando Não Autuar*, *Definições e Procedimentos*, *Exemplos de AIT*) em itens atômicos estruturados (`ItemRegra`), identificando códigos concomitantes e de redirecionamento.
4. **Cura da Parte Geral**:
   - Descartar ruído pré-textual/editorial e seções de mero ponteiro (`secoes_descartadas`).
   - Extrair o glossário de siglas (`ItemGlossario`) e classificar as seções (`TipoSecaoParteGeralEnum`).
   - Vincular deterministicamente as seções temáticas às fichas (`enquadramentos_alvo`) e popular `enquadramentos_correlatos` em cada ficha.

---

## 2. Entradas e Saídas

- **Entrada**:
  - `data/processed/extrator/fichas_mbft.json` (artefato bruto consolidado do Extrator).
  - `data/processed/extrator/mbft_parte_geral.md` (Parte Geral em Markdown; opcional — processada quando presente).
- **Saídas**:
  - `data/processed/enriquecedor/fichas_enriquecidas.json` (JSON consolidado aderente ao contrato `FichaEnriquecida`).
  - `data/processed/enriquecedor/parte_geral_enriquecida.json` (Parte Geral curada aderente ao contrato `ParteGeralEnriquecida`: seções classificadas, glossário de siglas e vínculos determinísticos às fichas).
  - `data/processed/enriquecedor/relatorio_enriquecimento.md` (relatório de auditoria e estatísticas da base).

---

## 3. Execução

O módulo pode ser executado via CLI registrada no UV Workspace:

```bash
# Execução direta via CLI do pacote
uv run mbft-enriquecedor

# Ou execução direta pelo módulo Python
uv run python -m mbft_enriquecedor.main
```
