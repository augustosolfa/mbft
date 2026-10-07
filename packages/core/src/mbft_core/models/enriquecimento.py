"""
Modelos de dados e contratos de guardrail para a etapa de enriquecimento do MBFT.
Serve como contrato de saída do Enriquecedor e contrato de entrada (guardrail) da Carga (PMS-004).
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class GravidadeEnum(str, Enum):
    LEVE = "LEVE"
    MEDIA = "MEDIA"
    GRAVE = "GRAVE"
    GRAVISSIMA = "GRAVISSIMA"
    NAO_APLICAVEL = "NAO_APLICAVEL"


class CompetenciaEnum(str, Enum):
    MUNICIPAL = "MUNICIPAL"
    ESTADUAL = "ESTADUAL"
    CONCORRENTE = "CONCORRENTE"


class CompetenciaFonteEnum(str, Enum):
    MBFT_ORIGINAL = "MBFT_ORIGINAL"
    RESOLUCAO_LEI_14599 = "RESOLUCAO_LEI_14599"


class ReferenciaCTB(BaseModel):
    artigo: str = Field(..., description="Número do artigo (ex.: '165', '230')")
    paragrafo: Optional[str] = Field(None, description="Parágrafo citado (ex.: '§ 1º', 'único')")
    inciso: Optional[str] = Field(None, description="Inciso em algarismo romano (ex.: 'V', 'VII')")
    alinea: Optional[str] = Field(None, description="Alínea citada (ex.: 'a', 'b')")


class FichaEnriquecida(BaseModel):
    id: str = Field(..., description="Código de enquadramento (ex.: '751-01')")
    tipificacao_resumida: str
    codigo_enquadramento: str
    amparo_legal: str
    tipificacao_enquadramento: str
    
    # Atributos brutos originais mantidos para auditoria
    gravidade_original: str
    penalidade_original: str
    medida_administrativa_original: str
    infrator_original: str
    competencia_original: str
    constatacao_infracao_original: str
    pontuacao_original: str
    
    # Atributos normalizados em vocabulário controlado
    gravidade: GravidadeEnum
    penalidades: List[str]
    medidas_administrativas: List[str]
    infratores: List[str]
    competencia: CompetenciaEnum
    competencia_fonte: CompetenciaFonteEnum
    competencia_alterada_lei_14599: bool
    crime_transito: bool
    pontuacao_valor: int = Field(default=0, description="0, 3, 4, 5 ou 7 pontos")
    pontuacao_suspensiva: bool = Field(default=False, description="True se gera suspensão direta da CNH")
    constatacao_infracao: List[str]
    
    # Informações Extraídas (IE)
    artigos_ctb: List[ReferenciaCTB] = Field(default_factory=list)
    resolucoes_contran: List[str] = Field(default_factory=list)
    enquadramentos_correlatos: List[str] = Field(default_factory=list)
    termos_chave: List[str] = Field(default_factory=list)
    
    # Textos canônicos e metadados
    quando_autuar_texto: str
    quando_nao_autuar_texto: str
    definicoes_procedimentos_texto: str
    exemplos_observacoes_ait_texto: str
    informacoes_complementares_html: str
    paginas: List[int]
    imagens: List[str]
    
    # Metadados de Fallback de IA
    campos_inferidos_por_llm: List[str] = Field(default_factory=list, description="Lista de campos onde a extração determinística falhou e o LLM atuou como fallback")
    revisao_manual_necessaria: bool = Field(default=False, description="True se a ficha sofreu intervenção de LLM e precisa de auditoria humana")


class ChunkMetadados(BaseModel):
    chunk_id: str = Field(..., description="Identificador unívoco do chunk (ex.: '751-01_QUANDO_AUTUAR' ou 'PG_CAP_02_SEC_01')")
    tipo_documento: str = Field(..., description="'FICHA' ou 'PARTE_GERAL'")
    origem_id: str = Field(..., description="Código da ficha ou ID do capítulo da Parte Geral")
    secao: str = Field(..., description="Nome da seção temática")
    hierarquia_titulos: List[str] = Field(default_factory=list)
    paginas: List[int]
    artigos_ctb_associados: List[str] = Field(default_factory=list)
    competencia: Optional[str] = None


class ChunkPayload(BaseModel):
    metadados: ChunkMetadados
    texto_contextualizado: str = Field(..., description="Texto final entregue ao modelo de embedding")
    tokens_estimados: int
