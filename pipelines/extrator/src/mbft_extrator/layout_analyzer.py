"""
Módulo especializado na análise de layout geométrico, limites e canais de colunas do MBFT (SRP).
"""

import re
from typing import Dict, List, Optional, Tuple

from .models import PaginaExtraida, RetanguloTexto
from .pdf_geometry import (
    Y_TOP_PRIMEIRA_PAGINA,
    MARGEM_ESQUERDA_TITULO,
    COL_BOUNDS_PCT,
    RE_IC_HEADER,
    RE_COLUMN_HEADER,
    agrupar_em_linhas,
)


class LayoutAnalyzer:
    """
    Responsável pela análise geométrica da página do PDF do MBFT:
    - Determinação de limites verticais (cabeçalho, colunas e Informações Complementares);
    - Classificação de retângulos nos 4 canais de colunas normativas;
    - Descarte de cabeçalhos repetitivos de colunas;
    - Agrupamento vertical de caixas de texto na mesma linha (clustering por tolerância Y).
    """

    # Tolerância vertical para agrupar fragmentos na mesma linha
    Y_LINE_TOLERANCE: float = 3.2

    def __init__(self, page_ext: PaginaExtraida, is_first_page: bool = False):
        self.page_ext = page_ext
        self.is_first_page = is_first_page
        self.width = page_ext.largura
        self.height = page_ext.altura

        self.y_top, self.y_bottom, self.ic_y_bound = self.detect_bounds()
        self.col_bounds = self.detect_column_bounds()

    def detect_column_bounds(self) -> List[float]:
        """
        Detecta dinamicamente os limites (X) das colunas buscando as linhas verticais separadoras.
        Caso as linhas vetoriais não existam na página, utiliza proporções da largura.
        """
        w = float(self.width)
        vlines_x: List[float] = []

        for b in self.page_ext.linhas_vetoriais:
            vw = b[2] - b[0]
            vh = b[3] - b[1]
            # Traço vertical fino e com altura mínima representativa
            if vw < 5.0 and vh > 20.0:
                vlines_x.append((b[0] + b[2]) / 2.0)

        clusters: List[List[float]] = []
        for x in sorted(vlines_x):
            if not clusters:
                clusters.append([x])
            elif abs(clusters[-1][-1] - x) < 5.0:
                clusters[-1].append(x)
            else:
                clusters.append([x])

        means = [sum(c) / len(c) for c in clusters]

        bounds: List[float] = []
        for exp in COL_BOUNDS_PCT:
            target = w * exp
            if means:
                best = min(means, key=lambda x: abs(x - target))
                if abs(best - target) < w * 0.05:  # Tolerância de 5% de variância
                    bounds.append(best)
                else:
                    bounds.append(target)
            else:
                bounds.append(target)

        return bounds

    def get_column_channel(self, x0: float, x1: float) -> int:
        """
        Calcula o centro horizontal da caixa de texto e atribui o canal de coluna (0 a 3).
        - 0: Quando Autuar
        - 1: Quando Não Autuar
        - 2: Definições e Procedimentos
        - 3: Exemplos do Campo Observações
        """
        xc = (x0 + x1) / 2.0
        if xc < self.col_bounds[0]:
            return 0
        elif xc < self.col_bounds[1]:
            return 1
        elif xc < self.col_bounds[2]:
            return 2
        else:
            return 3

    def detect_bounds(self) -> Tuple[float, float, Optional[float]]:
        """
        Determina os limites verticais (Y) da área útil das colunas na página.

        Returns:
            Tuple com:
            - y_top: limite superior da área de colunas (topo da página ou linha de 'Quando Autuar');
            - y_bottom: limite inferior (rodapé ou início de 'Informações Complementares');
            - ic_y_bound: coordenada Y do título 'Informações Complementares' (se presente).
        """
        y_top = float(self.height)
        y_bottom = 0.0
        ic_y_bound: Optional[float] = None

        # Localiza se a seção "Informações Complementares" se inicia nesta página como título
        # Deve estar na margem esquerda (r_text.x0 < MARGEM_ESQUERDA_TITULO) para não colidir com citações no corpo das colunas
        for r_text in self.page_ext.retangulos:
            if r_text.x0 < MARGEM_ESQUERDA_TITULO and RE_IC_HEADER.match(r_text.texto):
                y_bottom = max(y_bottom, r_text.y1)
                ic_y_bound = r_text.y1

        # Na primeira página, localiza a linha dos títulos das colunas ("Quando Autuar")
        if self.is_first_page:
            y_tops = []
            for r_text in self.page_ext.retangulos:
                txt_lower = r_text.texto.lower()
                if "quando autuar" in txt_lower or ("quando" in txt_lower and "autuar" in txt_lower):
                    y_tops.append(r_text.y0)
            
            if y_tops:
                y_top = max(y_tops)

        return y_top, y_bottom, ic_y_bound

    def extract_column_boxes(self) -> Dict[int, List[Tuple[Tuple[float, float, float, float], str]]]:
        """
        Extrai e filtra todos os retângulos válidos distribuídos pelos 4 canais de colunas.

        Returns:
            Dicionário canal -> lista de tuças ((x0, y0, x1, y1), texto).
        """
        page_boxes: Dict[int, List[Tuple[Tuple[float, float, float, float], str]]] = {
            0: [],
            1: [],
            2: [],
            3: [],
        }

        for r_text in self.page_ext.retangulos:
            # Na primeira página, caixas muito altas acima de Y_TOP_PRIMEIRA_PAGINA pt são do cabeçalho
            if self.is_first_page and r_text.y0 > Y_TOP_PRIMEIRA_PAGINA:
                continue

            # Apenas caixas situadas no intervalo vertical das colunas
            if r_text.y0 >= self.y_bottom and r_text.y1 <= self.y_top:
                if not r_text.texto:
                    continue

                # Ignora cabeçalhos de coluna repetitivos
                if RE_COLUMN_HEADER.search(r_text.texto):
                    continue

                ch = self.get_column_channel(r_text.x0, r_text.x1)
                page_boxes[ch].append(((r_text.x0, r_text.y0, r_text.x1, r_text.y1), r_text.texto))

        return page_boxes

    def cluster_lines(self) -> Dict[int, List[List[Tuple[float, float, str]]]]:
        """
        Agrupa verticalmente os retângulos de cada canal por proximidade de linha horizontal.

        Returns:
            Dicionário canal -> lista de linhas, onde cada linha é uma lista ordenada de
            fragmentos (x0, x1, texto).
        """
        page_boxes = self.extract_column_boxes()
        cols_clusters: Dict[int, List[List[Tuple[float, float, str]]]] = {
            0: [],
            1: [],
            2: [],
            3: [],
        }

        for ch in range(4):
            boxes = page_boxes[ch]
            if not boxes:
                continue

            # item format: (r, yc, txt)
            b_items = [(b[0], (b[0][1] + b[0][3]) / 2.0, b[1]) for b in boxes]
            
            linhas_agrupadas = agrupar_em_linhas(b_items, lambda x: x[1], self.Y_LINE_TOLERANCE)
            
            channel_lines = []
            for curr_line in linhas_agrupadas:
                curr_line.sort(key=lambda x: x[0][0]) # sort by x0
                channel_lines.append([(it[0][0], it[0][2], it[2]) for it in curr_line])

            cols_clusters[ch] = channel_lines

        return cols_clusters
