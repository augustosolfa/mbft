import os
from typing import List
import polars as pl
from sentence_transformers import SentenceTransformer
from mbft_core.models.enriquecimento import ChunkPayload

# Definições do Modelo
MODELO_BGE = "BAAI/bge-m3"

def vetorizar_e_exportar(chunks: List[ChunkPayload], output_path: str):
    """
    Vetoriza os payloads usando BAAI/bge-m3 com aceleração CUDA (se disponível)
    e exporta o resultado em formato Apache Parquet via Polars.
    """
    print(f"[{__name__}] Carregando modelo {MODELO_BGE}...")
    # sentence-transformers automaticamente usa 'cuda' se disponível no PyTorch
    modelo = SentenceTransformer(MODELO_BGE)
    
    textos = [chunk.texto_contextualizado for chunk in chunks]
    
    print(f"[{__name__}] Calculando embeddings para {len(textos)} chunks...")
    embeddings = modelo.encode(textos, batch_size=32, show_progress_bar=True)
    
    print(f"[{__name__}] Estruturando Dataframe Polars...")
    # Achatar os metadados para construir a tabela
    dados = []
    for i, chunk in enumerate(chunks):
        m = chunk.metadados
        dados.append({
            "chunk_id": m.chunk_id,
            "tipo_documento": m.tipo_documento,
            "origem_id": m.origem_id,
            "secao": m.secao,
            "competencia": m.competencia,
            "natureza_regra": m.natureza_regra.value if m.natureza_regra else None,
            "codigo_redirecionamento": m.codigo_redirecionamento,
            "codigos_concomitantes": ",".join(m.codigos_concomitantes) if m.codigos_concomitantes else None,
            "artigos_ctb_associados": ",".join(m.artigos_ctb_associados) if m.artigos_ctb_associados else None,
            "texto_contextualizado": chunk.texto_contextualizado,
            "tokens_estimados": chunk.tokens_estimados,
            "embedding": embeddings[i].tolist() # Converte numpy array para lista de floats nativa
        })
        
    df = pl.DataFrame(dados)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"[{__name__}] Exportando arquivo Parquet para {output_path}...")
    # Salvando em Parquet
    df.write_parquet(output_path)
    
    return df
