"""
Pipeline principal de orquestração da extração de fichas e persistência de checkpoints.
"""

import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

import pypdfium2 as pdfium
from docling.document_converter import DocumentConverter

from .models import Ficha, FichaMapeada, CampoNormativo
from .stitching import (
    extrair_metadados_cabecalho,
    extrair_linhas_colunas_pagina,
    processar_coluna_normativa,
    MetadadosCabecalho,
)
from .docling_extractor import processar_intervalo_docling, extrair_metadados_visuais
from .html_builder import formatar_tabela_html, construir_html_informacoes_complementares
from .pdf_geometry import RE_IC_HEADER, linhas_vetoriais, MARGEM_ESQUERDA_TITULO
from .auditoria import CorrecaoOcr
from .validators import detectar_anomalia_cabecalho

logger = logging.getLogger("MBFT-Pipeline")

@dataclass
class Conversores:
    _padrao: Optional[DocumentConverter] = None
    _ocr: Optional[DocumentConverter] = None

    @property
    def padrao(self) -> DocumentConverter:
        if self._padrao is None:
            from .docling_extractor import criar_conversor_docling
            self._padrao = criar_conversor_docling()
        return self._padrao

    @property
    def ocr(self) -> DocumentConverter:
        if self._ocr is None:
            from .docling_extractor import criar_conversor_docling_ocr
            self._ocr = criar_conversor_docling_ocr()
        return self._ocr

@dataclass(frozen=True)
class ResultadoExtracao:
    ficha: Ficha
    correcoes_ocr: List[CorrecaoOcr]


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
            if r[0] < MARGEM_ESQUERDA_TITULO:
                txt = tp.get_text_bounded(*r).strip()
                if RE_IC_HEADER.match(txt):
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
        paths = linhas_vetoriais(p)
        for b in paths:
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
    converter: Optional[DocumentConverter],
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
            docling_doc = processar_intervalo_docling(converter, pdf_path, pag_ini_ic, pag_fim)
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


def _extrair_metadados(
    doc: pdfium.PdfDocument, 
    mapeada: FichaMapeada, 
    conversores: Conversores, 
    pdf_path: Path, 
    correcoes: List[CorrecaoOcr]
) -> MetadadosCabecalho:
    page1 = doc[mapeada.pag_ini - 1]
    meta = extrair_metadados_cabecalho(page1, codigo_padrao=mapeada.codigo)
    anomalias = detectar_anomalia_cabecalho(meta)
    
    if anomalias:
        logger.warning(f"Ficha {mapeada.codigo} apresentou anomalias {anomalias}. Acionando OCR...")
        meta_visual = extrair_metadados_visuais(conversores.ocr, pdf_path, mapeada.pag_ini)
        
        for campo in anomalias:
            valor_novo = meta_visual.get(campo)
            if valor_novo:
                if campo == "infrator":
                    valor_antigo = meta.infrator
                    meta.infrator = valor_novo
                elif campo == "constatacao_infracao":
                    valor_antigo = meta.constatacao_infracao
                    meta.constatacao_infracao = valor_novo
                else:
                    continue
                correcoes.append(CorrecaoOcr(ficha=mapeada.codigo, campo=campo, antigo=str(valor_antigo or ""), novo=valor_novo))
    
    return meta

@dataclass(frozen=True)
class ColunasNormativas:
    quando_autuar: CampoNormativo
    quando_nao_autuar: CampoNormativo
    definicoes_procedimentos: CampoNormativo
    exemplos_observacoes_ait: CampoNormativo

def _extrair_colunas_normativas(
    doc: pdfium.PdfDocument,
    mapeada: FichaMapeada,
    col_end_page: int
) -> ColunasNormativas:
    all_col_lines: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}
    for p in range(mapeada.pag_ini - 1, col_end_page):
        is_first = (p == mapeada.pag_ini - 1)
        cols_p, _ = extrair_linhas_colunas_pagina(doc[p], is_first_page=is_first)
        for c in range(4):
            all_col_lines[c].extend(cols_p[c])

    quando_autuar = processar_coluna_normativa(all_col_lines[0])
    quando_nao_autuar = processar_coluna_normativa(all_col_lines[1])
    definicoes_procedimentos = processar_coluna_normativa(all_col_lines[2])
    exemplos_observacoes_ait = processar_coluna_normativa(all_col_lines[3])
    
    return ColunasNormativas(
        quando_autuar=quando_autuar,
        quando_nao_autuar=quando_nao_autuar,
        definicoes_procedimentos=definicoes_procedimentos,
        exemplos_observacoes_ait=exemplos_observacoes_ait,
    )

def _montar_ficha(
    meta: MetadadosCabecalho,
    colunas: ColunasNormativas,
    ic_html: str,
    imagens: List[str],
    mapeada: FichaMapeada
) -> Ficha:
    return Ficha(
        id=mapeada.codigo,
        tipificacao_resumida=meta.tipificacao_resumida or "",
        codigo_enquadramento=meta.codigo_enquadramento,
        amparo_legal=meta.amparo_legal or "",
        tipificacao_enquadramento=meta.tipificacao_enquadramento or "",
        gravidade=meta.gravidade or "",
        penalidade=meta.penalidade or "",
        medida_administrativa=meta.medida_administrativa or "",
        pode_configurar_crime_transito=meta.pode_configurar_crime_transito,
        infrator=meta.infrator or "",
        competencia=meta.competencia,
        competencia_alterada_lei_14599=meta.competencia_alterada_lei_14599,
        pontuacao=meta.pontuacao or "",
        constatacao_infracao=meta.constatacao_infracao or "",
        quando_autuar=colunas.quando_autuar,
        quando_nao_autuar=colunas.quando_nao_autuar,
        definicoes_procedimentos=colunas.definicoes_procedimentos,
        exemplos_observacoes_ait=colunas.exemplos_observacoes_ait,
        informacoes_complementares=ic_html,
        paginas=list(range(mapeada.pag_ini, mapeada.pag_fim + 1)),
        imagens=imagens,
    )

def extrair_ficha_completa(
    doc: pdfium.PdfDocument,
    conversores: Conversores,
    pdf_path: Path,
    mapeada: FichaMapeada,
    imagens_dir: Path,
) -> ResultadoExtracao:
    """
    Processa e extrai todos os campos estruturados de uma ficha de fiscalização.
    """
    correcoes = []

    # 1. Metadados do cabeçalho na primeira página
    meta = _extrair_metadados(doc, mapeada, conversores, pdf_path, correcoes)

    # 2. Localiza limites de Informações Complementares
    has_ic, ic_start_page, ic_y_bound = detectar_limites_ic(doc, mapeada.pag_ini, mapeada.pag_fim)
    col_end_page = ic_start_page if has_ic else mapeada.pag_fim

    # 3. Costura geométrica das 4 colunas normativas
    colunas = _extrair_colunas_normativas(doc, mapeada, col_end_page)

    # 4. Informações Complementares e Imagens
    if not has_ic:
        ic_html = "<p>Não há.</p>"
        imagens: List[str] = []
    else:
        ic_html, imagens = extrair_conteudo_ic(
            doc=doc,
            converter=conversores.padrao,
            pdf_path=pdf_path,
            codigo_ficha=mapeada.codigo,
            pag_ini_ic=ic_start_page,
            pag_fim=mapeada.pag_fim,
            ic_y_bound=ic_y_bound,
            imagens_dir=imagens_dir,
        )

    ficha = _montar_ficha(meta, colunas, ic_html, imagens, mapeada)
    return ResultadoExtracao(ficha=ficha, correcoes_ocr=correcoes)
