import re
from typing import List, Tuple, Any

import pypdfium2 as pdfium

FPDF_PAGEOBJ_PATH = pdfium.raw.FPDF_PAGEOBJ_PATH
FPDF_PAGEOBJ_IMAGE = pdfium.raw.FPDF_PAGEOBJ_IMAGE

Y_TOP_LIMIT_DEFAULT = 40.0
Y_MIN_IMAGE = 30.0
MIN_IMG_SIZE = 25.0
MARGEM_ESQUERDA_TITULO = 60.0
MARGEM_ESQUERDA_SECAO_NUMERADA = 80.0
COL_BOUNDS_PCT = [0.28, 0.50, 0.73]
Y_LIMIT_HEADER = 350.0
Y_TOP_PRIMEIRA_PAGINA = 715

X_LEFT_COL_MAX = 290.0
X_RIGHT_COL_MIN = 280.0
X_TEXT_LEFT_MAX = 300.0

RE_IC_HEADER = re.compile(r"^informa[cç][oõ]es\s+complementares:?$", re.IGNORECASE)
RE_QUANDO_AUTUAR = re.compile(r"quando\s+autuar", re.IGNORECASE)
RE_COLUMN_HEADER = re.compile(
    r"^(?:quando\s+autuar|quando\s+n[ãa]o\s+autuar|defini[cç][oõ]es.*|exemplos.*):?$",
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
