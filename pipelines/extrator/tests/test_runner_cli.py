"""
Testes unitários para o runner e cli do Extrator MBFT.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from mbft_extrator.models import FichaMapeada
from mbft_extrator.runner import (
    parse_faixa,
    filtrar_por_faixa,
    construir_tarefas,
    TarefaFicha,
)
from mbft_extrator.config import (
    LayoutConfig,
    DEFAULT_LAYOUT_CONFIG,
    PAGINA_INICIO_PARTE_GERAL,
    PAGINA_FIM_PARTE_GERAL,
    PAGINA_INICIO_FICHAS,
)


class TestExtratorRunner(unittest.TestCase):
    def setUp(self):
        self.fichas_mock = [
            FichaMapeada(identificador="500-20", codigo="500-20", pag_ini=32, pag_fim=33, paginas=[32, 33]),
            FichaMapeada(identificador="501-00", codigo="501-00", pag_ini=34, pag_fim=35, paginas=[34, 35]),
            FichaMapeada(identificador="502-91", codigo="502-91", pag_ini=36, pag_fim=37, paginas=[36, 37]),
            FichaMapeada(identificador="502-92", codigo="502-92", pag_ini=38, pag_fim=39, paginas=[38, 39]),
        ]

    def test_parse_faixa_valida(self):
        ini, fim = parse_faixa("32-35")
        self.assertEqual(ini, 32)
        self.assertEqual(fim, 35)

    def test_parse_faixa_invalida(self):
        with self.assertRaises(ValueError):
            parse_faixa("invalido")
        with self.assertRaises(ValueError):
            parse_faixa("32-abc")
        with self.assertRaises(ValueError):
            parse_faixa("32")

    def test_filtrar_por_paginas(self):
        filtradas = filtrar_por_faixa(self.fichas_mock, paginas="34-36")
        self.assertEqual(len(filtradas), 2)
        self.assertEqual(filtradas[0].codigo, "501-00")
        self.assertEqual(filtradas[1].codigo, "502-91")

    def test_filtrar_por_indices_fichas(self):
        filtradas = filtrar_por_faixa(self.fichas_mock, fichas="1-2")
        self.assertEqual(len(filtradas), 2)
        self.assertEqual(filtradas[0].codigo, "500-20")
        self.assertEqual(filtradas[1].codigo, "501-00")

    def test_filtrar_sem_filtros(self):
        filtradas = filtrar_por_faixa(self.fichas_mock)
        self.assertEqual(len(filtradas), 4)

    def test_construir_tarefas(self):
        tarefas = construir_tarefas(
            mapeadas=self.fichas_mock[:2],
            pdf_path=Path("dummy.pdf"),
            pdf_hash="fakehash123",
            imagens_dir=Path("img_dir"),
            cache_fichas_dir=Path("cache_dir"),
            pasta_individuais=Path("indiv_dir"),
            force=False,
        )
        self.assertEqual(len(tarefas), 2)
        self.assertIsInstance(tarefas[0], TarefaFicha)
        self.assertEqual(tarefas[0].pdf_hash, "fakehash123")
        self.assertEqual(tarefas[0].ficha_mapeada.codigo, "500-20")
        self.assertEqual(tarefas[0].pasta_individuais, "indiv_dir")
        self.assertFalse(tarefas[0].force)

    def test_fatiador_invalida_cache_quando_regex_muda(self):
        import json
        import tempfile
        from mbft_extrator.fatiador import mapear_fichas_no_pdf, REGEX_ENQUADRAMENTO
        from mbft_extrator.utils import VERSAO_PIPELINE

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            pdf_file = tmp / "dummy.pdf"
            pdf_file.write_bytes(b"%PDF-1.4 dummy")
            cache_file = tmp / "mapa_fichas.json"
            # Cache com regex antiga (sem 'regex_enquadramento' ou com padrão divergente)
            cache_file.write_text(
                json.dumps({
                    "pdf_sha256": "ignored_by_patch",
                    "versao_pipeline": VERSAO_PIPELINE,
                    "regex_enquadramento": "old_regex_pattern",
                    "fichas": [{"codigo": "500-20", "pag_ini": 32, "pag_fim": 33, "identificador": "500-20"}],
                }),
                encoding="utf-8",
            )

            with (
                patch("mbft_extrator.fatiador.calcular_hash_pdf", return_value="ignored_by_patch"),
                patch("mbft_extrator.fatiador.pdfium.PdfDocument") as mock_doc_cls,
            ):
                mock_doc = MagicMock()
                mock_doc.__len__.return_value = 32
                mock_page = MagicMock()
                mock_tp = MagicMock()
                mock_tp.get_text_range.return_value = "Código de Enquadramento: 516-91"
                mock_page.get_textpage.return_value = mock_tp
                mock_doc.__getitem__.return_value = mock_page
                mock_doc_cls.return_value = mock_doc

                res = mapear_fichas_no_pdf(pdf_file, cache_path=cache_file, force=False)
                self.assertEqual(len(res), 1)
                self.assertEqual(res[0].codigo, "516-91")
                saved = json.loads(cache_file.read_text(encoding="utf-8"))
                self.assertEqual(saved["regex_enquadramento"], REGEX_ENQUADRAMENTO.pattern)

    def test_extrair_ficha_completa_remove_imagens_orfas_ao_reextrair(self):
        import tempfile
        from mbft_extrator.models import CampoNormativo, MetadadosCabecalho
        from mbft_extrator.pipeline import ColunasNormativas, Conversores, extrair_ficha_completa

        with tempfile.TemporaryDirectory() as tmpdir:
            img_dir = Path(tmpdir)
            orfa_1 = img_dir / "ficha518-52_1.png"
            orfa_2 = img_dir / "ficha518-52_2.png"
            outra = img_dir / "ficha519-30_1.png"
            orfa_1.write_bytes(b"png1")
            orfa_2.write_bytes(b"png2")
            outra.write_bytes(b"png3")

            mapeada = FichaMapeada(identificador="518-52", codigo="518-52", pag_ini=125, pag_fim=132)
            meta_mock = MetadadosCabecalho(
                tipificacao_resumida="Deixar de usar cinto",
                codigo_enquadramento="518-52",
                amparo_legal="Art. 167.",
                tipificacao_enquadramento="Deixar o condutor de usar o cinto",
                gravidade="Grave",
                penalidade="Multa",
                medida_administrativa="Retenção",
                pode_configurar_crime_transito="NÃO",
                infrator="Condutor",
                competencia="Órgão Estadual",
                pontuacao="5",
                constatacao_infracao="Mediante abordagem",
            )
            vazio = CampoNormativo(texto="", itens=[])
            cols_mock = ColunasNormativas(vazio, vazio, vazio, vazio)

            with (
                patch("mbft_extrator.pipeline._extrair_metadados", return_value=meta_mock),
                patch("mbft_extrator.pipeline.detectar_limites_ic", return_value=(False, 125, None)),
                patch("mbft_extrator.pipeline._extrair_colunas_normativas", return_value=cols_mock),
            ):
                res = extrair_ficha_completa(
                    doc=MagicMock(),
                    conversores=Conversores(),
                    pdf_path=Path("dummy.pdf"),
                    mapeada=mapeada,
                    imagens_dir=img_dir,
                )
                self.assertEqual(res.ficha.imagens, [])
                self.assertFalse(orfa_1.exists())
                self.assertFalse(orfa_2.exists())
                self.assertTrue(outra.exists())



class TestExtratorCli(unittest.TestCase):
    @patch("mbft_extrator.cli.executar_extracao_geral")
    def test_cli_subcomando_geral(self, mock_geral):
        from mbft_extrator.cli import main
        with patch("sys.argv", ["extrair.py", "--pdf", "test.pdf", "geral", "--saida-md", "saida.md"]):
            main()
            mock_geral.assert_called_once_with(Path("test.pdf"), Path("saida.md"))

    @patch("mbft_extrator.cli.executar_extracao_fichas")
    def test_cli_subcomando_fichas(self, mock_fichas):
        from mbft_extrator.cli import main
        with patch("sys.argv", ["extrair.py", "--pdf", "test.pdf", "fichas", "--saida-json", "saida.json", "--paginas", "32-35", "--workers", "2", "--force"]):
            main()
            mock_fichas.assert_called_once_with(
                pdf_path=Path("test.pdf"),
                saida_json=Path("saida.json"),
                paginas="32-35",
                fichas=None,
                salvar_individuais=False,
                force=True,
                workers=2,
            )


class TestConfig(unittest.TestCase):
    def test_default_layout_config_valores(self):
        cfg = DEFAULT_LAYOUT_CONFIG
        self.assertEqual(cfg.col_bounds_pct, [0.28, 0.50, 0.73])
        self.assertEqual(cfg.y_top_limit_default, 40.0)
        self.assertEqual(cfg.y_min_image, 30.0)
        self.assertEqual(cfg.min_img_size, 25.0)
        self.assertEqual(cfg.y_limit_header, 350.0)
        self.assertEqual(cfg.y_top_primeira_pagina, 715.0)
        self.assertEqual(cfg.margem_esquerda_titulo, 60.0)
        self.assertEqual(cfg.margem_esquerda_secao_numerada, 80.0)

    def test_paginacao_mbft_coerencia(self):
        self.assertEqual(PAGINA_INICIO_PARTE_GERAL, 1)
        self.assertEqual(PAGINA_FIM_PARTE_GERAL, 31)
        self.assertEqual(PAGINA_INICIO_FICHAS, 32)
        self.assertEqual(PAGINA_INICIO_FICHAS, PAGINA_FIM_PARTE_GERAL + 1)


if __name__ == "__main__":
    unittest.main()

