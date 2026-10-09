import os
import json
import yaml
import logging
import argparse
from pathlib import Path
import numpy as np

# We'll import GeradorEmbeddings instead of sentence_transformers directly
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from mbft_indexador.embedder import GeradorEmbeddings

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jsonl", type=str, default="../../data/processed/indexador/embeddings_mbft.jsonl")
    parser.add_argument("--casos", type=str, default="casos_aderencia.yaml")
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl)
    casos_path = Path(args.casos)

    if not jsonl_path.exists():
        logger.error(f"Arquivo JSONL não encontrado: {jsonl_path}")
        return
    if not casos_path.exists():
        logger.error(f"Arquivo de casos não encontrado: {casos_path}")
        return

    logger.info("Carregando modelo via GeradorEmbeddings...")
    embedder = GeradorEmbeddings()

    logger.info(f"Carregando embeddings de {jsonl_path}...")
    chunks = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            chunks.append(json.loads(line))

    for c in chunks:
        c["values"] = np.array(c["values"], dtype=np.float32)

    logger.info(f"Carregando casos de teste de {casos_path}...")
    with open(casos_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        casos = data.get("casos", [])

    logger.info(f"Executando {len(casos)} casos de teste...")
    
    hits_top1 = 0
    hits_top3 = 0
    hits_top5 = 0

    for i, caso in enumerate(casos):
        query = caso["query"]
        expected_codes = set(caso["expected"])
        
        # GeradorEmbeddings returns List[List[float]], we just extract the first one and make it a numpy array
        query_emb_list = embedder.gerar_embeddings_lote([query], batch_size=1)[0]
        query_emb = np.array(query_emb_list, dtype=np.float32)
        
        results = []
        for c in chunks:
            sim = cosine_similarity(query_emb, c["values"])
            results.append((sim, c))
            
        results.sort(key=lambda x: x[0], reverse=True)
        
        def get_unique_codes(top_k_results):
            codes = []
            for _, res in top_k_results:
                code = res["metadata"]["codigo"]
                if code not in codes:
                    codes.append(code)
            return codes
            
        unique_codes = get_unique_codes(results)
        top1_codes = unique_codes[:1]
        top3_codes = unique_codes[:3]
        top5_codes = unique_codes[:5]
        
        is_top1 = any(c in expected_codes for c in top1_codes)
        is_top3 = any(c in expected_codes for c in top3_codes)
        is_top5 = any(c in expected_codes for c in top5_codes)
        
        if is_top1: hits_top1 += 1
        if is_top3: hits_top3 += 1
        if is_top5: hits_top5 += 1
        
        logger.info(f"Caso {i+1}: '{query}'")
        logger.info(f"  Esperado: {list(expected_codes)}")
        logger.info(f"  Top 1: {top1_codes[0] if top1_codes else 'N/A'} (Sim: {results[0][0]:.4f})")
        logger.info(f"  Top 5: {top5_codes}")
        logger.info("-" * 40)
        
    total = len(casos)
    logger.info("=== RELATÓRIO DE AVALIAÇÃO (RECALL DENSE) ===")
    logger.info(f"Recall@1: {hits_top1}/{total} ({hits_top1/total*100:.1f}%)")
    logger.info(f"Recall@3: {hits_top3}/{total} ({hits_top3/total*100:.1f}%)")
    logger.info(f"Recall@5: {hits_top5}/{total} ({hits_top5/total*100:.1f}%)")

if __name__ == "__main__":
    main()
