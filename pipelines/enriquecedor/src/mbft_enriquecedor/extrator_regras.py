import re
from typing import List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
import os

from mbft_core.models.extracao import CampoNormativo
from mbft_core.models.enriquecimento import ItemRegra, NaturezaRegraEnum

# Regex para detectar códigos \d{3}-\d{2}
REGEX_CODIGO_ENQUADRAMENTO = re.compile(r"\b(\d{3}-\d{2})\b")

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
        for texto_item in campo.itens:
            # 1. Aplicar Heurística Lexical (Expressões Regulares)
            regra = self._inferir_via_heuristica(texto_item, secao_origem)
            
            # 2. Se a heurística não conseguir determinar a natureza_regra, usa fallback (Gemini)
            if regra.natureza_regra == NaturezaRegraEnum.PROCEDIMENTO_GERAL and "QUANDO_NAO_AUTUAR" in secao_origem.upper():
                # É suspeito que um item de 'Quando Não Autuar' caia no fallback default de procedimento geral
                if self.client:
                    regra_llm = self._inferir_via_llm(texto_item, secao_origem)
                    if regra_llm:
                        regra = regra_llm
            
            itens_regras.append(regra)
            
        return itens_regras

    def _inferir_via_heuristica(self, texto: str, secao: str) -> ItemRegra:
        t_upper = texto.upper()
        natureza = NaturezaRegraEnum.PROCEDIMENTO_GERAL
        
        # Heurística de Seção
        secao_upper = secao.upper()
        if "QUANDO_AUTUAR" in secao_upper:
            natureza = NaturezaRegraEnum.HIPOTESE_AUTUACAO
        elif "QUANDO_NAO_AUTUAR" in secao_upper:
            natureza = NaturezaRegraEnum.EXCECAO_DESVIO
            
        # Heurística de Palavras-Chave
        if "CONCOMITANTE" in t_upper:
            natureza = NaturezaRegraEnum.CONCOMITANCIA
        
        # Extração de códigos
        codigos = REGEX_CODIGO_ENQUADRAMENTO.findall(texto)
        codigos = list(set(codigos)) # deduplicar
        
        redirecionamento = None
        concomitantes = []
        
        if natureza == NaturezaRegraEnum.EXCECAO_DESVIO and codigos:
            # Assume que o primeiro código citado é para onde deve ser lavrado o auto
            redirecionamento = codigos[0]
        elif natureza == NaturezaRegraEnum.CONCOMITANCIA:
            concomitantes = codigos
            
        return ItemRegra(
            texto=texto,
            natureza_regra=natureza,
            codigos_concomitantes=concomitantes,
            codigo_redirecionamento=redirecionamento
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
                # Retorna o objeto validado pelo SDK
                # O SDK retorna a instância Pydantic se passamos a classe no response_schema
                return response.parsed
        except Exception as e:
            # Em caso de falha do LLM (quota, timeout, parsing err), degrada graciosamente
            print(f"Erro no fallback LLM: {e}")
            pass
        return None
