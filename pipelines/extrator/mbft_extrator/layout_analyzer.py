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
        self.col_bounds = self.detect_column_bounds()

    def detect_column_bounds(self) -> List[float]:
        """
        Detecta dinamicamente os limites (X) das colunas buscando as linhas verticais separadoras.
        Caso as linhas vetoriais não existam na página, utiliza proporções da largura.
        """
        w = float(self.width)
        vlines_x: List[float] = []

        try:
            for obj in self.page.get_objects():
                if getattr(obj, "type", None) == 2:  # FPDF_PAGEOBJ_PATH
                    b = obj.get_bounds()
                    vw = b[2] - b[0]
                    vh = b[3] - b[1]
                    # Traço vertical fino e com altura mínima representativa
                    if vw < 5.0 and vh > 20.0:
                        vlines_x.append((b[0] + b[2]) / 2.0)
        except Exception:
            pass

        clusters: List[List[float]] = []
        for x in sorted(vlines_x):
            if not clusters:
                clusters.append([x])
            elif abs(clusters[-1][-1] - x) < 5.0:
                clusters[-1].append(x)
            else:
                clusters.append([x])

        means = [sum(c) / len(c) for c in clusters]

        # Proporções esperadas das 3 divisórias internas: ~28%, ~50% e ~73%
        expected_pct = [0.28, 0.50, 0.73]
        bounds: List[float] = []
        for exp in expected_pct:
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
        # Deve estar na margem esquerda (r[0] < 60) para não colidir com citações no corpo das colunas
        for i in range(self.num_rects):
            r = self.tp.get_rect(i)
            txt = self.tp.get_text_bounded(*r).strip()
            if r[0] < 60 and self.RE_IC_HEADER.match(txt):
                y_bottom = max(y_bottom, r[3])
                ic_y_bound = r[3]

        # Na primeira página, localiza a linha dos títulos das colunas ("Quando Autuar")
        if self.is_first_page:
            quando_ys = []
            search_q = self.tp.search("quando", match_case=False)
            while match := search_q.get_next():
                quando_ys.append(self.tp.get_charbox(match[0])[1])

            autuar_ys = []
            search_a = self.tp.search("autuar", match_case=False)
            while match := search_a.get_next():
                autuar_ys.append(self.tp.get_charbox(match[0])[1])

            valid_ys = []
            for qy in quando_ys:
                for ay in autuar_ys:
                    if abs(qy - ay) < 8.0:
                        valid_ys.append((qy + ay) / 2.0)

            if valid_ys:
                # O limite superior das colunas é o eixo Y da linha "Quando Autuar" mais alta na página
                y_top = max(valid_ys)

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
