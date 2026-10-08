from typing import List, Dict, Any
from mbft_recuperador.interfaces import IVectorDB, IRelationalDB, IEmbedderClient

class BuscadorHibrido:
    """
    Core engine do pipeline de recuperação RAG. 
    Agnóstico de infraestrutura, operando via Injeção de Dependência.
    """
    def __init__(self, vector_db: IVectorDB, relational_db: IRelationalDB, ai_client: IEmbedderClient):
        self.vector_db = vector_db
        self.relational_db = relational_db
        self.ai_client = ai_client
        
    def _aplicar_rrf(self, dense_results: List[Dict[str, Any]], sparse_results: List[Dict[str, Any]], k: int = 60) -> List[Dict[str, Any]]:
        """
        Aplica Reciprocal Rank Fusion para mesclar resultados densos e esparsos.
        score_rrf = 1 / (k + rank)
        """
        rrf_scores = {}
        documentos_agrupados = {}
        
        # Rankeia densos
        for rank_idx, doc in enumerate(dense_results):
            doc_id = doc["id"]
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
                documentos_agrupados[doc_id] = doc
            rrf_scores[doc_id] += 1.0 / (k + rank_idx + 1)
            
        # Rankeia esparsos (BM25)
        for rank_idx, doc in enumerate(sparse_results):
            doc_id = doc["id"]
            if doc_id not in rrf_scores:
                rrf_scores[doc_id] = 0.0
                documentos_agrupados[doc_id] = doc
            rrf_scores[doc_id] += 1.0 / (k + rank_idx + 1)
            
        # Ordena pelo score final do RRF
        resultados_finais = []
        for doc_id, score in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True):
            doc = documentos_agrupados[doc_id]
            doc["rrf_score"] = score
            resultados_finais.append(doc)
            
        return resultados_finais
        
    async def recuperar_contexto(self, pergunta: str, limit: int = 5) -> List[Dict[str, Any]]:
        # 1. Vetoriza a pergunta
        vetor = await self.ai_client.embed_query(pergunta)
        
        # 2. Executa as buscas (Idealmente executado de forma paralela usando asyncio.gather)
        # Por questão de legibilidade do algoritmo base, mantemos em sequência (ou pode-se usar gather).
        dense_results = await self.vector_db.buscar_similares(vetor, limit=limit)
        sparse_results = await self.relational_db.buscar_fts(pergunta, limit=limit)
        
        # 3. Mescla via RRF
        rrf_results = self._aplicar_rrf(dense_results, sparse_results)
        
        return rrf_results[:limit]
