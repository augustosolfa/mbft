"""
Modelos de dados estruturados para o Extrator MBFT.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CampoNormativo(BaseModel):
    """
    Representa uma coluna normativa composta (ex: Quando Autuar, Definições e Procedimentos).
    Contém a representação textual completa em Markdown e a lista de itens enumerados.
    """
    texto: str = Field(
        default="Não há.",
        description="Texto contínuo ou Markdown completo da seção."
    )
    itens: List[str] = Field(
        default_factory=list,
        description="Lista de itens, alíneas ou regras identificados na coluna."
    )


class Ficha(BaseModel):
    """
    Modelo representativo de uma Ficha de Fiscalização completa do MBFT.
    """
    id: str = Field(..., description="Identificador único da ficha, igual ao Código do Enquadramento (ex: '768-42')")
    tipificacao_resumida: str = Field(..., description="Título / tipificação resumida da infração")
    codigo_enquadramento: str = Field(..., description="Código de enquadramento da infração (ex: '768-42')")
    amparo_legal: str = Field(default="", description="Artigo e inciso do CTB")
    tipificacao_enquadramento: str = Field(default="", description="Descrição completa do enquadramento legal")
    gravidade: str = Field(default="", description="Leve, Média, Grave ou Gravíssima")
    penalidade: str = Field(default="", description="Penalidade prevista (ex: Multa)")
    medida_administrativa: str = Field(default="", description="Medida administrativa cabível")
    pode_configurar_crime_transito: str = Field(default="NÃO", description="Indicação de crime de trânsito")
    infrator: str = Field(default="", description="Condutor, Proprietário, etc.")
    competencia: str = Field(default="", description="Órgão ou entidade executiva competente")
    competencia_alterada_lei_14599: bool = Field(
        default=False,
        description="Indica se a competência da ficha foi alterada pela Lei n. 14.599/23"
    )
    pontuacao: str = Field(default="", description="Pontos a computar na CNH")
    constatacao_infracao: str = Field(default="", description="Com abordagem, Sem abordagem, etc.")
    
    quando_autuar: CampoNormativo = Field(default_factory=CampoNormativo)
    quando_nao_autuar: CampoNormativo = Field(default_factory=CampoNormativo)
    definicoes_procedimentos: CampoNormativo = Field(default_factory=CampoNormativo)
    exemplos_observacoes_ait: CampoNormativo = Field(default_factory=CampoNormativo)
    
    informacoes_complementares: str = Field(
        default="<p>Não há.</p>",
        description="Conteúdo semântico em HTML simples (tabelas, textos, imagens)"
    )
    paginas: List[int] = Field(default_factory=list, description="Páginas do PDF (1-indexadas) de onde a ficha foi extraída")
    imagens: List[str] = Field(default_factory=list, description="Caminhos relativos das imagens extraídas para esta ficha")


class FichaMapeada(BaseModel):
    """
    Intervalo e metadados básicos mapeados para uma ficha no PDF.
    """
    codigo: str
    pag_ini: int
    pag_fim: int
    identificador: str
