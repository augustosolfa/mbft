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
            "item_numero": getattr(m, "item_numero", None),
            "competencia": m.competencia,
            "natureza_regra": m.natureza_regra.value if m.natureza_regra else None,
            "codigos_redirecionamento": list(m.codigos_redirecionamento) if m.codigos_redirecionamento else [],
            "codigos_concomitantes": list(m.codigos_concomitantes) if m.codigos_concomitantes else [],
            "artigos_ctb_associados": list(m.artigos_ctb_associados) if m.artigos_ctb_associados else [],
            "texto_contextualizado": chunk.texto_contextualizado,
            "tokens_estimados": chunk.tokens_estimados,
            "embedding": embeddings[i].tolist() # Converte numpy array para lista de floats nativa
        })
        
    schema = {
        "chunk_id": pl.Utf8,
        "tipo_documento": pl.Utf8,
        "origem_id": pl.Utf8,
        "secao": pl.Utf8,
        "item_numero": pl.Int32,
        "competencia": pl.Utf8,
        "natureza_regra": pl.Utf8,
        "codigos_redirecionamento": pl.List(pl.Utf8),
        "codigos_concomitantes": pl.List(pl.Utf8),
        "artigos_ctb_associados": pl.List(pl.Utf8),
        "texto_contextualizado": pl.Utf8,
        "tokens_estimados": pl.Int32,
        "embedding": pl.Array(pl.Float32, shape=1024),
    }
        
    df = pl.DataFrame(dados, schema=schema)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"[{__name__}] Exportando arquivo Parquet para {output_path}...")
    # Salvando em Parquet
    df.write_parquet(output_path, compression="zstd")
    
    return df
