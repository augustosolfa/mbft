import logging
import hashlib
from typing import List, Protocol

try:
    from sentence_transformers import SentenceTransformer
    import torch
except ImportError:
    SentenceTransformer = None

logger = logging.getLogger(__name__)

class Embedder(Protocol):
    def gerar_embeddings_lote(self, textos: List[str], batch_size: int = 32) -> List[List[float]]:
        ...

class FakeEmbedder:
    def __init__(self, dimensoes: int = 1024):
        self.dimensoes = dimensoes

    def gerar_embeddings_lote(self, textos: List[str], batch_size: int = 32) -> List[List[float]]:
        resultados = []
        for texto in textos:
            h = hashlib.sha256(texto.encode("utf-8")).digest()
            vetor = [(b / 255.0) - 0.5 for b in h]
            while len(vetor) < self.dimensoes:
                vetor.extend(vetor)
            vetor = vetor[:self.dimensoes]
            resultados.append(vetor)
        return resultados


class GeradorEmbeddings:
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers não está instalado no ambiente.")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Carregando modelo {model_name} no dispositivo: {device}")
        self.model = SentenceTransformer(model_name, device=device)
        
    def gerar_embeddings_lote(self, textos: List[str], batch_size: int = 32) -> List[List[float]]:
        '''
        Processa uma lista de textos em lotes e retorna os vetores em formato float32.
        BGE-M3 gera vetores de 1024 dimensões.
        '''
        if not textos:
            return []
            
        logger.info(f"Gerando embeddings para {len(textos)} chunks em lotes de {batch_size}...")
        embeddings = self.model.encode(
            textos, 
            batch_size=batch_size, 
            normalize_embeddings=True,
            show_progress_bar=True
        )
        
        # Converte de numpy array para list de floats
        return embeddings.tolist()
