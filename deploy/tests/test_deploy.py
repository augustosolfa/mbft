import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mbft_core.models.indexacao import ChunkMetadados, ChunkPayload
from mbft_core.paths import RAIZ_REPO
from mbft_deploy.cli import main
from mbft_deploy.exporters import atualizar_config_js_site, exportar_fts_chunks_sql
from mbft_deploy.wrangler import (
    fazer_deploy_api,
    fazer_deploy_d1,
    fazer_deploy_site,
    fazer_deploy_vectorize,
    provisionar_recursos_cloudflare,
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
                        "kv_namespaces": [{"binding": "KV_TICKETS", "id": "0000"}],
                    }
                ),
                encoding="utf-8",
            )

            saidas = [
                'database_id = "12345678-1234-1234-1234-123456789abc"',
                "Created index mbft-embeddings",
                '{ "binding": "KV_TICKETS", "id": "abcdef0123456789abcdef0123456789" }',
            ]
            with patch("mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas):
                ids = provisionar_recursos_cloudflare(wrangler_config_path=wrangler_file)

            self.assertEqual(ids["database_id"], "12345678-1234-1234-1234-123456789abc")
            self.assertEqual(ids["kv_id"], "abcdef0123456789abcdef0123456789")

            atualizado = json.loads(wrangler_file.read_text(encoding="utf-8"))
            self.assertEqual(
                atualizado["d1_databases"][0]["database_id"],
                "12345678-1234-1234-1234-123456789abc",
            )
            self.assertEqual(
                atualizado["kv_namespaces"][0]["id"],
                "abcdef0123456789abcdef0123456789",
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
