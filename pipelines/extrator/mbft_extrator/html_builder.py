"""
Módulo para construção e serialização de HTML semântico limpo para 'Informações Complementares'
e exportação de imagens nativas e de alta resolução.
"""

import logging
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import pypdfium2 as pdfium
from PIL import Image

from .stitching import _join_line_fragments, unificar_linhas_e_hifens
from .pdf_geometry import (
    FPDF_PAGEOBJ_IMAGE,
    Y_MIN_IMAGE,
    MIN_IMG_SIZE,
    Y_TOP_LIMIT_DEFAULT,
    MARGEM_ESQUERDA_SECAO_NUMERADA,
    X_LEFT_COL_MAX,
    X_RIGHT_COL_MIN,
    X_TEXT_LEFT_MAX,
    RE_IC_HEADER,
    agrupar_em_linhas,
)

logger = logging.getLogger("MBFT-HtmlBuilder")


def formatar_tabela_html(html_bruto: str) -> str:
    """
    Limpa e padroniza tabela HTML gerada pelo Docling para garantir semântica pura.
    """
    limpo = re.sub(r'\s*style="[^"]*"', '', html_bruto)
    limpo = re.sub(r'\s*class="[^"]*"', '', limpo)
    limpo = re.sub(r'[\r\n]+', '\n', limpo)
    return limpo.strip()


def agrupar_retangulos_em_linhas(rects_list: List[Dict[str, Any]], y_tolerance: float = 3.5) -> List[Dict[str, Any]]:
    """
    Agrupa retângulos de texto horizontalmente adjacentes em linhas contínuas.
    """
    if not rects_list:
        return []

    linhas_agrupadas = agrupar_em_linhas(rects_list, lambda x: x["yc"], y_tolerance)

    lines = []
    for curr in linhas_agrupadas:
        curr.sort(key=lambda x: x["rect"][0])
        s = _join_line_fragments([(it["rect"][0], it["rect"][2], it["txt"]) for it in curr])
        if s:
            y_medio = sum(it["yc"] for it in curr) / len(curr)
            lines.append({"y": y_medio, "text": s, "rects": curr, "x0": curr[0]["rect"][0], "x1": curr[-1]["rect"][2]})

    return lines


def montar_celula_html(
    lines: List[Dict[str, Any]],
    imgs: List[Dict[str, Any]],
    codigo_ficha: str,
    default_alt: str = "",
) -> str:
    """
    Monta o conteúdo interno de uma célula <td> ou bloco seguindo a ordem:
    Subtítulo (topo) -> <img ... /> -> Legenda / Texto explicativo (rodapé).
    """
    partes = []

    if imgs:
        img = imgs[0]
        y_img = img["yc"]
        top_lines = [l for l in lines if l["y"] > y_img]
        bottom_lines = [l for l in lines if l["y"] <= y_img]

        # 1. Linhas do topo (subtítulo)
        if top_lines:
            texto_top = unificar_linhas_e_hifens([l["text"] for l in top_lines])
            partes.append(f"<p><strong>{texto_top}</strong></p>")

        # 2. Imagem com atributo alt descritivo
        alt = default_alt or f"Ilustração da Ficha {codigo_ficha}"
        if top_lines:
            alt = top_lines[0]["text"]
        elif bottom_lines:
            alt = " - ".join(l["text"] for l in bottom_lines[:2])

        rel_path = img.get("rel_path", "")
        partes.append(f'<img src="{rel_path}" alt="{alt}" />')

        # 3. Linhas abaixo da imagem (legenda / parágrafo explicativo)
        if bottom_lines:
            if len(bottom_lines) > 2 and any(len(l["text"]) > 40 for l in bottom_lines):
                texto_bot = unificar_linhas_e_hifens([l["text"] for l in bottom_lines])
                partes.append(f"<p>{texto_bot}</p>")
            else:
                for l in bottom_lines:
                    partes.append(f"<p>{l['text']}</p>")
    else:
        # Sem imagem na célula
        if lines:
            if len(lines) > 2 and any(len(l["text"]) > 40 for l in lines):
                texto = unificar_linhas_e_hifens([l["text"] for l in lines])
                partes.append(f"<p>{texto}</p>")
            else:
                for l in lines:
                    partes.append(f"<p>{l['text']}</p>")

    return "\n".join(partes)


def extrair_imagens_pagina(page, y_top_limit: float, imagens_dir: Path, codigo_ficha: str, img_idx_inicial: int) -> Tuple[List[Dict[str, Any]], List[str], int]:
    page_imgs = []
    imagens_extraidas = []
    img_idx = img_idx_inicial

    for obj in page.get_objects():
        if getattr(obj, "type", None) == FPDF_PAGEOBJ_IMAGE:
            x0, y0, x1, y1 = obj.get_bounds()
            if (x1 - x0) >= MIN_IMG_SIZE and (y1 - y0) >= MIN_IMG_SIZE and y0 >= Y_MIN_IMAGE and y1 <= (y_top_limit + 15.0):
                img_nome = f"ficha{codigo_ficha}_{img_idx}.png"
                img_path = imagens_dir / img_nome
                rel_path = f"imagens/{img_nome}"

                try:
                    bm = obj.get_bitmap()
                    pil_img = bm.to_pil()
                    pil_img.save(img_path, "PNG")
                    logger.info(f"Imagem extraída: {img_path} ({pil_img.width}x{pil_img.height} px)")
                    imagens_extraidas.append(rel_path)
                    img_idx += 1
                    page_imgs.append({
                        "bounds": (x0, y0, x1, y1),
                        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                        "yc": (y0 + y1) / 2.0, "xc": (x0 + x1) / 2.0,
                        "rel_path": rel_path,
                        "width": x1 - x0,
                    })
                except Exception as e:
                    logger.warning(f"Erro ao salvar bitmap {img_nome}: {e}")

    return page_imgs, imagens_extraidas, img_idx

def coletar_retangulos_texto(tp, y_top_limit: float) -> List[Dict[str, Any]]:
    page_rects = []
    for i in range(tp.count_rects()):
        r = tp.get_rect(i)
        if r[3] <= y_top_limit and r[1] >= Y_MIN_IMAGE:
            txt = tp.get_text_bounded(*r).strip()
            if not txt:
                continue
            
            if RE_IC_HEADER.match(txt):
                continue
            if any(x in txt.upper() for x in ["CONSELHO NACIONAL", "MANUAL BRASILEIRO", "MBFT", "FICHA DE FISCALIZAÇÃO"]):
                continue

            yc = (r[1] + r[3]) / 2.0
            xc = (r[0] + r[2]) / 2.0
            page_rects.append({"rect": r, "yc": yc, "xc": xc, "txt": txt, "id": i})
    return page_rects

def detectar_secoes(page_rects: List[Dict[str, Any]], y_top_limit: float) -> Tuple[List[Tuple[str, float, float]], List[Dict[str, Any]]]:
    global_lines = agrupar_retangulos_em_linhas(page_rects)
    sections = []
    section_rect_ids = set()
    for gl in global_lines:
        if gl["x0"] < MARGEM_ESQUERDA_SECAO_NUMERADA and re.match(r"^\d+\.", gl["text"]):
            sections.append(gl)
            for r_item in gl["rects"]:
                section_rect_ids.add(r_item["id"])

    if not sections:
        sections = [{"y": y_top_limit, "text": "", "rects": [], "x0": 0.0}]

    internal_rects = [r for r in page_rects if r["id"] not in section_rect_ids]

    section_bounds = []
    if sections and sections[0]["text"] and (y_top_limit - sections[0]["y"] > 25.0):
        section_bounds.append(("", y_top_limit, sections[0]["y"]))

    for idx, s in enumerate(sections):
        yt = s["y"]
        yb = sections[idx + 1]["y"] if idx + 1 < len(sections) else Y_MIN_IMAGE
        section_bounds.append((s["text"], yt, yb))

    return section_bounds, internal_rects

def renderizar_secao(title: str, yt: float, yb: float, page_imgs: List[Dict[str, Any]], internal_rects: List[Dict[str, Any]], codigo_ficha: str) -> str:
    blocos = []
    sec_imgs = [img for img in page_imgs if yb <= img["yc"] <= yt]
    sec_rects = [r for r in internal_rects if yb <= r["yc"] <= yt]

    left_imgs = [img for img in sec_imgs if img["x1"] <= X_LEFT_COL_MAX]
    right_imgs = [img for img in sec_imgs if img["x0"] >= X_RIGHT_COL_MIN]
    wide_imgs = [img for img in sec_imgs if img not in left_imgs and img not in right_imgs]

    left_rects = [r for r in sec_rects if r["rect"][2] <= X_TEXT_LEFT_MAX]
    right_rects = [r for r in sec_rects if r["rect"][0] >= X_RIGHT_COL_MIN]

    left_lines = agrupar_retangulos_em_linhas(left_rects)
    right_lines = agrupar_retangulos_em_linhas(right_rects)

    if title:
        blocos.append(f"<p><strong>{title}</strong></p>")

    # Condição para 2 colunas:
    is_2col = (len(left_imgs) > 0 and len(right_imgs) > 0 and len(wide_imgs) == 0) or (
        len(left_imgs) == 0 and len(right_imgs) == 0 and len(wide_imgs) == 0
        and len(left_lines) > 0 and len(right_lines) > 0
        and abs(len(left_lines) - len(right_lines)) <= 4
    )

    if is_2col:
        td_left = montar_celula_html(left_lines, left_imgs, codigo_ficha=codigo_ficha)
        td_right = montar_celula_html(right_lines, right_imgs, codigo_ficha=codigo_ficha)
        tabela = (
            "<table>\n"
            "  <tr>\n"
            f"    <td>\n{td_left}\n    </td>\n"
            f"    <td>\n{td_right}\n    </td>\n"
            "  </tr>\n"
            "</table>"
        )
        blocos.append(tabela)
    else:
        # 1 coluna linear
        all_lines = agrupar_retangulos_em_linhas(sec_rects)
        conteudo = montar_celula_html(all_lines, sec_imgs, codigo_ficha=codigo_ficha)
        if conteudo:
            blocos.append(conteudo)
            
    return "\n\n".join(blocos)

def construir_html_informacoes_complementares(
    doc: pdfium.PdfDocument,
    codigo_ficha: str,
    pag_ini_ic: int,
    pag_fim: int,
    ic_y_bound: Optional[float],
    imagens_dir: Path,
    tabelas_docling: Optional[List[str]] = None,
) -> Tuple[str, List[str]]:
    """
    Processa geometricamente as seções de 'Informações Complementares' ao longo das páginas da ficha.
    Identifica ilustrações nativas, monta tabelas de 2 colunas quando cabível e parágrafos estruturados.
    """
    imagens_dir.mkdir(parents=True, exist_ok=True)
    imagens_extraidas_totais: List[str] = []
    blocos_html: List[str] = []
    img_idx = 1

    for p_no in range(pag_ini_ic - 1, pag_fim):
        page = doc[p_no]
        tp = page.get_textpage()
        w, h = page.get_size()
        y_top_limit = ic_y_bound if (p_no == pag_ini_ic - 1 and ic_y_bound is not None) else (h - Y_TOP_LIMIT_DEFAULT)

        page_imgs, novas_imagens, img_idx = extrair_imagens_pagina(page, y_top_limit, imagens_dir, codigo_ficha, img_idx)
        imagens_extraidas_totais.extend(novas_imagens)

        page_rects = coletar_retangulos_texto(tp, y_top_limit)

        if not page_rects and not page_imgs:
            continue

        section_bounds, internal_rects = detectar_secoes(page_rects, y_top_limit)

        for title, yt, yb in section_bounds:
            bloco_secao = renderizar_secao(title, yt, yb, page_imgs, internal_rects, codigo_ficha)
            if bloco_secao:
                blocos_html.append(bloco_secao)

    if tabelas_docling:
        for tab in tabelas_docling:
            blocos_html.append(tab)

    html_final = "\n\n".join(blocos_html).strip() if blocos_html else "<p>Não há.</p>"
    return html_final, imagens_extraidas_totais
