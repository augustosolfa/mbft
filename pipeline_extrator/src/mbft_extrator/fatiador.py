"""
Módulo de fatiamento e mapeamento dos intervalos de páginas das fichas do MBFT.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

import pypdfium2 as pdfium
from .models import FichaMapeada

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
    """
    Varre o PDF a partir da página 32 e localiza o início e término de cada uma das 402 fichas.
    Utiliza cache em disco para evitar revarredura do documento de 826 páginas.
    """
    if cache_path and cache_path.exists() and not force:
        logger.info(f"Carregando mapeamento de fichas do cache: {cache_path}")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return [FichaMapeada(**item) for item in dados]
        except Exception as e:
            logger.warning(f"Falha ao ler cache ({e}). Recalculando mapeamento...")

    logger.info(f"Iniciando varredura vetorial do PDF: {pdf_path.name}...")
    doc = pdfium.PdfDocument(str(pdf_path))
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

    logger.info(f"Mapeamento concluído com sucesso: {len(resultado)} fichas localizadas no PDF.")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump([item.model_dump() for item in resultado], f, ensure_ascii=False, indent=2)
        logger.info(f"Mapeamento persistido em cache: {cache_path}")

    return resultado
