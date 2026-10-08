from typing import List, Optional
from pydantic import BaseModel, Field

class ChunkMetadados(BaseModel):
    """
    Metadados estruturados para pre-filtering no Cloudflare Vectorize e D1.
    Estes campos não entram no texto que compõe o vetor denso (para evitar distorção),
    mas são indexados para buscas cruzadas.
    """
    origem_id: str = Field(..., description="Código de enquadramento da ficha de origem")
    secao: str = Field(..., description="Nome da seção temática (ex: 'QUANDO_NAO_AUTUAR')")
    codigo: str = Field(..., description="Código do enquadramento")
    artigo: str = Field(..., description="Artigo principal relacionado à infração")
    gravidade: str = Field(..., description="Nível de gravidade (ex: GRAVISSIMA)")
    infratores: List[str] = Field(default_factory=list, description="Lista de infratores aplicáveis")
    competencias: List[str] = Field(default_factory=list, description="Lista de esferas de competência")
    texto_contextualizado: str = Field(..., description="Texto do fragmento original com prefixo (usado para RAG)")


class ChunkPayload(BaseModel):
    """
    Unidade atômica para o modelo vetorial (compatível com a API do Cloudflare Vectorize via NDJSON).
    """
    id: str = Field(..., description="Chave primária do chunk (ex: '751-01_QUANDO_AUTUAR')")
    values: List[float] = Field(..., description="Vetor denso (1024 dims para BGE-M3)")
    metadata: ChunkMetadados = Field(..., description="Objeto de metadados associados")
