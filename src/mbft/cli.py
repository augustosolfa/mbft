import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

from mbft_core.paths import PROCESSED_DIR, RAIZ_REPO, RAW_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mbft")

MAPA_MODULOS_TESTE: dict[str, str] = {
    "core": "pipelines/core/tests",
    "extrator": "pipelines/extrator/tests",
    "enriquecedor": "pipelines/enriquecedor/tests",
    "indexador": "pipelines/indexador/tests",
    "ssg": "pipelines/ssg/tests",
    "api": "apps/api/tests",
    "deploy": "deploy/tests",
    "governanca": "tests/test_governanca_docs.py",
}


def _configurar_parser_pipeline(subparsers: argparse._SubParsersAction) -> None:
    p_pipe = subparsers.add_parser(
        "pipeline",
        help="Executa etapas de processamento de dados offline (extrator, enriquecedor, indexador, ssg, tudo).",
    )
    pipe_sub = p_pipe.add_subparsers(dest="etapa", required=True)

    # 1. extrator
    p_ext = pipe_sub.add_parser(
        "extrator",
        help="Extrai Parte Geral (Markdown), Fichas (JSON) e Imagens (300 DPI) do mbft.pdf.",
    )
    p_ext.add_argument(
        "escopo",
        nargs="?",
        choices=["tudo", "geral", "fichas"],
        default="tudo",
        help="Sub-etapa do extrator (padrão: tudo).",
    )
    p_ext.add_argument(
        "--pdf", default=str(RAW_DIR / "mbft.pdf"), help="Caminho do mbft.pdf."
    )
    p_ext.add_argument(
        "--saida-md",
        default=str(PROCESSED_DIR / "extrator" / "mbft_parte_geral.md"),
        help="Saída Markdown da Parte Geral.",
    )
    p_ext.add_argument(
        "--saida-json",
        default=str(PROCESSED_DIR / "extrator" / "fichas_mbft.json"),
        help="Saída JSON consolidada das fichas.",
    )
    p_ext.add_argument("--paginas", help="Filtrar por faixa de páginas (ex.: 32-37).")
    p_ext.add_argument("--fichas", help="Filtrar por índice de fichas (ex.: 1-5).")
    p_ext.add_argument(
        "--salvar-individuais", action="store_true", help="Salva fichas individuais."
    )
    p_ext.add_argument(
        "--force", action="store_true", help="Ignora cache e reprocessa do zero."
    )
    p_ext.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Número de workers paralelos (padrão: 4).",
    )

    # 2. enriquecedor
    pipe_sub.add_parser(
        "enriquecedor",
        help="Normaliza campos categóricos e extrai regras atômicas (fichas_enriquecidas.json).",
    )

    # 3. indexador
    p_idx = pipe_sub.add_parser(
        "indexador",
        help="Gera chunks semânticos e embeddings densos BAAI/bge-m3 (embeddings_mbft.jsonl).",
    )
    p_idx.add_argument(
        "--input",
        "-i",
        default=str(PROCESSED_DIR / "enriquecedor" / "fichas_enriquecidas.json"),
        help="Caminho do fichas_enriquecidas.json.",
    )
    p_idx.add_argument(
        "--output", "-o", default=None, help="Caminho de saída do JSONL."
    )
    p_idx.add_argument(
        "--batch-size", "-b", type=int, default=32, help="Tamanho do batch na GPU."
    )
    p_idx.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Modo debug rápido com FakeEmbedder (gera embeddings_debug.jsonl).",
    )

    # 4. ssg
    p_ssg = pipe_sub.add_parser(
        "ssg",
        help="Compila o site estático HTML/Jinja2 em data/processed/site/.",
    )
    p_ssg.add_argument(
        "--input", type=Path, default=None, help="Caminho do fichas_enriquecidas.json."
    )
    p_ssg.add_argument(
        "--output", type=Path, default=None, help="Diretório de saída do site."
    )
    p_ssg.add_argument(
        "--imagens", type=Path, default=None, help="Diretório de imagens de entrada."
    )

    # 5. tudo
    p_tudo = pipe_sub.add_parser(
        "tudo",
        help="Executa todas as pipelines em cadeia: extrator -> enriquecedor -> indexador -> ssg.",
    )
    p_tudo.add_argument(
        "--force", action="store_true", help="Ignora cache do extrator."
    )
    p_tudo.add_argument(
        "--workers", type=int, default=4, help="Workers paralelos no extrator."
    )
    p_tudo.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=32,
        help="Batch size na GPU do indexador.",
    )
    p_tudo.add_argument(
        "--skip-embeddings", action="store_true", help="Usa FakeEmbedder no indexador."
    )


def _configurar_parser_deploy(subparsers: argparse._SubParsersAction) -> None:
    p_dep = subparsers.add_parser(
        "deploy",
        help="Exporta artefatos de nuvem, provisiona e publica na Cloudflare.",
        description="Exporta artefatos, provisiona recursos e publica o MBFT na Cloudflare.",
        epilog="""\
Subcomandos:
  export-d1   Gera o dump SQL FTS5 a partir de embeddings_mbft.jsonl.
  provision   Provisiona D1 e Vectorize; --status apenas consulta o estado.
  data        Gera/aplica o SQL e envia embeddings ao Vectorize.
  api         Publica o Worker único `mbft` (API + site estático).
  tudo        Executa data -> api.

As opções pertencem ao subcomando correspondente; não são globais. Use:
  mbft deploy <subcomando> --help

Padrões principais:
  data/tudo       usam o D1 remoto (--remote) e embeddings_mbft.jsonl padrão.
  data            envia vetores ao Vectorize, salvo se --skip-vectorize.
  api/tudo        publicam o Worker `mbft`; --hostname ou MBFT_HOSTNAME definem um
                  Custom Domain e desativam o workers.dev (sem hostname, o Worker
                  permanece apenas em workers.dev).
  provision       usa mbft-d1 e mbft-embeddings.
  --dry-run       simula operações nos subcomandos que suportam essa opção.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_dep.add_argument(
        "deploy_args",
        nargs=argparse.REMAINDER,
        metavar="SUBCOMANDO [OPÇÕES ...]",
        help="Subcomando e opções repassados ao mbft-deploy; consulte a lista acima.",
    )


def _configurar_parser_testes(subparsers: argparse._SubParsersAction) -> None:
    p_test = subparsers.add_parser(
        "testes",
        help="Executa suítes pytest (rapidos, tudo, governanca) e benchmarks (recall, diff-extracao, gerador).",
    )
    p_test.add_argument(
        "alvo",
        nargs="?",
        choices=["rapidos", "tudo", "governanca", "recall", "diff-extracao", "gerador"],
        default="rapidos",
        help="Escopo de teste/avaliação (padrão: rapidos = unitários + governança sem GPU).",
    )
    p_test.add_argument(
        "--modulo",
        "-m",
        choices=sorted(MAPA_MODULOS_TESTE.keys()),
        default=None,
        help="Filtra a execução do pytest para um pacote específico.",
    )
    p_test.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Exibe saída detalhada (pytest -v ou diff-extracao --verbose).",
    )


def _configurar_parser_dev(subparsers: argparse._SubParsersAction) -> None:
    p_dev = subparsers.add_parser(
        "dev",
        help="Sobe os servidores locais de desenvolvimento (API FastAPI na 8000 e/ou Site estático na 3000).",
    )
    p_dev.add_argument(
        "servico",
        nargs="?",
        choices=["tudo", "api", "site"],
        default="tudo",
        help="Serviço local para iniciar (padrão: tudo = API + Site simultaneamente).",
    )
    p_dev.add_argument(
        "--host", default="127.0.0.1", help="Host de bind local (padrão: 127.0.0.1)."
    )
    p_dev.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="Porta da API FastAPI (padrão: 8000).",
    )
    p_dev.add_argument(
        "--site-port",
        type=int,
        default=3000,
        help="Porta do Site estático (padrão: 3000).",
    )
    p_dev.add_argument(
        "--no-reload", action="store_true", help="Desativa auto-reload do uvicorn."
    )


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mbft",
        description="CLI centralizada do monorepo MBFT (pipeline, deploy, testes e dev).",
    )
    subparsers = parser.add_subparsers(dest="grupo")
    _configurar_parser_pipeline(subparsers)
    _configurar_parser_deploy(subparsers)
    _configurar_parser_testes(subparsers)
    _configurar_parser_dev(subparsers)
    return parser


def _executar_pipeline(args: argparse.Namespace) -> None:
    if args.etapa == "extrator":
        from mbft_extrator.cli import main as extrator_main

        ext_argv = ["--pdf", args.pdf, args.escopo]
        if args.escopo in ("geral", "tudo"):
            ext_argv.extend(["--saida-md", args.saida_md])
        if args.escopo in ("fichas", "tudo"):
            ext_argv.extend(
                ["--saida-json", args.saida_json, "--workers", str(args.workers)]
            )
            if args.paginas:
                ext_argv.extend(["--paginas", args.paginas])
            if args.fichas:
                ext_argv.extend(["--fichas", args.fichas])
            if args.salvar_individuais:
                ext_argv.append("--salvar-individuais")
            if args.force:
                ext_argv.append("--force")
        extrator_main(ext_argv)

    elif args.etapa == "enriquecedor":
        from mbft_enriquecedor.main import main as enriquecedor_main

        enriquecedor_main()

    elif args.etapa == "indexador":
        from mbft_indexador.cli import main as indexador_main

        idx_argv = ["--input", args.input, "--batch-size", str(args.batch_size)]
        if args.output:
            idx_argv.extend(["--output", args.output])
        if args.skip_embeddings:
            idx_argv.append("--skip-embeddings")
        indexador_main(idx_argv)

    elif args.etapa == "ssg":
        from mbft_ssg.builder import run_build

        run_build(
            fichas_json=args.input,
            output_dir=args.output,
            imagens_src=args.imagens,
        )

    elif args.etapa == "tudo":
        from mbft_enriquecedor.main import main as enriquecedor_main
        from mbft_extrator.cli import main as extrator_main
        from mbft_indexador.cli import main as indexador_main
        from mbft_ssg.builder import run_build

        ext_argv = ["tudo", "--workers", str(args.workers)]
        if args.force:
            ext_argv.append("--force")
        extrator_main(ext_argv)
        enriquecedor_main()

        idx_argv = ["--batch-size", str(args.batch_size)]
        if args.skip_embeddings:
            idx_argv.append("--skip-embeddings")
        indexador_main(idx_argv)
        run_build()


def _executar_testes(args: argparse.Namespace) -> None:
    if args.alvo == "recall":
        script = (
            RAIZ_REPO / "pipelines" / "indexador" / "scripts" / "avaliacao_aderencia.py"
        )
        jsonl = PROCESSED_DIR / "indexador" / "embeddings_mbft.jsonl"
        casos = (
            RAIZ_REPO / "pipelines" / "indexador" / "scripts" / "casos_aderencia.yaml"
        )
        cmd = [
            sys.executable,
            str(script),
            "--jsonl",
            str(jsonl),
            "--casos",
            str(casos),
        ]
        res = subprocess.run(cmd, cwd=str(RAIZ_REPO))
        if res.returncode != 0:
            sys.exit(res.returncode)
        return

    if args.alvo == "diff-extracao":
        script = (
            RAIZ_REPO / "pipelines" / "extrator" / "scripts" / "comparar_versoes.py"
        )
        cmd = [sys.executable, str(script)]
        if args.verbose:
            cmd.append("--verbose")
        res = subprocess.run(cmd, cwd=str(RAIZ_REPO))
        if res.returncode != 0:
            sys.exit(res.returncode)
        return

    if args.alvo == "gerador":
        script = RAIZ_REPO / "apps" / "api" / "scripts" / "testar_gerador.py"
        res = subprocess.run([sys.executable, str(script)], cwd=str(RAIZ_REPO))
        if res.returncode != 0:
            sys.exit(res.returncode)
        return

    import pytest

    pytest_args: list[str] = []
    if args.verbose:
        pytest_args.append("-v")

    if args.alvo == "governanca":
        pytest_args.append(str(RAIZ_REPO / "tests" / "test_governanca_docs.py"))
    elif args.modulo:
        rel_target = MAPA_MODULOS_TESTE[args.modulo]
        pytest_args.append(str(RAIZ_REPO / rel_target))
        if args.alvo == "rapidos" and args.modulo == "api":
            pytest_args.append(
                f"--ignore={RAIZ_REPO / 'apps' / 'api' / 'tests' / 'test_integracao.py'}"
            )
    else:
        pytest_args.append(str(RAIZ_REPO))
        if args.alvo == "rapidos":
            pytest_args.append(
                f"--ignore={RAIZ_REPO / 'apps' / 'api' / 'tests' / 'test_integracao.py'}"
            )

    code = pytest.main(pytest_args)
    if code != 0:
        sys.exit(int(code))


def _carregar_env_local(env: dict[str, str]) -> None:
    """
    Carrega o `.env` da raiz do monorepo no ambiente dos subprocessos locais,
    preservando variáveis já definidas no shell (o ambiente real tem precedência).
    """
    env_file = RAIZ_REPO / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import dotenv_values
    except ImportError:
        logger.warning(
            "python-dotenv ausente: '.env' ignorado. Exporte as variáveis no shell (ex.: GEMINI_API_KEY)."
        )
        return
    for chave, valor in dotenv_values(env_file).items():
        if valor is not None and chave not in env:
            env[chave] = valor


def _executar_dev(args: argparse.Namespace) -> None:
    env = os.environ.copy()
    _carregar_env_local(env)

    cmd_api = [
        sys.executable,
        "-m",
        "uvicorn",
        "mbft_api.main:app",
        "--host",
        args.host,
        "--port",
        str(args.api_port),
    ]
    if not args.no_reload:
        cmd_api.append("--reload")

    site_dir = PROCESSED_DIR / "site"
    cmd_site = [
        sys.executable,
        "-m",
        "http.server",
        str(args.site_port),
        "--bind",
        args.host,
        "-d",
        str(site_dir),
    ]

    if args.servico == "api":
        logger.info(
            "Iniciando API FastAPI em http://%s:%d ...", args.host, args.api_port
        )
        subprocess.run(cmd_api, cwd=str(RAIZ_REPO), env=env)
        return

    if args.servico == "site":
        if not site_dir.exists():
            logger.error(
                "Diretório %s não existe. Execute `uv run mbft pipeline ssg` primeiro.",
                site_dir,
            )
            sys.exit(1)
        logger.info(
            "Iniciando Site Estático em http://%s:%d ...", args.host, args.site_port
        )
        subprocess.run(cmd_site, cwd=str(RAIZ_REPO), env=env)
        return

    # Modo 'tudo': sobe API + Site juntos
    if not site_dir.exists():
        logger.error(
            "Diretório %s não existe. Execute `uv run mbft pipeline ssg` primeiro.",
            site_dir,
        )
        sys.exit(1)

    logger.info(
        "Iniciando ambiente local completo: API (http://%s:%d) + Site (http://%s:%d)",
        args.host,
        args.api_port,
        args.host,
        args.site_port,
    )
    proc_api = subprocess.Popen(cmd_api, cwd=str(RAIZ_REPO), env=env)
    proc_site = subprocess.Popen(cmd_site, cwd=str(RAIZ_REPO), env=env)
    try:
        proc_api.wait()
    except KeyboardInterrupt:
        logger.info("Encerrando servidores locais...")
    finally:
        for p in (proc_api, proc_site):
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()


def main(argv: list[str] | None = None) -> None:
    parser = construir_parser()
    args = parser.parse_args(argv)

    if args.grupo is None:
        parser.print_help()
        return

    if args.grupo == "pipeline":
        _executar_pipeline(args)
    elif args.grupo == "deploy":
        from mbft_deploy.cli import main as deploy_main

        deploy_argv = list(args.deploy_args)
        if deploy_argv and deploy_argv[0] == "--":
            deploy_argv = deploy_argv[1:]
        deploy_main(deploy_argv or ["--help"])
    elif args.grupo == "testes":
        _executar_testes(args)
    elif args.grupo == "dev":
        _executar_dev(args)


if __name__ == "__main__":
    main()
