import json
import logging
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import pypdfium2 as pdfium
from .models import FichaMapeada
from .utils import calcular_hash_pdf, VERSAO_PIPELINE

logger = logging.getLogger("MBFT-Fatiador")

REGEX_ENQUADRAMENTO = re.compile(
    r"c[oó]digo\s+(?:d?o?\s*)?enquadramento:?\s*([0-9]{3}[-\s][0-9]{1,2})",
    re.IGNORECASE,
)

def mapear_fichas_no_pdf(
    pdf_path: Path,
    cache_path: Optional[Path] = None,
    force: bool = False,
) -> List[FichaMapeada]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF n\u00e3o encontrado: {pdf_path}")
        
    pdf_hash = calcular_hash_pdf(pdf_path)
    
    if cache_path and cache_path.exists() and not force:
        logger.info(f"Carregando mapeamento de fichas do cache: {cache_path}")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                dados_cache = json.load(f)
                
            if isinstance(dados_cache, dict):
                # New cache format with version and hash
                cache_hash = dados_cache.get("pdf_sha256")
                cache_versao = dados_cache.get("versao_pipeline")
                fichas_raw = dados_cache.get("fichas", [])
                
                if cache_hash == pdf_hash and cache_versao == VERSAO_PIPELINE:
                    return [FichaMapeada(**item) for item in fichas_raw]
                else:
                    logger.warning("Cache invalidado por diverg\u00eancia de hash do PDF ou vers\u00e3o do pipeline.")
            else:
                logger.warning("Formato antigo de cache detectado. Ignorando.")
        except Exception as e:
            logger.warning(f"Falha ao ler cache ({e}). Recalculando mapeamento...")

    logger.info(f"Iniciando varredura vetorial do PDF: {pdf_path.name}...")
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        total_pags = len(doc)
    
        fichas_encontradas: List[Dict[str, Any]] = []
        ocorrencias_codigo: Dict[str, int] = {}
    
        # As fichas começam na página 32 (índice 31 em 0-index)
        inicio_fichas_idx = 31
    
        for idx in range(inicio_fichas_idx, total_pags):
            tp = doc[idx].get_textpage()
            texto_pag = tp.get_text_range()
            match = REGEX_ENQUADRAMENTO.search(texto_pag)
            if match:
                raw_codigo = match.group(1)
                codigo = re.sub(r"\s+", "", raw_codigo)
                fichas_encontradas.append({
                    "codigo": codigo,
                    "pag_ini": idx + 1,  # 1-indexed
                })
    finally:
        doc.close()

    # Define o término de cada ficha como a página anterior ao início da seguinte
    resultado: List[FichaMapeada] = []
    for i in range(len(fichas_encontradas)):
        item = fichas_encontradas[i]
        if i + 1 < len(fichas_encontradas):
            pag_fim = fichas_encontradas[i + 1]["pag_ini"] - 1
        else:
            pag_fim = total_pags

        cod = item["codigo"]
        ocorrencias_codigo[cod] = ocorrencias_codigo.get(cod, 0) + 1
        if ocorrencias_codigo[cod] > 1:
            identificador = f"{cod}_p{ocorrencias_codigo[cod]}"
        else:
            identificador = cod

        resultado.append(
            FichaMapeada(
                codigo=cod,
                pag_ini=item["pag_ini"],
                pag_fim=pag_fim,
                identificador=identificador,
            )
        )

    logger.info(f"Mapeamento conclu\u00eddo com sucesso: {len(resultado)} fichas localizadas no PDF.")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_cache = cache_path.with_suffix(".tmp")
        
        cache_data = {
            "pdf_sha256": pdf_hash,
            "versao_pipeline": VERSAO_PIPELINE,
            "fichas": [item.model_dump() for item in resultado]
        }
        
        with open(temp_cache, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
        os.replace(temp_cache, cache_path)
        logger.info(f"Mapeamento persistido em cache at\u00f4mico: {cache_path}")

    return resultado
