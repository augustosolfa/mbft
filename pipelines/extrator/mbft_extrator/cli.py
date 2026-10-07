"""
Ponto de entrada de linha de comando (CLI) para o Extrator do MBFT.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from typing import List, Optional, Tuple, Any

import pypdfium2 as pdfium

from .models import Ficha, FichaMapeada
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

# Variáveis globais do processo worker (lazy loading)
_WORKER_DOC: Optional[pdfium.PdfDocument] = None
_WORKER_CONVERTER: Optional[Any] = None


def _get_worker_converter():
    """Inicializa o conversor Docling sob demanda (lazy) na GPU para o worker."""
    global _WORKER_CONVERTER
    if _WORKER_CONVERTER is None:
        _WORKER_CONVERTER = criar_conversor_docling()
    return _WORKER_CONVERTER


def _obter_raiz_repo() -> Path:
    """Encontra a raiz do monorepo de forma resiliente."""
    cwd = Path.cwd()
    if (cwd / "data" / "raw").exists():
        return cwd
    atual = Path(__file__).resolve().parent
    for p in [atual, *atual.parents]:
        if (p / "data" / "raw").exists():
            return p
    return cwd


RAIZ_REPO = _obter_raiz_repo()
DEFAULT_PDF = RAIZ_REPO / "data" / "raw" / "mbft.pdf"
DEFAULT_MD = RAIZ_REPO / "data" / "processed" / "extrator" / "mbft_parte_geral.md"
DEFAULT_JSON = RAIZ_REPO / "data" / "processed" / "extrator" / "fichas_mbft.json"
DEFAULT_IMAGENS = RAIZ_REPO / "data" / "processed" / "extrator" / "imagens"
DEFAULT_FICHAS_INDIV = RAIZ_REPO / "data" / "processed" / "extrator" / "fichas"
DEFAULT_RELATORIO = RAIZ_REPO / "data" / "processed" / "extrator" / "relatorio_extracao.md"
DEFAULT_CACHE = RAIZ_REPO / "pipelines" / "extrator" / ".cache_extracao"


def _processar_uma_ficha_worker(item_args: Tuple[str, dict, str, str, bool, bool]) -> dict:
    """Função executada em cada processo worker para processar uma ficha individual."""
    pdf_path_str, m_dict, imagens_dir_str, cache_fichas_dir_str, salvar_individuais, force = item_args
    m = FichaMapeada(**m_dict)
    pdf_path = Path(pdf_path_str)
    imagens_dir = Path(imagens_dir_str)
    cache_fichas_dir = Path(cache_fichas_dir_str)
    f_cache = cache_fichas_dir / f"ficha_{m.codigo}.json"

    # Checkpoint
    if f_cache.exists() and not force:
        with open(f_cache, "r", encoding="utf-8") as f:
            return json.load(f)

    global _WORKER_DOC
    if _WORKER_DOC is None:
        _WORKER_DOC = pdfium.PdfDocument(pdf_path_str)

    ficha_obj = extrair_ficha_completa(
        doc=_WORKER_DOC,
        converter=_get_worker_converter,
        pdf_path=pdf_path,
        mapeada=m,
        imagens_dir=imagens_dir,
    )
    dados = ficha_obj.model_dump()

    # Salva checkpoint no cache
    with open(f_cache, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    # Se salvar individuais
    if salvar_individuais:
        pasta_indiv = DEFAULT_FICHAS_INDIV
        pasta_indiv.mkdir(parents=True, exist_ok=True)
        with open(pasta_indiv / f"ficha_{m.codigo}.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)

    return dados


def cmd_geral(args):
    """Executa a extração da Parte Geral (Páginas 1 a 31) para Markdown."""
    pdf_path = Path(args.pdf)
    saida = Path(args.saida_md)
    saida.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"=== Extraindo Parte Geral de {pdf_path} ===")
    extrair_parte_geral(pdf_path, saida, pag_ini=1, pag_fim=31)
    logger.info("Extração da Parte Geral concluída com sucesso.")


def cmd_fichas(args):
    """Executa a extração das Fichas de Fiscalização Estruturadas."""
    pdf_path = Path(args.pdf)
    saida_json = Path(args.saida_json)
    cache_dir = DEFAULT_CACHE
    cache_fichas_dir = cache_dir / "fichas"
    cache_fichas_dir.mkdir(parents=True, exist_ok=True)
    mapa_cache = cache_dir / "mapa_fichas.json"

    imagens_dir = DEFAULT_IMAGENS
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

    total = len(mapeadas)
    workers = max(1, getattr(args, "workers", 4))
    logger.info(f"Processando {total} fichas com {workers} worker(s) paralelos...")

    tasks = [
        (
            str(pdf_path),
            m.model_dump(),
            str(imagens_dir),
            str(cache_fichas_dir),
            args.salvar_individuais,
            args.force,
        )
        for m in mapeadas
    ]

    fichas_extraidas: List[Ficha] = []
    concluidas = 0
    t0 = time.time()

    if workers <= 1:
        for t in tasks:
            dados = _processar_uma_ficha_worker(t)
            concluidas += 1
            logger.info(f"[{concluidas}/{total}] Ficha {dados['id']} processada.")
            fichas_extraidas.append(Ficha(**dados))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for dados in executor.map(_processar_uma_ficha_worker, tasks):
                concluidas += 1
                logger.info(f"[{concluidas}/{total}] Ficha {dados['id']} processada.")
                fichas_extraidas.append(Ficha(**dados))

    elapsed = time.time() - t0

    # Gravação do JSON consolidado principal
    saida_json.parent.mkdir(parents=True, exist_ok=True)
    with open(saida_json, "w", encoding="utf-8") as f:
        json.dump([f.model_dump() for f in fichas_extraidas], f, ensure_ascii=False, indent=2)

    logger.info(f"Consolidado salvo em: {saida_json} ({len(fichas_extraidas)} fichas, tempo: {elapsed:.1f}s)")

    # Gera relatório de auditoria
    relatorio_path = DEFAULT_RELATORIO
    relatorio_path.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--pdf", default=str(DEFAULT_PDF), help=f"Caminho do arquivo mbft.pdf (padrão: {DEFAULT_PDF})")
    subparsers = parser.add_subparsers(dest="subcomando", required=True)

    # Subcomando geral
    p_geral = subparsers.add_parser("geral", help="Extrai a Parte Geral (páginas 1 a 31) para Markdown")
    p_geral.add_argument("--saida-md", default=str(DEFAULT_MD), help=f"Arquivo de saída Markdown (padrão: {DEFAULT_MD})")

    # Subcomando fichas
    p_fichas = subparsers.add_parser("fichas", help="Extrai as Fichas Estruturadas para JSON")
    p_fichas.add_argument("--saida-json", default=str(DEFAULT_JSON), help=f"Arquivo JSON consolidado (padrão: {DEFAULT_JSON})")
    p_fichas.add_argument("--range", help="Faixa de páginas (ex: 32-37) ou de fichas (ex: 1-5)")
    p_fichas.add_argument("--salvar-individuais", action="store_true", help="Salva cada ficha em fichas/ficha_<id>.json")
    p_fichas.add_argument("--force", action="store_true", help="Ignora checkpoints e reprocessa do zero")
    p_fichas.add_argument("--workers", type=int, default=4, help="Número de workers paralelos (padrão: 4)")

    # Subcomando tudo
    p_tudo = subparsers.add_parser("tudo", help="Executa o pipeline completo (Parte Geral + Fichas)")
    p_tudo.add_argument("--saida-md", default=str(DEFAULT_MD))
    p_tudo.add_argument("--saida-json", default=str(DEFAULT_JSON))
    p_tudo.add_argument("--range", help="Faixa opcional para as fichas")
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

