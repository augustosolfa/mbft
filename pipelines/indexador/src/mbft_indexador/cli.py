import os
import sys
import json
import logging
import argparse
from pathlib import Path
from tqdm import tqdm
from typing import List

from mbft_core.models import FichaEnriquecida
from mbft_core.models.indexacao import ChunkPayload
from mbft_indexador.chunker import gerar_chunks_ficha
from mbft_indexador.embedder import Embedder

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def processar_indexacao(fichas: List[FichaEnriquecida], embedder: Embedder, batch_size: int = 32) -> List[ChunkPayload]:
    logger.info("Iniciando processo de chunking...")
    todos_chunks = []
    for ficha in tqdm(fichas, desc="Fazendo chunking"):
        chunks = gerar_chunks_ficha(ficha)
        todos_chunks.extend(chunks)
        
    logger.info(f"Total de {len(todos_chunks)} chunks gerados.")
    
    textos_para_vetorizar = [c.texto_para_embedding for c in todos_chunks]
    vetores = embedder.gerar_embeddings_lote(textos_para_vetorizar, batch_size=batch_size)
    
    payloads = []
    for i, c in enumerate(todos_chunks):
        payloads.append(ChunkPayload(
            id=c.id,
            values=vetores[i],
            metadata=c.metadata
        ))
    return payloads

def main():
    parser = argparse.ArgumentParser(description="MBFT Indexador - Gera chunks e embeddings BAAI/bge-m3 para o Cloudflare Vectorize.")
    parser.add_argument("--input", "-i", type=str, default="../../data/processed/enriquecedor/fichas_enriquecidas.json", help="Caminho para o JSON das fichas enriquecidas.")
    parser.add_argument("--output", "-o", type=str, default="../../data/processed/indexador/embeddings_mbft.jsonl", help="Caminho de saída para o JSONL de embeddings.")
    parser.add_argument("--batch-size", "-b", type=int, default=32, help="Tamanho do batch para inferência do modelo na GPU.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Faz apenas o chunking e salva metadados sem calcular os vetores densos (para debug rápido).")
    parser.add_argument("--deploy", action="store_true", help="Faz o upload do JSONL gerado para o Cloudflare Vectorize via wrangler.")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)

    if args.deploy:
        from mbft_indexador.deploy import fazer_deploy_vectorize
        try:
            fazer_deploy_vectorize(output_path)
        except (RuntimeError, FileNotFoundError) as e:
            logger.error(str(e))
            sys.exit(1)
        return

    if not input_path.exists():
        logger.error(f"Arquivo de entrada não encontrado: {input_path}")
        return
        
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
