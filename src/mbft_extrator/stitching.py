"""
Módulo de costura geométrica contínua e normalização de colunas paralelas do MBFT.
"""

import logging
import re
from typing import List, Dict, Tuple, Optional, Any

import pypdfium2 as pdfium
from .models import CampoNormativo

logger = logging.getLogger("MBFT-Stitching")

METADATA_FIELDS = [
    ("tipificacao_resumida", r"\bTipifica[cç][aã]o\s+Resumida\s*:"),
    ("codigo_enquadramento", r"\bC[oó]digo\s+(?:d?o?\s*)?Enquadramento\s*:"),
    ("amparo_legal", r"\bAmparo\s+Legal\s*:"),
    ("tipificacao_enquadramento", r"\bTipifica[cç][aã]o\s+do\s+Enquadramento\s*:"),
    ("gravidade", r"\bGravidade\s*:"),
    ("penalidade", r"\bPenalidade\s*:"),
    ("medida_administrativa", r"\bMedida\s+Administrativa\s*:"),
    ("pode_configurar_crime_transito", r"\bPode\s+Configurar\s+(?:Crime\s+de\s+Tr[aâ]nsito|Infra[cç][aã]o\s+Penal)\s*:?"),
    ("infrator", r"\bInfrator\s*:"),
    ("competencia", r"\bCompet[eê]ncia\s*:"),
    ("pontuacao", r"\bPontua[cç][aã]o\s*:"),
    ("constatacao_infracao", r"\bConstata[cç][aã]o\s+da\s+Infra[cç][aã]o\s*:"),
]


def extrair_metadados_cabecalho(page: pdfium.PdfPage, codigo_padrao: str = "") -> Dict[str, str]:
    """
    Extrai do cabeçalho da primeira página os metadados jurídicos da infração.
    """
    txt_page = page.get_textpage().get_text_range()

    # O cabeçalho estende-se até a linha dos títulos das colunas ("Quando Autuar")
    m_qa = re.search(r"quando\s+autuar", txt_page, re.IGNORECASE)
    header_txt = txt_page[:m_qa.start()] if m_qa else txt_page[:1600]

    # Remove ruídos de cabeçalho governamental repetitivo
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

    # Normalizações determinísticas (heurísticas consagradas do extrair_mbft_old.py):
    infrator = meta.get("infrator", "")
    crime = meta.get("pode_configurar_crime_transito", "")
    if not crime:
        m_sim_nao = re.match(r"^(N[ÃA]O|SIM)\s*(.*)$", infrator, re.IGNORECASE)
        if m_sim_nao:
            crime = m_sim_nao.group(1).upper()
            infrator = m_sim_nao.group(2).strip()

    # Tratamento de vazamento de Artigo de Trânsito do Crime para Infrator
    m_art = re.search(r"((?:Art\.?\s*)?\d{3}(?:\s*-[A-Za-z]+)?\s*do\s*CTB)", infrator, re.IGNORECASE)
    if m_art:
        artigo = m_art.group(1).strip()
        if not artigo.lower().startswith("art"):
            artigo = "Art. " + artigo
        infrator = infrator.replace(m_art.group(0), "").strip()
        if artigo not in crime:
            crime = f"{crime} {artigo}".strip()

    cod = meta.get("codigo_enquadramento", "")
    m_cod = re.search(r"([0-9]{3}\s*-\s*[0-9]{1,2})", cod)
    if m_cod:
        meta["codigo_enquadramento"] = re.sub(r"\s+", "", m_cod.group(1))
    elif codigo_padrao:
        meta["codigo_enquadramento"] = codigo_padrao

    if not crime:
        crime = "NÃO"

    meta["infrator"] = infrator
    meta["pode_configurar_crime_transito"] = crime

    return meta


def _join_line_fragments(frags: List[Tuple[float, float, str]]) -> str:
    """
    Junta fragmentos de texto na mesma linha horizontal com tolerância espacial.
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
    # Corrige quebras em códigos como "502 - 91" -> "502-91"
    joined = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1-\2", joined)
    return re.sub(r"\s+", " ", joined).strip()


def extrair_linhas_colunas_pagina(page: pdfium.PdfPage, is_first_page: bool) -> Tuple[Dict[int, List[str]], Optional[float]]:
    """
    Extrai as linhas de texto distribuídas nos 4 canais de colunas do MBFT.
    Retorna também o Y do início de Informações Complementares, se presente na página.
    """
    tp = page.get_textpage()
    num_rects = tp.count_rects()
    w, h = page.get_size()

    y_top = h
    y_bottom = 0.0
    ic_y_bound = None

    # Localiza se a seção "Informações Complementares" se inicia nesta página como título de seção
    # Deve estar na margem esquerda (r[0] < 60) para não coincidir com menções no corpo das colunas
    for i in range(num_rects):
        r = tp.get_rect(i)
        txt = tp.get_text_bounded(*r).strip()
        if r[0] < 60 and re.match(r"^informa[cç][oõ]es\s+complementares:?$", txt, re.IGNORECASE):
            y_bottom = max(y_bottom, r[3])
            ic_y_bound = r[3]

    # Na primeira página, localiza a linha dos títulos das colunas ("Quando Autuar")
    if is_first_page:
        for i in range(num_rects):
            r = tp.get_rect(i)
            txt = tp.get_text_bounded(*r).strip()
            if re.search(r"quando\s+autuar", txt, re.IGNORECASE):
                y_top = min(y_top, r[1])

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
        if is_first_page and r[1] > 715:
            continue
        if r[1] >= y_bottom and r[3] <= y_top:
            txt = tp.get_text_bounded(*r).strip()
            if not txt:
                continue
            # Ignora cabeçalhos de coluna repetitivos
            if re.search(
                r"^(?:quando\s+autuar|quando\s+n[ãa]o\s+autuar|defini[cç][oõ]es\s+e\s+procedimentos|exemplos\s+do\s+campo.*):?$",
                txt,
                re.IGNORECASE,
            ):
                continue
            ch = col_channel(r[0], r[2])
            page_boxes[ch].append((r, txt))

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

    return cols_lines, ic_y_bound


def processar_coluna_normativa(lines: List[str]) -> CampoNormativo:
    """
    Costura as linhas de uma coluna formando itens estruturados e um texto limpo:
    1. Unifica quebras duras de linha dentro de parágrafos/itens com espaço.
    2. Reúne palavras hifenizadas no final da linha (ex: 'cruzamen-' + 'to' -> 'cruzamento').
    3. Retorna objeto CampoNormativo com o texto Markdown completo e a lista de itens.
    """
    if not lines:
        return CampoNormativo(texto="Não há.", itens=[])

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
            # Continuação direta do item ou frase anterior (costura entre quebras e páginas)
            if itens:
                prev = itens[-1]
                # Reunião de palavras hifenizadas
                if prev.endswith("-") and not prev.endswith(" -"):
                    itens[-1] = prev[:-1] + line
                else:
                    itens[-1] = prev + " " + line
            else:
                itens.append(line)

    texto_md = "\n\n".join(itens).strip() if itens else "Não há."
    return CampoNormativo(texto=texto_md, itens=itens)
