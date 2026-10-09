# MBFT Enriquecedor (`mbft-enriquecedor`)

Módulo de processamento em lote (*batch*) responsável pelo enriquecimento semântico, normalização categórica sob vocabulário controlado e extração atômica de regras normativas das fichas do Manual Brasileiro de Fiscalização de Trânsito (**MBFT**), conforme especificado na **PMS-003**.

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

---

## 2. Entradas e Saídas

- **Entrada**:
  - `data/processed/extrator/fichas_mbft.json` (artefato bruto consolidado do Extrator).
- **Saídas**:
  - `data/processed/enriquecedor/fichas_enriquecidas.json` (JSON consolidado aderente ao contrato `FichaEnriquecida`).
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
