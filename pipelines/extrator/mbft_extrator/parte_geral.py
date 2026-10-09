"""
Módulo de extração da Parte Geral / Normativa do MBFT (Páginas 1 a 31).
Gera um arquivo Markdown estruturado e sem ruídos em 'mbft_parte_geral.md'.
"""

import logging
import re
from pathlib import Path

import pypdfium2 as pdfium
from .docling_extractor import criar_conversor

logger = logging.getLogger("MBFT-ParteGeral")


def limpar_ruidos_parte_geral(texto_md: str) -> str:
    """
    Remove cabeçalhos governamentais repetitivos, rodapés e números de página.
    """
    # Remove marcadores de imagem não renderizados
    limpo = re.sub(r"<!--\s*image\s*-->", "", texto_md)

    # Remove cabeçalhos institucionais repetidos
    limpo = re.sub(
        r"^\s*#+\s*CONSELHO\s+NACIONAL\s+DE\s+TR[AÂ]NSITO.*$",
        "",
        limpo,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    limpo = re.sub(
        r"^\s*#+\s*MANUAL\s+BRASILEIRO\s+DE\s+FISCALIZA[CÇ][AÃ]O\s+DE\s+TR[AÂ]NSITO.*$",
        "",
        limpo,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # Normaliza múltiplas quebras de linha residuais
    limpo = re.sub(r"\n{3,}", "\n\n", limpo)
    return limpo.strip()


def extrair_parte_geral(
    pdf_path: Path,
    output_path: Path,
    pag_ini: int = 1,
    pag_fim: int = 31,
) -> Path:
    """
    Extrai as páginas normativas iniciais (1 a 31) do PDF e grava em Markdown estruturado.
    """
    logger.info(f"Iniciando extração da Parte Geral (páginas {pag_ini} a {pag_fim})...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    converter = criar_conversor(do_ocr=False)
    res = converter.convert(str(pdf_path), page_range=(pag_ini, pag_fim))
    doc = res.document

    conteudo_md = doc.export_to_markdown()
    conteudo_limpo = limpar_ruidos_parte_geral(conteudo_md)

    # Anotação inicial do documento
    cabecalho = (
        "# MANUAL BRASILEIRO DE FISCALIZAÇÃO DE TRÂNSITO (MBFT)\n"
        "## PARTE GERAL - DISPOSIÇÕES GERAIS E CONCEITOS\n\n"
        f"<!-- Páginas do documento original: {pag_ini} a {pag_fim} -->\n\n"
    )

    documento_final = cabecalho + conteudo_limpo + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(documento_final)

    logger.info(f"Parte Geral salva com sucesso em: {output_path} ({len(documento_final)} caracteres)")
    return output_path
