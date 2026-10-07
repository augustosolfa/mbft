"""
Testes unitários para TextJoiner, LayoutAnalyzer e desacoplamento SRP do stitching.
"""

import unittest
from mbft_extrator.text_joiner import TextJoiner, _join_line_fragments, unificar_linhas_e_hifens
from mbft_extrator.layout_analyzer import LayoutAnalyzer
from mbft_extrator.stitching import (
    extrair_linhas_colunas_pagina,
    _join_line_fragments as stitching_join,
    unificar_linhas_e_hifens as stitching_unificar,
)


class TestTextJoiner(unittest.TestCase):
    def test_join_horizontal_fragments_gap_menor_que_limiar(self):
        # Dois fragmentos com gap de 1.0 pt (< 2.5 pt) sem espaço explícito
        frags = [(10.0, 20.0, "Trans"), (21.0, 35.0, "portador")]
        res = TextJoiner.join_horizontal_fragments(frags, gap_threshold=2.5)
        self.assertEqual(res, "Transportador")

    def test_join_horizontal_fragments_gap_maior_com_espaco(self):
        # Dois fragmentos com gap de 5.0 pt (>= 2.5 pt)
        frags = [(10.0, 20.0, "Auto"), (25.0, 35.0, "de")]
        res = TextJoiner.join_horizontal_fragments(frags, gap_threshold=2.5)
        self.assertEqual(res, "Auto de")

    def test_join_horizontal_fragments_com_espaco_existente(self):
        # Gap pequeno (< 2.5 pt), mas o primeiro fragmento já termina em espaço
        frags = [(10.0, 20.0, "Veículo "), (21.0, 35.0, "parado")]
        res = TextJoiner.join_horizontal_fragments(frags, gap_threshold=2.5)
        self.assertEqual(res, "Veículo parado")

    def test_join_horizontal_fragments_reuniao_codigo_enquadramento(self):
        # Quebra em código de enquadramento com hífen espaçado
        frags = [(10.0, 20.0, "Art. 182 | Cód. 502"), (25.0, 30.0, "-"), (35.0, 45.0, "91")]
        res = TextJoiner.join_horizontal_fragments(frags, gap_threshold=2.5)
        self.assertIn("502-91", res)

    def test_unificar_linhas_e_hifens(self):
        # Palavra quebrada com hífen no final de linha
        linhas = [
            "Veículo parado sobre a área de cruzamen-",
            "to de vias com prejuízo da circulação.",
        ]
        res = TextJoiner.unificar_linhas_e_hifens(linhas)
        self.assertEqual(
            res,
            "Veículo parado sobre a área de cruzamento de vias com prejuízo da circulação.",
        )

    def test_unificar_linhas_sem_hifens(self):
        linhas = [
            "Primeira linha do parágrafo",
            "segunda linha contínua.",
        ]
        res = TextJoiner.unificar_linhas_e_hifens(linhas)
        self.assertEqual(res, "Primeira linha do parágrafo segunda linha contínua.")

    def test_compatibilidade_funcoes_legadas(self):
        # Garante que os aliases legados são equivalentes
        frags = [(10.0, 20.0, "Auto"), (25.0, 35.0, "de")]
        self.assertEqual(_join_line_fragments(frags), TextJoiner.join_horizontal_fragments(frags))
        self.assertEqual(stitching_join(frags), TextJoiner.join_horizontal_fragments(frags))
        self.assertEqual(stitching_unificar(["a-", "b"]), "ab")


class TestLayoutAnalyzer(unittest.TestCase):
    def test_get_column_channel(self):
        # Canal 0: xc < 165
        self.assertEqual(LayoutAnalyzer.get_column_channel(50.0, 100.0), 0)
        # Canal 1: 165 <= xc < 298
        self.assertEqual(LayoutAnalyzer.get_column_channel(170.0, 230.0), 1)
        # Canal 2: 298 <= xc < 433
        self.assertEqual(LayoutAnalyzer.get_column_channel(320.0, 380.0), 2)
        # Canal 3: xc >= 433
        self.assertEqual(LayoutAnalyzer.get_column_channel(450.0, 500.0), 3)

    def test_regex_column_headers(self):
        # Verifica se as regexes de cabeçalho casam corretamente
        self.assertTrue(LayoutAnalyzer.RE_COLUMN_HEADER.match("Quando Autuar"))
        self.assertTrue(LayoutAnalyzer.RE_COLUMN_HEADER.match("quando autuar:"))
        self.assertTrue(LayoutAnalyzer.RE_COLUMN_HEADER.match("Quando Não Autuar"))
        self.assertTrue(LayoutAnalyzer.RE_COLUMN_HEADER.match("Definições e Procedimentos"))
        self.assertTrue(LayoutAnalyzer.RE_COLUMN_HEADER.match("Exemplos do campo Observações do AIT:"))
        self.assertFalse(LayoutAnalyzer.RE_COLUMN_HEADER.match("1. Autuar condutor sem cinto"))


if __name__ == "__main__":
    unittest.main()
