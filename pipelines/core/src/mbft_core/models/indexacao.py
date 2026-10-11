from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

class ChunkMetadados(BaseModel):
    """
    Metadados estruturados associados a cada fragmento normativo.
    Estes campos não entram no texto que compõe o vetor denso (para evitar distorção),
    mas são preservados para filtragem exata e hidratação na busca híbrida.
    """
    origem_id: str = Field(..., description="Código de enquadramento da ficha de origem")
    secao: str = Field(..., description="Nome da seção temática (ex: 'QUANDO_NAO_AUTUAR')")
    codigo: str = Field(..., description="Código do enquadramento")
    artigo: str = Field(..., description="Artigo principal relacionado à infração")
    gravidade: str = Field(..., description="Nível de gravidade (ex: GRAVISSIMA)")
    infratores: List[str] = Field(default_factory=list, description="Lista de infratores aplicáveis")
    competencias: List[str] = Field(default_factory=list, description="Lista de esferas de competência")
    texto_contextualizado: str = Field(..., min_length=1, description="Texto do fragmento original com prefixo (usado para RAG)")
    natureza_regra: Optional[str] = Field(default=None, description="Classificação semântica da regra atômica (ex: EXCECAO_DESVIO)")

    @field_validator("texto_contextualizado")
    @classmethod
    def validar_texto_contextualizado_nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("O campo 'texto_contextualizado' não pode ser vazio.")
        return v


class ChunkPayload(BaseModel):
    """
    Unidade atômica do índice vetorial serializada em formato canônico NDJSON (JSONL).
    """
    id: str = Field(..., description="Chave primária do chunk (ex: '751-01_QUANDO_AUTUAR')")
    values: List[float] = Field(..., description="Vetor denso (1024 dims para BGE-M3)")
    metadata: ChunkMetadados = Field(..., description="Objeto de metadados associados")
