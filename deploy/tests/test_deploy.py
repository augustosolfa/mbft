import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mbft_api.asgi_prefix import RUN_WORKER_FIRST_PATTERNS
from mbft_core.models.indexacao import ChunkMetadados, ChunkPayload
from mbft_core.paths import RAIZ_REPO
from mbft_deploy.cli import _carregar_env_de_deploy, main
from mbft_deploy.exporters import (
    dividir_jsonl_vectorize,
    exportar_fts_chunks_sql,
)
from mbft_deploy.manifest import (
    calcular_hash_arquivo,
    recurso_precisa_sincronizar,
)
from mbft_deploy.wrangler import (
    MBFT_HOSTNAME_ENV,
    NOME_CONFIG_DEPLOY,
    _carregar_jsonc,
    fazer_deploy_api,
    fazer_deploy_d1,
    fazer_deploy_vectorize,
    invocacao_do_comando,
    montar_manifest_deploy,
    normalizar_hostname,
    provisionar_recursos_cloudflare,
    resolver_hostname_deploy,
    validar_assets_do_worker,
    verificar_status_recursos_cloudflare,
)


def _config_wrangler_valido() -> dict:
    """Config mínima com o bloco `assets` exigido pelo Worker único `mbft` (PMS-010)."""
    return {
        "name": "mbft",
        "assets": {
            "directory": "../../data/processed/site",
            "run_worker_first": list(RUN_WORKER_FIRST_PATTERNS),
            "not_found_handling": "404-page",
        },
    }


def _criar_payload_exemplo(
    chunk_id: str = "751-01_QUANDO_AUTUAR_ITEM_1",
) -> ChunkPayload:
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
    def test_manifesto_decide_por_hash_e_estado(self):
        manifesto = {
            ("d1_content", "mbft-d1"): {
                "content_hash": "sha256:igual",
                "status": "ready",
            }
        }
        self.assertFalse(
            recurso_precisa_sincronizar(
                manifesto, "d1_content", "mbft-d1", "sha256:igual"
            )
        )
        self.assertTrue(
            recurso_precisa_sincronizar(
                manifesto, "d1_content", "mbft-d1", "sha256:novo"
            )
        )
        self.assertTrue(
            recurso_precisa_sincronizar(
                {
                    ("d1_content", "mbft-d1"): {
                        "content_hash": "sha256:igual",
                        "status": "pending",
                    }
                },
                "d1_content",
                "mbft-d1",
                "sha256:igual",
            )
        )
        self.assertTrue(
            recurso_precisa_sincronizar(
                manifesto, "d1_content", "mbft-d1", "sha256:igual", force=True
            )
        )

    def test_manifesto_hash_do_artefato_e_deterministico(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artefato = Path(tmpdir) / "artefato.bin"
            artefato.write_bytes(b"mbft")
            self.assertEqual(
                calcular_hash_arquivo(artefato),
                "sha256:9eb68ed040e78f918ee9525cba98c126842e36af9fad65120db51642921eb6ad",
            )

    def test_exportar_fts_chunks_sql_gera_dump_idempotente_e_compativel_com_sqlite_fts5(
        self,
    ):
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
            schema_sql = (RAIZ_REPO / "apps" / "api" / "schema.sql").read_text(
                encoding="utf-8"
            )
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

    def test_normalizar_hostname_rejeita_valores_malformados(self):
        self.assertEqual(normalizar_hostname("  mbft.exemplo.com "), "mbft.exemplo.com")
        for invalido in (
            "",
            "http://mbft.exemplo.com",
            "mbft.exemplo.com/",
            "mbft exemplo com",
            "sem-ponto",
        ):
            with self.subTest(valor=invalido), self.assertRaises(ValueError):
                normalizar_hostname(invalido)

    def test_resolver_hostname_deploy_precedencia_hostname_env_e_nenhum(self):
        with patch.dict(os.environ, {MBFT_HOSTNAME_ENV: "env.exemplo.com"}, clear=True):
            self.assertEqual(
                resolver_hostname_deploy("cli.exemplo.com"), "cli.exemplo.com"
            )
            self.assertEqual(resolver_hostname_deploy(), "env.exemplo.com")
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolver_hostname_deploy())
            self.assertIsNone(resolver_hostname_deploy(""))

    def test_validar_assets_do_worker_reprova_divergencia_de_prefixo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(_config_wrangler_valido()), encoding="utf-8"
            )
            validar_assets_do_worker(wrangler_file)

            divergente = _config_wrangler_valido()
            divergente["assets"]["run_worker_first"] = ["/outra/*"]
            wrangler_file.write_text(json.dumps(divergente), encoding="utf-8")
            with self.assertRaises(ValueError):
                validar_assets_do_worker(wrangler_file)

    def test_montar_manifest_deploy_ajusta_workers_dev_sem_mutar_origem(self):
        base = _config_wrangler_valido()
        com_hostname = montar_manifest_deploy(base, "mbft.exemplo.com")
        sem_hostname = montar_manifest_deploy(base, None)

        self.assertFalse(com_hostname["workers_dev"])
        self.assertTrue(sem_hostname["workers_dev"])
        self.assertEqual(
            com_hostname["routes"],
            [{"pattern": "mbft.exemplo.com", "custom_domain": True}],
        )
        self.assertNotIn("routes", base, "A origem não deve ser mutada.")
        self.assertNotIn("workers_dev", base, "A origem não deve ser mutada.")
        self.assertNotIn("vars", base, "A origem não deve ser mutada.")
        self.assertIn("RATE_LIMIT_SALT", com_hostname["vars"])
        self.assertEqual(len(com_hostname["vars"]["RATE_LIMIT_SALT"]), 64)

    def test_montar_manifest_deploy_preserva_rate_limit_salt_preexistente(self):
        base = _config_wrangler_valido()
        base["vars"] = {"RATE_LIMIT_SALT": "sal-fixo-preexistente"}
        res = montar_manifest_deploy(base, None)
        self.assertEqual(res["vars"]["RATE_LIMIT_SALT"], "sal-fixo-preexistente")

    def test_montar_manifest_deploy_injeta_access_vars_do_ambiente(self):
        base = _config_wrangler_valido()
        with patch.dict(
            os.environ,
            {
                "ACCESS_TEAM_DOMAIN": "meutime.cloudflareaccess.com",
                "ACCESS_AUD": "aud-tag-teste",
            },
        ):
            res = montar_manifest_deploy(base, None)
            self.assertEqual(
                res["vars"]["ACCESS_TEAM_DOMAIN"], "meutime.cloudflareaccess.com"
            )
            self.assertEqual(res["vars"]["ACCESS_AUD"], "aud-tag-teste")

    def test_montar_manifest_deploy_injeta_admin_email_do_ambiente(self):
        base = _config_wrangler_valido()
        with patch.dict(
            os.environ,
            {
                "ADMIN_EMAIL": "  Admin.Chefe@Exemplo.COM  ",
            },
        ):
            res = montar_manifest_deploy(base, None)
            self.assertEqual(res["vars"]["ADMIN_EMAIL"], "admin.chefe@exemplo.com")

    def test_carregar_jsonc_ignora_comentarios_de_linha_e_bloco(self):
        jsonc = """{
            // Comentário de linha no início
            "name": "mbft",
            /* Comentário de bloco */
            "vars": {
                "URL": "https://meutime.cloudflareaccess.com//api", // comentário com barra
                "ATIVO": true
            }
        }"""
        dados = _carregar_jsonc(jsonc)
        self.assertEqual(dados["name"], "mbft")
        self.assertEqual(
            dados["vars"]["URL"], "https://meutime.cloudflareaccess.com//api"
        )
        self.assertTrue(dados["vars"]["ATIVO"])

    def test_comandos_wrangler_vectorize_d1_e_api_com_custom_domain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            sql_file = tmp / "schema.sql"
            api_dir = tmp / "api"
            api_dir.mkdir()
            jsonl_file.write_text(
                _criar_payload_exemplo().model_dump_json() + "\n", encoding="utf-8"
            )
            sql_file.write_text("SELECT 1;\n", encoding="utf-8")
            (api_dir / "wrangler.jsonc").write_text(
                json.dumps(_config_wrangler_valido()), encoding="utf-8"
            )

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("mbft_deploy.wrangler.rodar_comando_wrangler") as mock_cmd,
            ):
                fazer_deploy_vectorize(jsonl_file)
                fazer_deploy_d1(sql_file, remote=True)
                fazer_deploy_d1(sql_file, remote=False)
                hostname = fazer_deploy_api(
                    api_dir=api_dir, hostname="mbft.exemplo.com"
                )

                self.assertEqual(hostname, "mbft.exemplo.com")
                self.assertEqual(
                    mock_cmd.call_args_list[0][0][0],
                    [
                        "wrangler",
                        "vectorize",
                        "insert",
                        "mbft-embeddings",
                        "--file",
                        str(jsonl_file),
                    ],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[1][0][0],
                    [
                        "wrangler",
                        "d1",
                        "execute",
                        "mbft-d1",
                        "--file",
                        str(sql_file),
                        "--remote",
                    ],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[2][0][0],
                    [
                        "wrangler",
                        "d1",
                        "execute",
                        "mbft-d1",
                        "--file",
                        str(sql_file),
                        "--local",
                    ],
                )
                self.assertEqual(
                    mock_cmd.call_args_list[3][0][0],
                    [
                        "wrangler",
                        "deploy",
                        "--config",
                        str(api_dir / NOME_CONFIG_DEPLOY),
                    ],
                )
                # Nenhum comando legado de Cloudflare Pages deve ser emitido.
                self.assertTrue(
                    all("pages" not in cmd.args[0] for cmd in mock_cmd.call_args_list)
                )

    def test_deploy_api_sem_hostname_usa_workers_dev(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            api_dir = Path(tmpdir) / "api"
            api_dir.mkdir()
            (api_dir / "wrangler.jsonc").write_text(
                json.dumps(_config_wrangler_valido()), encoding="utf-8"
            )

            with (
                patch.dict(os.environ, {}, clear=True),
                patch("mbft_deploy.wrangler.rodar_comando_wrangler") as mock_cmd,
            ):
                hostname = fazer_deploy_api(api_dir=api_dir, dry_run=True)

            self.assertIsNone(hostname)
            self.assertEqual(
                mock_cmd.call_args_list[0][0][0],
                ["wrangler", "deploy", "--config", str(api_dir / NOME_CONFIG_DEPLOY)],
            )
            # O manifesto efêmero é removido após o deploy.
            self.assertFalse((api_dir / NOME_CONFIG_DEPLOY).exists())

    def test_deploy_api_usa_env_quando_hostname_ausente(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            api_dir = Path(tmpdir) / "api"
            api_dir.mkdir()
            (api_dir / "wrangler.jsonc").write_text(
                json.dumps(_config_wrangler_valido()), encoding="utf-8"
            )

            with (
                patch.dict(os.environ, {MBFT_HOSTNAME_ENV: "env.exemplo.com"}),
                patch("mbft_deploy.wrangler.rodar_comando_wrangler") as mock_cmd,
            ):
                hostname = fazer_deploy_api(api_dir=api_dir, dry_run=True)

            self.assertEqual(hostname, "env.exemplo.com")
            self.assertEqual(
                mock_cmd.call_args_list[0][0][0],
                [
                    "wrangler",
                    "deploy",
                    "--config",
                    str(api_dir / NOME_CONFIG_DEPLOY),
                ],
            )

    def test_provisionar_recursos_atualiza_wrangler_jsonc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft",
                        "d1_databases": [
                            {
                                "binding": "DB",
                                "database_name": "mbft-d1",
                                "database_id": "0000",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            saidas = [
                json.dumps([]),
                'database_id = "12345678-1234-1234-1234-123456789abc"',
                json.dumps([]),
                "Created index mbft-embeddings",
            ]
            with patch(
                "mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas
            ):
                ids = provisionar_recursos_cloudflare(
                    wrangler_config_path=wrangler_file
                )

            self.assertEqual(ids["database_id"], "12345678-1234-1234-1234-123456789abc")

            atualizado = json.loads(wrangler_file.read_text(encoding="utf-8"))
            self.assertEqual(
                atualizado["d1_databases"][0]["database_id"],
                "12345678-1234-1234-1234-123456789abc",
            )

    def test_provisionar_recursos_reutiliza_recursos_existentes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft",
                        "d1_databases": [
                            {
                                "binding": "DB",
                                "database_name": "mbft-d1",
                                "database_id": "0000",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "mbft_deploy.wrangler.rodar_comando_wrangler",
                side_effect=[
                    json.dumps(
                        [
                            {
                                "name": "mbft-d1",
                                "uuid": "12345678-1234-1234-1234-123456789abc",
                            }
                        ]
                    ),
                    json.dumps(
                        [
                            {
                                "name": "mbft-embeddings",
                                "config": {"dimensions": 1024, "metric": "cosine"},
                            }
                        ]
                    ),
                ],
            ) as mock_cmd:
                ids = provisionar_recursos_cloudflare(
                    wrangler_config_path=wrangler_file
                )

            self.assertEqual(
                ids["database_id"], "12345678-1234-1234-1234-123456789abc"
            )
            self.assertEqual(mock_cmd.call_count, 2)
            self.assertTrue(
                all("create" not in call.args[0] for call in mock_cmd.call_args_list)
            )

    def test_status_verifica_recursos_sem_criar_nada(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft",
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
                json.dumps(
                    [
                        {
                            "uuid": "12345678-1234-1234-1234-123456789abc",
                            "name": "mbft-d1",
                        }
                    ]
                ),
                json.dumps(
                    [
                        {
                            "name": "mbft-embeddings",
                            "config": {"dimensions": 1024, "metric": "cosine"},
                        }
                    ]
                ),
                json.dumps([{"id": "deployment-1"}]),
            ]
            with patch(
                "mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas
            ) as mock_cmd:
                status = verificar_status_recursos_cloudflare(
                    wrangler_config_path=wrangler_file,
                )

            self.assertTrue(status["ok"])
            self.assertEqual(
                status["checks"], {"d1": True, "vectorize": True, "worker": True}
            )
            self.assertTrue(
                all("create" not in call.args[0] for call in mock_cmd.call_args_list)
            )
            # O status não deve mais consultar o legado Cloudflare Pages.
            self.assertTrue(
                all("pages" not in call.args[0] for call in mock_cmd.call_args_list)
            )

    def test_status_aceita_formatos_diretos_das_propriedades(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft",
                        "d1_databases": [
                            {"database_name": "mbft-d1", "database_id": "id-local"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            saidas = [
                json.dumps([{"name": "mbft-d1", "database_id": "id-local"}]),
                json.dumps(
                    [
                        {
                            "name": "mbft-embeddings",
                            "dimensions": 1024,
                            "metric": "cosine",
                        }
                    ]
                ),
                json.dumps([{"id": "deployment-1"}]),
            ]
            with patch(
                "mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas
            ):
                status = verificar_status_recursos_cloudflare(
                    wrangler_config_path=wrangler_file
                )

            self.assertTrue(status["ok"])

    def test_status_reprova_recurso_ausente_ou_configuracao_invalida(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft",
                        "d1_databases": [
                            {"database_name": "mbft-d1", "database_id": "id-local"}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            saidas = [
                json.dumps([{"name": "mbft-d1", "database_id": "id-remoto"}]),
                json.dumps(
                    [{"name": "mbft-embeddings", "dimensions": 768, "metric": "cosine"}]
                ),
                json.dumps([]),
            ]
            with patch(
                "mbft_deploy.wrangler.rodar_comando_wrangler", side_effect=saidas
            ):
                status = verificar_status_recursos_cloudflare(
                    wrangler_config_path=wrangler_file
                )

            self.assertFalse(status["ok"])
            self.assertEqual(
                status["checks"], {"d1": False, "vectorize": False, "worker": False}
            )

    def test_status_trata_worker_inexistente_como_recurso_ausente(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wrangler_file = Path(tmpdir) / "wrangler.jsonc"
            wrangler_file.write_text(
                json.dumps(
                    {
                        "name": "mbft",
                        "d1_databases": [
                            {
                                "database_name": "mbft-d1",
                                "database_id": "id-local",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            saidas = [
                json.dumps([{"name": "mbft-d1", "database_id": "id-local"}]),
                json.dumps(
                    [
                        {
                            "name": "mbft-embeddings",
                            "dimensions": 1024,
                            "metric": "cosine",
                        }
                    ]
                ),
                RuntimeError(
                    "Falha ao executar wrangler: Worker does not exist "
                    "on your account. [code: 10007]"
                ),
            ]
            with patch(
                "mbft_deploy.wrangler.rodar_comando_wrangler",
                side_effect=saidas,
            ):
                status = verificar_status_recursos_cloudflare(
                    wrangler_config_path=wrangler_file
                )

            self.assertFalse(status["ok"])
            self.assertEqual(
                status["checks"], {"d1": True, "vectorize": True, "worker": False}
            )
            self.assertFalse(status["worker"])

    def test_dividir_jsonl_vectorize_respeita_limite_sem_cortar_linhas(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            jsonl_file = tmp / "embeddings_mbft.jsonl"
            linhas = [
                _criar_payload_exemplo(f"751-01_CHUNK_{indice}").model_dump_json()
                for indice in range(5)
            ]
            jsonl_file.write_bytes(
                b"\n".join(linha.encode("utf-8") for linha in linhas) + b"\n"
            )

            limite = (len(linhas[0].encode("utf-8")) + 1) * 2
            partes = dividir_jsonl_vectorize(
                jsonl_file, tmp / "vectorize", limite_bytes=limite
            )

            self.assertEqual(
                [p.name for p in partes],
                ["parte_01.jsonl", "parte_02.jsonl", "parte_03.jsonl"],
            )
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

    def test_carregar_env_de_deploy_limita_variaveis_e_preserva_o_shell(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            raiz = Path(tmpdir)
            (raiz / ".env").write_text(
                "CLOUDFLARE_API_TOKEN=token-do-arquivo\n"
                "CLOUDFLARE_ACCOUNT_ID=conta-do-arquivo\n"
                "MBFT_HOSTNAME=mbft.exemplo.com\n"
                "ACCESS_TEAM_DOMAIN=meutime.cloudflareaccess.com\n"
                "ACCESS_AUD=aud-tag-teste\n"
                "GEMINI_API_KEY=segredo-de-outro-passo\n",
                encoding="utf-8",
            )

            with (
                patch("mbft_deploy.cli.RAIZ_REPO", raiz),
                patch.dict(
                    os.environ, {"CLOUDFLARE_ACCOUNT_ID": "conta-do-shell"}, clear=True
                ),
            ):
                _carregar_env_de_deploy()

                self.assertEqual(os.environ["CLOUDFLARE_API_TOKEN"], "token-do-arquivo")
                self.assertEqual(os.environ["CLOUDFLARE_ACCOUNT_ID"], "conta-do-shell")
                self.assertEqual(os.environ["MBFT_HOSTNAME"], "mbft.exemplo.com")
                self.assertEqual(
                    os.environ["ACCESS_TEAM_DOMAIN"], "meutime.cloudflareaccess.com"
                )
                self.assertEqual(os.environ["ACCESS_AUD"], "aud-tag-teste")
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
            api_dir.mkdir()

            jsonl_file.write_text(
                _criar_payload_exemplo().model_dump_json() + "\n", encoding="utf-8"
            )
            schema_file.write_text("SELECT 1;\n", encoding="utf-8")
            (api_dir / "wrangler.jsonc").write_text(
                json.dumps(_config_wrangler_valido()), encoding="utf-8"
            )

            with patch.dict(os.environ, {}, clear=True):
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
                        "--hostname",
                        "mbft.exemplo.com",
                        "--dry-run",
                    ]
                )
            self.assertTrue(sql_out.exists())

    def test_cli_site_foi_descontinuado(self):
        with self.assertRaises(SystemExit) as contexto:
            main(["site"])
        self.assertNotEqual(contexto.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
