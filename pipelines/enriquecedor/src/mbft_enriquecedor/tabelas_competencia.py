from mbft_core.models.enriquecimento import CompetenciaEnum

# Tabela Canônica de Competência Normativa (Lei nº 14.599/2023)
# Mapeia os códigos de enquadramento (que tiveram competência esvaziada ou alterada)
# para a competência correta (MUNICIPAL, ESTADUAL, CONCORRENTE).
# TODO: Preencher com a lista exaustiva de códigos conforme anexo da Lei 14.599.
COMPETENCIA_LEI_14599: dict[str, CompetenciaEnum] = {
    # Exemplos de mapeamento:
    # "501-00": CompetenciaEnum.ESTADUAL,
    # "516-91": CompetenciaEnum.MUNICIPAL,
    # "518-51": CompetenciaEnum.CONCORRENTE,
}

def obter_competencia_atualizada(codigo_enquadramento: str, competencia_original: str | None) -> tuple[CompetenciaEnum, bool]:
    """
    Retorna a competência normalizada e um booleano indicando se foi resolvida pela tabela da Lei 14.599.
    Se a ficha já tinha competência válida e não está na tabela, tenta inferir a partir do texto original.
    """
    if codigo_enquadramento in COMPETENCIA_LEI_14599:
        return COMPETENCIA_LEI_14599[codigo_enquadramento], True
    
    # Se não está na tabela de alterações, faz parse do texto original
    comp_upper = (competencia_original or "").upper()
    if "MUNICIPAL" in comp_upper and "ESTADUAL" not in comp_upper:
        return CompetenciaEnum.MUNICIPAL, False
    elif "ESTADUAL" in comp_upper and "MUNICIPAL" not in comp_upper:
        return CompetenciaEnum.ESTADUAL, False
    elif "CONCORRENTE" in comp_upper or ("ESTADUAL" in comp_upper and "MUNICIPAL" in comp_upper):
        return CompetenciaEnum.CONCORRENTE, False
    
    # Fallback default para infrações sem preenchimento que não constam na tabela (geralmente concorrentes após a Lei)
    return CompetenciaEnum.CONCORRENTE, True
