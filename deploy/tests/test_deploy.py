import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mbft_core.models.indexacao import ChunkMetadados, ChunkPayload
from mbft_core.paths import RAIZ_REPO
from mbft_deploy.cli import _carregar_env_de_deploy, main
from mbft_deploy.exporters import (
    atualizar_config_js_site,
    dividir_jsonl_vectorize,
    exportar_fts_chunks_sql,
)
from mbft_deploy.wrangler import (
    fazer_deploy_api,
    fazer_deploy_d1,
    fazer_deploy_site,
    fazer_deploy_vectorize,
    garantir_projeto_pages,
    invocacao_do_comando,
    provisionar_recursos_cloudflare,
    verificar_status_recursos_cloudflare,
)


def _criar_payload_exemplo(chunk_id: str = "751-01_QUANDO_AUTUAR_ITEM_1") -> ChunkPayload:
    return ChunkPayload(
        id=chunk_id,
        values=[0.1] * 1024,
        metadata=ChunkMetadados(
            origem_id="751-01",
            secao="QUANDO_AUTUAR",
            codigo="751-01",
            artigo="Art. 95",
            gravidade="NAO_APLICAVEL",
            infratores=["PESSOA_FISICA_OU_JURIDICA"],
            competencias=["MUNICIPAL"],
            texto_contextualizado="Obra d'água na via sem permissão prévia.",
            natureza_regra="HIPOTESE_AUTUACAO",
        ),
    )


class TestMbftDeploy(unittest.TestCase):
    def test_exportar_fts_chunks_sql_gera_dump_idempotente_e_compativel_com_sqlite_fts5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            sql_file = tmp / "fts_chunks.sql"

            p1 = _criar_payload_exemplo("751-01_QUANDO_AUTUAR_ITEM_1")
            p2 = _criar_payload_exemplo("751-01_EMENTA")
            jsonl_file.write_text(
                p1.model_dump_json() + "\n" + p2.model_dump_json() + "\n",
                encoding="utf-8",
            )

            total = exportar_fts_chunks_sql(jsonl_file, sql_file, batch_size=1)
            self.assertEqual(total, 2)
            self.assertTrue(sql_file.exists())

            sql_content = sql_file.read_text(encoding="utf-8")
            self.assertIn("DELETE FROM fts_chunks;", sql_content)
            self.assertIn("Obra d''água na via", sql_content)
            self.assertNotIn("BEGIN TRANSACTION", sql_content.upper())

            # Executa schema.sql real da API + fts_chunks.sql num SQLite FTS5 em memória
            schema_sql = (RAIZ_REPO / "apps" / "api" / "schema.sql").read_text(encoding="utf-8")
            conn = sqlite3.connect(":memory:")
            try:
                conn.executescript(schema_sql)
                conn.executescript(sql_content)
                # Executar segunda vez prova idempotência do DELETE FROM fts_chunks;
                conn.executescript(sql_content)
                rows = conn.execute(
                    "SELECT id, codigo FROM fts_chunks WHERE fts_chunks MATCH 'agua'"
                ).fetchall()
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0][1], "751-01")
            finally:
                conn.close()

    def test_exportador_e_vectorize_recusam_artefato_debug(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            debug_file = tmp / "embeddings_debug.jsonl"
            debug_file.write_text("{}\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                exportar_fts_chunks_sql(debug_file, tmp / "fts.sql")

            with self.assertRaises(ValueError):
                fazer_deploy_vectorize(debug_file)

            with self.assertRaises(SystemExit) as cm:
                main(["export-d1", "--input", str(debug_file)])
            self.assertNotEqual(cm.exception.code, 0)

    def test_atualizar_config_js_site_remove_barra_final(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            site_dir = Path(tmpdir)
            cfg = atualizar_config_js_site(site_dir, "https://mbft-api.exemplo.workers.dev///")
            texto = cfg.read_text(encoding="utf-8")
            self.assertIn('"https://mbft-api.exemplo.workers.dev"', texto)

    def test_comandos_wrangler_vectorize_d1_api_e_site(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            sql_file = tmp / "schema.sql"
            api_dir = tmp / "api"
            site_dir = tmp / "site"
            api_dir.mkdir()
            site_dir.mkdir()
            jsonl_file.write_text(_criar_payload_exemplo().model_dump_json() + "\n", encoding="utf-8")
            sql_file.write_text("SELECT 1;\n", encoding="utf-8")
            (api_dir / "wrangler.jsonc").write_text("{}", encoding="utf-8")

            with patch("mbft_deploy.wrangler.rodar_comando_wrangler") as mock_cmd:
                fazer_deploy_vectorize(jsonl_file)
                fazer_deploy_d1(sql_file, remote=True)
                fazer_deploy_d1(sql_file, remote=False)
                fazer_deploy_api(api_dir=api_dir)
                fazer_deploy_site(site_dir=site_dir, project_name="mbft-site", api_url="https://api.teste.dev")

                self.assertEqual(
                    mock_cmd.call_args_list[0][0][0],
                    ["wrangler", "vectorize", "insert", "mbft-embeddings", "--file", str(jsonl_file)],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[1][0][0],
                    ["wrangler", "d1", "execute", "mbft-d1", "--file", str(sql_file), "--remote"],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[2][0][0],
                    ["wrangler", "d1", "execute", "mbft-d1", "--file", str(sql_file), "--local"],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[3][0][0],
                    ["wrangler", "deploy"],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[4][0][0],
                    [
                        "wrangler",
                        "pages",
                        "project",
                        "create",
                        "mbft-site",
                        "--production-branch=main",
                    ],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[5][0][0],
                    ["wrangler", "pages", "deploy", str(site_dir), "--project-name=mbft-site"],
                )
                self.assertIn(
                    '"https://api.teste.dev"',
                    (site_dir / "config.js").read_text(encoding="utf-8"),
                )

    def test_provisionar_recursos_atualiza_wrangler_jsonc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft-api",
                        "d1_databases": [{"binding": "DB", "database_name": "mbft-d1", "database_id": "0000"}],
                    }
                ),
                encoding="utf-8",
            )

            saidas = [
                'database_id = "12345678-1234-1234-1234-123456789abc"',
                "Created index mbft-embeddings",
                "",
            ]
            with patch("mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas):
                ids = provisionar_recursos_cloudflare(wrangler_config_path=wrangler_file)

            self.assertEqual(ids["database_id"], "12345678-1234-1234-1234-123456789abc")

            atualizado = json.loads(wrangler_file.read_text(encoding="utf-8"))
            self.assertEqual(
                atualizado["d1_databases"][0]["database_id"],
                "12345678-1234-1234-1234-123456789abc",
            )

    def test_status_verifica_recursos_sem_criar_nada(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft-api",
                        "d1_databases": [
                            {
                                "binding": "DB",
                                "database_name": "mbft-d1",
                                "database_id": "12345678-1234-1234-1234-123456789abc",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            saidas = [
                json.dumps([{"uuid": "12345678-1234-1234-1234-123456789abc", "name": "mbft-d1"}]),
                json.dumps(
                    [
                        {
                            "name": "mbft-embeddings",
                            "config": {"dimensions": 1024, "metric": "cosine"},
                        }
                    ]
                ),
                json.dumps([{"Project Name": "mbft-site"}]),
                json.dumps([{"id": "deployment-1"}]),
            ]
            with patch("mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas) as mock_cmd:
                status = verificar_status_recursos_cloudflare(
                    wrangler_config_path=wrangler_file,
                )

            self.assertTrue(status["ok"])
            self.assertEqual(status["checks"], {"d1": True, "vectorize": True, "pages": True, "worker": True})
            self.assertTrue(all("create" not in call.args[0] for call in mock_cmd.call_args_list))

    def test_status_aceita_formatos_diretos_das_propriedades(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft-api",
                        "d1_databases": [{"database_name": "mbft-d1", "database_id": "id-local"}],
                    }
                ),
                encoding="utf-8",
            )
            saidas = [
                json.dumps([{"name": "mbft-d1", "database_id": "id-local"}]),
                json.dumps([{"name": "mbft-embeddings", "dimensions": 1024, "metric": "cosine"}]),
                json.dumps([{"name": "mbft-site"}]),
                json.dumps([{"id": "deployment-1"}]),
            ]
            with patch("mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas):
                status = verificar_status_recursos_cloudflare(wrangler_config_path=wrangler_file)

            self.assertTrue(status["ok"])

    def test_status_reprova_recurso_ausente_ou_configuracao_invalida(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft-api",
                        "d1_databases": [{"database_name": "mbft-d1", "database_id": "id-local"}],
                    }
                ),
                encoding="utf-8",
            )
            saidas = [
                json.dumps([{"name": "mbft-d1", "database_id": "id-remoto"}]),
                json.dumps([{"name": "mbft-embeddings", "dimensions": 768, "metric": "cosine"}]),
                json.dumps([]),
                json.dumps([]),
            ]
            with patch("mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas):
                status = verificar_status_recursos_cloudflare(wrangler_config_path=wrangler_file)

            self.assertFalse(status["ok"])
            self.assertEqual(status["checks"], {"d1": False, "vectorize": False, "pages": False, "worker": False})

    def test_dividir_jsonl_vectorize_respeita_limite_sem_cortar_linhas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            linhas = [
                _criar_payload_exemplo(f"751-01_CHUNK_{indice}").model_dump_json()
                for indice in range(5)
            ]
            jsonl_file.write_bytes(b"\n".join(linha.encode("utf-8") for linha in linhas) + b"\n")

            limite = (len(linhas[0].encode("utf-8")) + 1) * 2
            partes = dividir_jsonl_vectorize(jsonl_file, tmp / "vectorize", limite_bytes=limite)

            self.assertEqual([p.name for p in partes], ["parte_01.jsonl", "parte_02.jsonl", "parte_03.jsonl"])
            for parte in partes:
                self.assertLessEqual(parte.stat().st_size, limite)
                for linha in parte.read_text(encoding="utf-8").splitlines():
                    ChunkPayload.model_validate_json(linha)
            self.assertEqual(
                sum(len(p.read_text(encoding="utf-8").splitlines()) for p in partes),
                len(linhas),
            )

    def test_dividir_jsonl_vectorize_recusa_id_acima_do_limite_do_vectorize(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            jsonl_file.write_text(
                _criar_payload_exemplo("x" * 65).model_dump_json() + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                dividir_jsonl_vectorize(jsonl_file, tmp / "vectorize")

    def test_garantir_projeto_pages_tolera_apenas_projeto_existente(self):
        with patch(
            "mbft_deploy.wrangler.rodar_comando_wrangler",
            side_effect=RuntimeError(
                "A request to the Cloudflare API failed: A project with this name already exists. [code: 8000002]"
            ),
        ):
            garantir_projeto_pages("mbft-site")

        with patch(
            "mbft_deploy.wrangler.rodar_comando_wrangler",
            side_effect=RuntimeError("Authentication error [code: 10000]"),
        ):
            with self.assertRaises(RuntimeError):
                garantir_projeto_pages("mbft-site")

    def test_carregar_env_de_deploy_limita_variaveis_e_preserva_o_shell(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            (raiz / ".env").write_text(
                "CLOUDFLARE_API_TOKEN=token-do-arquivo\n"
                "CLOUDFLARE_ACCOUNT_ID=conta-do-arquivo\n"
                "GEMINI_API_KEY=segredo-de-outro-passo\n",
                encoding="utf-8",
            )

            with patch("mbft_deploy.cli.RAIZ_REPO", raiz), patch.dict(
                os.environ, {"CLOUDFLARE_ACCOUNT_ID": "conta-do-shell"}, clear=True
            ):
                _carregar_env_de_deploy()

                self.assertEqual(os.environ["CLOUDFLARE_API_TOKEN"], "token-do-arquivo")
                self.assertEqual(os.environ["CLOUDFLARE_ACCOUNT_ID"], "conta-do-shell")
                self.assertNotIn("GEMINI_API_KEY", os.environ)

    def test_invocacao_do_comando_delega_script_cmd_ao_shell(self):
        with patch(
            "mbft_deploy.wrangler.shutil.which",
            return_value=r"C:\Program Files\nodejs\npx.cmd",
        ):
            invocacao, usar_shell = invocacao_do_comando(
                ["npx", "wrangler", "d1", "execute", "D:/pasta com espaco/schema.sql"],
                windows=True,
            )

        self.assertTrue(usar_shell)
        self.assertEqual(
            invocacao,
            r'"C:\Program Files\nodejs\npx.cmd" wrangler d1 execute "D:/pasta com espaco/schema.sql"',
        )
        self.assertEqual(
            invocacao_do_comando(["npx", "wrangler"], windows=False),
            (["npx", "wrangler"], False),
        )

    def test_cli_tudo_dry_run_executa_fluxo_completo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            sql_out = tmp / "fts_chunks.sql"
            schema_file = tmp / "schema.sql"
            api_dir = tmp / "api"
            site_dir = tmp / "site"
            api_dir.mkdir()
            site_dir.mkdir()

            jsonl_file.write_text(_criar_payload_exemplo().model_dump_json() + "\n", encoding="utf-8")
            schema_file.write_text("SELECT 1;\n", encoding="utf-8")
            (api_dir / "wrangler.jsonc").write_text("{}", encoding="utf-8")

            main(
                [
                    "tudo",
                    "--input",
                    str(jsonl_file),
                    "--sql-output",
                    str(sql_out),
                    "--schema",
                    str(schema_file),
                    "--api-dir",
                    str(api_dir),
                    "--site-dir",
                    str(site_dir),
                    "--dry-run",
                ]
            )
            self.assertTrue(sql_out.exists())


if __name__ == "__main__":
    unittest.main()
