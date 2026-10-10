import re
from typing import List, Tuple, Any

import pypdfium2 as pdfium

from .config import DEFAULT_LAYOUT_CONFIG

FPDF_PAGEOBJ_PATH = pdfium.raw.FPDF_PAGEOBJ_PATH
FPDF_PAGEOBJ_IMAGE = pdfium.raw.FPDF_PAGEOBJ_IMAGE

# Constantes retrocompatíveis espelhadas a partir de DEFAULT_LAYOUT_CONFIG
Y_TOP_LIMIT_DEFAULT = DEFAULT_LAYOUT_CONFIG.y_top_limit_default
Y_MIN_IMAGE = DEFAULT_LAYOUT_CONFIG.y_min_image
MIN_IMG_SIZE = DEFAULT_LAYOUT_CONFIG.min_img_size
MARGEM_ESQUERDA_TITULO = DEFAULT_LAYOUT_CONFIG.margem_esquerda_titulo
MARGEM_ESQUERDA_SECAO_NUMERADA = DEFAULT_LAYOUT_CONFIG.margem_esquerda_secao_numerada
COL_BOUNDS_PCT = DEFAULT_LAYOUT_CONFIG.col_bounds_pct
Y_LIMIT_HEADER = DEFAULT_LAYOUT_CONFIG.y_limit_header
Y_TOP_PRIMEIRA_PAGINA = DEFAULT_LAYOUT_CONFIG.y_top_primeira_pagina

X_LEFT_COL_MAX = DEFAULT_LAYOUT_CONFIG.x_left_col_max
X_RIGHT_COL_MIN = DEFAULT_LAYOUT_CONFIG.x_right_col_min
X_TEXT_LEFT_MAX = DEFAULT_LAYOUT_CONFIG.x_text_left_max

RE_IC_HEADER = re.compile(r"^informa[cç][oõ]es\s+complementares:?$", re.IGNORECASE)
RE_QUANDO_AUTUAR = re.compile(r"quando\s+autuar", re.IGNORECASE)
RE_COLUMN_HEADER = re.compile(
    r"^(?:quando\s+autuar|quando\s+n[ãa]o\s+autuar|defini[cç][oõ]es\s+e\s+procedimentos|exemplos\s+(?:do\s+campo\s+)?(?:de\s+)?['\"‘“]?observa[cç][oõ]es['\"’”]?(?:\s+do\s+ait)?):?$",
    re.IGNORECASE,
)

def linhas_vetoriais(page: pdfium.PdfPage) -> List[Tuple[float, float, float, float]]:
    """Retorna os limites (x0, y0, x1, y1) dos caminhos vetoriais da página."""
    paths = []
    for obj in page.get_objects():
        if getattr(obj, "type", None) == FPDF_PAGEOBJ_PATH:
            paths.append(obj.get_bounds())
    return paths

def agrupar_em_linhas(items: List[Any], yc_extractor, y_tolerance: float = 3.5) -> List[List[Any]]:
    """
    Agrupa uma lista de itens horizontalmente em linhas contínuas, baseado
    na tolerância da coordenada Y central (yc).
    Retorna uma lista de listas de itens (cada sublista é uma linha).
    """
    if not items:
        return []
    
    items_sorted = sorted(items, key=lambda it: -yc_extractor(it))
    lines = []
    curr = []
    curr_y = None
    
    for item in items_sorted:
        yc = yc_extractor(item)
        if curr_y is None or abs(yc - curr_y) <= y_tolerance:
            curr.append(item)
            curr_y = yc if len(curr) == 1 else (curr_y + yc) / 2.0
        else:
            lines.append(curr)
            curr = [item]
            curr_y = yc
            
    if curr:
        lines.append(curr)
        
    return lines
