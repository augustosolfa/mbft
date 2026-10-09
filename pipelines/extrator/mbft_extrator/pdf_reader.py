import pypdfium2 as pdfium
from typing import List, Tuple
import logging

from .models import RetanguloTexto, PaginaExtraida, ImagemExtraida
from .pdf_geometry import FPDF_PAGEOBJ_PATH, FPDF_PAGEOBJ_IMAGE, MIN_IMG_SIZE, Y_MIN_IMAGE

logger = logging.getLogger("MBFT-PdfReader")

def ler_pagina(page: pdfium.PdfPage) -> PaginaExtraida:
    """
    Camada fina de I/O. Extrai a geometria e texto usando pdfium e retorna um DTO puro.
    """
    width, height = page.get_size()
    
    tp = page.get_textpage()
    num_rects = tp.count_rects()
    retangulos = []
    
    for i in range(num_rects):
        r = tp.get_rect(i)
        txt = tp.get_text_bounded(*r).strip()
        if txt:
            # pdfium get_rect retorna (left, bottom, right, top) = (x0, y0, x1, y1)
            retangulos.append(
                RetanguloTexto(
                    x0=r[0],
                    y0=r[1],
                    x1=r[2],
                    y1=r[3],
                    texto=txt, id=i
                )
            )
            
    paths = []
    for obj in page.get_objects():
        if getattr(obj, "type", None) == FPDF_PAGEOBJ_PATH:
            paths.append(obj.get_bounds())
            
    return PaginaExtraida(
        largura=float(width),
        altura=float(height),
        retangulos=retangulos,
        linhas_vetoriais=paths
    )

def extrair_imagens_pagina(page: pdfium.PdfPage, y_top_limit: float, codigo_ficha: str, img_idx_inicial: int) -> Tuple[List[ImagemExtraida], int]:
    """
    Extrai imagens (bitmaps) da página, respeitando o limite Y_TOP.
    Retorna a lista de DTOs e o próximo índice de imagem.
    """
    page_imgs = []
    img_idx = img_idx_inicial

    for obj in page.get_objects():
        if getattr(obj, "type", None) == FPDF_PAGEOBJ_IMAGE:
            x0, y0, x1, y1 = obj.get_bounds()
            if (x1 - x0) >= MIN_IMG_SIZE and (y1 - y0) >= MIN_IMG_SIZE and y0 >= Y_MIN_IMAGE and y1 <= (y_top_limit + 15.0):
                img_nome = f"ficha{codigo_ficha}_{img_idx}.png"
                rel_path = f"imagens/{img_nome}"

                try:
                    bm = obj.get_bitmap()
                    pil_img = bm.to_pil()
                    img_idx += 1
                    page_imgs.append(ImagemExtraida(
                        bounds=(x0, y0, x1, y1),
                        x0=x0, y0=y0, x1=x1, y1=y1,
                        yc=(y0 + y1) / 2.0, xc=(x0 + x1) / 2.0,
                        rel_path=rel_path,
                        width=x1 - x0,
                        img_data=pil_img
                    ))
                except Exception:
                    logger.exception(f"Erro ao extrair bitmap {img_nome}")

    return page_imgs, img_idx
