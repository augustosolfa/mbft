import sqlite3
import json
import logging
from typing import List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

from mbft_recuperador.interfaces import IVectorDB, IRelationalDB, IEmbedderClient

class LocalSqliteDB(IRelationalDB):
    def __init__(self, jsonl_path: Path):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self._setup_db(jsonl_path)
        
    def _setup_db(self, jsonl_path: Path):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE VIRTUAL TABLE fts_chunks USING fts5(
                id UNINDEXED,
                codigo,
                artigo,
                secao,
                texto_contextualizado,
                tokenize="unicode61 remove_diacritics 1"
            )
        ''')
        
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Arquivo {jsonl_path} não encontrado.")
            
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                meta = data["metadata"]
                
                cursor.execute('''
                    INSERT INTO fts_chunks (id, codigo, artigo, secao, texto_contextualizado)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    data["id"],
                    meta.get("codigo", ""),
                    meta.get("artigo", ""),
                    meta.get("secao", ""),
                    meta.get("texto_contextualizado", "")
                ))
        self.conn.commit()

    async def buscar_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        # Para FTS5 no SQLite, precisamos escapar a query ou usar syntax de MATCH apropriada.
        # Por simplicidade, vamos usar o query term por term, adicionando * (prefix search)
        import re
        tokens = re.findall(r'\w+', query)
        if not tokens:
            return []
            
        fts_query = " ".join([f"{t}*" for t in tokens])
        
        cursor = self.conn.cursor()
        # bm25() no FTS5 ordena automaticamente do menor pro maior se quisermos os melhores (mais negativos)
        # O FTS5 rank é negativo, onde menores valores são melhores.
        cursor.execute('''
            SELECT id, codigo, artigo, texto_contextualizado, bm25(fts_chunks) as score
            FROM fts_chunks 
            WHERE fts_chunks MATCH ? 
            ORDER BY score ASC 
            LIMIT ?
        ''', (fts_query, limit))
        
        resultados = []
        for row in cursor.fetchall():
            # Inverter o score para ficar numérico positivo comparável (opcional, já que RRF usa apenas rank posicional)
            # FTS5 score original = menor é melhor.
            resultados.append({
                "id": row["id"],
                "metadata": {
                    "codigo": row["codigo"],
                    "artigo": row["artigo"],
                    "texto_contextualizado": row["texto_contextualizado"]
                },
                "score": abs(row["score"])
            })
        return resultados

class NumpyVectorDB(IVectorDB):
    def __init__(self, jsonl_path: Path):
        import numpy as np
        self.np = np
        self.chunks = []
        
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Arquivo {jsonl_path} não encontrado.")
            
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                data["values"] = self.np.array(data["values"], dtype=self.np.float32)
                self.chunks.append(data)
                
    async def buscar_similares(self, vetor: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        q_vec = self.np.array(vetor, dtype=self.np.float32)
        q_norm = self.np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
            
        resultados = []
        for c in self.chunks:
            c_vec = c["values"]
            sim = self.np.dot(q_vec, c_vec) / (q_norm * self.np.linalg.norm(c_vec))
            resultados.append({
                "id": c["id"],
                "score": float(sim),
                "metadata": c["metadata"]
            })
            
        resultados.sort(key=lambda x: x["score"], reverse=True)
        return resultados[:limit]

class PyTorchEmbedder(IEmbedderClient):
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except ImportError:
            raise RuntimeError("sentence-transformers ou torch não estão instalados.")
            
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Carregando {model_name} em {device}...")
        self.model = SentenceTransformer(model_name, device=device)
        
    async def embed_query(self, query: str) -> List[float]:
        # Codificação síncrona, mas envolvida num método async para obedecer interface
        emb = self.model.encode(query, normalize_embeddings=True)
        return emb.tolist()
