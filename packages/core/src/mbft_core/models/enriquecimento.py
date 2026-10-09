"""
Modelos de dados e contratos de guardrail para a etapa de enriquecimento do MBFT.
Serve como contrato de saída do Enriquecedor e contrato de entrada (guardrail) da Carga (PMS-004).
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from mbft_core.models.extracao import CampoNormativo


class GravidadeEnum(str, Enum):
    LEVE = "LEVE"
    MEDIA = "MEDIA"
    GRAVE = "GRAVE"
    GRAVISSIMA = "GRAVISSIMA"
    NAO_APLICAVEL = "NAO_APLICAVEL"

class PenalidadeEnum(str, Enum):
    MULTA = "MULTA"
    ADVERTENCIA_POR_ESCRITO = "ADVERTENCIA_POR_ESCRITO"
    SUSPENSAO_DIREITO_DIRIGIR = "SUSPENSAO_DIREITO_DIRIGIR"
    CASSACAO_CNH = "CASSACAO_CNH"
    NAO_APLICAVEL = "NAO_APLICAVEL"

class MedidaAdministrativaEnum(str, Enum):
    RETENCAO_VEICULO = "RETENCAO_VEICULO"
    REMOCAO_VEICULO = "REMOCAO_VEICULO"
    RECOLHIMENTO_CNH = "RECOLHIMENTO_CNH"
    RECOLHIMENTO_CRLV = "RECOLHIMENTO_CRLV"
    TRANSBORDO_CARGA = "TRANSBORDO_CARGA"
    REALIZACAO_TESTE_ALCOOLEMIA = "REALIZACAO_TESTE_ALCOOLEMIA"
    RECOLHIMENTO_PLACAS = "RECOLHIMENTO_PLACAS"
    NAO_APLICAVEL = "NAO_APLICAVEL"

class InfratorEnum(str, Enum):
    CONDUTOR = "CONDUTOR"
    PROPRIETARIO = "PROPRIETARIO"
    CONDUTOR_OU_PROPRIETARIO = "CONDUTOR_OU_PROPRIETARIO"
    PESSOA_FISICA_OU_JURIDICA = "PESSOA_FISICA_OU_JURIDICA"
    EMBARCADOR = "EMBARCADOR"
    TRANSPORTADOR = "TRANSPORTADOR"
    PEDESTRE = "PEDESTRE"
    NAO_IDENTIFICADO = "NAO_IDENTIFICADO"

class ConstatacaoInfracaoEnum(str, Enum):
    COM_ABORDAGEM = "COM_ABORDAGEM"
    SEM_ABORDAGEM = "SEM_ABORDAGEM"
    MEDIANTE_ABORDAGEM_OU_NAO = "MEDIANTE_ABORDAGEM_OU_NAO"
    VIDEOMONITORAMENTO = "VIDEOMONITORAMENTO"
    VIDE_PROCEDIMENTOS = "VIDE_PROCEDIMENTOS"
    NAO_APLICAVEL = "NAO_APLICAVEL"

class CompetenciaEnum(str, Enum):
    MUNICIPAL = "MUNICIPAL"
    ESTADUAL = "ESTADUAL"
    RODOVIARIO = "RODOVIARIO"

class CompetenciaFonteEnum(str, Enum):
    MBFT_ORIGINAL = "MBFT_ORIGINAL"
    RESOLUCAO_LEI_14599 = "RESOLUCAO_LEI_14599"

class NaturezaRegraEnum(str, Enum):
    HIPOTESE_AUTUACAO = "HIPOTESE_AUTUACAO"
    EXCECAO_DESVIO = "EXCECAO_DESVIO"
    CONCOMITANCIA = "CONCOMITANCIA"
    PROCEDIMENTO_GERAL = "PROCEDIMENTO_GERAL"
    EXEMPLO_OBSERVACAO = "EXEMPLO_OBSERVACAO"


class ReferenciaCTB(BaseModel):
    artigo: str = Field(..., description="Número do artigo (ex.: '165', '230')")
    paragrafo: Optional[str] = Field(None, description="Parágrafo citado (ex.: '§ 1º', 'único')")
    inciso: Optional[str] = Field(None, description="Inciso em algarismo romano (ex.: 'V', 'VII')")
    alinea: Optional[str] = Field(None, description="Alínea citada (ex.: 'a', 'b')")

class ItemRegra(BaseModel):
    texto: str = Field(..., description="Texto integral do item atômico.")
    natureza_regra: NaturezaRegraEnum
    codigos_concomitantes: List[str] = Field(default_factory=list, description="Lista de códigos (ex.: '507-01') a serem autuados concomitantemente.")
    codigos_redirecionamento: List[str] = Field(default_factory=list, description="Lista de códigos para os quais este item redireciona em caso de exceção.")

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
    pode_configurar_crime_transito_original: Optional[str] = None
    
    quando_autuar_original: CampoNormativo
    quando_nao_autuar_original: CampoNormativo
    definicoes_procedimentos_original: CampoNormativo
    exemplos_observacoes_ait_original: CampoNormativo
    
    # Atributos normalizados em vocabulário controlado
    gravidade: GravidadeEnum
    penalidades: List[PenalidadeEnum]
    medidas_administrativas: List[MedidaAdministrativaEnum]
    infratores: List[InfratorEnum]
    competencias: List[CompetenciaEnum]
    competencia_fonte: CompetenciaFonteEnum
    competencia_alterada_lei_14599: bool
    crime_transito: bool
    pontuacao_valor: int = Field(default=0, description="0, 3, 4, 5 ou 7 pontos")
    pontuacao_suspensiva: bool = Field(default=False, description="True se gera suspensão direta da CNH")
    pontuacao_asterisco: bool = Field(default=False, description="True se a pontuação possui asterisco (ex: vide item...)")
    constatacao_infracao: List[ConstatacaoInfracaoEnum]
    
    # Informações Extraídas (IE)
    artigos_ctb: List[ReferenciaCTB] = Field(default_factory=list)
    resolucoes_contran: List[str] = Field(default_factory=list)
    enquadramentos_correlatos: List[str] = Field(default_factory=list)
    termos_chave: List[str] = Field(default_factory=list)
    
    # Textos canônicos e metadados com granularidade atômica
    quando_autuar_itens: List[ItemRegra] = Field(default_factory=list)
    quando_nao_autuar_itens: List[ItemRegra] = Field(default_factory=list)
    definicoes_procedimentos_itens: List[ItemRegra] = Field(default_factory=list)
    exemplos_observacoes_ait_itens: List[ItemRegra] = Field(default_factory=list)
    informacoes_complementares_html: str
    paginas: List[int]
    imagens: List[str]
    
    # Metadados de Fallback de IA
    campos_inferidos_por_llm: List[str] = Field(default_factory=list, description="Lista de campos onde a extração determinística falhou e o LLM atuou como fallback")
    revisao_manual_necessaria: bool = Field(default=False, description="True se a ficha sofreu intervenção de LLM e precisa de auditoria humana")



