"""
Modelos de dados para a etapa de extração do MBFT.
Serve como guardrail de saída do Extrator e guardrail de entrada do Enriquecedor.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class SecaoFichaEnum(str, Enum):
    QUANDO_AUTUAR = "QUANDO_AUTUAR"
    QUANDO_NAO_AUTUAR = "QUANDO_NAO_AUTUAR"
    DEFINICOES_PROCEDIMENTOS = "DEFINICOES_PROCEDIMENTOS"
    EXEMPLOS_AIT = "EXEMPLOS_AIT"

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
    Atua como contrato canônico de saída do Extrator e entrada do Enriquecedor.
    """
    id: str = Field(..., min_length=1, description="Identificador único da ficha, igual ao Código do Enquadramento (ex: '768-42')")
    tipificacao_resumida: str = Field(..., min_length=1, description="Título / tipificação resumida da infração")
    codigo_enquadramento: str = Field(..., min_length=1, description="Código de enquadramento da infração (ex: '768-42')")
    amparo_legal: str = Field(..., min_length=1, description="Artigo e inciso do CTB")
    tipificacao_enquadramento: str = Field(..., min_length=1, description="Descrição completa do enquadramento legal")
    gravidade: str = Field(..., min_length=1, description="Leve, Média, Grave ou Gravíssima")
    penalidade: str = Field(..., min_length=1, description="Penalidade prevista (ex: Multa)")
    medida_administrativa: str = Field(..., min_length=1, description="Medida administrativa cabível")
    pode_configurar_crime_transito: Optional[str] = Field(
        default=None,
        description="Indicação de crime de trânsito (ou None se em branco no PDF original)"
    )
    infrator: str = Field(..., min_length=1, description="Condutor, Proprietário, etc.")
    competencia: Optional[str] = Field(
        default=None,
        description="Órgão ou entidade executiva competente (ou None se pendente/alterada pela Lei 14.599)"
    )
    competencia_alterada_lei_14599: bool = Field(
        default=False,
        description="Indica se a competência da ficha foi alterada pela Lei n. 14.599/23"
    )
    pontuacao: str = Field(..., min_length=1, description="Pontos a computar na CNH")
    constatacao_infracao: str = Field(..., min_length=1, description="Com abordagem, Sem abordagem, etc.")
    
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

    @field_validator("codigo_enquadramento")
    @classmethod
    def validar_consistencia_id(cls, v: str, info) -> str:
        id_val = info.data.get("id") if info.data else None
        if id_val and v != id_val:
            raise ValueError(f"codigo_enquadramento ('{v}') deve ser idêntico ao id ('{id_val}')")
        return v

    @field_validator("competencia")
    @classmethod
    def validar_competencia(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError(
                "competencia não pode ser string vazia; passe texto válido ou explicitamente None para indicar ausência/alteração pela Lei 14.599/2023"
            )
        return v

    @field_validator("pode_configurar_crime_transito")
    @classmethod
    def validar_crime(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def inferir_competencia_lei_14599(self) -> "Ficha":
        if self.competencia is None:
            self.competencia_alterada_lei_14599 = True
        return self


class FichaMapeada(BaseModel):
    """
    Intervalo e metadados básicos mapeados para uma ficha no PDF.
    """
    codigo: str
    pag_ini: int
    pag_fim: int
    identificador: str
