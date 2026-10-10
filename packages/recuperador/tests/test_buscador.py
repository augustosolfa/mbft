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

@pytest.mark.asyncio
async def test_diversificacao_por_ficha_evita_monopolio_e_faz_backfill():
    dense_docs = [
        {"id": "752-81_1", "metadata": {"codigo": "752-81"}},
        {"id": "752-81_2", "metadata": {"codigo": "752-81"}},
        {"id": "752-81_3", "metadata": {"codigo": "752-81"}},
        {"id": "752-82_1", "metadata": {"codigo": "752-82"}},
        {"id": "751-01_1", "metadata": {"codigo": "751-01"}},
    ]
    sparse_docs = [
        {"id": "752-81_1", "metadata": {"codigo": "752-81"}},
        {"id": "752-81_2", "metadata": {"codigo": "752-81"}},
        {"id": "752-82_1", "metadata": {"codigo": "752-82"}},
        {"id": "751-01_1", "metadata": {"codigo": "751-01"}},
    ]

    buscador = BuscadorHibrido(MockVectorDB(dense_docs), MockRelationalDB(sparse_docs), MockEmbedder())

    # Com limit=3, deve trazer 1 chunk de cada código único (752-81, 752-82, 751-01)
    top3 = await buscador.recuperar_contexto("art 95", limit=3)
    assert [r["metadata"]["codigo"] for r in top3] == ["752-81", "752-82", "751-01"]
    assert [r["id"] for r in top3] == ["752-81_1", "752-82_1", "751-01_1"]

    # Com limit=5, após esgotar os 3 códigos únicos, preenche (backfill) com os chunks restantes de maior RRF
    top5 = await buscador.recuperar_contexto("art 95", limit=5)
    assert len(top5) == 5
    assert [r["id"] for r in top5] == ["752-81_1", "752-82_1", "751-01_1", "752-81_2", "752-81_3"]

def test_formatar_token_fts_preserva_exatos_curtos_numericos_e_romanos():
    from mbft_recuperador.local_adapters import LocalSqliteDB

    assert LocalSqliteDB._formatar_token_fts("") == ""
    assert LocalSqliteDB._formatar_token_fts("Art") == "Art"
    assert LocalSqliteDB._formatar_token_fts("162") == "162"
    assert LocalSqliteDB._formatar_token_fts("I") == "I"
    assert LocalSqliteDB._formatar_token_fts("II") == "II"
    assert LocalSqliteDB._formatar_token_fts("VIII") == "VIII"
    assert LocalSqliteDB._formatar_token_fts("XVIII") == "XVIII"
    assert LocalSqliteDB._formatar_token_fts("XLII") == "XLII"
    assert LocalSqliteDB._formatar_token_fts("14599") == "14599"
    assert LocalSqliteDB._formatar_token_fts("dirigir") == "dirigir*"
    assert LocalSqliteDB._formatar_token_fts("álcool") == "álcool*"
    assert LocalSqliteDB._formatar_token_fts("civil") == "civil*"
    assert LocalSqliteDB._formatar_token_fts("NOT") == '"NOT"'


@pytest.mark.asyncio
async def test_local_sqlite_db_normaliza_grau_para_ordinal_e_ignora_underscores(tmp_path):
    import json
    from mbft_recuperador.local_adapters import LocalSqliteDB

    jsonl = tmp_path / "test_emb.jsonl"
    chunk = {
        "id": "712-92_EMENTA",
        "values": [0.1, 0.2],
        "metadata": {
            "codigo": "712-92",
            "artigo": "244",
            "secao": "EMENTA",
            "texto_contextualizado": "[Infração 712-92 | Art. 244 | Amparo: Art. 244, § 2º.] Conduzir ciclomotor.",
        },
    }
    jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")

    db = LocalSqliteDB(jsonl)
    res_grau = await db.buscar_fts("Art. 244, § 2°", limit=5)
    assert [r["id"] for r in res_grau] == ["712-92_EMENTA"]

    res_underscore = await db.buscar_fts("____ Art_244", limit=5)
    assert [r["id"] for r in res_underscore] == ["712-92_EMENTA"]

