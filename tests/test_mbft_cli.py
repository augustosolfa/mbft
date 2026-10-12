import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from mbft.cli import main


class TestMbftUnifiedCli(unittest.TestCase):
    def test_sem_argumentos_exibe_help_sem_erro(self):
        stdout = StringIO()
        stderr = StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            main([])

        self.assertIn("usage: mbft", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_deploy_help_lista_subcomandos_e_explica_escopo_das_opcoes(self):
        stdout = StringIO()

        with redirect_stdout(stdout), self.assertRaises(SystemExit) as contexto:
            main(["deploy", "-h"])

        self.assertEqual(contexto.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn("export-d1", help_text)
        self.assertIn("provision", help_text)
        self.assertIn("data -> api", help_text)
        self.assertIn("MBFT_HOSTNAME", help_text)
        self.assertIn("não são globais", help_text)
        self.assertIn("mbft deploy <subcomando> --help", help_text)

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
            patch(
                "mbft_extrator.cli.main",
                side_effect=lambda *a, **kw: ordem.append("extrator"),
            ),
            patch(
                "mbft_enriquecedor.main.main",
                side_effect=lambda *a, **kw: ordem.append("enriquecedor"),
            ),
            patch(
                "mbft_indexador.cli.main",
                side_effect=lambda *a, **kw: ordem.append("indexador"),
            ),
            patch(
                "mbft_ssg.builder.run_build",
                side_effect=lambda *a, **kw: ordem.append("ssg"),
            ),
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
            self.assertTrue(
                any(
                    "--ignore=" in item and "test_integracao.py" in item
                    for item in chamado
                )
            )

    def test_testes_tudo_passa_raiz_repo_como_alvo(self):
        from mbft_core.paths import RAIZ_REPO

        with patch("pytest.main", return_value=0) as mock_pytest:
            main(["testes", "tudo"])
            chamado = mock_pytest.call_args[0][0]
            self.assertIn(str(RAIZ_REPO), chamado)
            self.assertFalse(any("--ignore=" in item for item in chamado))


class TestCarregamentoEnvLocal(unittest.TestCase):
    def test_carrega_env_da_raiz_sem_sobrescrever_o_shell(self):
        import tempfile
        from pathlib import Path

        from mbft.cli import _carregar_env_local

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / ".env").write_text(
                "GEMINI_API_KEY=chave-do-arquivo\n# comentário\nVAR_TESTE=do-arquivo\n",
                encoding="utf-8",
            )
            env = {"VAR_TESTE": "do-shell"}
            with patch("mbft.cli.RAIZ_REPO", raiz):
                _carregar_env_local(env)

            self.assertEqual(env["GEMINI_API_KEY"], "chave-do-arquivo")
            self.assertEqual(
                env["VAR_TESTE"],
                "do-shell",
                "O ambiente do shell deve ter precedência.",
            )

    def test_carrega_env_ignora_ausencia_do_arquivo(self):
        import tempfile
        from pathlib import Path

        from mbft.cli import _carregar_env_local

        with tempfile.TemporaryDirectory() as tmp:
            env = {}
            with patch("mbft.cli.RAIZ_REPO", Path(tmp)):
                _carregar_env_local(env)
            self.assertEqual(env, {})

    def test_dev_api_propaga_env_local_para_uvicorn(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / ".env").write_text(
                "GEMINI_API_KEY=chave-do-arquivo\n", encoding="utf-8"
            )
            with (
                patch("mbft.cli.RAIZ_REPO", raiz),
                patch("mbft.cli.subprocess.run") as mock_run,
            ):
                main(["dev", "api", "--no-reload"])

            env_passado = mock_run.call_args.kwargs["env"]
            self.assertEqual(env_passado["GEMINI_API_KEY"], "chave-do-arquivo")
            self.assertNotIn(
                "--reload",
                mock_run.call_args.args[0],
                "--no-reload deve suprimir o auto-reload.",
            )


if __name__ == "__main__":
    unittest.main()
