from typing import List, Tuple
from mbft_core.models.enriquecimento import CompetenciaEnum, CompetenciaFonteEnum

def obter_competencia_atualizada(codigo_enquadramento: str, competencia_original: str | None) -> Tuple[List[CompetenciaEnum], CompetenciaFonteEnum]:
    """
    Retorna a competência normalizada e a fonte normativa correspondente.
    """
    comp_upper = (competencia_original or "").upper()
    comps = []
    if "MUNICIPAL" in comp_upper:
        comps.append(CompetenciaEnum.MUNICIPAL)
    if "ESTADUAL" in comp_upper:
        comps.append(CompetenciaEnum.ESTADUAL)
    if "RODOVIARIO" in comp_upper or "RODOVIÁRIO" in comp_upper:
        comps.append(CompetenciaEnum.RODOVIARIO)
        
    if not comps:
        # Fallback para infrações anômalas ou de preenchimento inválido
        return [], CompetenciaFonteEnum.NAO_RESOLVIDA
        
    return comps, CompetenciaFonteEnum.MBFT_ORIGINAL
