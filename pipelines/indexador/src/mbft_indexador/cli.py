import os
import sys
import json
import logging
import argparse
from pathlib import Path
from tqdm import tqdm
from typing import List, Optional

from mbft_core.models import FichaEnriquecida
from mbft_core.models.indexacao import ChunkPayload
from mbft_core.paths import PROCESSED_DIR
from mbft_indexador.chunker import gerar_chunks_ficha
from mbft_indexador.embedder import Embedder

DIMENSAO_VETOR_ESPERADA = 1024

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def processar_indexacao(
    fichas: List[FichaEnriquecida],
    embedder: Embedder,
    batch_size: int = 32,
    dimensao_esperada: int = DIMENSAO_VETOR_ESPERADA
) -> List[ChunkPayload]:
    logger.info("Iniciando processo de chunking...")
    todos_chunks = []
    for ficha in tqdm(fichas, desc="Fazendo chunking"):
        chunks = gerar_chunks_ficha(ficha)
        todos_chunks.extend(chunks)
        
    logger.info(f"Total de {len(todos_chunks)} chunks gerados.")
    
    textos_para_vetorizar = [c.texto_para_embedding for c in todos_chunks]
    vetores = embedder.gerar_embeddings_lote(textos_para_vetorizar, batch_size=batch_size)
    
    assert len(vetores) == len(todos_chunks), (
        f"Quantidade de vetores gerados ({len(vetores)}) difere da quantidade de chunks ({len(todos_chunks)})."
    )
    if vetores:
        assert len(vetores[0]) == dimensao_esperada, (
            f"Dimensão do vetor ({len(vetores[0])}) difere da esperada ({dimensao_esperada})."
        )
    
    payloads = []
    for i, c in enumerate(todos_chunks):
        payloads.append(ChunkPayload(
            id=c.id,
            values=vetores[i],
            metadata=c.metadata
        ))
    return payloads

def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="MBFT Indexador - Gera chunks semânticos e embeddings densos BAAI/bge-m3 em formato JSONL.")
    parser.add_argument("--input", "-i", type=str, default=str(PROCESSED_DIR / "enriquecedor" / "fichas_enriquecidas.json"), help="Caminho para o JSON das fichas enriquecidas.")
    parser.add_argument("--output", "-o", type=str, default=None, help="Caminho de saída para o JSONL de embeddings.")
    parser.add_argument("--batch-size", "-b", type=int, default=32, help="Tamanho do batch para inferência do modelo na GPU.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Modo debug/teste sem modelo real de embeddings (salva em arquivo de debug).")
    
    args = parser.parse_args(argv)
    
    input_path = Path(args.input)
    
    # Determina arquivo de saída padrão dependendo de --skip-embeddings
    if args.output is not None:
        output_path = Path(args.output)
    else:
        if args.skip_embeddings:
            output_path = PROCESSED_DIR / "indexador" / "embeddings_debug.jsonl"
        else:
            output_path = PROCESSED_DIR / "indexador" / "embeddings_mbft.jsonl"

    if not input_path.exists():
        logger.error(f"Arquivo de entrada não encontrado: {input_path}")
        sys.exit(1)
        
    os.makedirs(output_path.parent, exist_ok=True)
    
    logger.info(f"Lendo fichas enriquecidas de: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        fichas_data = json.load(f)
        
    fichas = [FichaEnriquecida.model_validate(f) for f in fichas_data]
    logger.info(f"{len(fichas)} fichas validadas com sucesso.")
    
    if args.skip_embeddings:
        logger.info("Pulando geração de embeddings (modo skip). Usando FakeEmbedder.")
        from mbft_indexador.embedder import FakeEmbedder
        embedder = FakeEmbedder()
    else:
        logger.info("Carregando modelo de embeddings...")
        from mbft_indexador.embedder import GeradorEmbeddings
        embedder = GeradorEmbeddings()

    payloads = processar_indexacao(fichas, embedder, args.batch_size)
            
    logger.info(f"Salvando artefato JSONL (NDJSON) em {output_path}...")
    with open(output_path, "w", encoding="utf-8") as out_f:
        for payload in payloads:
            out_f.write(payload.model_dump_json() + "\n")
            
    logger.info(f"Concluído! {len(payloads)} registros exportados.")

if __name__ == "__main__":
    main()
