import re
from typing import Any, Dict, List, Tuple

from .models import MetadadosCabecalho, PaginaExtraida, RetanguloTexto
from .pdf_geometry import (
    RE_COLUMN_HEADER,
    RE_QUANDO_AUTUAR,
    Y_LIMIT_HEADER,
    agrupar_em_linhas,
)
from .text_joiner import join_line_fragments


METADATA_FIELDS = [
    ("tipificacao_resumida", r"\bTipifica[cç][aã]o\s+Resumida\s*:?"),
    ("codigo_enquadramento", r"\bC[oó]digo\s+(?:d\s*[eo]\s+)?Enquadramento\s*:?"),
    ("amparo_legal", r"\b(?:Amparo\s+Legal\s*:?|Legal:\s*Amparo\s*:?)"),
    ("tipificacao_enquadramento", r"\bTipifica[cç][aã]o\s+(?:d\s*[eo]\s+)?Enquadramento\s*:?"),
    ("gravidade", r"\bGravidade\s*:?"),
    ("penalidade", r"(?:\bPenalidade\s*:|(?:^|\n)\s*Penalidade\b\s*:?)"),
    ("medida_administrativa", r"\bMedidas?\s+Administrativas?\s*:?"),
    (
        "pode_configurar_crime_transito",
        r"\bPode\s+Configurar\s+(?:Crime\s+de\s+Tr[aâã]nsito|Infra[cç][aã]o\s+Penal)\s*\??\s*:?",
    ),
    ("infrator", r"(?:\bInfrator\s*:|(?:^|\n)\s*Infrator\b\s*:?)"),
    ("competencia", r"\bCompet[eê\ufffd]ncia(?:\s*\(\s*alterada[^)]*\))?\s*:?"),
    ("pontuacao", r"\bPontua[cç][aã]o\s*:?"),
    ("constatacao_infracao", r"\bConstata[cç][aã]o\s+da\s+Infra[cç][aã]o\s*:?"),
]


def identificar_linhas_grade_cabecalho(page_ext: PaginaExtraida) -> Tuple[float, List[Tuple], List[Tuple]]:
    y_limit = Y_LIMIT_HEADER
    for r in page_ext.retangulos:
        if RE_QUANDO_AUTUAR.search(r.texto):
            y_limit = r.y0 - 5.0
            break

    v_lines, h_lines = [], []
    paths = page_ext.linhas_vetoriais
    for b in paths:
        w, h = b[2] - b[0], b[3] - b[1]
        if b[3] > y_limit:  # Região dinâmica do cabeçalho
            if w > 20 and h < 5:
                h_lines.append(b)
            elif h > 10 and w < 5:
                v_lines.append(b)
                
    return y_limit, h_lines, v_lines


def _agrupar_retangulos_em_colunas(box_rects: List[RetanguloTexto]) -> List[Tuple[float, str]]:
    """
    Agrupa retângulos de uma faixa horizontal sem linhas verticais em colunas inferidas
    por sobreposição/proximidade horizontal de segmentos de linha, preservando a leitura
    de cima para baixo dentro de cada coluna e da esquerda para a direita entre colunas.
    """
    if not box_rects:
        return []

    linhas = agrupar_em_linhas(box_rects, lambda r: r.yc, y_tolerance=3.2)
    segments: List[List[RetanguloTexto]] = []
    for linha in linhas:
        ls = sorted(linha, key=lambda r: r.x0)
        seg = [ls[0]]
        for r in ls[1:]:
            prev_x1 = max(x.x1 for x in seg)
            if r.x0 - prev_x1 <= 10.0:
                seg.append(r)
            else:
                segments.append(seg)
                seg = [r]
        segments.append(seg)

    clusters: List[Dict[str, Any]] = []
    for seg in segments:
        s_x0 = min(r.x0 for r in seg)
        s_x1 = max(r.x1 for r in seg)
        best_c = None
        best_score = None
        for c in clusters:
            overlap = min(s_x1, c["x1"]) - max(s_x0, c["x0"])
            gap = max(0.0, max(s_x0 - c["x1"], c["x0"] - s_x1))
            if overlap >= 0.0 or gap <= 20.0:
                score = (overlap, -abs(s_x0 - c["x0"]))
                if best_score is None or score > best_score:
                    best_score = score
                    best_c = c
        if best_c is not None:
            best_c["segs"].append(seg)
            best_c["x0"] = min(best_c["x0"], s_x0)
            best_c["x1"] = max(best_c["x1"], s_x1)
        else:
            clusters.append({"x0": s_x0, "x1": s_x1, "segs": [seg]})

    clusters.sort(key=lambda c: c["x0"])
    colunas: List[Tuple[float, str]] = []
    for c in clusters:
        c_segs = sorted(c["segs"], key=lambda s: -sum(r.yc for r in s) / len(s))
        partes = [
            join_line_fragments([(r.x0, r.x1, r.texto) for r in s])
            for s in c_segs
        ]
        txt = " ".join(p for p in partes if p).strip()
        txt = re.sub(r"[\r\n]+", " ", txt)
        txt = re.sub(r"\s+", " ", txt)
        if txt:
            col_left = 440.0 if c["x0"] >= 435.0 else c["x0"]
            colunas.append((col_left, txt))

    return colunas


def _reconstruir_texto_celula(
    box_rects: List[RetanguloTexto],
    possui_grade_vertical: bool = True,
) -> str:
    """
    Reconstrói o texto de uma célula do cabeçalho agrupando fragmentos da mesma
    linha horizontal (tolerância Y) e unificando-os espacialmente da esquerda
    para a direita via join_line_fragments.
    """
    if not box_rects:
        return ""

    if not possui_grade_vertical:
        colunas = _agrupar_retangulos_em_colunas(box_rects)
        return " ".join(txt for _, txt in colunas)

    linhas = agrupar_em_linhas(box_rects, lambda r: r.yc, y_tolerance=3.2)
    partes_linha = [
        join_line_fragments([(r.x0, r.x1, r.texto) for r in linha])
        for linha in linhas
    ]
    txt = " ".join(p for p in partes_linha if p).strip()
    txt = re.sub(r"[\r\n]+", " ", txt)
    return re.sub(r"\s+", " ", txt)


def extrair_celulas_cabecalho(page_ext: PaginaExtraida, h_lines: List[Tuple], v_lines: List[Tuple]) -> List[Dict[str, Any]]:
    def dedup(lines, idx):
        lines = sorted([l[idx] for l in lines])
        res = []
        for x in lines:
            if not res or x - res[-1] > 3:
                res.append(x)
        return res
    
    hl = dedup(h_lines, 1)[::-1]
    cells = []
    used_rect_indices = set()
    
    for i in range(len(hl) - 1):
        top, bottom = hl[i], hl[i + 1]
        
        band_v_lines = [b for b in v_lines if b[1] <= bottom + 6 and b[3] >= top - 6]
        vl = dedup(band_v_lines, 0)
        possui_grade_vertical = len(vl) >= 2
        
        if not possui_grade_vertical:
            box_rects = []
            for idx_r, r in enumerate(page_ext.retangulos):
                if (
                    idx_r not in used_rect_indices
                    and 0 <= r.xc <= 800
                    and (bottom - 2) <= r.yc <= (top + 2)
                ):
                    box_rects.append(r)
                    used_rect_indices.add(idx_r)

            for col_left, txt in _agrupar_retangulos_em_colunas(box_rects):
                if txt and not RE_COLUMN_HEADER.match(txt):
                    cells.append({'text': txt, 'left': col_left, 'top': top})
            continue
            
        for j in range(len(vl) - 1):
            left = 0 if j == 0 else vl[j] - 2
            right = 800 if j == len(vl) - 2 else vl[j + 1] + 2
            
            box_rects = []
            for idx_r, r in enumerate(page_ext.retangulos):
                if (
                    idx_r not in used_rect_indices
                    and left <= r.xc <= right
                    and (bottom - 2) <= r.yc <= (top + 2)
                ):
                    box_rects.append(r)
                    used_rect_indices.add(idx_r)
            
            txt = _reconstruir_texto_celula(box_rects, possui_grade_vertical=True)
            if txt and not RE_COLUMN_HEADER.match(txt):
                cells.append({'text': txt, 'left': vl[j], 'top': top})
                    
    return cells


def agrupar_texto_por_colunas(cells: List[Dict[str, Any]]) -> str:
    cols = {}
    for c in cells:
        col_idx = round(c['left'] / 10) * 10
        cols.setdefault(col_idx, []).append(c)
        
    header_text = ""
    for k in sorted(cols.keys()):
        for c in sorted(cols[k], key=lambda x: -x['top']):
            header_text += c['text'] + "\n\n"
            
    return header_text


def get_header_text_by_column(page_ext: PaginaExtraida) -> str:
    """Reconstrói o texto do cabeçalho agrupado por colunas, guiando-se pela grade vetorial."""
    y_limit, h_lines, v_lines = identificar_linhas_grade_cabecalho(page_ext)
    cells = extrair_celulas_cabecalho(page_ext, h_lines, v_lines)
    return agrupar_texto_por_colunas(cells)


def fatiar_texto_em_campos(header_txt: str) -> MetadadosCabecalho:
    header_txt = re.sub(
        r"CONSELHO\s+NACIONAL\s+DE\s+TR[AÂÃ]NSITO.*|MANUAL\s+BRASILEIRO\s+DE\s+FISCALIZA[CÇ][AÃ]O.*|FICHA\s+DE\s+FISCALIZA[CÇ][AÃ]O.*",
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

    kwargs = {}
    competencia_alterada_lei = False
    for i, (start, end, label) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(header_txt)
        val = header_txt[end:next_start]
        val = re.sub(r"[\r\n]+", " ", val)
        val = re.sub(r"\s+", " ", val).strip()
        val = re.sub(r"^[:\s]+", "", val).strip()
        kwargs[label] = val
        if label == "competencia":
            if re.search(r"14\.?\s*599", val) or re.search(r"14\.?\s*599", header_txt[start:end]):
                competencia_alterada_lei = True

    kwargs["competencia_alterada_lei_14599"] = competencia_alterada_lei
    return MetadadosCabecalho(**kwargs)


def aplicar_correcoes_metadados(meta: MetadadosCabecalho, codigo_padrao: str = "") -> MetadadosCabecalho:
    infrator = meta.infrator or ""
    crime = meta.pode_configurar_crime_transito or ""
    
    m_sim_nao = re.match(r"^(N[ÃA]O|SIM)\b\s*(.*)$", infrator, re.IGNORECASE)
    if m_sim_nao:
        crime_ext = m_sim_nao.group(1).upper()
        infrator = m_sim_nao.group(2).strip()
        if not crime or len(crime) > 25 or "Cã" in crime or "14599" in crime:
            crime = crime_ext

    cod = meta.codigo_enquadramento or ""
    m_cod = re.search(r"([0-9]{3}\s*-\s*[0-9]{1,2})", cod)
    if m_cod:
        meta.codigo_enquadramento = re.sub(r"\s+", "", m_cod.group(1))
    elif codigo_padrao:
        meta.codigo_enquadramento = codigo_padrao

    meta.infrator = infrator
    meta.pode_configurar_crime_transito = crime.strip() if crime and crime.strip() else None

    const_inf = meta.constatacao_infracao or ""
    const_inf = re.split(r'(?i)constata[cç][aã]o da infra[cç][aã]o', const_inf)[0].strip()
    meta.constatacao_infracao = const_inf

    return meta


def extrair_metadados_cabecalho(page_ext: PaginaExtraida, codigo_padrao: str = "") -> MetadadosCabecalho:
    """
    Extrai do cabeçalho da primeira página os metadados jurídicos da infração.
    """
    header_txt = get_header_text_by_column(page_ext)
    meta = fatiar_texto_em_campos(header_txt)
    return aplicar_correcoes_metadados(meta, codigo_padrao)


def parse_metadados_markdown(md_text: str) -> dict:
    """
    Função pura de extração via regex de campos de metadados a partir de texto Markdown (OCR/Docling).
    """
    meta_limpo = {}
    m_inf = re.search(r'Infrator\s*:?\s*([^|]*?)(?=\n|$|\||Compet[eê]ncia)', md_text, re.IGNORECASE)
    if m_inf:
        val = m_inf.group(1).strip()
        val = re.sub(r'[\*_\|]', '', val)
        val = re.sub(r'\s+', ' ', val).strip()
        meta_limpo['infrator'] = val

    m_const = re.search(r'Constata[cç][aã]o da Infra[cç][aã]o\s*:?\s*([^|]*?)(?=\n|$|\||Quando)', md_text, re.IGNORECASE)
    if m_const:
        val = m_const.group(1).strip()
        val = re.sub(r'[\*_\|]', '', val)
        val = re.sub(r'\s+', ' ', val).strip()
        meta_limpo['constatacao_infracao'] = val

    return meta_limpo
