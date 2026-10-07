import re
from typing import List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
import os

from mbft_core.models.extracao import CampoNormativo
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

class ExtratorRegrasAtomo:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def extrair_itens(self, campo: CampoNormativo, secao_origem: str) -> List[ItemRegra]:
        """
        Converte as strings do CampoNormativo em ItemRegra estruturado usando heurísticas,
        com fallback para Gemini caso a estrutura seja complexa.
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
            else:
                pass
                
            # 1. Aplicar Heurística Lexical (Expressões Regulares)
            regra = self._inferir_via_heuristica(texto_final, secao_origem)
            
            # 2. Se a heurística não conseguir determinar a natureza_regra, usa fallback (Gemini)
            if regra.natureza_regra == NaturezaRegraEnum.PROCEDIMENTO_GERAL and "QUANDO_NAO_AUTUAR" in secao_origem.upper():
                # É suspeito que um item de 'Quando Não Autuar' caia no fallback default de procedimento geral
                if self.client:
                    regra_llm = self._inferir_via_llm(texto_final, secao_origem)
                    if regra_llm:
                        regra = regra_llm
            
            itens_regras.append(regra)
            
        return itens_regras

    def _inferir_via_heuristica(self, texto: str, secao: str) -> ItemRegra:
        t_upper = texto.upper()
        natureza = NaturezaRegraEnum.PROCEDIMENTO_GERAL
        
        # Heurística de Seção
        secao_upper = secao.upper()
        if "EXEMPLOS" in secao_upper:
            natureza = NaturezaRegraEnum.EXEMPLO_OBSERVACAO
        elif "QUANDO_AUTUAR" in secao_upper:
            natureza = NaturezaRegraEnum.HIPOTESE_AUTUACAO
        elif "QUANDO_NAO_AUTUAR" in secao_upper:
            natureza = NaturezaRegraEnum.EXCECAO_DESVIO
            
        # Heurística de Palavras-Chave
        if "CONCOMITANTE" in t_upper:
            natureza = NaturezaRegraEnum.CONCOMITANCIA
        
        # Extração de códigos
        codigos = expandir_codigos(texto)
        
        redirecionamentos = []
        concomitantes = []
        
        if natureza == NaturezaRegraEnum.EXCECAO_DESVIO and codigos:
            redirecionamentos = codigos
        elif natureza == NaturezaRegraEnum.CONCOMITANCIA:
            concomitantes = codigos
            
        return ItemRegra(
            texto=texto,
            natureza_regra=natureza,
            codigos_concomitantes=concomitantes,
            codigos_redirecionamento=redirecionamentos
        )

    def _inferir_via_llm(self, texto: str, secao: str) -> Optional[ItemRegra]:
        """
        Fallback utilizando o Gemini 2.5 Flash-Lite com Structured Outputs.
        """
        try:
            prompt = f"""
            Analise a seguinte regra extraída da seção '{secao}' do Manual Brasileiro de Fiscalização de Trânsito:
            Regra: "{texto}"
            
            Classifique a natureza da regra e extraia códigos de enquadramento (formato NNN-NN).
            - HIPOTESE_AUTUACAO: Quando descreve uma situação em que o agente DEVE autuar.
            - EXCECAO_DESVIO: Quando descreve uma situação que NÃO é infração, ou que deve autuar em OUTRO artigo (redirecionamento).
            - CONCOMITANCIA: Quando manda autuar concorrentemente com outro código.
            - PROCEDIMENTO_GERAL: Notas, definições ou regras de medição.
            - EXEMPLO_OBSERVACAO: Sugestão do que escrever no bloco de observações do Auto de Infração.
            """
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ItemRegra,
                    temperature=0.0
                ),
            )
            if response.parsed:
                return response.parsed
        except Exception as e:
            print(f"Erro no fallback LLM: {e}")
            pass
        return None
