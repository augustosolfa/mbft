import re
from typing import Dict, List, Optional, Tuple

from .layout_analyzer import LayoutAnalyzer
from .models import CampoNormativo, PaginaExtraida
from .text_joiner import join_line_fragments


def extrair_linhas_colunas_pagina(
    page_ext: PaginaExtraida, is_first_page: bool
) -> Tuple[Dict[int, List[str]], Optional[float]]:
    """
    Extrai as linhas de texto distribuídas nos 4 canais de colunas do MBFT.
    Utiliza LayoutAnalyzer para análise geométrica e join_line_fragments para unificação espacial.
    Retorna também o Y do início de Informações Complementares, se presente na página.
    """
    analyzer = LayoutAnalyzer(page_ext=page_ext, is_first_page=is_first_page)
    clustered = analyzer.cluster_lines()

    cols_lines: Dict[int, List[str]] = {0: [], 1: [], 2: [], 3: []}
    for ch, line_clusters in clustered.items():
        lines = []
        for line_frags in line_clusters:
            line_str = join_line_fragments(line_frags)
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

    re_item_num = re.compile(r"^(\d{1,3})\.(?!\d)\s*(.*)$")
    re_subitem_num = re.compile(r"^(\d{1,3}(?:\.\d{1,3})+)\.(?!\d)\s*(.*)$")
    re_bullet = re.compile(r"^[-–—*]\s*(.*)$")
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
