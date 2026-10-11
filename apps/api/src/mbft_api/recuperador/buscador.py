from typing import List, Dict, Any
from .interfaces import IVectorDB, IRelationalDB, IEmbedderClient

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
            doc = {**documentos_agrupados[doc_id], "rrf_score": score}
            resultados_finais.append(doc)
            
        return resultados_finais
        
    def _diversificar_por_ficha(self, rrf_results: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """
        Prioriza o chunk de maior score RRF de cada ficha (código de enquadramento),
        evitando que múltiplos chunks da mesma ficha monopolizem o Top-K.
        Caso haja menos fichas distintas que `limit`, preenche as vagas restantes
        com os demais chunks na ordem original do RRF.
        """
        if limit <= 0 or not rrf_results:
            return []

        selecionados: List[Dict[str, Any]] = []
        codigos_vistos = set()
        ids_selecionados = set()

        for doc in rrf_results:
            codigo = (doc.get("metadata") or {}).get("codigo")
            if codigo:
                if codigo in codigos_vistos:
                    continue
                codigos_vistos.add(codigo)

            selecionados.append(doc)
            ids_selecionados.add(doc["id"])
            if len(selecionados) >= limit:
                return selecionados

        for doc in rrf_results:
            if doc["id"] not in ids_selecionados:
                selecionados.append(doc)
                ids_selecionados.add(doc["id"])
                if len(selecionados) >= limit:
                    break

        return selecionados

    async def recuperar_contexto(self, pergunta: str, limit: int = 5) -> List[Dict[str, Any]]:
        # O pool precisa ser fundo o suficiente para o RRF funcionar
        pool_size = max(limit * 10, 60)
        
        # 1. Vetoriza a pergunta
        vetor = await self.ai_client.embed_query(pergunta)
        
        # 2. Executa as buscas
        dense_results = await self.vector_db.buscar_similares(vetor, limit=pool_size)
        sparse_results = await self.relational_db.buscar_fts(pergunta, limit=pool_size)
        
        # 3. Mescla via RRF e diversifica por ficha
        rrf_results = self._aplicar_rrf(dense_results, sparse_results)
        
        return self._diversificar_por_ficha(rrf_results, limit)
