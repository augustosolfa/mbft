from typing import List, Protocol, Dict, Any

class IVectorDB(Protocol):
    async def buscar_similares(self, vetor: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retorna uma lista de chunks.
        Exemplo de retorno: [{"id": "751-01_QUANDO_AUTUAR", "score": 0.85, "metadata": {...}}]
        """
        ...

class IRelationalDB(Protocol):
    async def buscar_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retorna uma lista de chunks via busca textual exata (BM25).
        Exemplo de retorno: [{"id": "751-01_QUANDO_AUTUAR", "score": 0.9, "metadata": {...}}]
        """
        ...

class IEmbedderClient(Protocol):
    async def embed_query(self, query: str) -> List[float]:
        """Gera o vetor denso de 1024 dimensões da pergunta."""
        ...
