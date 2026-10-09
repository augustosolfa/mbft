import logging
from typing import Optional, List, Tuple
from pathlib import Path
import re

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableFormerMode,
    AcceleratorOptions,
)
from docling.datamodel.base_models import InputFormat

logger = logging.getLogger("MBFT-Docling")

def _patch_transformers():
    """
    Compatibilidade com Windows Smart App Control: desativa checagem opcional de scipy
    em transformers para evitar bloqueio de DLLs C-extensions não assinadas (_lbfgsb/_hausdorff)
    """
    try:
        import transformers.utils.import_utils as _tf_utils
        _tf_utils.is_scipy_available = lambda: False
    except Exception:
        pass


def criar_conversor(
    do_ocr: bool,
    num_threads: int = 8,
    device: str = "cuda",
) -> DocumentConverter:
    """
    Inicializa o pipeline do Docling configurado para acelerar via CUDA / GPU
    na NVIDIA GeForce RTX 4070.
    """
    _patch_transformers()
    
    logger.info(f"Inicializando pipeline Docling (OCR={do_ocr}) com aceleração '{device}'...")

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = do_ocr
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    pipeline_options.table_structure_options.do_cell_matching = True

    # Aceleração explícita via GPU CUDA
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=num_threads,
        device=device,
    )

    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
    }

    return DocumentConverter(format_options=format_options)


def processar_intervalo_docling(
    converter: DocumentConverter,
    pdf_path: Path,
    pag_ini: int,
    pag_fim: int,
):
    """
    Processa um intervalo de páginas com o Docling retornando o documento estruturado.
    """
    logger.info(f"Executando Docling com CUDA nas páginas {pag_ini} a {pag_fim}...")
    conv_result = converter.convert(str(pdf_path), page_range=(pag_ini, pag_fim))
    return conv_result.document


def parse_metadados_markdown(md_text: str) -> dict:
    meta_limpo = {}
    m_inf = re.search(r'Infrator\s*:?\s*([^|]*?)(?=\n|$|Compet[eê]ncia)', md_text, re.IGNORECASE)
    if m_inf:
        val = m_inf.group(1).strip()
        val = re.sub(r'[\*_\|]', '', val)
        val = re.sub(r'\s+', ' ', val).strip()
        meta_limpo['infrator'] = val
        
    m_const = re.search(r'Constata[cç][aã]o da Infra[cç][aã]o\s*:?\s*([^|]*?)(?=\n|$|Quando)', md_text, re.IGNORECASE)
    if m_const:
        val = m_const.group(1).strip()
        val = re.sub(r'[\*_\|]', '', val)
        val = re.sub(r'\s+', ' ', val).strip()
        meta_limpo['constatacao_infracao'] = val
        
    return meta_limpo


def extrair_metadados_visuais(converter_ocr: DocumentConverter, pdf_path: Path, pagina: int) -> dict:
    logger.info(f"Executando Docling OCR na pagina {pagina} de {pdf_path.name}...")
    conv_result = converter_ocr.convert(str(pdf_path), page_range=(pagina, pagina))
    md_text = conv_result.document.export_to_markdown()
    return parse_metadados_markdown(md_text)
