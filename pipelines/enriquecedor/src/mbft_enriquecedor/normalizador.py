import re
from typing import List, Tuple
from mbft_core.models.enriquecimento import (
    GravidadeEnum, PenalidadeEnum, MedidaAdministrativaEnum,
    InfratorEnum, ConstatacaoInfracaoEnum, ReferenciaCTB
)

# Regex para limpar vazamento tabular de artigos
REGEX_ARTIGO_CTB_VAZADO = re.compile(r"((?:Art\.?\s*)?(\d{1,3}(?:\s*-[A-Za-z]+)?)\s*do\s*CTB)", re.IGNORECASE)
# Regex mais flexível para capturar a essência do amparo legal (ex: Art. 330, § 5º e § 6º)
REGEX_ARTIGO_AMPARO = re.compile(r"Art\.?\s*(\d{1,3}(?:\s*-[A-Za-z]+)?)", re.IGNORECASE)
REGEX_PARAGRAFO_AMPARO = re.compile(r"(§\s*\d+º?|par[aá]grafo\s+[uú]nico)", re.IGNORECASE)

def sanitizar_texto(texto: str) -> str:
    if not texto:
        return ""
    # Recompor hifenização perdida (Problema 3) ex: "registrar\u0002 se-ão" -> "registrar-se-ão"
    t = re.sub(r'\u0002\s+', '-', texto)
    # Recompor "retirá\u0002los" -> "retirá-los"
    t = re.sub(r'\u0002', '-', t)
    # Remover quaisquer outros caracteres de controle (0x00-0x1F, 0x7F-0x9F) exceto newline e tab se houver
    t = re.sub(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', '', t)
    # Limpeza de glifos residuais no final da string
    t = re.sub(r'\s+(?:[pgqçc][pgqçc\s,\(\)]*|[\s,\(\)]+)$', '', t, flags=re.IGNORECASE)
    return t.strip()

def normalizar_gravidade(texto: str) -> GravidadeEnum:
    t = sanitizar_texto(texto).upper().replace("Í", "I").replace("É", "E").replace("Á", "A")
    if "GRAVISSIMA" in t: return GravidadeEnum.GRAVISSIMA
    if "GRAVE" in t: return GravidadeEnum.GRAVE
    if "MEDIA" in t: return GravidadeEnum.MEDIA
    if "LEVE" in t: return GravidadeEnum.LEVE
    return GravidadeEnum.NAO_APLICAVEL

def normalizar_penalidades(texto: str) -> List[PenalidadeEnum]:
    t = sanitizar_texto(texto).upper()
    rens = []
    if "MULTA" in t: rens.append(PenalidadeEnum.MULTA)
    if "ADVERTENCIA" in t: rens.append(PenalidadeEnum.ADVERTENCIA_POR_ESCRITO)
    if "SUSPENSAO" in t: rens.append(PenalidadeEnum.SUSPENSAO_DIREITO_DIRIGIR)
    if "CASSACAO" in t: rens.append(PenalidadeEnum.CASSACAO_CNH)
    return rens if rens else [PenalidadeEnum.NAO_APLICAVEL]

def normalizar_medidas_administrativas(texto: str) -> List[MedidaAdministrativaEnum]:
    t = sanitizar_texto(texto).upper().replace("Ç", "C").replace("Ã", "A")
    rens = []
    if "RETENCAO" in t: rens.append(MedidaAdministrativaEnum.RETENCAO_VEICULO)
    if "REMOCAO" in t: rens.append(MedidaAdministrativaEnum.REMOCAO_VEICULO)
    if "RECOLHIMENTO" in t and "CNH" in t: rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_CNH)
    if "RECOLHIMENTO" in t and "CRLV" in t: rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_CRLV)
    if "TRANSBORDO" in t: rens.append(MedidaAdministrativaEnum.TRANSBORDO_CARGA)
    if "ALCOOLEMIA" in t or "TESTE" in t: rens.append(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA)
    return rens if rens else [MedidaAdministrativaEnum.NAO_APLICAVEL]

def higienizar_infrator_crime(texto_infrator: str, texto_crime: str | None) -> Tuple[List[InfratorEnum], bool, List[ReferenciaCTB]]:
    texto_infrator = sanitizar_texto(texto_infrator)
    texto_crime = sanitizar_texto(texto_crime or "")
    
    texto_combinado = f"{texto_infrator} {texto_crime}".strip()
    
    artigos_extraidos = []
    
    # Extrair todos os artigos entre 'Art' e 'CTB'
    bloco_match = re.search(r'Art\.?(.*?)do\s*CTB', texto_combinado, re.IGNORECASE)
    if bloco_match:
        bloco = bloco_match.group(1)
        numeros = re.findall(r'\b\d{1,3}(?:\s*-[A-Za-z]+)?\b', bloco)
        for num in numeros:
            artigos_extraidos.append(ReferenciaCTB(artigo=num.strip()))
            
    # Remover o vazamento do texto do infrator
    texto_infrator_limpo = re.sub(r'Art\.?.*?do\s*CTB', '', texto_infrator, flags=re.IGNORECASE).strip()
    texto_infrator_limpo = texto_infrator_limpo.replace("SIM", "").replace("NÃO", "").replace("NAO", "").strip()
    
    tem_crime = False
    if "SIM" in texto_crime.upper() or "SIM" in texto_infrator.upper():
        tem_crime = True
    if artigos_extraidos:
        tem_crime = True
        
    # Normalizar Infrator (removendo acentos para não perder JURÍDICA / FÍSICA)
    t_inf = texto_infrator_limpo.upper().replace("Í", "I").replace("Á", "A").replace("Ó", "O")
    infratores = []
    
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
        infratores.append(InfratorEnum.NAO_IDENTIFICADO)
        
    return infratores, tem_crime, artigos_extraidos

def normalizar_constatacao(texto: str) -> List[ConstatacaoInfracaoEnum]:
    t = sanitizar_texto(texto).upper().replace("Ã", "A")
    res = []
    if "MEDIANTE ABORDAGEM OU NAO" in t:
        res.append(ConstatacaoInfracaoEnum.MEDIANTE_ABORDAGEM_OU_NAO)
    else:
        if "SEM ABORDAGEM" in t:
            res.append(ConstatacaoInfracaoEnum.SEM_ABORDAGEM)
        elif "COM ABORDAGEM" in t or "MEDIANTE ABORDAGEM" in t:
            res.append(ConstatacaoInfracaoEnum.COM_ABORDAGEM)
            
    if "VIDEOMONITORAMENTO" in t:
        res.append(ConstatacaoInfracaoEnum.VIDEOMONITORAMENTO)
        
    if "VIDE PROCEDIMENTO" in t or "VIDE OS PROCEDIMENTOS" in t:
        res.append(ConstatacaoInfracaoEnum.VIDE_PROCEDIMENTOS)
        
    if "NAO APLICAVEL" in t or "NAO SE APLICA" in t:
        res.append(ConstatacaoInfracaoEnum.NAO_APLICAVEL)
        
    if not res:
        res.append(ConstatacaoInfracaoEnum.MEDIANTE_ABORDAGEM_OU_NAO)
    return res

def parse_amparo_legal(texto: str) -> List[ReferenciaCTB]:
    texto = sanitizar_texto(texto)
    artigos = []
    
    # Ex: "Art. 330, § 5º e § 6º." ou "Art. 40... III - "
    match_artigo = REGEX_ARTIGO_AMPARO.search(texto)
    if not match_artigo:
        return []
        
    artigo_base = match_artigo.group(1)
    
    # Encontrar os parágrafos mencionados
    paragrafos = []
    for m in REGEX_PARAGRAFO_AMPARO.finditer(texto):
        p = m.group(1) or m.group(2)
        if p: paragrafos.append(p)
        
    # Encontrar incisos (ex: "III -" ou "inciso III")
    incisos = []
    for m in re.finditer(r"\b(?:inciso\s+)?([IVXLCDM]+)(?:\s*-|\b)", texto, re.IGNORECASE):
        inc = m.group(1).upper()
        # Validação simples para evitar falsos positivos
        if inc in ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]:
            incisos.append(inc)
            
    if not paragrafos and not incisos:
        artigos.append(ReferenciaCTB(artigo=artigo_base))
    else:
        for p in paragrafos:
            artigos.append(ReferenciaCTB(artigo=artigo_base, paragrafo=p))
        for inc in incisos:
            artigos.append(ReferenciaCTB(artigo=artigo_base, inciso=inc))
            
    return artigos

def parse_resolucoes_contran(texto: str) -> List[str]:
    texto = sanitizar_texto(texto)
    # Ex: "Resolução do Contran nº 970/2022" ou "Resolução CONTRAN 970"
    regex_contran = re.compile(r"Resoluç[ãa]o(?:\s+do)?\s+CONTRAN\s*(?:n[ºo°]?\s*)?(\d+(?:/\d+)?)", re.IGNORECASE)
    matches = regex_contran.findall(texto)
    return matches

def calcular_pontuacao(texto: str) -> Tuple[int, bool]:
    t = sanitizar_texto(texto).lower()
    valor = 0
    if "7" in t or "sete" in t: valor = 7
    elif "5" in t or "cinco" in t: valor = 5
    elif "4" in t or "quatro" in t: valor = 4
    elif "3" in t or "tres" in t or "três" in t: valor = 3
    
    suspensiva = "suspensão" in t or "suspensao" in t
    return valor, suspensiva
