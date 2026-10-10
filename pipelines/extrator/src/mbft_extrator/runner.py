import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor

import pypdfium2 as pdfium

from mbft_core.paths import PROCESSED_DIR
from .models import Ficha, FichaMapeada
from .fatiador import mapear_fichas_no_pdf
from .pipeline import extrair_ficha_completa, Conversores, ResultadoExtracao
from .parte_geral import extrair_parte_geral
from .auditoria import gerar_relatorio_auditoria, CorrecaoOcr
from .utils import calcular_hash_pdf, VERSAO_PIPELINE
from .config import PAGINA_INICIO_PARTE_GERAL, PAGINA_FIM_PARTE_GERAL

logger = logging.getLogger("MBFT-RUNNER")

@lru_cache(maxsize=1)
def get_conversores() -> Conversores:
    c = Conversores()
    _ = c.padrao
    return c

@dataclass(frozen=True)
class TarefaFicha:
    pdf_path: str
    pdf_hash: str
    ficha_mapeada: FichaMapeada
    imagens_dir: str
    cache_fichas_dir: str
    pasta_individuais: Optional[str]
    force: bool

def _processar_uma_ficha_worker(tarefa: TarefaFicha) -> ResultadoExtracao:
    m = tarefa.ficha_mapeada
    pdf_path = Path(tarefa.pdf_path)
    imagens_dir = Path(tarefa.imagens_dir)
    cache_fichas_dir = Path(tarefa.cache_fichas_dir)
    f_cache = cache_fichas_dir / f"ficha_{m.identificador}.json"

    # Checkpoint
    if f_cache.exists() and not tarefa.force:
        try:
            with open(f_cache, "r", encoding="utf-8") as f:
                c_data = json.load(f)
                
            cache_hash = c_data.get("pdf_sha256")
            cache_versao = c_data.get("versao_pipeline")
            
            if cache_hash == tarefa.pdf_hash and cache_versao == VERSAO_PIPELINE:
                if "dados" in c_data and "correcoes" in c_data:
                    paginas_esperadas = list(range(m.pag_ini, m.pag_fim + 1))
                    if c_data["dados"].get("paginas") == paginas_esperadas:
                        return ResultadoExtracao(
                            ficha=Ficha.model_validate(c_data["dados"]),
                            correcoes_ocr=[CorrecaoOcr(**c) for c in c_data["correcoes"]]
                        )
                    logger.info(f"Intervalo de páginas da ficha {m.identificador} mudou ({c_data['dados'].get('paginas')} -> {paginas_esperadas}), reprocessando...")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"Cache corrompido para ficha {m.identificador}, reprocessando: {e}")

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        conversores = get_conversores()
    
        resultado = extrair_ficha_completa(
            doc=doc,
            conversores=conversores,
            pdf_path=pdf_path,
            mapeada=m,
            imagens_dir=imagens_dir,
        )
        dados = resultado.ficha.model_dump()
        correcoes = [c.__dict__ for c in resultado.correcoes_ocr]
    finally:
        doc.close()

    # Salva checkpoint no cache atômicamente
    temp_cache = f_cache.with_suffix(".tmp")
    cache_to_save = {
        "pdf_sha256": tarefa.pdf_hash,
        "versao_pipeline": VERSAO_PIPELINE,
        "dados": dados,
        "correcoes": correcoes
    }
    with open(temp_cache, "w", encoding="utf-8") as f:
        json.dump(cache_to_save, f, ensure_ascii=False, indent=2)
    os.replace(temp_cache, f_cache)

    # Se salvar individuais atômicamente
    if tarefa.pasta_individuais:
        pasta_indiv = Path(tarefa.pasta_individuais)
        pasta_indiv.mkdir(parents=True, exist_ok=True)
        f_indiv = pasta_indiv / f"ficha_{m.identificador}.json"
        temp_indiv = f_indiv.with_suffix(".tmp")
        
        with open(temp_indiv, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        os.replace(temp_indiv, f_indiv)

    return resultado

def parse_faixa(range_str: str) -> Tuple[int, int]:
    partes = range_str.split("-")
    if len(partes) != 2 or not partes[0].isdigit() or not partes[1].isdigit():
        raise ValueError(f"Formato de faixa inválido: '{range_str}'. Use o formato INICIO-FIM (ex: 32-35).")
    return int(partes[0]), int(partes[1])

def filtrar_por_faixa(mapeadas: List[FichaMapeada], paginas: Optional[str] = None, fichas: Optional[str] = None) -> List[FichaMapeada]:
    if paginas:
        v_ini, v_fim = parse_faixa(paginas)
        filtradas = [m for m in mapeadas if (m.pag_ini <= v_fim and m.pag_fim >= v_ini)]
        logger.info(f"Filtro por páginas {v_ini}-{v_fim}: {len(filtradas)} fichas selecionadas.")
        return filtradas
    elif fichas:
        v_ini, v_fim = parse_faixa(fichas)
        filtradas = mapeadas[v_ini - 1 : v_fim]
        logger.info(f"Filtro por índice de fichas {v_ini}-{v_fim}: {len(filtradas)} fichas selecionadas.")
        return filtradas
    return mapeadas

def construir_tarefas(mapeadas: List[FichaMapeada], pdf_path: Path, pdf_hash: str, imagens_dir: Path, cache_fichas_dir: Path, pasta_individuais: Optional[Path], force: bool) -> List[TarefaFicha]:
    return [
        TarefaFicha(
            pdf_path=str(pdf_path),
            pdf_hash=pdf_hash,
            ficha_mapeada=m,
            imagens_dir=str(imagens_dir),
            cache_fichas_dir=str(cache_fichas_dir),
            pasta_individuais=str(pasta_individuais) if pasta_individuais else None,
            force=force,
        )
        for m in mapeadas
    ]

def executar_tarefas(tasks: List[TarefaFicha], workers: int, total_fichas: int) -> Tuple[List[Ficha], List[Any]]:
    fichas_extraidas = []
    correcoes_totais = []
    concluidas = 0

    if workers <= 1:
        for t in tasks:
            result = _processar_uma_ficha_worker(t)
            correcoes_totais.extend(result.correcoes_ocr)
            concluidas += 1
            logger.info(f"[{concluidas}/{total_fichas}] Ficha {result.ficha.id} processada.")
            fichas_extraidas.append(result.ficha)
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(_processar_uma_ficha_worker, tasks):
                correcoes_totais.extend(result.correcoes_ocr)
                concluidas += 1
                logger.info(f"[{concluidas}/{total_fichas}] Ficha {result.ficha.id} processada.")
                fichas_extraidas.append(result.ficha)
                
    return fichas_extraidas, correcoes_totais

def salvar_consolidado(fichas_extraidas: List[Ficha], saida_json: Path, elapsed: float) -> None:
    saida_json.parent.mkdir(parents=True, exist_ok=True)
    temp_json = saida_json.with_suffix(".tmp")
    with open(temp_json, "w", encoding="utf-8") as f:
        json.dump([f.model_dump() for f in fichas_extraidas], f, ensure_ascii=False, indent=2)
    os.replace(temp_json, saida_json)
    logger.info(f"Consolidado salvo em: {saida_json} ({len(fichas_extraidas)} fichas, tempo: {elapsed:.1f}s)")

def executar_extracao_geral(pdf_path: Path, saida_md: Path) -> None:
    saida_md.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"=== Extraindo Parte Geral de {pdf_path} ===")
    extrair_parte_geral(pdf_path, saida_md, pag_ini=PAGINA_INICIO_PARTE_GERAL, pag_fim=PAGINA_FIM_PARTE_GERAL)
    logger.info("Extração da Parte Geral concluída com sucesso.")

def executar_extracao_fichas(
    pdf_path: Path,
    saida_json: Path,
    paginas: Optional[str] = None,
    fichas: Optional[str] = None,
    salvar_individuais: bool = False,
    force: bool = False,
    workers: int = 4,
) -> None:
    cache_fichas_dir = PROCESSED_DIR.parent.parent / "pipelines" / "extrator" / ".cache_extracao" / "fichas"
    cache_fichas_dir.mkdir(parents=True, exist_ok=True)
    mapa_cache = cache_fichas_dir.parent / "mapa_fichas.json"

    imagens_dir = saida_json.parent / "imagens"
    imagens_dir.mkdir(parents=True, exist_ok=True)
    
    pasta_individuais = (saida_json.parent / "fichas") if salvar_individuais else None

    logger.info(f"=== Iniciando Extração de Fichas de {pdf_path} ===")
    
    if not pdf_path.exists():
        logger.error(f"Arquivo não encontrado: {pdf_path}")
        sys.exit(1)
        
    pdf_hash = calcular_hash_pdf(pdf_path)
    
    mapeadas = mapear_fichas_no_pdf(pdf_path, cache_path=mapa_cache, force=force)
    
    try:
        mapeadas = filtrar_por_faixa(mapeadas, paginas=paginas, fichas=fichas)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    total = len(mapeadas)
    workers_num = max(1, workers)
    logger.info(f"Processando {total} fichas com {workers_num} worker(s) paralelos...")

    tasks = construir_tarefas(mapeadas, pdf_path, pdf_hash, imagens_dir, cache_fichas_dir, pasta_individuais, force)

    t0 = time.time()
    fichas_extraidas, correcoes_totais = executar_tarefas(tasks, workers_num, total)
    elapsed = time.time() - t0

    salvar_consolidado(fichas_extraidas, saida_json, elapsed)

    relatorio_path = saida_json.parent / "relatorio_extracao.md"
    relatorio_path.parent.mkdir(parents=True, exist_ok=True)
    doc_total = pdfium.PdfDocument(str(pdf_path))
    try:
        gerar_relatorio_auditoria(fichas_extraidas, len(doc_total), relatorio_path, correcoes_totais)
    finally:
        doc_total.close()
