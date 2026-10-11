import unittest
from unittest.mock import patch

from mbft.cli import main


class TestMbftUnifiedCli(unittest.TestCase):
    def test_pipeline_extrator_delega_com_default_tudo(self):
        with patch("mbft_extrator.cli.main") as mock_ext:
            main(["pipeline", "extrator", "--workers", "2", "--force"])
            args_passados = mock_ext.call_args[0][0]
            self.assertIn("tudo", args_passados)
            self.assertIn("--workers", args_passados)
            self.assertIn("2", args_passados)
            self.assertIn("--force", args_passados)

    def test_pipeline_tudo_encadeia_quatro_etapas_na_ordem(self):
        ordem = []
        with (
            patch("mbft_extrator.cli.main", side_effect=lambda *a, **kw: ordem.append("extrator")),
            patch("mbft_enriquecedor.main.main", side_effect=lambda *a, **kw: ordem.append("enriquecedor")),
            patch("mbft_indexador.cli.main", side_effect=lambda *a, **kw: ordem.append("indexador")),
            patch("mbft_ssg.builder.run_build", side_effect=lambda *a, **kw: ordem.append("ssg")),
        ):
            main(["pipeline", "tudo", "--skip-embeddings"])
        self.assertEqual(ordem, ["extrator", "enriquecedor", "indexador", "ssg"])

    def test_deploy_repassa_argumentos_para_mbft_deploy(self):
        with patch("mbft_deploy.cli.main") as mock_dep:
            main(["deploy", "tudo", "--dry-run"])
            mock_dep.assert_called_once_with(["tudo", "--dry-run"])

    def test_testes_governanca_chama_pytest_no_arquivo_correto(self):
        with patch("pytest.main", return_value=0) as mock_pytest:
            main(["testes", "governanca"])
            chamado = mock_pytest.call_args[0][0]
            self.assertTrue(any("test_governanca_docs.py" in item for item in chamado))

    def test_testes_rapidos_ignora_test_integracao_gpu(self):
        with patch("pytest.main", return_value=0) as mock_pytest:
            main(["testes"])
            chamado = mock_pytest.call_args[0][0]
            self.assertTrue(any("--ignore=" in item and "test_integracao.py" in item for item in chamado))


if __name__ == "__main__":
    unittest.main()
