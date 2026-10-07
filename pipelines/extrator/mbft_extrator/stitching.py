"""
Módulo de costura geométrica contínua e normalização de colunas paralelas do MBFT.
"""

import logging
import re
from typing import List, Dict, Tuple, Optional, Any

import pypdfium2 as pdfium
from .models import CampoNormativo
from .layout_analyzer import LayoutAnalyzer
from .text_joiner import TextJoiner, _join_line_fragments, unificar_linhas_e_hifens

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
    ("competencia", r"\bCompet[eê\ufffd]ncia(?:\s*\([^)]*\))?\s*:"),
    ("pontuacao", r"\bPontua[cç][aã]o\s*:"),
    ("constatacao_infracao", r"\bConstata[cç][aã]o\s+da\s+Infra[cç][aã]o\s*:"),
]


def extrair_metadados_cabecalho(page: pdfium.PdfPage, codigo_padrao: str = "") -> Dict[str, Any]:
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
    competencia_alterada_lei = False
    for label, pat in METADATA_FIELDS:
        m = re.search(pat, header_txt, re.IGNORECASE)
        if m:
            positions.append((m.start(), m.end(), label))
            if label == "competencia" and re.search(r"14\.?599", m.group(0)):
                competencia_alterada_lei = True

    positions.sort(key=lambda x: x[0])

    meta: Dict[str, Any] = {label: "" for label, _ in METADATA_FIELDS}
    meta["competencia_alterada_lei_14599"] = competencia_alterada_lei
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


def extrair_linhas_colunas_pagina(
    page: pdfium.PdfPage, is_first_page: bool
) -> Tuple[Dict[int, List[str]], Optional[float]]:
    """
    Extrai as linhas de texto distribuídas nos 4 canais de colunas do MBFT.
    Utiliza LayoutAnalyzer para análise geométrica e TextJoiner para unificação espacial.
    Retorna também o Y do início de Informações Complementares, se presente na página.
    """
    analyzer = LayoutAnalyzer(page=page, is_first_page=is_first_page)
    clustered = analyzer.cluster_lines()

    cols_lines: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}
    for ch, line_clusters in clustered.items():
        lines = []
        for line_frags in line_clusters:
            line_str = TextJoiner.join_horizontal_fragments(line_frags)
            if line_str:
                lines.append(line_str)
        cols_lines[ch] = lines

    return cols_lines, analyzer.ic_y_bound


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

