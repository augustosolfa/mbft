import argparse
import logging
from pathlib import Path

from mbft_core.paths import RAW_DIR, PROCESSED_DIR
from .runner import executar_extracao_geral, executar_extracao_fichas

logger = logging.getLogger("MBFT-CLI")

def cmd_geral(args):
    pdf_path = Path(args.pdf)
    saida = Path(args.saida_md)
    executar_extracao_geral(pdf_path, saida)

def cmd_fichas(args):
    pdf_path = Path(args.pdf)
    saida_json = Path(args.saida_json)
    executar_extracao_fichas(
        pdf_path=pdf_path,
        saida_json=saida_json,
        paginas=args.paginas,
        fichas=args.fichas,
        salvar_individuais=args.salvar_individuais,
        force=args.force,
        workers=getattr(args, "workers", 4),
    )

def cmd_tudo(args):
    cmd_geral(args)
    cmd_fichas(args)

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    
    default_pdf = RAW_DIR / "mbft.pdf"
    default_md = PROCESSED_DIR / "extrator" / "mbft_parte_geral.md"
    default_json = PROCESSED_DIR / "extrator" / "fichas_mbft.json"

    parser = argparse.ArgumentParser(
        description="Extrator de Alta Fidelidade do Manual Brasileiro de Fiscalização de Trânsito (MBFT)"
    )
    parser.add_argument("--pdf", default=str(default_pdf), help=f"Caminho do arquivo mbft.pdf (padrão: {default_pdf})")
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    p_geral = subparsers.add_parser("geral", help="Extrai a Parte Geral (páginas 1 a 31) para Markdown")
    p_geral.add_argument("--saida-md", default=str(default_md), help=f"Arquivo de saída Markdown (padrão: {default_md})")

    p_fichas = subparsers.add_parser("fichas", help="Extrai as Fichas Estruturadas para JSON")
    p_fichas.add_argument("--saida-json", default=str(default_json), help=f"Arquivo JSON consolidado (padrão: {default_json})")
    p_fichas.add_argument("--paginas", help="Filtrar por faixa de páginas no PDF (ex: 32-37)")
    p_fichas.add_argument("--fichas", help="Filtrar por índice das fichas (ex: 1-5)")
    p_fichas.add_argument("--salvar-individuais", action="store_true", help="Salva cada ficha em fichas/ficha_<id>.json")
    p_fichas.add_argument("--force", action="store_true", help="Ignora checkpoints e reprocessa do zero")
    p_fichas.add_argument("--workers", type=int, default=4, help="Número de workers paralelos (padrão: 4)")

    p_tudo = subparsers.add_parser("tudo", help="Executa o pipeline completo (Parte Geral + Fichas)")
    p_tudo.add_argument("--saida-md", default=str(default_md))
    p_tudo.add_argument("--saida-json", default=str(default_json))
    p_tudo.add_argument("--paginas", help="Filtrar por faixa de páginas no PDF (ex: 32-37)")
    p_tudo.add_argument("--fichas", help="Filtrar por índice das fichas (ex: 1-5)")
    p_tudo.add_argument("--salvar-individuais", action="store_true")
    p_tudo.add_argument("--force", action="store_true")
    p_tudo.add_argument("--workers", type=int, default=4, help="Número de workers paralelos (padrão: 4)")

    args = parser.parse_args()

    if args.subcomando == "geral":
        cmd_geral(args)
    elif args.subcomando == "fichas":
        cmd_fichas(args)
    elif args.subcomando == "tudo":
        cmd_tudo(args)

if __name__ == "__main__":
    main()
