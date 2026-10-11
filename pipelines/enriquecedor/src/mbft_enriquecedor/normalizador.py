import re
import unicodedata
from itertools import zip_longest
from typing import List, Tuple
from mbft_core.models.enriquecimento import (
    GravidadeEnum, PenalidadeEnum, MedidaAdministrativaEnum,
    InfratorEnum, ConstatacaoInfracaoEnum, ReferenciaCTB
)

def _sem_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).upper()

# Regex para limpar vazamento tabular de artigos
REGEX_ARTIGO_CTB_VAZADO = re.compile(r"((?:Art\.?\s*)?(\d{1,3}(?:\s*-[A-Za-z]+)?)\s*do\s*CTB)", re.IGNORECASE)
# Regex mais flexível para capturar a essência do amparo legal (ex: Art. 330, § 5º e § 6º)
REGEX_ARTIGO_AMPARO = re.compile(r"(?:Art\.?|c/c)\s*(\d{1,3}(?:\s*-[A-Za-z]+)?)\b(?!\s*-\d{2})", re.IGNORECASE)
REGEX_PARAGRAFO_AMPARO = re.compile(r"(§\s*\d+º?|par[aá]grafo\s+[uú]nico|§\s*[uú]nico)", re.IGNORECASE)
ROMANOS_CTB = {
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX"
}
REGEX_INCISO_AMPARO = re.compile(r"\b(?:inciso\s+)?([IVXLCDM]+)(?:\s*[-–—]|\b)")

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
    t = _sem_acentos(sanitizar_texto(texto))
    if "GRAVISSIMA" in t: return GravidadeEnum.GRAVISSIMA
    if "GRAVE" in t: return GravidadeEnum.GRAVE
    if "MEDIA" in t: return GravidadeEnum.MEDIA
    if "LEVE" in t: return GravidadeEnum.LEVE
    return GravidadeEnum.NAO_APLICAVEL

def normalizar_penalidades(texto: str) -> List[PenalidadeEnum]:
    t = _sem_acentos(sanitizar_texto(texto))
    rens = []
    if "MULTA" in t: rens.append(PenalidadeEnum.MULTA)
    if "ADVERTENCIA" in t: rens.append(PenalidadeEnum.ADVERTENCIA_POR_ESCRITO)
    if "SUSPENSAO" in t: rens.append(PenalidadeEnum.SUSPENSAO_DIREITO_DIRIGIR)
    if "CASSACAO" in t: rens.append(PenalidadeEnum.CASSACAO_CNH)
    return rens if rens else [PenalidadeEnum.NAO_APLICAVEL]

def normalizar_medidas_administrativas(texto: str) -> List[MedidaAdministrativaEnum]:
    t = _sem_acentos(sanitizar_texto(texto))
    rens = []
    if "RETENCAO" in t: rens.append(MedidaAdministrativaEnum.RETENCAO_VEICULO)
    if "REMOCAO" in t and ("MERCADORIA" in t or "MATERIAL" in t):
        rens.append(MedidaAdministrativaEnum.REMOCAO_MERCADORIA_MATERIAL)
    if "REMOCAO" in t and ("VEICULO" in t or ("MERCADORIA" not in t and "MATERIAL" not in t)):
        rens.append(MedidaAdministrativaEnum.REMOCAO_VEICULO)
    if "RECOLHIMENTO" in t and ("CNH" in t or "DOCUMENTO DE HABILITACAO" in t): rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_CNH)
    if "RECOLHIMENTO" in t and ("CRLV" in t or "LICENCIAMENTO" in t or "CERTIFICADO DE REGISTRO" in t): rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_CRLV)
    if ("RECOLHIMENTO" in t or "APREENSAO" in t) and "PLACA" in t: rens.append(MedidaAdministrativaEnum.RECOLHIMENTO_PLACAS)
    if "TRANSBORDO" in t: rens.append(MedidaAdministrativaEnum.TRANSBORDO_CARGA)
    if "ALCOOLEMIA" in t or bool(re.search(r"\bTESTES?\b", t)): rens.append(MedidaAdministrativaEnum.REALIZACAO_TESTE_ALCOOLEMIA)
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
    texto_infrator_limpo = re.sub(r'\b(?:SIM|N[ÃA]O)\b', '', texto_infrator_limpo, flags=re.IGNORECASE).strip()
    texto_infrator_limpo = re.sub(r'\s+', ' ', texto_infrator_limpo).strip()
    
    tem_crime = bool(
        re.search(r'\bSIM\b', texto_crime, re.IGNORECASE) or
        re.search(r'\bSIM\b', texto_infrator, re.IGNORECASE)
    )
        
    # Normalizar Infrator (removendo acentos para não perder JURÍDICA / FÍSICA)
    t_inf = _sem_acentos(texto_infrator_limpo)
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
    t = _sem_acentos(sanitizar_texto(texto))
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
        
    if "VIDE PROCEDIMENTO" in t or "VIDE OS PROCEDIMENTOS" in t or "VIDE DEFINICOES E PROCEDIMENTOS" in t:
        res.append(ConstatacaoInfracaoEnum.VIDE_PROCEDIMENTOS)
        
    if "NAO APLICAVEL" in t or "NAO SE APLICA" in t:
        res.append(ConstatacaoInfracaoEnum.NAO_APLICAVEL)
        
    if not res:
        res.append(ConstatacaoInfracaoEnum.MEDIANTE_ABORDAGEM_OU_NAO)
    return res

def parse_amparo_legal(texto: str) -> List[ReferenciaCTB]:
    texto = sanitizar_texto(texto)
    artigos = []
    
    # Se mencionar outras Leis, cortamos a string para não capturar incisos de lá (Bug da Ficha 606-85)
    texto_ctb = re.split(r'\b(?:da\s+)?Lei\b', texto, flags=re.IGNORECASE)[0]
    
    # Ex: "Art. 330, § 5º e § 6º." ou "Art. 233 c/c 123"
    artigos_encontrados = list(REGEX_ARTIGO_AMPARO.finditer(texto_ctb))
    if not artigos_encontrados:
        return []

    # Processar cada artigo encontrado limitando parágrafos e incisos ao texto após o artigo
    for i, match_artigo in enumerate(artigos_encontrados):
        art_num = match_artigo.group(1).strip()
        start_pos = match_artigo.end()
        end_pos = artigos_encontrados[i + 1].start() if i + 1 < len(artigos_encontrados) else len(texto_ctb)
        texto_apos = texto_ctb[start_pos:end_pos]
        
        # Encontrar os parágrafos mencionados no trecho após o artigo
        paragrafos = []
        for m in REGEX_PARAGRAFO_AMPARO.finditer(texto_apos):
            p = m.group(1) or m.group(2) or m.group(3) if m.groups() else m.group(0)
            p = re.sub(r'\s+', ' ', p).strip()
            if p and p not in paragrafos:
                paragrafos.append(p)
                
        # Encontrar incisos (case-sensitive) no trecho após o artigo
        incisos = []
        for m in REGEX_INCISO_AMPARO.finditer(texto_apos):
            inc = m.group(1)
            if inc in ROMANOS_CTB and inc not in incisos:
                incisos.append(inc)
                
        # Emitir ReferenciaCTB combinando parágrafo e inciso na mesma instância
        if not paragrafos and not incisos:
            artigos.append(ReferenciaCTB(artigo=art_num))
        elif paragrafos and not incisos:
            for p in paragrafos:
                artigos.append(ReferenciaCTB(artigo=art_num, paragrafo=p))
        elif not paragrafos and incisos:
            for inc in incisos:
                artigos.append(ReferenciaCTB(artigo=art_num, inciso=inc))
        else:
            if len(paragrafos) == 1:
                p = paragrafos[0]
                for inc in incisos:
                    artigos.append(ReferenciaCTB(artigo=art_num, paragrafo=p, inciso=inc))
            elif len(incisos) == 1:
                inc = incisos[0]
                for p in paragrafos:
                    artigos.append(ReferenciaCTB(artigo=art_num, paragrafo=p, inciso=inc))
            else:
                for p, inc in zip_longest(paragrafos, incisos, fillvalue=None):
                    artigos.append(ReferenciaCTB(artigo=art_num, paragrafo=p, inciso=inc))
            
    return artigos

def parse_resolucoes_contran(texto: str) -> List[str]:
    texto = sanitizar_texto(texto)
    # Ex: "Resolução do Contran nº 970/2022" ou "Resolução CONTRAN 970"
    regex_contran = re.compile(r"Resoluç[ãa]o(?:\s+do)?\s+CONTRAN\s*(?:n[ºo°]?\s*)?(\d+(?:/\d+)?)", re.IGNORECASE)
    matches = regex_contran.findall(texto)
    return matches

def calcular_pontuacao(texto: str, penalidades_norm: List[PenalidadeEnum]) -> Tuple[int, bool, bool]:
    t = sanitizar_texto(texto).lower()
    valor = 0
    tem_asterisco = "*" in t
    
    m = re.match(r"\s*(\d+)", t)
    if m:
        valor = int(m.group(1))
        if valor not in [0, 3, 4, 5, 7]:
            valor = 0
    else:
        if "sete" in t: valor = 7
        elif "cinco" in t: valor = 5
        elif "quatro" in t: valor = 4
        elif "tres" in t or "três" in t: valor = 3
        
    suspensiva = ("suspensão" in t or "suspensao" in t) or (PenalidadeEnum.SUSPENSAO_DIREITO_DIRIGIR in penalidades_norm)
    return valor, suspensiva, tem_asterisco
