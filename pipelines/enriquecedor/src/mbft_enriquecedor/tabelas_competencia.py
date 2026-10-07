from typing import List
from mbft_core.models.enriquecimento import CompetenciaEnum

# Tabela Canônica de Competência Normativa (Lei nº 14.599/2023)
COMPETENCIA_LEI_14599: dict[str, List[CompetenciaEnum]] = {
    # Exemplos:
    # "501-00": [CompetenciaEnum.ESTADUAL],
    # "516-91": [CompetenciaEnum.MUNICIPAL],
    # "518-51": [CompetenciaEnum.MUNICIPAL, CompetenciaEnum.ESTADUAL],
}

def obter_competencia_atualizada(codigo_enquadramento: str, competencia_original: str | None) -> tuple[List[CompetenciaEnum], bool]:
    """
    Retorna a competência normalizada e um booleano indicando se foi resolvida pela tabela da Lei 14.599.
    """
    if codigo_enquadramento in COMPETENCIA_LEI_14599:
        return COMPETENCIA_LEI_14599[codigo_enquadramento], True
    
    comp_upper = (competencia_original or "").upper()
    comps = []
    if "MUNICIPAL" in comp_upper:
        comps.append(CompetenciaEnum.MUNICIPAL)
    if "ESTADUAL" in comp_upper:
        comps.append(CompetenciaEnum.ESTADUAL)
    if "RODOVIARIO" in comp_upper or "RODOVIÁRIO" in comp_upper:
        comps.append(CompetenciaEnum.RODOVIARIO)
        
    if not comps:
        # Fallback default para infrações sem preenchimento que não constam na tabela
        # Assumiremos Municipal e Estadual como concorrentes
        return [CompetenciaEnum.MUNICIPAL, CompetenciaEnum.ESTADUAL], True
        
    return comps, False
