"""
Testes unitários para text_joiner, LayoutAnalyzer e desacoplamento SRP do stitching.
"""

import unittest
from mbft_extrator.text_joiner import join_line_fragments, unificar_linhas_e_hifens
from mbft_extrator.layout_analyzer import LayoutAnalyzer
from mbft_extrator.pdf_geometry import RE_COLUMN_HEADER
from mbft_extrator.colunas import extrair_linhas_colunas_pagina
from mbft_extrator.cabecalho import parse_metadados_markdown
from mbft_extrator.models import PaginaExtraida, RetanguloTexto


class TestTextJoiner(unittest.TestCase):
    def test_join_horizontal_fragments_gap_menor_que_limiar(self):
        # Dois fragmentos com gap de 1.0 pt (< 2.5 pt) sem espaço explícito
        frags = [(10.0, 20.0, "Trans"), (21.0, 35.0, "portador")]
        res = join_line_fragments(frags, gap_threshold=2.5)
        self.assertEqual(res, "Transportador")

    def test_join_horizontal_fragments_gap_maior_com_espaco(self):
        # Dois fragmentos com gap de 5.0 pt (>= 2.5 pt)
        frags = [(10.0, 20.0, "Auto"), (25.0, 35.0, "de")]
        res = join_line_fragments(frags, gap_threshold=2.5)
        self.assertEqual(res, "Auto de")

    def test_join_horizontal_fragments_com_espaco_existente(self):
        # Gap pequeno (< 2.5 pt), mas o primeiro fragmento já termina em espaço
        frags = [(10.0, 20.0, "Veículo "), (21.0, 35.0, "parado")]
        res = join_line_fragments(frags, gap_threshold=2.5)
        self.assertEqual(res, "Veículo parado")

    def test_join_horizontal_fragments_reuniao_codigo_enquadramento(self):
        # Quebra em código de enquadramento com hífen espaçado
        frags = [(10.0, 20.0, "Art. 182 | Cód. 502"), (25.0, 30.0, "-"), (35.0, 45.0, "91")]
        res = join_line_fragments(frags, gap_threshold=2.5)
        self.assertIn("502-91", res)

    def test_unificar_linhas_e_hifens(self):
        # Palavra quebrada com hífen no final de linha
        linhas = [
            "Veículo parado sobre a área de cruzamen-",
            "to de vias com prejuízo da circulação.",
        ]
        res = unificar_linhas_e_hifens(linhas)
        self.assertEqual(
            res,
            "Veículo parado sobre a área de cruzamento de vias com prejuízo da circulação.",
        )

    def test_unificar_linhas_sem_hifens(self):
        linhas = [
            "Primeira linha do parágrafo",
            "segunda linha contínua.",
        ]
        res = unificar_linhas_e_hifens(linhas)
        self.assertEqual(res, "Primeira linha do parágrafo segunda linha contínua.")


class TestLayoutAnalyzer(unittest.TestCase):
    def test_get_column_channel(self):
        # Mock do analisador com limites dinâmicos conhecidos
        analyzer = LayoutAnalyzer.__new__(LayoutAnalyzer)
        analyzer.col_bounds = [165.0, 298.0, 433.0]

        # Canal 0: xc < 165
        self.assertEqual(analyzer.get_column_channel(50.0, 100.0), 0)
        # Canal 1: 165 <= xc < 298
        self.assertEqual(analyzer.get_column_channel(170.0, 230.0), 1)
        # Canal 2: 298 <= xc < 433
        self.assertEqual(analyzer.get_column_channel(320.0, 380.0), 2)
        # Canal 3: xc >= 433
        self.assertEqual(analyzer.get_column_channel(450.0, 500.0), 3)

    def test_detect_column_bounds_fallback(self):
        # Sem objetos na página, deve utilizar fallback proporcional (28%, 50%, 73%)
        page_ext = PaginaExtraida(
            largura=600.0,
            altura=800.0,
            retangulos=[],
            linhas_vetoriais=[],
        )

        analyzer = LayoutAnalyzer.__new__(LayoutAnalyzer)
        analyzer.page_ext = page_ext
        analyzer.width = 600.0

        bounds = analyzer.detect_column_bounds()
        self.assertEqual(len(bounds), 3)
        self.assertAlmostEqual(bounds[0], 600.0 * 0.28)
        self.assertAlmostEqual(bounds[1], 600.0 * 0.50)
        self.assertAlmostEqual(bounds[2], 600.0 * 0.73)

    def test_detect_column_bounds_com_tracos_verticais(self):
        # Com linhas vetoriais presentes na página
        linhas = [
            # Linha margem esquerda
            (35.0, 100.0, 36.0, 700.0),
            # Divisória 1: ~168.0 (dentro da tolerância de 5% de 600*0.28 = 168)
            (168.0, 100.0, 169.0, 700.0),
            # Divisória 2: ~302.0 (dentro da tolerância de 5% de 600*0.50 = 300)
            (302.0, 100.0, 303.0, 700.0),
            # Divisória 3: ~437.0 (dentro da tolerância de 5% de 600*0.73 = 438)
            (437.0, 100.0, 438.0, 700.0),
            # Linha margem direita
            (560.0, 100.0, 561.0, 700.0),
        ]
        page_ext = PaginaExtraida(
            largura=600.0,
            altura=800.0,
            retangulos=[],
            linhas_vetoriais=linhas,
        )

        analyzer = LayoutAnalyzer.__new__(LayoutAnalyzer)
        analyzer.page_ext = page_ext
        analyzer.width = 600.0

        bounds = analyzer.detect_column_bounds()
        self.assertEqual(len(bounds), 3)
        self.assertAlmostEqual(bounds[0], 168.5)
        self.assertAlmostEqual(bounds[1], 302.5)
        self.assertAlmostEqual(bounds[2], 437.5)

    def test_detect_column_bounds_erro_real_exposto(self):
        # Garante que erros reais em page_ext não são silenciados por broad except
        analyzer = LayoutAnalyzer.__new__(LayoutAnalyzer)
        analyzer.page_ext = None
        analyzer.width = 600.0
        with self.assertRaises(AttributeError):
            analyzer.detect_column_bounds()

    def test_regex_column_headers(self):
        # Verifica se as regexes de cabeçalho casam corretamente
        self.assertTrue(RE_COLUMN_HEADER.match("Quando Autuar"))
        self.assertTrue(RE_COLUMN_HEADER.match("quando autuar:"))
        self.assertTrue(RE_COLUMN_HEADER.match("Quando Não Autuar"))
        self.assertTrue(RE_COLUMN_HEADER.match("Definições e Procedimentos"))
        self.assertTrue(RE_COLUMN_HEADER.match("Exemplos do campo Observações do AIT:"))
        self.assertFalse(RE_COLUMN_HEADER.match("1. Autuar condutor sem cinto"))


class TestFuncoesPurasExtracao(unittest.TestCase):
    def test_parse_metadados_markdown(self):
        md = (
            "| Infrator: Condutor | Competência: Órgão Municipal |\n"
            "| Constatação da Infração: Mediante abordagem | Quando autuar |"
        )
        res = parse_metadados_markdown(md)
        self.assertEqual(res.get("infrator"), "Condutor")
        self.assertEqual(res.get("constatacao_infracao"), "Mediante abordagem")

    def test_extrair_linhas_colunas_pagina_basica(self):
        retangulos = [
            RetanguloTexto(x0=50.0, y0=200.0, x1=120.0, y1=212.0, texto="Item 1 autuar"),
        ]
        page_ext = PaginaExtraida(
            largura=595.0,
            altura=842.0,
            retangulos=retangulos,
            linhas_vetoriais=[],
        )
        cols_lines, ic_y = extrair_linhas_colunas_pagina(page_ext, is_first_page=False)
        self.assertIn("Item 1 autuar", cols_lines[0])
        self.assertEqual(cols_lines[1], [])
        self.assertEqual(cols_lines[2], [])
        self.assertEqual(cols_lines[3], [])


if __name__ == "__main__":
    unittest.main()

