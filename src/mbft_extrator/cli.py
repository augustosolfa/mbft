"""
Ponto de entrada de linha de comando (CLI) para o Extrator do MBFT.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

import pypdfium2 as pdfium

from .models import Ficha
from .fatiador import mapear_fichas_no_pdf
from .pipeline import extrair_ficha_completa
from .parte_geral import extrair_parte_geral
from .auditoria import gerar_relatorio_auditoria
from .docling_extractor import criar_conversor_docling

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MBFT-CLI")


def cmd_geral(args):
    """Executa a extração da Parte Geral (Páginas 1 a 31) para Markdown."""
    pdf_path = Path(args.pdf)
    saida = Path(args.saida_md)
    logger.info(f"=== Extraindo Parte Geral de {pdf_path} ===")
    extrair_parte_geral(pdf_path, saida, pag_ini=1, pag_fim=31)
    logger.info("Extração da Parte Geral concluída com sucesso.")


def cmd_fichas(args):
    """Executa a extração das Fichas de Fiscalização Estruturadas."""
    pdf_path = Path(args.pdf)
    saida_json = Path(args.saida_json)
    cache_dir = Path(".cache_extracao")
    cache_fichas_dir = cache_dir / "fichas"
    cache_fichas_dir.mkdir(parents=True, exist_ok=True)
    mapa_cache = cache_dir / "mapa_fichas.json"

    imagens_dir = Path("imagens")
    imagens_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== Iniciando Extração de Fichas de {pdf_path} ===")
    mapeadas = mapear_fichas_no_pdf(pdf_path, cache_path=mapa_cache, force=args.force)

    # Filtro por --range se especificado (ex: 32-37 para páginas, ou 1-5 para índice de fichas)
    if args.range:
        partes = args.range.split("-")
        if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
            v_ini, v_fim = int(partes[0]), int(partes[1])
            # Se valores forem >= 32, trata como número de página
            if v_ini >= 32:
                mapeadas = [m for m in mapeadas if (m.pag_ini <= v_fim and m.pag_fim >= v_ini)]
                logger.info(f"Filtro por faixa de páginas {v_ini}-{v_fim}: {len(mapeadas)} fichas selecionadas.")
            else:
                # Trata como índice de fichas (1-based)
                mapeadas = mapeadas[v_ini - 1 : v_fim]
                logger.info(f"Filtro por índice de fichas {v_ini}-{v_fim}: {len(mapeadas)} fichas selecionadas.")

    doc = pdfium.PdfDocument(str(pdf_path))
    converter = criar_conversor_docling()

    fichas_extraidas: List[Ficha] = []
    total = len(mapeadas)

    t0 = time.time()
    for idx, m in enumerate(mapeadas, start=1):
        f_cache = cache_fichas_dir / f"ficha_{m.codigo}.json"
        
        # Checkpointing
        if f_cache.exists() and not args.force:
            logger.info(f"[{idx}/{total}] Ficha {m.codigo} carregada do checkpoint.")
            with open(f_cache, "r", encoding="utf-8") as f:
                ficha_obj = Ficha(**json.load(f))
        else:
            logger.info(f"[{idx}/{total}] Extraindo Ficha {m.codigo} (págs {m.pag_ini}-{m.pag_fim})...")
            ficha_obj = extrair_ficha_completa(
                doc=doc,
                converter=converter,
                pdf_path=pdf_path,
                mapeada=m,
                imagens_dir=imagens_dir,
            )
            # Salva checkpoint
            with open(f_cache, "w", encoding="utf-8") as f:
                json.dump(ficha_obj.model_dump(), f, ensure_ascii=False, indent=2)

        fichas_extraidas.append(ficha_obj)

        # Se solicitado salvar individuais
        if args.salvar_individuais:
            pasta_indiv = Path("fichas")
            pasta_indiv.mkdir(parents=True, exist_ok=True)
            with open(pasta_indiv / f"ficha_{m.codigo}.json", "w", encoding="utf-8") as f:
                json.dump(ficha_obj.model_dump(), f, ensure_ascii=False, indent=2)

    doc.close()
    elapsed = time.time() - t0

    # Gravação do JSON consolidado principal
    saida_json.parent.mkdir(parents=True, exist_ok=True)
    with open(saida_json, "w", encoding="utf-8") as f:
        json.dump([f.model_dump() for f in fichas_extraidas], f, ensure_ascii=False, indent=2)

    logger.info(f"Consolidado salvo em: {saida_json} ({len(fichas_extraidas)} fichas, tempo: {elapsed:.1f}s)")

    # Gera relatório de auditoria
    relatorio_path = Path("relatorio_extracao.md")
    doc_total = pdfium.PdfDocument(str(pdf_path))
    gerar_relatorio_auditoria(fichas_extraidas, len(doc_total), relatorio_path)
    doc_total.close()


def cmd_tudo(args):
    """Executa a extração completa (Parte Geral + Fichas)."""
    cmd_geral(args)
    cmd_fichas(args)


def main():
    parser = argparse.ArgumentParser(
        description="Extrator de Alta Fidelidade do Manual Brasileiro de Fiscalização de Trânsito (MBFT)"
    )
    parser.add_argument("--pdf", default="mbft.pdf", help="Caminho do arquivo mbft.pdf")
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    # Subcomando geral
    p_geral = subparsers.add_parser("geral", help="Extrai a Parte Geral (páginas 1 a 31) para Markdown")
    p_geral.add_argument("--saida-md", default="mbft_parte_geral.md", help="Arquivo de saída Markdown")

    # Subcomando fichas
    p_fichas = subparsers.add_parser("fichas", help="Extrai as Fichas Estruturadas para JSON")
    p_fichas.add_argument("--saida-json", default="fichas_mbft.json", help="Arquivo JSON consolidado")
    p_fichas.add_argument("--range", help="Faixa de páginas (ex: 32-37) ou de fichas (ex: 1-5)")
    p_fichas.add_argument("--salvar-individuais", action="store_true", help="Salva cada ficha em fichas/ficha_<id>.json")
    p_fichas.add_argument("--force", action="store_true", help="Ignora checkpoints e reprocessa do zero")

    # Subcomando tudo
    p_tudo = subparsers.add_parser("tudo", help="Executa o pipeline completo (Parte Geral + Fichas)")
    p_tudo.add_argument("--saida-md", default="mbft_parte_geral.md")
    p_tudo.add_argument("--saida-json", default="fichas_mbft.json")
    p_tudo.add_argument("--range", help="Faixa opcional para as fichas")
    p_tudo.add_argument("--salvar-individuais", action="store_true")
    p_tudo.add_argument("--force", action="store_true")

    args = parser.parse_args()

    if args.subcomando == "geral":
        cmd_geral(args)
    elif args.subcomando == "fichas":
        cmd_fichas(args)
    elif args.subcomando == "tudo":
        cmd_tudo(args)


if __name__ == "__main__":
    main()
