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
from .html_builder import formatar_tabela_html, construir_html_informacoes_complementares

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


def tem_tabela_em_ic(
    doc: pdfium.PdfDocument,
    pag_ini_ic: int,
    pag_fim: int,
    ic_y_bound: Optional[float],
) -> bool:
    """
    Verifica se a região de Informações Complementares contém linhas de grade de tabela
    (linhas horizontais E verticais vetoriais cruzadas).
    """
    for p_no in range(pag_ini_ic - 1, pag_fim):
        p = doc[p_no]
        max_y = ic_y_bound if (p_no == pag_ini_ic - 1) else None
        linhas_h = 0
        linhas_v = 0
        for obj in p.get_objects():
            if obj.type == 2:  # FPDF_PAGEOBJ_PATH
                b = obj.get_bounds()
                top = b[3]
                if max_y is not None and top > max_y:
                    continue
                w = b[2] - b[0]
                h = b[3] - b[1]
                if w > 80 and h < 4:
                    linhas_h += 1
                elif h > 20 and w < 4:
                    linhas_v += 1
        if linhas_h >= 3 and linhas_v >= 2:
            return True
    return False


def extrair_conteudo_ic(
    doc: pdfium.PdfDocument,
    converter: Any,
    pdf_path: Path,
    codigo_ficha: str,
    pag_ini_ic: int,
    pag_fim: int,
    ic_y_bound: Optional[float],
    imagens_dir: Path,
) -> Tuple[str, List[str]]:
    """
    Extrai textos, tabelas (Docling CUDA) e ilustrações (nativas em PNG) de Informações Complementares.
    """
    # 1. Extração seletiva de Tabelas Complexas via Docling (GPU CUDA sob demanda)
    tabelas_html: List[str] = []
    possui_tabela = tem_tabela_em_ic(doc, pag_ini_ic, pag_fim, ic_y_bound)

    if possui_tabela and converter and (pag_fim >= pag_ini_ic):
        try:
            actual_converter = converter() if callable(converter) else converter
            docling_doc = processar_intervalo_docling(actual_converter, pdf_path, pag_ini_ic, pag_fim)
            for item, lvl in docling_doc.iterate_items():
                if type(item).__name__ == "TableItem":
                    t_md = item.export_to_markdown(docling_doc)
                    if "inscrições previstas" not in t_md.lower() and "quando autuar" not in t_md.lower():
                        html_tabela = item.export_to_html(docling_doc)
                        tabelas_html.append(formatar_tabela_html(html_tabela))
        except Exception as e:
            logger.warning(f"Aviso na extração tabular Docling da ficha {codigo_ficha}: {e}")

    # 2. Constrói o HTML estruturado com tabelas de 2 colunas e posicionamento exato de imagens
    html_final, imagens = construir_html_informacoes_complementares(
        doc=doc,
        codigo_ficha=codigo_ficha,
        pag_ini_ic=pag_ini_ic,
        pag_fim=pag_fim,
        ic_y_bound=ic_y_bound,
        imagens_dir=imagens_dir,
        tabelas_docling=tabelas_html,
    )
    return html_final, imagens


def extrair_ficha_completa(
    doc: pdfium.PdfDocument,
    converter: Any,
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
        tipificacao_resumida=meta.get("tipificacao_resumida"),
        codigo_enquadramento=codigo,
        amparo_legal=meta.get("amparo_legal"),
        tipificacao_enquadramento=meta.get("tipificacao_enquadramento"),
        gravidade=meta.get("gravidade"),
        penalidade=meta.get("penalidade"),
        medida_administrativa=meta.get("medida_administrativa"),
        pode_configurar_crime_transito=meta.get("pode_configurar_crime_transito"),
        infrator=meta.get("infrator"),
        competencia=meta.get("competencia") or None,
        competencia_alterada_lei_14599=meta.get("competencia_alterada_lei_14599", False),
        pontuacao=meta.get("pontuacao"),
        constatacao_infracao=meta.get("constatacao_infracao"),
        quando_autuar=quando_autuar,
        quando_nao_autuar=quando_nao_autuar,
        definicoes_procedimentos=definicoes_procedimentos,
        exemplos_observacoes_ait=exemplos_observacoes_ait,
        informacoes_complementares=ic_html,
        paginas=list(range(pag_ini, pag_fim + 1)),
        imagens=imagens,
    )
