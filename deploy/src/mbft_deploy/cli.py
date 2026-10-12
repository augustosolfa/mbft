import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from mbft_core.paths import PROCESSED_DIR, RAIZ_REPO
from .exporters import exportar_fts_chunks_sql
from .wrangler import (
    fazer_deploy_api,
    fazer_deploy_d1,
    fazer_deploy_site,
    fazer_deploy_vectorize,
    provisionar_recursos_cloudflare,
    verificar_status_recursos_cloudflare,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_JSONL = PROCESSED_DIR / "indexador" / "embeddings_mbft.jsonl"
DEFAULT_SQL_OUT = PROCESSED_DIR / "deploy" / "fts_chunks.sql"
DEFAULT_SCHEMA_SQL = RAIZ_REPO / "apps" / "api" / "schema.sql"
DEFAULT_API_DIR = RAIZ_REPO / "apps" / "api"
DEFAULT_SITE_DIR = PROCESSED_DIR / "site"


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbft-deploy",
        description="Exportadores para Cloudflare (D1 SQL) e automação de provisionamento/deploy (PMS-010).",
    )
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    # 1. export-d1
    p_export = subparsers.add_parser(
        "export-d1",
        help="Converte embeddings_mbft.jsonl em script SQL FTS5 (data/processed/deploy/fts_chunks.sql).",
    )
    p_export.add_argument("--input", "-i", type=Path, default=DEFAULT_JSONL, help="Caminho do embeddings_mbft.jsonl.")
    p_export.add_argument("--output", "-o", type=Path, default=DEFAULT_SQL_OUT, help="Caminho de saída do fts_chunks.sql.")
    p_export.add_argument("--batch-size", "-b", type=int, default=100, help="Quantidade de linhas por comando INSERT.")

    # 2. provision
    p_prov = subparsers.add_parser(
        "provision",
        help="Provisiona D1 e Vectorize na Cloudflare e atualiza IDs em apps/api/wrangler.jsonc.",
    )
    p_prov.add_argument("--wrangler-config", type=Path, default=DEFAULT_API_DIR / "wrangler.jsonc")
    p_prov.add_argument("--db-name", default="mbft-d1")
    p_prov.add_argument("--index-name", default="mbft-embeddings")
    p_prov.add_argument("--project-name", default="mbft-site")
    p_prov.add_argument("--status", action="store_true", help="Consulta o estado sem criar ou alterar recursos.")
    p_prov.add_argument("--dry-run", action="store_true", help="Apenas exibe os comandos Wrangler sem executá-los.")

    # 3. data
    p_data = subparsers.add_parser(
        "data",
        help="Gera fts_chunks.sql, aplica schema.sql + fts_chunks.sql no D1 e envia embeddings_mbft.jsonl ao Vectorize.",
    )
    p_data.add_argument("--input", "-i", type=Path, default=DEFAULT_JSONL, help="Caminho do embeddings_mbft.jsonl.")
    p_data.add_argument("--sql-output", type=Path, default=DEFAULT_SQL_OUT, help="Caminho do fts_chunks.sql gerado.")
    p_data.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_SQL, help="Caminho do apps/api/schema.sql.")
    p_data.add_argument("--db-name", default="mbft-d1")
    p_data.add_argument("--index-name", default="mbft-embeddings")
    grupo_alvo = p_data.add_mutually_exclusive_group()
    grupo_alvo.add_argument("--remote", dest="remote", action="store_true", default=True, help="Executa no Cloudflare D1 remoto (padrão).")
    grupo_alvo.add_argument("--local", dest="remote", action="store_false", help="Executa apenas no D1 local (Miniflare) e pula Vectorize.")
    p_data.add_argument("--skip-vectorize", action="store_true", help="Pula o envio de vetores para o Cloudflare Vectorize.")
    p_data.add_argument("--dry-run", action="store_true", help="Apenas simula os comandos Wrangler.")

    # 4. api
    p_api = subparsers.add_parser(
        "api",
        help="Publica o Worker FastAPI (apps/api) no Cloudflare Workers.",
    )
    p_api.add_argument("--api-dir", type=Path, default=DEFAULT_API_DIR)
    p_api.add_argument("--dry-run", action="store_true")

    # 5. site
    p_site = subparsers.add_parser(
        "site",
        help="Atualiza config.js (opcional) e publica data/processed/site no Cloudflare Pages.",
    )
    p_site.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR)
    p_site.add_argument("--project-name", default="mbft-site")
    p_site.add_argument("--api-url", default=None, help="URL de produção da API para injetar em site/config.js.")
    p_site.add_argument("--dry-run", action="store_true")

    # 6. tudo
    p_tudo = subparsers.add_parser(
        "tudo",
        help="Executa o fluxo completo de publicação: data -> api -> site.",
    )
    p_tudo.add_argument("--input", "-i", type=Path, default=DEFAULT_JSONL)
    p_tudo.add_argument("--sql-output", type=Path, default=DEFAULT_SQL_OUT)
    p_tudo.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA_SQL)
    p_tudo.add_argument("--api-dir", type=Path, default=DEFAULT_API_DIR)
    p_tudo.add_argument("--site-dir", type=Path, default=DEFAULT_SITE_DIR)
    p_tudo.add_argument("--db-name", default="mbft-d1")
    p_tudo.add_argument("--index-name", default="mbft-embeddings")
    p_tudo.add_argument("--project-name", default="mbft-site")
    p_tudo.add_argument("--api-url", default=None, help="URL de produção da API para injetar em site/config.js.")
    grupo_tudo_alvo = p_tudo.add_mutually_exclusive_group()
    grupo_tudo_alvo.add_argument("--remote", dest="remote", action="store_true", default=True)
    grupo_tudo_alvo.add_argument("--local", dest="remote", action="store_false")
    p_tudo.add_argument("--dry-run", action="store_true")

    return parser


def _executar_data(
    input_jsonl: Path,
    sql_output: Path,
    schema_sql: Path,
    db_name: str,
    index_name: str,
    remote: bool,
    skip_vectorize: bool,
    dry_run: bool,
    api_dir: Path = DEFAULT_API_DIR,
) -> None:
    exportar_fts_chunks_sql(input_jsonl, sql_output)
    fazer_deploy_d1(schema_sql, db_name=db_name, remote=remote, cwd=api_dir, dry_run=dry_run)
    fazer_deploy_d1(sql_output, db_name=db_name, remote=remote, cwd=api_dir, dry_run=dry_run)
    if remote and not skip_vectorize:
        fazer_deploy_vectorize(input_jsonl, index_name=index_name, dry_run=dry_run)


VARIAVEIS_DE_DEPLOY = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "MBFT_API_URL")


def _carregar_env_de_deploy() -> None:
    """
    Carrega do `.env` da raiz apenas as variáveis usadas pelo deploy (credenciais da Cloudflare e
    `MBFT_API_URL`), preservando variáveis já definidas no shell. A lista é fechada de propósito:
    despejar o `.env` inteiro no processo vazaria segredos de outras etapas (ex.: `GEMINI_API_KEY`).
    """
    env_file = RAIZ_REPO / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import dotenv_values
    except ImportError:
        logger.warning("python-dotenv ausente: '.env' ignorado. Exporte as credenciais no shell.")
        return

    valores = dotenv_values(env_file)
    for chave in VARIAVEIS_DE_DEPLOY:
        valor = valores.get(chave)
        if valor and chave not in os.environ:
            os.environ[chave] = valor


def main(argv: Optional[List[str]] = None) -> None:
    parser = construir_parser()
    args = parser.parse_args(argv)
    _carregar_env_de_deploy()

    try:
        if args.subcomando == "export-d1":
            exportar_fts_chunks_sql(args.input, args.output, batch_size=args.batch_size)
        elif args.subcomando == "provision":
            if args.status:
                status = verificar_status_recursos_cloudflare(
                    wrangler_config_path=args.wrangler_config,
                    db_name=args.db_name,
                    index_name=args.index_name,
                    project_name=args.project_name,
                )
                for recurso, ok in status["checks"].items():
                    logger.info("%s: %s", recurso, "OK" if ok else "INCOMPLETO")
                if not status["ok"]:
                    sys.exit(1)
            else:
                provisionar_recursos_cloudflare(
                    wrangler_config_path=args.wrangler_config,
                    db_name=args.db_name,
                    index_name=args.index_name,
                    project_name=args.project_name,
                    dry_run=args.dry_run,
                )
        elif args.subcomando == "data":
            _executar_data(
                input_jsonl=args.input,
                sql_output=args.sql_output,
                schema_sql=args.schema,
                db_name=args.db_name,
                index_name=args.index_name,
                remote=args.remote,
                skip_vectorize=args.skip_vectorize,
                dry_run=args.dry_run,
            )
        elif args.subcomando == "api":
            fazer_deploy_api(api_dir=args.api_dir, dry_run=args.dry_run)
        elif args.subcomando == "site":
            fazer_deploy_site(
                site_dir=args.site_dir,
                project_name=args.project_name,
                api_url=args.api_url,
                dry_run=args.dry_run,
            )
        elif args.subcomando == "tudo":
            _executar_data(
                input_jsonl=args.input,
                sql_output=args.sql_output,
                schema_sql=args.schema,
                db_name=args.db_name,
                index_name=args.index_name,
                remote=args.remote,
                skip_vectorize=False,
                dry_run=args.dry_run,
                api_dir=args.api_dir,
            )
            fazer_deploy_api(api_dir=args.api_dir, dry_run=args.dry_run)
            fazer_deploy_site(
                site_dir=args.site_dir,
                project_name=args.project_name,
                api_url=args.api_url,
                dry_run=args.dry_run,
            )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logger.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
