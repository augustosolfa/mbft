import re
from typing import List, Optional
from pydantic import BaseModel

from mbft_core.models.extracao import CampoNormativo, SecaoFichaEnum
from mbft_core.models.enriquecimento import ItemRegra, NaturezaRegraEnum
from mbft_enriquecedor.normalizador import sanitizar_texto

# Regex para detectar códigos \d{3}-\d{2}
REGEX_CODIGO_ENQUADRAMENTO = re.compile(r"\b(\d{3}-\d{2})\b")

# Regex para detectar cabeçalhos de lista "12. " vs "12.1. "
REGEX_ITEM_PAI = re.compile(r"^(\d+)\.\s+(.*)")
REGEX_SUB_ITEM = re.compile(r"^(\d+)\.(\d+)\.\s+")

def expandir_codigos(texto: str) -> List[str]:
    # Expande intervalos como "505-31 a 505-34"
    codigos_expandidos = set()
    
    # 1. Encontrar intervalos com ' a '
    for match in re.finditer(r"\b(\d{3})-(\d{2})\s+a\s+(?:(\d{3})-)?(\d{2})\b", texto):
        raiz_ini = match.group(1)
        desd_ini = int(match.group(2))
        raiz_fim = match.group(3) if match.group(3) else raiz_ini
        desd_fim = int(match.group(4))
        
        # Só expandimos se a raiz for a mesma
        if raiz_ini == raiz_fim and desd_ini < desd_fim:
            for d in range(desd_ini, desd_fim + 1):
                codigos_expandidos.add(f"{raiz_ini}-{d:02d}")
                
    # 2. Adicionar códigos normais encontrados (inclui os que estão separados por 'ou')
    for match in REGEX_CODIGO_ENQUADRAMENTO.finditer(texto):
        codigos_expandidos.add(match.group(1))
        
    return sorted(list(codigos_expandidos))

import logging

logger = logging.getLogger(__name__)

class ExtratorRegrasAtomo:
    def __init__(self):
        pass

    def extrair_itens(self, campo: CampoNormativo, secao_origem: SecaoFichaEnum, codigo_enquadramento: str) -> List[ItemRegra]:
        """
        Converte as strings do CampoNormativo em ItemRegra estruturado usando heurísticas determinísticas.
        """
        itens_regras = []
        
        ultimo_pai_num = None
        ultimo_pai_texto = None
        
        for texto_item_bruto in campo.itens:
            texto_item = sanitizar_texto(texto_item_bruto)
            # Resolução de herança de pai para filho (Problema 2)
            texto_final = texto_item
            
            match_pai = REGEX_ITEM_PAI.match(texto_item)
            match_sub = REGEX_SUB_ITEM.match(texto_item)
            
            if match_sub:
                pai_num = match_sub.group(1)
                if pai_num == ultimo_pai_num and ultimo_pai_texto:
                    # Injeta o texto do pai no texto do subitem
                    texto_limpo = re.sub(r"^\d+\.\d+\.\s+", "", texto_item)
                    texto_final = f"{match_sub.group(0)}{ultimo_pai_texto} {texto_limpo}"
            elif match_pai:
                ultimo_pai_num = match_pai.group(1)
                # O texto do pai é até os dois pontos ou final
                texto_pai_limpo = match_pai.group(2)
                if ":" in texto_pai_limpo:
                    texto_pai_limpo = texto_pai_limpo.split(":")[0] + ":"
                ultimo_pai_texto = texto_pai_limpo
                
            # Descartar o Chunk Fantasma (pai oco que termina em :)
            if match_pai and not match_sub and texto_item.strip().endswith(":"):
                continue
                
            # Aplicar Heurística Lexical (Expressões Regulares)
            regra = self._inferir_via_heuristica(texto_final, secao_origem, codigo_enquadramento)
            itens_regras.append(regra)
            
        return itens_regras

    def _inferir_via_heuristica(self, texto: str, secao: SecaoFichaEnum, codigo_enquadramento: str) -> ItemRegra:
        t_upper = texto.upper()
        natureza = NaturezaRegraEnum.PROCEDIMENTO_GERAL
        
        if secao == SecaoFichaEnum.EXEMPLOS_AIT:
            natureza = NaturezaRegraEnum.EXEMPLO_OBSERVACAO
        elif secao == SecaoFichaEnum.QUANDO_AUTUAR:
            natureza = NaturezaRegraEnum.HIPOTESE_AUTUACAO
        elif secao == SecaoFichaEnum.QUANDO_NAO_AUTUAR:
            natureza = NaturezaRegraEnum.EXCECAO_DESVIO
            
        # Heurística de Palavras-Chave
        if "CONCOMITANTE" in t_upper:
            natureza = NaturezaRegraEnum.CONCOMITANCIA
        
        # Extração de códigos
        codigos_encontrados = expandir_codigos(texto)
        codigos_filtrados = [c for c in codigos_encontrados if c != codigo_enquadramento]
        
        redirecionamentos = []
        concomitantes = []
        
        if natureza == NaturezaRegraEnum.EXCECAO_DESVIO and codigos_filtrados:
            redirecionamentos = codigos_filtrados
        elif natureza == NaturezaRegraEnum.CONCOMITANCIA:
            concomitantes = codigos_filtrados
            
        return ItemRegra(
            texto=texto,
            natureza_regra=natureza,
            codigos_concomitantes=concomitantes,
            codigos_redirecionamento=redirecionamentos
        )
