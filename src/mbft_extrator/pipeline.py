"""
Pipeline principal de orquestração da extração de fichas e persistência de checkpoints.
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

import pypdfium2 as pdfium
from docling.document_converter import DocumentConverter

from .models import Ficha, FichaMapeada, CampoNormativo
from .fatiador import mapear_fichas_no_pdf
from .stitching import (
    extrair_metadados_cabecalho,
    extrair_linhas_colunas_pagina,
    processar_coluna_normativa,
)
from .docling_extractor import criar_conversor_docling, processar_intervalo_docling
from .html_builder import recortar_imagem_300dpi, formatar_tabela_html

logger = logging.getLogger("MBFT-Pipeline")


def detectar_limites_ic(
    doc: pdfium.PdfDocument,
    pag_ini: int,
    pag_fim: int,
) -> Tuple[bool, int, Optional[float]]:
    """
    Localiza em qual página e em qual altura Y a seção 'Informações Complementares' se inicia.
    """
    for p_no in range(pag_ini - 1, pag_fim):
        page = doc[p_no]
        tp = page.get_textpage()
        for i in range(tp.count_rects()):
            r = tp.get_rect(i)
            # A linha de Informações Complementares é o cabeçalho largo que inicia na margem esquerda
            if r[0] < 60.0:
                txt = tp.get_text_bounded(*r).strip()
                if re.match(r"^informa[cç][oõ]es\s+complementares:?$", txt, re.IGNORECASE):
                    return True, p_no + 1, r[3]

    return False, pag_ini, None


def extrair_conteudo_ic(
    doc: pdfium.PdfDocument,
    converter: Optional[DocumentConverter],
    pdf_path: Path,
    codigo_ficha: str,
    pag_ini_ic: int,
    pag_fim: int,
    ic_y_bound: Optional[float],
    imagens_dir: Path,
) -> Tuple[str, List[str]]:
    """
    Extrai textos, tabelas (Docling CUDA) e ilustrações (300 DPI) de Informações Complementares.
    """
    imagens_extraidas: List[str] = []
    blocos_html: List[str] = []

    # 1. Extração do texto vetorial limpo de Informações Complementares
    textos_ic: List[str] = []
    tem_desenho_mencionado = False

    for p_no in range(pag_ini_ic - 1, pag_fim):
        page = doc[p_no]
        tp = page.get_textpage()
        w, h = page.get_size()
        y_limite_superior = ic_y_bound if (p_no == pag_ini_ic - 1 and ic_y_bound is not None) else h

        linhas_p: List[Tuple[float, str]] = []
        for i in range(tp.count_rects()):
            r = tp.get_rect(i)
            if r[3] <= y_limite_superior and r[1] >= 45.0:
                txt = tp.get_text_bounded(*r).strip()
                if not txt:
                    continue
                # Ignora o cabeçalho da própria seção
                if re.match(r"^informa[cç][oõ]es\s+complementares:?$", txt, re.IGNORECASE):
                    continue
                # Ignora cabeçalhos institucionais entre páginas
                if any(x in txt.upper() for x in ["CONSELHO NACIONAL", "MANUAL BRASILEIRO", "FICHA DE FISCALIZAÇÃO"]):
                    continue
                if re.search(r"desenho\s+ilustrativo|imagens\s+ilustrativas", txt, re.IGNORECASE):
                    tem_desenho_mencionado = True

                linhas_p.append((r[1], txt))

        if linhas_p:
            # Ordena de cima para baixo
            linhas_p.sort(key=lambda x: -x[0])
            for _, txt in linhas_p:
                textos_ic.append(txt)

    # Verifica se é vazio ou "Não há."
    texto_combinado = " ".join(textos_ic).strip()
    if not texto_combinado or texto_combinado.lower() in ["não há.", "não há", "nao ha.", "nao ha"]:
        return "<p>Não há.</p>", []

    # 2. Extração de Tabelas Complexas via Docling (com GPU CUDA)
    tabelas_html: List[str] = []
    if converter and (pag_fim >= pag_ini_ic):
        try:
            docling_doc = processar_intervalo_docling(converter, pdf_path, pag_ini_ic, pag_fim)
            for item, lvl in docling_doc.iterate_items():
                if type(item).__name__ == "TableItem":
                    # Verifica se a tabela não é o cabeçalho residual da página
                    t_md = item.export_to_markdown(docling_doc)
                    if "inscrições previstas" not in t_md.lower() and "quando autuar" not in t_md.lower():
                        html_tabela = item.export_to_html(docling_doc)
                        tabelas_html.append(formatar_tabela_html(html_tabela))
        except Exception as e:
            logger.warning(f"Aviso na extração tabular Docling da ficha {codigo_ficha}: {e}")

    # 3. Extração de Imagens e Ilustrações Nativas do PDF
    img_idx = 1
    for p_no in range(pag_ini_ic - 1, pag_fim):
        page = doc[p_no]
        w, h = page.get_size()
        y_superior = ic_y_bound if (p_no == pag_ini_ic - 1 and ic_y_bound is not None) else h

        for obj in page.get_objects():
            if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
                x0, y0, x1, y1 = obj.get_bounds()
                # Verifica se o objeto está dentro do espaço de Informações Complementares
                if y1 <= y_superior + 20.0 and y0 >= 30.0:
                    # Filtra artefatos minúsculos (pontos/linhas)
                    if (x1 - x0) >= 25.0 and (y1 - y0) >= 25.0:
                        img_nome = f"ficha{codigo_ficha}_{img_idx}.png"
                        img_caminho = imagens_dir / img_nome
                        caminho_rel = f"imagens/{img_nome}"

                        try:
                            bm = obj.get_bitmap()
                            pil_img = bm.to_pil()
                            pil_img.save(img_caminho, "PNG")
                            logger.info(f"Imagem nativa extraída com sucesso: {img_caminho} ({pil_img.width}x{pil_img.height} px)")
                            imagens_extraidas.append(caminho_rel)
                            img_idx += 1
                        except Exception as e:
                            logger.warning(f"Erro ao extrair bitmap da imagem {img_nome}: {e}")

    # 4. Montagem do HTML Semântico
    if textos_ic:
        # Agrupa itens em parágrafos ou listas
        linhas_formatadas = []
        for l in textos_ic:
            if re.match(r"^\d+\.", l):
                linhas_formatadas.append(f"<p><strong>{l}</strong></p>")
            else:
                linhas_formatadas.append(f"<p>{l}</p>")
        blocos_html.append("\n".join(linhas_formatadas))

    if tabelas_html:
        for tab in tabelas_html:
            blocos_html.append(tab)

    if imagens_extraidas:
        for img_rel in imagens_extraidas:
            blocos_html.append(f'<p><img src="{img_rel}" alt="Ilustração da Ficha {codigo_ficha}" /></p>')

    html_final = "\n\n".join(blocos_html).strip() if blocos_html else "<p>Não há.</p>"
    return html_final, imagens_extraidas


def extrair_ficha_completa(
    doc: pdfium.PdfDocument,
    converter: Optional[DocumentConverter],
    pdf_path: Path,
    mapeada: FichaMapeada,
    imagens_dir: Path,
) -> Ficha:
    """
    Processa e extrai todos os campos estruturados de uma ficha de fiscalização.
    """
    codigo = mapeada.codigo
    pag_ini = mapeada.pag_ini
    pag_fim = mapeada.pag_fim

    # 1. Metadados do cabeçalho na primeira página
    page1 = doc[pag_ini - 1]
    meta = extrair_metadados_cabecalho(page1, codigo_padrao=codigo)

    # 2. Localiza limites de Informações Complementares
    has_ic, ic_start_page, ic_y_bound = detectar_limites_ic(doc, pag_ini, pag_fim)
    col_end_page = ic_start_page if has_ic else pag_fim

    # 3. Costura geométrica das 4 colunas normativas
    all_col_lines: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}
    for p in range(pag_ini - 1, col_end_page):
        is_first = (p == pag_ini - 1)
        cols_p, _ = extrair_linhas_colunas_pagina(doc[p], is_first_page=is_first)
        for c in range(4):
            all_col_lines[c].extend(cols_p[c])

    quando_autuar = processar_coluna_normativa(all_col_lines[0])
    quando_nao_autuar = processar_coluna_normativa(all_col_lines[1])
    definicoes_procedimentos = processar_coluna_normativa(all_col_lines[2])
    exemplos_observacoes_ait = processar_coluna_normativa(all_col_lines[3])

    # 4. Informações Complementares e Imagens
    if not has_ic:
        ic_html = "<p>Não há.</p>"
        imagens: List[str] = []
    else:
        ic_html, imagens = extrair_conteudo_ic(
            doc=doc,
            converter=converter,
            pdf_path=pdf_path,
            codigo_ficha=codigo,
            pag_ini_ic=ic_start_page,
            pag_fim=pag_fim,
            ic_y_bound=ic_y_bound,
            imagens_dir=imagens_dir,
        )

    return Ficha(
        id=codigo,
        tipificacao_resumida=meta.get("tipificacao_resumida", ""),
        codigo_enquadramento=codigo,
        amparo_legal=meta.get("amparo_legal", ""),
        tipificacao_enquadramento=meta.get("tipificacao_enquadramento", ""),
        gravidade=meta.get("gravidade", ""),
        penalidade=meta.get("penalidade", ""),
        medida_administrativa=meta.get("medida_administrativa", ""),
        pode_configurar_crime_transito=meta.get("pode_configurar_crime_transito", "NÃO"),
        infrator=meta.get("infrator", ""),
        competencia=meta.get("competencia", ""),
        pontuacao=meta.get("pontuacao", ""),
        constatacao_infracao=meta.get("constatacao_infracao", ""),
        quando_autuar=quando_autuar,
        quando_nao_autuar=quando_nao_autuar,
        definicoes_procedimentos=definicoes_procedimentos,
        exemplos_observacoes_ait=exemplos_observacoes_ait,
        informacoes_complementares=ic_html,
        paginas=list(range(pag_ini, pag_fim + 1)),
        imagens=imagens,
    )
