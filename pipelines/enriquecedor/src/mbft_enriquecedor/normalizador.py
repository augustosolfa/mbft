import re
from typing import List, Tuple
from mbft_core.models.enriquecimento import (
    GravidadeEnum, PenalidadeEnum, MedidaAdministrativaEnum,
    InfratorEnum, ConstatacaoInfracaoEnum, ReferenciaCTB
)

# Regex para limpar vazamento tabular de artigos na coluna de infrator/crime
REGEX_ARTIGO_CTB = re.compile(r"((?:Art\.?\s*)?(\d{1,3}(?:\s*-[A-Za-z]+)?)\s*do\s*CTB)", re.IGNORECASE)

def normalizar_gravidade(texto: str) -> GravidadeEnum:
    t = texto.upper().replace("Í", "I").replace("É", "E").replace("Á", "A")
    if "GRAVISSIMA" in t: return GravidadeEnum.GRAVISSIMA
    if "GRAVE" in t: return GravidadeEnum.GRAVE
    if "MEDIA" in t: return GravidadeEnum.MEDIA
    if "LEVE" in t: return GravidadeEnum.LEVE
    return GravidadeEnum.NAO_APLICAVEL

def normalizar_penalidades(texto: str) -> List[PenalidadeEnum]:
    t = texto.upper()
    rens = []
    if "MULTA" in t: rens.append(PenalidadeEnum.MULTA)
    if "ADVERTENCIA" in t: rens.append(PenalidadeEnum.ADVERTENCIA_POR_ESCRITO)
    if "SUSPENSAO" in t: rens.append(PenalidadeEnum.SUSPENSAO_DIREITO_DIRIGIR)
    if "CASSACAO" in t: rens.append(PenalidadeEnum.CASSACAO_CNH)
    return rens if rens else [PenalidadeEnum.NAO_APLICAVEL]

def normalizar_medidas_administrativas(texto: str) -> List[MedidaAdministrativaEnum]:
    t = texto.upper()
    rens = []
    if "RETENCAO" in t: rens.append(MedidaAdministrativaEnum.RETENCAO_VEICULO)
    if "REMOCAO" in t: rens.append(MedidaAdministrativaEnum.REMOCAO_VEICULO)
    if "RECOLHIMENTO" in t and "CNH" in t: rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_CNH)
    if "RECOLHIMENTO" in t and "CRLV" in t: rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_CRLV)
    if "TRANSBORDO" in t: rens.append(MedidaAdministrativaEnum.TRANSBORDO_CARGA)
    if "ALCOOLEMIA" in t or "TESTE" in t: rens.append(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA)
    return rens if rens else [MedidaAdministrativaEnum.NAO_APLICAVEL]

def higienizar_infrator_crime(texto_infrator: str, texto_crime: str | None) -> Tuple[List[InfratorEnum], bool, List[ReferenciaCTB]]:
    """
    Higieniza a coluna de Infrator e de Crime de Trânsito, resolvendo vazamentos tabulares.
    Retorna (infratores_normalizados, tem_crime, artigos_ctb_extraidos).
    """
    texto_combinado = f"{texto_infrator} {texto_crime or ''}".strip()
    
    artigos_extraidos = []
    # Buscar artigos vazados
    for match in REGEX_ARTIGO_CTB.finditer(texto_combinado):
        # match.group(2) contém o número do artigo (ex: 306)
        artigos_extraidos.append(ReferenciaCTB(artigo=match.group(2)))
    
    # Remover o vazamento do texto do infrator
    texto_infrator_limpo = REGEX_ARTIGO_CTB.sub("", texto_infrator).strip()
    texto_infrator_limpo = texto_infrator_limpo.replace("SIM", "").replace("NÃO", "").replace("NAO", "").strip()
    
    # Validar se é crime
    tem_crime = False
    if "SIM" in (texto_crime or "").upper() or "SIM" in texto_infrator.upper():
        tem_crime = True
    if artigos_extraidos:
        tem_crime = True
        
    # Normalizar Infrator
    t_inf = texto_infrator_limpo.upper()
    infratores = []
    
    # Tratamento para Condutor E Proprietário / OU
    if "CONDUTOR" in t_inf and "PROPRIETARIO" in t_inf:
        infratores.append(InfratorEnum.CONDUTOR_OU_PROPRIETARIO)
    else:
        if "CONDUTOR" in t_inf: infratores.append(InfratorEnum.CONDUTOR)
        if "PROPRIETARIO" in t_inf: infratores.append(InfratorEnum.PROPRIETARIO)
        
    if "PESSOA" in t_inf and ("FISICA" in t_inf or "JURIDICA" in t_inf):
        infratores.append(InfratorEnum.PESSOA_FISICA_OU_JURIDICA)
    if "EMBARCADOR" in t_inf: infratores.append(InfratorEnum.EMBARCADOR)
    if "TRANSPORTADOR" in t_inf: infratores.append(InfratorEnum.TRANSPORTADOR)
    if "PEDESTRE" in t_inf: infratores.append(InfratorEnum.PEDESTRE)
    
    if not infratores:
        # Fallback genérico caso a limpeza tenha esvaziado o campo
        infratores.append(InfratorEnum.CONDUTOR)
        
    return infratores, tem_crime, artigos_extraidos

def normalizar_constatacao(texto: str) -> List[ConstatacaoInfracaoEnum]:
    t = texto.upper()
    res = []
    if "MEDIANTE ABORDAGEM OU NAO" in t or "MEDIANTE ABORDAGEM OU NÃO" in t:
        res.append(ConstatacaoInfracaoEnum.MEDIANTE_ABORDAGEM_OU_NAO)
    else:
        if "SEM ABORDAGEM" in t:
            res.append(ConstatacaoInfracaoEnum.SEM_ABORDAGEM)
        elif "COM ABORDAGEM" in t:
            res.append(ConstatacaoInfracaoEnum.COM_ABORDAGEM)
            
    if "VIDEOMONITORAMENTO" in t:
        res.append(ConstatacaoInfracaoEnum.VIDEOMONITORAMENTO)
        
    if not res:
        res.append(ConstatacaoInfracaoEnum.MEDIANTE_ABORDAGEM_OU_NAO)
    return res

def calcular_pontuacao(texto: str) -> Tuple[int, bool]:
    """
    Retorna a pontuação (int) e se gera suspensão direta (bool).
    """
    t = texto.lower()
    valor = 0
    if "7" in t or "sete" in t: valor = 7
    elif "5" in t or "cinco" in t: valor = 5
    elif "4" in t or "quatro" in t: valor = 4
    elif "3" in t or "tres" in t or "três" in t: valor = 3
    
    suspensiva = "suspensão" in t or "suspensao" in t
    return valor, suspensiva
