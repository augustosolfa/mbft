import re
from typing import Any, Dict, List, Tuple

from .models import MetadadosCabecalho, PaginaExtraida
from .pdf_geometry import RE_COLUMN_HEADER, RE_QUANDO_AUTUAR, Y_LIMIT_HEADER


METADATA_FIELDS = [
    ("tipificacao_resumida", r"tipifica[cç][aã]o\s+resumida"),
    ("codigo_enquadramento", r"c[óo]digo\s+do\s+enquadramento"),
    ("amparo_legal", r"amparo\s+legal"),
    ("tipificacao_enquadramento", r"tipifica[cç][aã]o\s+do\s+enquadramento"),
    ("gravidade", r"gravidade"),
    ("penalidade", r"penalidade"),
    ("medida_administrativa", r"medida\s+administrativa"),
    ("pode_configurar_crime_transito", r"pode\s+configurar\s+crime\s+de\s+tr[aã]nsito\?"),
    ("infrator", r"infrator"),
    ("competencia", r"compet[êe]ncia"),
    ("pontuacao", r"pontua[cç][aã]o"),
    ("constatacao_infracao", r"constata[cç][aã]o\s+da\s+infra[cç][aã]o"),
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
    
    for i in range(len(hl) - 1):
        top, bottom = hl[i], hl[i + 1]
        
        band_v_lines = [b for b in v_lines if b[1] <= bottom + 5 and b[3] >= top - 5]
        vl = dedup(band_v_lines, 0)
        
        if len(vl) < 2:
            vl = [36.0, 560.0]
            
        for j in range(len(vl) - 1):
            left = 0 if j == 0 else vl[j] - 2
            right = 800 if j == len(vl) - 2 else vl[j + 1] + 2
            
            box_rects = []
            for r in page_ext.retangulos:
                if left <= r.xc <= right and (bottom - 2) <= r.yc <= (top + 2):
                    box_rects.append(r)
            
            box_rects.sort(key=lambda r: (-r.yc, r.xc))
            txt = " ".join([r.texto for r in box_rects]).strip()
            
            if txt:
                txt = re.sub(r'[\r\n]+', ' ', txt)
                txt = re.sub(r'\s+', ' ', txt)
                if not RE_COLUMN_HEADER.match(txt):
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
        r"CONSELHO\s+NACIONAL\s+DE\s+TR[AÃ]NSITO.*|MANUAL\s+BRASILEIRO\s+DE\s+FISCALIZA[CÇ][AÃ]O.*|FICHA\s+DE\s+FISCALIZA[CÇ][AÃ]O.*",
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

    kwargs = {"competencia_alterada_lei_14599": competencia_alterada_lei}
    for i, (start, end, label) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(header_txt)
        val = header_txt[end:next_start]
        val = re.sub(r"[\r\n]+", " ", val)
        val = re.sub(r"\s+", " ", val).strip()
        kwargs[label] = val
        
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
