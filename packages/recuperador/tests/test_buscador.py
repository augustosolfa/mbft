import pytest
from typing import List, Dict, Any
from mbft_recuperador.buscador import BuscadorHibrido

class MockEmbedder:
    async def embed_query(self, query: str) -> List[float]:
        return [0.1, 0.2, 0.3]

class MockVectorDB:
    def __init__(self, resultados: List[Dict[str, Any]]):
        self.resultados = resultados
        
    async def buscar_similares(self, vetor: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        return self.resultados[:limit]

class MockRelationalDB:
    def __init__(self, resultados: List[Dict[str, Any]]):
        self.resultados = resultados
        
    async def buscar_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.resultados[:limit]

@pytest.mark.asyncio
async def test_reciprocal_rank_fusion_prioriza_intersecao():
    # Arrange: Simula resultados do banco vetorial e de texto exato
    dense_docs = [
        {"id": "doc_A", "metadata": {"codigo": "123"}}, # rank 1
        {"id": "doc_B", "metadata": {"codigo": "456"}}, # rank 2
        {"id": "doc_C", "metadata": {"codigo": "789"}}, # rank 3
    ]
    
    sparse_docs = [
        {"id": "doc_C", "metadata": {"codigo": "789"}}, # rank 1
        {"id": "doc_D", "metadata": {"codigo": "000"}}, # rank 2
        {"id": "doc_A", "metadata": {"codigo": "123"}}, # rank 3
    ]
    
    vector_db = MockVectorDB(dense_docs)
    relational_db = MockRelationalDB(sparse_docs)
    embedder = MockEmbedder()
    
    buscador = BuscadorHibrido(vector_db, relational_db, embedder)
    
    # Act
    resultados = await buscador.recuperar_contexto("qualquer_pergunta", limit=5)
    
    # Assert
    assert len(resultados) == 4
    
    ids = [r["id"] for r in resultados]
    
    # doc_A e doc_C aparecem nas duas listas, logo o RRF deles será maior
    # doc_C: rank 3 (denso) e rank 1 (esparso)
    # doc_A: rank 1 (denso) e rank 3 (esparso)
    # Como a matemática RRF é 1/(k+rank), eles empatam e devem dominar o topo.
    assert set(ids[:2]) == {"doc_A", "doc_C"}
    
    # doc_B e doc_D aparecem apenas em uma das listas, com rank 2
    assert set(ids[2:]) == {"doc_B", "doc_D"}
    
    for r in resultados:
        assert "rrf_score" in r
        assert r["rrf_score"] > 0.0

@pytest.mark.asyncio
async def test_reciprocal_rank_fusion_limite():
    # Arrange: Apenas para garantir que o limit é respeitado
    dense_docs = [{"id": f"doc_dense_{i}"} for i in range(10)]
    sparse_docs = [{"id": f"doc_sparse_{i}"} for i in range(10)]
    
    buscador = BuscadorHibrido(MockVectorDB(dense_docs), MockRelationalDB(sparse_docs), MockEmbedder())
    
    # Act
    resultados = await buscador.recuperar_contexto("limite", limit=3)
    
    # Assert
    assert len(resultados) == 3
