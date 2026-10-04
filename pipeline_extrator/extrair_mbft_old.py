#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=============================================================================
Extrator e Fatiador do Manual Brasileiro de Fiscalização de Trânsito (MBFT)
=============================================================================

Este script analisa, extrai e fatia o conteúdo do ficheiro PDF "mbvt20222.pdf"
(MBFT - Resolução CONTRAN nº 985/2022 e atualizações), convertendo-o para
Markdown estruturado de alta fidelidade com a biblioteca Docling e
pós-processamento determinístico com pypdfium2.

Arquitetura e Soluções Implementadas:
------------------------------------
1. Extração Direta de Metadados via Regex Vetorial (pypdfium2 / Texto Nativo):
   - Os metadados da ficha (Amparo Legal, Infrator, Competência, Pontuação,
     Medida Administrativa, Crime de Trânsito, etc.) são extraídos diretamente
     do texto vetorial da primeira página de cada ficha.
   - Elimina a contaminação e a mistura em grelha tabular, gerando no topo
     de cada ficha uma lista chave-valor limpa e padronizada.

2. Costura e Deslocamento de Células Particionadas (Pagination Stitching):
   - As colunas normativas paralelas ("Quando Autuar", "Quando NÃO Autuar",
     "Definições e Procedimentos", "Exemplos do Campo de Observações do AIT")
     são mapeadas geometricamente em 4 canais de coordenadas.
   - Costura contínua entre páginas consecutivas: blocos de uma mesma coluna
     são concatenados entre quebras de página, recompondo itens divididos ao
     meio (ex.: subitens de 12.1 a 12.9, prazos e idades) e normalizando quebras
     duras de linha dentro dos parágrafos.
   - Cada coluna é serializada diretamente como seção Markdown (##) com listas
     ordenadas íntegras (1., 2.), eliminando tabelas de texto denso.

3. Serialização Semântica e Preservação de Matrizes Reais (Docling):
   - Tabelas Markdown são reservadas exclusivamente para matrizes genuínas de
     dados em "Informações Complementares" (ex.: tabelas de cinto de segurança).
   - O Docling processa o modelo de objetos de documento (iterate_items e
     TableItem) mantendo a integridade estrutural das matrizes técnicas.

4. Fatiamento Preciso das 404 Fichas:
   - Mapeamento vetorial exato dos limites de cada ficha através do campo
     "Código do Enquadramento: <código>".
   - Gravação individual em 'fichas_extraidas/ficha_<codigo>.md' e consolidação
     em 'mbft_completo.md' para auditoria completa.
"""

import os
import re
import sys
import time
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

# Bibliotecas de análise e conversão
import pypdfium2 as pdfium
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
    AcceleratorOptions,
)
from docling.datamodel.base_models import InputFormat

# Configuração de Logging com formato legível
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MBFT-Extractor")


# =============================================================================
# 1. PIPELINE DOCLING (LAYOUT & TABELAS GENUÍNAS)
# =============================================================================
def criar_pipeline_docling(
    num_threads: int = 8,
    do_cell_matching: bool = True,
    table_mode: TableFormerMode = TableFormerMode.ACCURATE,
) -> DocumentConverter:
    """
    Inicializa o DocumentConverter do Docling otimizado para extração de matrizes
    genuínas de dados no MBFT.
    """
    logger.info("A inicializar pipeline do Docling (TableFormer ACCURATE)...")

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = table_mode
    pipeline_options.table_structure_options.do_cell_matching = do_cell_matching

    # Otimização de threads de CPU / GPU
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=num_threads,
        device="auto",
    )

    # Desativação de imagens intermediárias para manter baixo consumo de memória
    pipeline_options.generate_page_images = False
    pipeline_options.generate_picture_images = False
    pipeline_options.generate_table_images = False

    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }

    return DocumentConverter(format_options=format_options)


# =============================================================================
# 2. FILTRO DE LIMPEZA DE CABEÇALHOS E RUÍDOS DE PÁGINA
# =============================================================================
def limpar_ruido_cabecalhos(texto_md: str) -> str:
    """
    Elimina cabeçalhos governamentais repetitivos e rodapés institucionais
    que quebram a fluidez de leitura do documento entre páginas.
    """
    # 1. Remove marcadores de imagem
    limpo = re.sub(r"<!--\s*image\s*-->", "", texto_md)

    # 2. Remove linhas do CONTRAN
    limpo = re.sub(
        r"^\s*#+\s*CONSELHO\s+NACIONAL\s+DE\s+TR[AÂ]NSITO.*$",
        "",
        limpo,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # 3. Remove cabeçalho do MBFT
    limpo = re.sub(
        r"^\s*#+\s*MANUAL\s+BRASILEIRO\s+DE\s+FISCALIZA[CÇ][AÃ]O\s+DE\s+TR[AÂ]NSITO\s*[-–]?\s*MBFT.*$",
        "",
        limpo,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # 4. Remove o subtítulo repetitivo 'FICHA DE FISCALIZAÇÃO'
    limpo = re.sub(
        r"^\s*#+\s*FICHA\s+DE\s+FISCALIZA[CÇ][AÃ]O.*$",
        "",
        limpo,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # 5. Normaliza quebras de linha múltiplas residuais
    limpo = re.sub(r"\n{3,}", "\n\n", limpo)

    return limpo.strip()


# =============================================================================
# 3. MAPEAMENTO ESTRUTURAL DAS FICHAS NO PDF
# =============================================================================
REGEX_ENQUADRAMENTO = re.compile(
    r"c[oó]digo\s+d?o?\s*enquadramento:?\s*([0-9]{3}-[0-9]{1,2})",
    re.IGNORECASE,
)


def mapear_fichas_no_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Varre a estrutura vetorial do PDF com pypdfium2 e identifica o intervalo
    exato de páginas (pag_ini até pag_fim) de cada ficha.
    """
    logger.info("A mapear intervalos de páginas das fichas no PDF...")
    doc = pdfium.PdfDocument(str(pdf_path))
    total_pags = len(doc)

    fichas_mapeadas = []
    ocorrencias_codigo: Dict[str, int] = {}

    for i in range(total_pags):
        texto_pag = doc[i].get_textpage().get_text_range()
        match = REGEX_ENQUADRAMENTO.search(texto_pag)
        if match:
            codigo = match.group(1)
            fichas_mapeadas.append({
                "codigo": codigo,
                "pag_ini": i + 1,  # 1-indexed para uso no Docling
            })

    doc.close()

    # Define o fim de cada ficha como a página anterior ao início da próxima
    for i in range(len(fichas_mapeadas)):
        if i + 1 < len(fichas_mapeadas):
            fichas_mapeadas[i]["pag_fim"] = fichas_mapeadas[i + 1]["pag_ini"] - 1
        else:
            fichas_mapeadas[i]["pag_fim"] = total_pags

        # Trata possíveis códigos repetidos no PDF oficial (ex.: 542-81)
        cod = fichas_mapeadas[i]["codigo"]
        ocorrencias_codigo[cod] = ocorrencias_codigo.get(cod, 0) + 1
        if ocorrencias_codigo[cod] > 1:
            fichas_mapeadas[i]["identificador"] = f"{cod}_parte{ocorrencias_codigo[cod]}"
        else:
            fichas_mapeadas[i]["identificador"] = cod

    logger.info(f"Mapeamento concluído: {len(fichas_mapeadas)} fichas localizadas no PDF.")
    return fichas_mapeadas


# =============================================================================
# 4. EXTRAÇÃO DIRETA DE METADADOS VIA REGEX VETORIAL (PYPDFIUM2)
# =============================================================================
METADATA_FIELDS = [
    ("Tipificação Resumida", r"\bTipifica[cç][aã]o\s+Resumida\s*:"),
    ("Código do Enquadramento", r"\bC[oó]digo\s+(?:d?o?\s*)?Enquadramento\s*:"),
    ("Amparo Legal", r"\bAmparo\s+Legal\s*:"),
    ("Tipificação do Enquadramento", r"\bTipifica[cç][aã]o\s+do\s+Enquadramento\s*:"),
    ("Gravidade", r"\bGravidade\s*:"),
    ("Penalidade", r"\bPenalidade\s*:"),
    ("Medida Administrativa", r"\bMedida\s+Administrativa\s*:"),
    ("Pode Configurar Crime de Trânsito", r"\bPode\s+Configurar\s+(?:Crime\s+de\s+Tr[aâ]nsito|Infra[cç][aã]o\s+Penal)\s*:?"),
    ("Infrator", r"\bInfrator\s*:"),
    ("Competência", r"\bCompet[eê]ncia\s*:"),
    ("Pontuação", r"\bPontua[cç][aã]o\s*:"),
    ("Constatação da Infração", r"\bConstata[cç][aã]o\s+da\s+Infra[cç][aã]o\s*:"),
]


def extrair_metadados_ficha(page: pdfium.PdfPage, codigo_padrao: str = "") -> Dict[str, str]:
    """
    Extrai deterministamente os metadados do cabeçalho da ficha a partir do texto
    nativo da primeira página com pypdfium2 e expressões regulares posicionais.
    """
    txt_page = page.get_textpage().get_text_range()

    # Delimita o cabeçalho até o início das 4 colunas ("Quando Autuar")
    m_qa = re.search(r"quando\s+autuar", txt_page, re.IGNORECASE)
    header_txt = txt_page[:m_qa.start()] if m_qa else txt_page[:1500]

    # Remove ruídos de cabeçalho institucional se presentes no topo
    header_txt = re.sub(
        r"CONSELHO\s+NACIONAL\s+DE\s+TR[AÂ]NSITO.*|MANUAL\s+BRASILEIRO\s+DE\s+FISCALIZA[CÇ][AÃ]O.*|FICHA\s+DE\s+FISCALIZA[CÇ][AÃ]O.*",
        "",
        header_txt,
        flags=re.IGNORECASE,
    )

    positions = []
    for label, pat in METADATA_FIELDS:
        m = re.search(pat, header_txt, re.IGNORECASE)
        if m:
            positions.append((m.start(), m.end(), label))

    positions.sort(key=lambda x: x[0])

    meta: Dict[str, str] = {label: "" for label, _ in METADATA_FIELDS}
    for i, (start, end, label) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(header_txt)
        val = header_txt[end:next_start]
        val = re.sub(r"[\r\n]+", " ", val)
        val = re.sub(r"\s+", " ", val).strip()
        meta[label] = val

    # Normalizações determinísticas:
    # 1. Caso onde Crime ficou vazio porque Infrator apareceu antes no fluxo de texto
    infrator = meta.get("Infrator", "")
    crime = meta.get("Pode Configurar Crime de Trânsito", "")
    if not crime:
        m_sim_nao = re.match(r"^(N[ÃA]O|SIM)\s*(.*)$", infrator, re.IGNORECASE)
        if m_sim_nao:
            crime = m_sim_nao.group(1).upper()
            infrator = m_sim_nao.group(2).strip()

    # 2. Vazamento de Artigo de Trânsito do Crime para o campo Infrator (ex: Art. 309 do CTB Condutor)
    m_art = re.search(r"((?:Art\.?\s*)?\d{3}(?:\s*-[A-Za-z]+)?\s*do\s*CTB)", infrator, re.IGNORECASE)
    if m_art:
        artigo = m_art.group(1).strip()
        if not artigo.lower().startswith("art"):
            artigo = "Art. " + artigo
        infrator = infrator.replace(m_art.group(0), "").strip()
        if artigo not in crime:
            crime = f"{crime} {artigo}".strip()

    # 3. Código do Enquadramento padronizado no formato XXX-XX
    cod = meta.get("Código do Enquadramento", "")
    m_cod = re.search(r"([0-9]{3}\s*-\s*[0-9]{1,2})", cod)
    if m_cod:
        meta["Código do Enquadramento"] = re.sub(r"\s+", "", m_cod.group(1))
    elif codigo_padrao:
        meta["Código do Enquadramento"] = codigo_padrao

    # 4. Default de Crime se não especificado no PDF oficial (ex.: Ficha 638-60)
    if not crime:
        crime = "NÃO"

    meta["Infrator"] = infrator
    meta["Pode Configurar Crime de Trânsito"] = crime

    return meta


# =============================================================================
# 5. EXTRAÇÃO E COSTURA DE COLUNAS PARALELAS (PAGINATION STITCHING)
# =============================================================================
def _join_line_fragments(frags: List[Tuple[float, float, str]]) -> str:
    """
    Junta fragmentos de texto na mesma linha horizontal. Se o intervalo entre
    o fim de um fragmento e o início do próximo for menor que 2.5pt, junta sem espaço.
    """
    if not frags:
        return ""
    res = [frags[0][2]]
    for i in range(1, len(frags)):
        prev_x1 = frags[i - 1][1]
        curr_x0 = frags[i][0]
        curr_txt = frags[i][2]
        gap = curr_x0 - prev_x1
        if gap < 2.5 and not res[-1].endswith(" ") and not curr_txt.startswith(" "):
            res.append(curr_txt)
        else:
            res.append(" " + curr_txt)
    joined = "".join(res)
    # Corrige quebras no meio de códigos enquadramento como "502 - 91" -> "502-91"
    joined = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1-\2", joined)
    return re.sub(r"\s+", " ", joined).strip()


def extrair_linhas_colunas_pagina(page: pdfium.PdfPage, is_first_page: bool) -> Dict[int, List[str]]:
    """
    Extrai as linhas de texto distribuídas nos 4 canais de colunas do MBFT.
    """
    tp = page.get_textpage()
    num_rects = tp.count_rects()
    w, h = page.get_size()

    y_top = h
    y_bottom = 0.0

    # Localiza início de Informações Complementares nesta página
    for i in range(num_rects):
        r = tp.get_rect(i)
        txt = tp.get_text_bounded(*r).strip()
        if re.search(r"informa[cç][oõ]es\s+complementares", txt, re.IGNORECASE):
            y_bottom = max(y_bottom, r[3])

    # Na primeira página, localiza a linha dos títulos das colunas ("Quando Autuar")
    if is_first_page:
        for i in range(num_rects):
            r = tp.get_rect(i)
            txt = tp.get_text_bounded(*r).strip()
            if re.search(r"quando\s+autuar", txt, re.IGNORECASE):
                y_top = min(y_top, r[1])

    # Canais de colunas padrão MBFT:
    # 0: Quando Autuar             (x < 165)
    # 1: Quando NÃO Autuar         (165 <= x < 298)
    # 2: Definições e Procedimentos (298 <= x < 433)
    # 3: Observações do AIT        (433 <= x)
    def col_channel(x0: float, x1: float) -> int:
        xc = (x0 + x1) / 2
        if xc < 165:
            return 0
        elif xc < 298:
            return 1
        elif xc < 433:
            return 2
        else:
            return 3

    page_boxes: Dict[int, List[Tuple[Tuple[float, float, float, float], str]]] = {0: [], 1: [], 2: [], 3: []}
    for i in range(num_rects):
        r = tp.get_rect(i)  # (x0, y0, x1, y1)
        # Ignora cabeçalhos institucionais
        if is_first_page and r[1] > 715:
            continue
        if r[1] >= y_bottom and r[3] <= y_top:
            txt = tp.get_text_bounded(*r).strip()
            if not txt:
                continue
            # Ignora cabeçalhos de coluna residuais
            if re.search(
                r"^(?:quando\s+autuar|quando\s+n[ãa]o\s+autuar|defini[cç][oõ]es\s+e\s+procedimentos|exemplos\s+do\s+campo.*):?$",
                txt,
                re.IGNORECASE,
            ):
                continue
            ch = col_channel(r[0], r[2])
            page_boxes[ch].append((r, txt))

    # Para cada coluna, agrupa retângulos em linhas horizontais por proximidade de Y
    cols_lines: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}
    for ch in range(4):
        boxes = page_boxes[ch]
        if not boxes:
            continue

        b_yc = [(b[0], (b[0][1] + b[0][3]) / 2, b[1]) for b in boxes]
        b_yc.sort(key=lambda item: -item[1])

        lines = []
        curr_line: List[Tuple[float, float, str]] = []
        curr_y: Optional[float] = None
        for r, yc, txt in b_yc:
            if curr_y is None or abs(yc - curr_y) <= 3.2:
                curr_line.append((r[0], r[2], txt))
                curr_y = yc if len(curr_line) == 1 else (curr_y + yc) / 2
            else:
                curr_line.sort(key=lambda x: x[0])
                line_str = _join_line_fragments(curr_line)
                if line_str:
                    lines.append(line_str)
                curr_line = [(r[0], r[2], txt)]
                curr_y = yc
        if curr_line:
            curr_line.sort(key=lambda x: x[0])
            line_str = _join_line_fragments(curr_line)
            if line_str:
                lines.append(line_str)

        cols_lines[ch] = lines

    return cols_lines


def formatar_coluna_markdown(lines: List[str]) -> str:
    """
    Costura as linhas de uma coluna formando uma lista numerada íntegra.
    Elimina quebras duras de linha e recompõe frases partidas entre páginas.
    """
    if not lines:
        return "Não há.\n"

    itens: List[str] = []

    re_item_num = re.compile(r"^(\d{1,3})\.\s*(.*)$")
    re_subitem_num = re.compile(r"^(\d{1,3}\.\d{1,2})\.?\s*(.*)$")
    re_bullet = re.compile(r"^[-•*]\s*(.*)$")
    re_letra = re.compile(r"^([a-z]\))\s*(.*)$")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        m_sub = re_subitem_num.match(line)
        m_num = re_item_num.match(line)
        m_let = re_letra.match(line)
        m_bul = re_bullet.match(line)

        if m_sub:
            num = m_sub.group(1)
            resto = m_sub.group(2)
            itens.append(f"{num}. {resto}".strip())
        elif m_num:
            num = m_num.group(1)
            resto = m_num.group(2)
            itens.append(f"{num}. {resto}".strip())
        elif m_let:
            let = m_let.group(1)
            resto = m_let.group(2)
            itens.append(f"- {let} {resto}".strip())
        elif m_bul:
            resto = m_bul.group(1)
            itens.append(f"- {resto}".strip())
        else:
            # Continuação direta do item ou frase anterior (Costura entre quebras)
            if itens:
                prev = itens[-1]
                if prev.endswith("-") and not prev.endswith(" -"):
                    itens[-1] = prev[:-1] + line
                else:
                    itens[-1] = prev + " " + line
            else:
                itens.append(line)

    return "\n\n".join(itens) + "\n"


# =============================================================================
# 6. EXTRAÇÃO DE INFORMAÇÕES COMPLEMENTARES E TABELAS REAIS (DOCLING)
# =============================================================================
def detectar_informacoes_complementares(
    pdf_doc: pdfium.PdfDocument,
    pag_ini: int,
    pag_fim: int,
) -> Tuple[bool, int]:
    """
    Verifica no texto vetorial se há conteúdo em Informações Complementares
    além do tradicional 'Não há.', e retorna a página onde a seção começa.
    """
    parts = []
    found = False
    ic_start_page = pag_ini

    for p_no in range(pag_ini - 1, pag_fim):
        txt = pdf_doc[p_no].get_textpage().get_text_range()
        m = re.search(r"informa[cç][oõ]es\s+complementares:?", txt, re.IGNORECASE)
        if m:
            if not found:
                found = True
                ic_start_page = p_no + 1
            parts.append(txt[m.end():].strip())
        elif found:
            parts.append(txt.strip())

    comb = " ".join(parts).strip()
    comb = re.sub(
        r"CONSELHO\s+NACIONAL.*|MANUAL\s+BRASILEIRO.*|FICHA\s+DE\s+FISCALIZA[CÇ][AÃ]O.*",
        "",
        comb,
        flags=re.IGNORECASE,
    )
    comb = re.sub(r"\s+", " ", comb).strip()

    has_content = not (not comb or comb.lower() in ["não há.", "não há", "nao ha.", "nao ha"])
    return has_content, ic_start_page


def extrair_informacoes_complementares(
    docling_doc,
    pag_ini: int,
    pag_fim: int,
) -> str:
    """
    Extrai a seção 'Informações Complementares' preservando matrizes tabulares genuínas
    através do modelo Docling, sem misturar com as colunas normativas paralelas.
    """
    items = list(docling_doc.iterate_items())
    ic_start_idx = None

    for i, (item, lvl) in enumerate(items):
        txt = getattr(item, "text", "")
        if re.search(r"informa[cç][oõ]es\s+complementares", txt, re.IGNORECASE):
            ic_start_idx = i
            break
        if hasattr(item, "data") and item.data.grid:
            for row in item.data.grid:
                for c in row:
                    if re.search(r"informa[cç][oõ]es\s+complementares", c.text, re.IGNORECASE):
                        ic_start_idx = i
                        break
                if ic_start_idx is not None:
                    break
            if ic_start_idx is not None:
                break

    if ic_start_idx is None:
        return "## Informações Complementares\n\nNão há.\n"

    ic_parts: List[str] = []
    for i in range(ic_start_idx, len(items)):
        item, lvl = items[i]
        t_type = type(item).__name__

        if "Picture" in t_type:
            continue

        txt = getattr(item, "text", "")
        # Remove cabeçalhos institucionais entre páginas
        if any(h in txt for h in ["CONSELHO NACIONAL", "MANUAL BRASILEIRO", "MBFT", "FICHA DE FISCALIZAÇÃO"]):
            continue
        if re.search(r"c[oó]digo\s+(?:d?o?\s*)?enquadramento:?\s*[0-9]{3}-[0-9]{1,2}", txt, re.IGNORECASE):
            continue

        if hasattr(item, "data"):
            # É uma tabela
            t_md = item.export_to_markdown(docling_doc).strip()
            # Se for uma pseudotabela residual contendo apenas "Não há."
            if "Não há" in t_md and len(t_md.split("\n")) <= 4 and item.data.num_cols == 1:
                ic_parts.append("Não há.")
            else:
                ic_parts.append(t_md)
        else:
            if hasattr(item, "export_to_markdown"):
                part_md = item.export_to_markdown(docling_doc).strip()
            else:
                part_md = txt.strip()
            if part_md:
                if re.match(r"^#*\s*informa[cç][oõ]es\s+complementares:?$", part_md, re.IGNORECASE):
                    continue
                ic_parts.append(part_md)

    resultado_ic = "\n\n".join(ic_parts).strip()
    if not resultado_ic or resultado_ic == "Não há." or ("não há" in resultado_ic.lower() and len(resultado_ic) < 20):
        return "## Informações Complementares\n\nNão há.\n"
    else:
        return f"## Informações Complementares\n\n{resultado_ic}\n"


# =============================================================================
# 7. GERAÇÃO DO MARKDOWN FINAL DA FICHA
# =============================================================================
def gerar_markdown_ficha(
    pdf_doc: pdfium.PdfDocument,
    converter: DocumentConverter,
    pdf_path: Path,
    ficha_info: Dict[str, Any],
) -> str:
    """
    Gera o Markdown completo, estruturado e normalizado de uma ficha:
    1. Metadados limpos em lista chave-valor.
    2. Seções ## para cada coluna normativa com listas ordenadas íntegras.
    3. Informações Complementares com tabelas reais preservadas via Docling.
    """
    codigo = ficha_info["codigo"]
    pag_ini = ficha_info["pag_ini"]
    pag_fim = ficha_info["pag_fim"]

    # 1. Metadados na primeira página
    page1 = pdf_doc[pag_ini - 1]
    meta = extrair_metadados_ficha(page1, codigo_padrao=codigo)

    bloco_metadados = [
        f"# FICHA DE FISCALIZAÇÃO - CÓDIGO {codigo}",
        f"<!-- Páginas no MBFT: {pag_ini} a {pag_fim} -->\n",
    ]
    for chave, _ in METADATA_FIELDS:
        val = meta.get(chave, "")
        bloco_metadados.append(f"- **{chave}:** {val}")

    # 2. Costura das 4 colunas normativas até o início de Informações Complementares
    has_ic, ic_start_page = detectar_informacoes_complementares(pdf_doc, pag_ini, pag_fim)
    col_end_page = ic_start_page if has_ic else pag_fim

    all_col_lines: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}
    for p in range(pag_ini - 1, col_end_page):
        is_first = (p == pag_ini - 1)
        cols_p = extrair_linhas_colunas_pagina(pdf_doc[p], is_first)
        for c in range(4):
            all_col_lines[c].extend(cols_p[c])

    titulos_colunas = [
        "Quando Autuar",
        "Quando NÃO Autuar",
        "Definições e Procedimentos",
        "Exemplos do Campo de Observações do AIT",
    ]

    blocos_colunas = []
    for c, tit in enumerate(titulos_colunas):
        md_col = formatar_coluna_markdown(all_col_lines[c])
        blocos_colunas.append(f"## {tit}\n\n{md_col.strip()}")

    # 3. Informações Complementares
    if not has_ic:
        bloco_ic = "## Informações Complementares\n\nNão há.\n"
    else:
        # Chama Docling apenas para o intervalo com conteúdo real em IC
        res_docling = converter.convert(str(pdf_path), page_range=(ic_start_page, pag_fim))
        bloco_ic = extrair_informacoes_complementares(res_docling.document, ic_start_page, pag_fim)

    partes = [
        "\n".join(bloco_metadados),
        "\n\n".join(blocos_colunas),
        bloco_ic.strip(),
    ]
    return "\n\n".join(partes).strip() + "\n"


# =============================================================================
# 8. FATIAMENTO VIA REGEX NO MARKDOWN CONSOLIDADO (MÉTODO ALTERNATIVO)
# =============================================================================
def localizar_inicio_bloco_ficha(texto: str, match_pos: int) -> int:
    """
    Heurística para encontrar o início de uma ficha numa string de Markdown contínua.
    """
    line_start = texto.rfind("\n", 0, match_pos)
    line_start = 0 if line_start == -1 else line_start + 1

    if texto[line_start : line_start + 1] == "|":
        return line_start

    janela_busca = max(0, line_start - 350)
    trecho = texto[janela_busca:line_start]
    pos_tip = trecho.rfind("Tipifica")
    if pos_tip != -1:
        abs_pos = janela_busca + pos_tip
        tip_line = texto.rfind("\n", 0, abs_pos)
        return 0 if tip_line == -1 else tip_line + 1

    return line_start


def fatiar_markdown_por_regex(markdown_texto: str) -> List[Dict[str, str]]:
    """
    Fatia um texto Markdown completo usando delimitação por Regex.
    """
    matches = list(REGEX_ENQUADRAMENTO.finditer(markdown_texto))
    if not matches:
        return []

    pontos_inicio = [localizar_inicio_bloco_ficha(markdown_texto, m.start()) for m in matches]

    fatias = []
    ocorrencias: Dict[str, int] = {}
    for i in range(len(matches)):
        cod = matches[i].group(1)
        inicio = pontos_inicio[i]
        fim = pontos_inicio[i + 1] if i + 1 < len(pontos_inicio) else len(markdown_texto)
        conteudo = markdown_texto[inicio:fim].strip()

        ocorrencias[cod] = ocorrencias.get(cod, 0) + 1
        identificador = cod if ocorrencias[cod] == 1 else f"{cod}_parte{ocorrencias[cod]}"

        fatias.append({
            "codigo": cod,
            "identificador": identificador,
            "conteudo": conteudo,
        })
    return fatias


# =============================================================================
# 9. GRAVAÇÃO DOS FICHEIROS
# =============================================================================
def gravar_ficha_individual(
    ficha_info: Dict[str, Any],
    conteudo_md: str,
    output_dir: Path,
) -> Path:
    """
    Grava o ficheiro .md individual de uma ficha na pasta 'fichas_extraidas/'.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    nome_ficheiro = f"ficha_{ficha_info['identificador']}.md"
    caminho = output_dir / nome_ficheiro

    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo_md.strip() + "\n")

    return caminho


# =============================================================================
# 10. FLUXO PRINCIPAL DE PROCESSAMENTO
# =============================================================================
def executar_extracao(
    pdf_path: Path,
    output_dir: Path = Path("fichas_extraidas"),
    full_output_path: Path = Path("mbft_completo.md"),
    page_start: Optional[int] = None,
    page_end: Optional[int] = None,
    skip_existing: bool = False,
    num_threads: int = 8,
) -> None:
    """
    Orquestra o pipeline completo de extração e fatiamento:
    1. Mapeia as 404 fichas e respectivos intervalos de páginas no PDF.
    2. Extrai metadados estruturados, costura colunas e processa tabelas reais.
    3. Grava as fichas normalizadas individualmente e o documento auditável.
    """
    t_global_inicio = time.time()

    if not pdf_path.exists():
        raise FileNotFoundError(f"Ficheiro PDF não encontrado: {pdf_path.resolve()}")

    logger.info("=" * 75)
    logger.info("EXTRAÇÃO E FATIAMENTO DO MBFT INICIADA (PIPELINE REFATORADO)")
    logger.info(f"Ficheiro PDF: {pdf_path.name}")
    logger.info(f"Diretório de saída das fichas: {output_dir}")
    logger.info(f"Ficheiro consolidado de auditoria: {full_output_path}")
    logger.info("=" * 75)

    # 1. Mapeamento das fichas no PDF
    todas_fichas = mapear_fichas_no_pdf(pdf_path)

    # 2. Filtragem opcional de intervalo de páginas
    fichas_alvo = []
    for f in todas_fichas:
        if page_start and f["pag_fim"] < page_start:
            continue
        if page_end and f["pag_ini"] > page_end:
            continue
        fichas_alvo.append(f)

    logger.info(f"Fichas selecionadas para processamento: {len(fichas_alvo)} de {len(todas_fichas)}.")

    # 3. Inicialização dos recursos (Docling e pypdfium2)
    converter = criar_pipeline_docling(num_threads=num_threads)
    pdf_doc = pdfium.PdfDocument(str(pdf_path))

    # Lista para acumular o Markdown consolidado para auditoria
    documento_completo_partes: List[str] = []

    # Se estivermos a começar do início (página 1), converte também a Parte Geral (págs 1 a 31)
    if (page_start is None or page_start <= 1) and fichas_alvo:
        primeira_ficha_pag = fichas_alvo[0]["pag_ini"]
        if primeira_ficha_pag > 1:
            logger.info(f"A converter Parte Geral do MBFT (páginas 1 a {primeira_ficha_pag - 1})...")
            try:
                res_intro = converter.convert(str(pdf_path), page_range=(1, primeira_ficha_pag - 1))
                md_intro = limpar_ruido_cabecalhos(res_intro.document.export_to_markdown())
                documento_completo_partes.append(
                    "# MANUAL BRASILEIRO DE FISCALIZAÇÃO DE TRÂNSITO - PARTE GERAL\n\n" + md_intro
                )
            except Exception as e:
                logger.warning(f"Não foi possível converter a introdução (págs 1-{primeira_ficha_pag - 1}): {e}")

    # 4. Processamento iterativo de cada ficha
    total_fichas = len(fichas_alvo)
    fichas_processadas = 0

    for idx, f in enumerate(fichas_alvo, start=1):
        codigo = f["codigo"]
        pag_ini = f["pag_ini"]
        pag_fim = f["pag_fim"]
        identificador = f["identificador"]
        ficheiro_destino = output_dir / f"ficha_{identificador}.md"

        # Verifica se deve ignorar fichas já processadas
        if skip_existing and ficheiro_destino.exists() and ficheiro_destino.stat().st_size > 200:
            logger.info(f"[{idx}/{total_fichas}] Ficha {codigo} já existe em disco. Ignorando...")
            with open(ficheiro_destino, "r", encoding="utf-8") as arq:
                documento_completo_partes.append(arq.read())
            fichas_processadas += 1
            continue

        qtd_pags = pag_fim - pag_ini + 1
        logger.info(
            f"[{idx}/{total_fichas}] Convertendo Ficha {codigo} "
            f"(págs. {pag_ini}-{pag_fim}, {qtd_pags} pág{'s' if qtd_pags > 1 else ''})..."
        )

        t_ficha_ini = time.time()
        try:
            # Geração do Markdown normalizado com pós-processamento determinístico
            md_normalizado = gerar_markdown_ficha(
                pdf_doc=pdf_doc,
                converter=converter,
                pdf_path=pdf_path,
                ficha_info=f,
            )

            # Salva o arquivo individual
            gravar_ficha_individual(f, md_normalizado, output_dir)

            # Acumula no documento completo de auditoria
            documento_completo_partes.append(md_normalizado.strip())

            t_ficha_dur = time.time() - t_ficha_ini
            logger.info(
                f"  -> Concluída em {t_ficha_dur:.1f}s ({len(md_normalizado):,} caracteres)."
            )
            fichas_processadas += 1

        except Exception as e:
            logger.error(f"Erro ao processar Ficha {codigo} (págs. {pag_ini}-{pag_fim}): {e}", exc_info=True)

    pdf_doc.close()

    # 5. Gravação do arquivo consolidado de auditoria
    if documento_completo_partes:
        logger.info(f"A compilar ficheiro unificado para auditoria: '{full_output_path}'...")
        with open(full_output_path, "w", encoding="utf-8") as f_audit:
            f_audit.write("\n\n---\n\n".join(documento_completo_partes))
        logger.info(f"Documento consolidado gravado com sucesso ({full_output_path.stat().st_size:,} bytes).")

    # Resumo final
    t_global_dur = time.time() - t_global_inicio
    logger.info("=" * 75)
    logger.info("PROCESSAMENTO CONCLUÍDO COM SUCESSO!")
    logger.info(f"Tempo total: {t_global_dur:.1f} segundos ({t_global_dur/60:.2f} minutos)")
    logger.info(f"Fichas geradas: {fichas_processadas} ficheiros na pasta '{output_dir.resolve()}'")
    logger.info(f"Auditoria consolidada: '{full_output_path.resolve()}'")
    logger.info("=" * 75)


# =============================================================================
# 11. PARSER DE ARGUMENTOS DA LINHA DE COMANDO
# =============================================================================
def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrai e fatia o MBFT em ficheiros Markdown estruturados com Docling e pypdfium2.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pdf-path",
        type=Path,
        default=Path("mbvt20222.pdf"),
        help="Caminho para o ficheiro PDF do MBFT.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("fichas_extraidas"),
        help="Diretório onde as fichas individuais serão gravadas.",
    )
    parser.add_argument(
        "--full-output",
        type=Path,
        default=Path("mbft_completo.md"),
        help="Arquivo Markdown unificado completo para auditoria.",
    )
    parser.add_argument(
        "--page-start",
        type=int,
        default=None,
        help="Página inicial para processamento (opcional, padrão: início).",
    )
    parser.add_argument(
        "--page-end",
        type=int,
        default=None,
        help="Página final para processamento (opcional, padrão: fim do PDF).",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Se informado, pula as fichas cujos arquivos já foram gerados.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=8,
        help="Número de threads da CPU para processamento paralelo.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    executar_extracao(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        full_output_path=args.full_output,
        page_start=args.page_start,
        page_end=args.page_end,
        skip_existing=args.skip_existing,
        num_threads=args.threads,
    )
