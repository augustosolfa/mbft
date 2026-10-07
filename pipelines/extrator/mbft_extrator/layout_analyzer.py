"""
Módulo especializado na análise de layout geométrico, limites e canais de colunas do MBFT (SRP).
"""

import re
from typing import Dict, List, Optional, Tuple
import pypdfium2 as pdfium


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

    # Divisões espaciais das 4 colunas normativas pelo centro horizontal (xc)
    COL_BOUNDS: Tuple[float, float, float] = (165.0, 298.0, 433.0)

    # Regex para ignorar cabeçalhos repetitivos impressos no topo de colunas
    RE_COLUMN_HEADER = re.compile(
        r"^(?:quando\s+autuar|quando\s+n[ãa]o\s+autuar|defini[cç][oõ]es\s+e\s+procedimentos|exemplos\s+do\s+campo.*):?$",
        re.IGNORECASE,
    )

    # Regex para detecção de início da seção de Informações Complementares
    RE_IC_HEADER = re.compile(r"^informa[cç][oõ]es\s+complementares:?$", re.IGNORECASE)

    # Regex para identificação da linha de início das colunas
    RE_QUANDO_AUTUAR = re.compile(r"quando\s+autuar", re.IGNORECASE)

    def __init__(self, page: pdfium.PdfPage, is_first_page: bool = False):
        self.page = page
        self.is_first_page = is_first_page
        self.tp = page.get_textpage()
        self.num_rects = self.tp.count_rects()
        self.width, self.height = page.get_size()

        self.y_top, self.y_bottom, self.ic_y_bound = self.detect_bounds()

    @classmethod
    def get_column_channel(cls, x0: float, x1: float) -> int:
        """
        Calcula o centro horizontal da caixa de texto e atribui o canal de coluna (0 a 3).
        - 0: Quando Autuar
        - 1: Quando Não Autuar
        - 2: Definições e Procedimentos
        - 3: Exemplos do Campo Observações
        """
        xc = (x0 + x1) / 2.0
        if xc < cls.COL_BOUNDS[0]:
            return 0
        elif xc < cls.COL_BOUNDS[1]:
            return 1
        elif xc < cls.COL_BOUNDS[2]:
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
        # Deve estar na margem esquerda (r[0] < 60) para não colidir com citações no corpo das colunas
        for i in range(self.num_rects):
            r = self.tp.get_rect(i)
            txt = self.tp.get_text_bounded(*r).strip()
            if r[0] < 60 and self.RE_IC_HEADER.match(txt):
                y_bottom = max(y_bottom, r[3])
                ic_y_bound = r[3]

        # Na primeira página, localiza a linha dos títulos das colunas ("Quando Autuar")
        if self.is_first_page:
            for i in range(self.num_rects):
                r = self.tp.get_rect(i)
                txt = self.tp.get_text_bounded(*r).strip()
                if self.RE_QUANDO_AUTUAR.search(txt):
                    y_top = min(y_top, r[1])

        return y_top, y_bottom, ic_y_bound

    def extract_column_boxes(self) -> Dict[int, List[Tuple[Tuple[float, float, float, float], str]]]:
        """
        Extrai e filtra todos os retângulos válidos distribuídos pelos 4 canais de colunas.

        Returns:
            Dicionário canal -> lista de tuplas ((x0, y0, x1, y1), texto).
        """
        page_boxes: Dict[int, List[Tuple[Tuple[float, float, float, float], str]]] = {
            0: [],
            1: [],
            2: [],
            3: [],
        }

        for i in range(self.num_rects):
            r = self.tp.get_rect(i)  # (x0, y0, x1, y1)

            # Na primeira página, caixas muito altas acima de 715 pt são do cabeçalho
            if self.is_first_page and r[1] > 715:
                continue

            # Apenas caixas situadas no intervalo vertical das colunas
            if r[1] >= self.y_bottom and r[3] <= self.y_top:
                txt = self.tp.get_text_bounded(*r).strip()
                if not txt:
                    continue

                # Ignora cabeçalhos de coluna repetitivos
                if self.RE_COLUMN_HEADER.search(txt):
                    continue

                ch = self.get_column_channel(r[0], r[2])
                page_boxes[ch].append((r, txt))

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

            # Calcula centro vertical (yc) de cada caixa e ordena de cima para baixo
            b_yc = [(b[0], (b[0][1] + b[0][3]) / 2.0, b[1]) for b in boxes]
            b_yc.sort(key=lambda item: -item[1])

            channel_lines: List[List[Tuple[float, float, str]]] = []
            curr_line: List[Tuple[float, float, str]] = []
            curr_y: Optional[float] = None

            for r, yc, txt in b_yc:
                if curr_y is None or abs(yc - curr_y) <= self.Y_LINE_TOLERANCE:
                    curr_line.append((r[0], r[2], txt))
                    curr_y = yc if len(curr_line) == 1 else (curr_y + yc) / 2.0
                else:
                    curr_line.sort(key=lambda x: x[0])
                    channel_lines.append(curr_line)
                    curr_line = [(r[0], r[2], txt)]
                    curr_y = yc

            if curr_line:
                curr_line.sort(key=lambda x: x[0])
                channel_lines.append(curr_line)

            cols_clusters[ch] = channel_lines

        return cols_clusters
