"""
Módulo para construção e serialização de HTML semântico limpo para 'Informações Complementares'
e exportação de imagens em alta resolução (300 DPI).
"""

import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional

import pypdfium2 as pdfium
from PIL import Image

logger = logging.getLogger("MBFT-HtmlBuilder")


def recortar_imagem_300dpi(
    page: pdfium.PdfPage,
    bbox_pt: Tuple[float, float, float, float],  # (x0, y0, x1, y1) em pontos PDF (bottom-left)
    output_path: Path,
    dpi: int = 300,
) -> str:
    """
    Renderiza e recorta em 300 DPI a região visual especificada pelo bounding box.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    w_pt, h_pt = page.get_size()
    scale = dpi / 72.0

    # Renderiza a página em alta definição
    img_page = page.render(scale=scale).to_pil()

    x0, y0, x1, y1 = bbox_pt
    # Conversão para o sistema de coordenadas do PIL (top-left)
    crop_x0 = max(0, int(x0 * scale))
    crop_y0 = max(0, int((h_pt - y1) * scale))
    crop_x1 = min(img_page.width, int(x1 * scale))
    crop_y1 = min(img_page.height, int((h_pt - y0) * scale))

    if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
        logger.warning(f"Dimensões inválidas para recorte de imagem: {bbox_pt}")
        return ""

    cropped = img_page.crop((crop_x0, crop_y0, crop_x1, crop_y1))
    cropped.save(output_path, "PNG")
    logger.info(f"Imagem 300 DPI exportada: {output_path} ({cropped.width}x{cropped.height} px)")
    return output_path.as_posix()


def detectar_e_extrair_desenhos_ic(
    page: pdfium.PdfPage,
    ic_y_top: float,
    codigo_ficha: str,
    output_dir: Path,
    img_start_index: int = 1,
) -> Tuple[List[str], Optional[float]]:
    """
    Detecta áreas de ilustração/desenho vetorial abaixo do texto de Informações Complementares.
    Retorna a lista de caminhos relativos das imagens geradas e o Y inferior da imagem.
    """
    tp = page.get_textpage()
    num_rects = tp.count_rects()
    w, h = page.get_size()

    # Identifica o Y mais baixo de texto em Informações Complementares
    lowest_text_y = ic_y_top
    has_drawing_text = False

    for i in range(num_rects):
        r = tp.get_rect(i)
        # Considera apenas retângulos dentro do espaço de IC
        if r[3] <= ic_y_top:
            txt = tp.get_text_bounded(*r).strip()
            if not txt:
                continue
            if re.search(r"desenho\s+ilustrativo|imagens\s+ilustrativas", txt, re.IGNORECASE):
                has_drawing_text = True
            lowest_text_y = min(lowest_text_y, r[1])

    # Se há menção a desenho ilustrativo ou espaço vazio relevante antes da margem inferior (50pt)
    # e não há mais texto abaixo de lowest_text_y, essa região é o desenho!
    caminhos = []
    if has_drawing_text and (lowest_text_y - 50.0 > 40.0):
        # A ilustração está localizada entre a margem inferior (aprox 50pt) e lowest_text_y
        bbox = (35.0, 50.0, w - 35.0, lowest_text_y - 5.0)
        img_filename = f"ficha{codigo_ficha}_{img_start_index}.png"
        img_path = output_dir / img_filename
        caminho_rel = f"imagens/{img_filename}"

        recortar_imagem_300dpi(page, bbox, img_path)
        caminhos.append(caminho_rel)

    return caminhos, lowest_text_y


def formatar_tabela_html(html_bruto: str) -> str:
    """
    Limpa e padroniza tabela HTML gerada pelo Docling para garantir semântica pura.
    """
    # Remove estilos inline intrusivos
    limpo = re.sub(r'\s*style="[^"]*"', '', html_bruto)
    limpo = re.sub(r'\s*class="[^"]*"', '', limpo)
    limpo = re.sub(r'[\r\n]+', '\n', limpo)
    return limpo.strip()
