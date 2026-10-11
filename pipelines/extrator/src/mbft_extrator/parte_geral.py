"""
Módulo de extração da Parte Geral / Normativa do MBFT (Páginas 1 a 31).
Gera um arquivo Markdown estruturado em 'mbft_parte_geral.md' preservando a ordem
linear de leitura e a reconstrução geométrica de parágrafos via pypdfium2.
"""

import logging
import re
from pathlib import Path
from typing import List, Tuple

import pypdfium2 as pdfium

from .pdf_geometry import agrupar_em_linhas
from .pdf_reader import ler_pagina

logger = logging.getLogger("MBFT-ParteGeral")

RE_SEC_MAIN = re.compile(r"^\d{1,2}\.\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ\s]+$")
RE_SEC_SUB = re.compile(r"^\d{1,2}\.\d+\.\s+.+$")
RE_SEC_INF = re.compile(r"^Infrações\s+(?:Concorrentes|Concomitantes|Continuadas|Sucessivas)$")
RE_LIST_ITEM = re.compile(
    r"^(?:[●•]|[a-d]\)\s+|(?:I|II|III|IV|V)\s*[\.\-–—]\s+|Exemplo\s+\d+\s*:|Observação\s*:|Tratando-se\s+de\s+combinação)"
)

TOLERANCIA_LINHA_Y: float = 5.0
Y_LIMITE_NUMERO_PAGINA: float = 80.0
X0_RECUO_PARAGRAFO_MIN: float = 138.0
X0_RECUO_PARAGRAFO_MAX: float = 148.0


def limpar_ruidos_parte_geral(texto_md: str) -> str:
    """
    Normaliza quebras de linha excessivas e marcadores residuais.
    Nota: O descarte semântico de seções institucionais/editoriais (capa, ministros, sumário)
    é responsabilidade exclusiva do Enriquecedor (PMS-003).
    """
    limpo = re.sub(r"<!--\s*image\s*-->", "", texto_md)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo)
    return limpo.strip()


def extrair_linhas_geometricas_pagina(
    page: pdfium.PdfPage, num_pagina: int
) -> List[Tuple[int, float, float, str]]:
    """
    Extrai as linhas visuais de uma página ordenadas de cima para baixo,
    retornando tuplas (num_pagina, x0, yc, texto) e descartando o número de página no rodapé.
    """
    tp = page.get_textpage()
    pe = ler_pagina(page)
    items = [(r, (r.y0 + r.y1) / 2.0) for r in pe.retangulos]
    clusters = agrupar_em_linhas(items, lambda x: x[1], TOLERANCIA_LINHA_Y)

    linhas: List[Tuple[int, float, float, str]] = []
    for cl in clusters:
        cl.sort(key=lambda x: x[0].x0)
        x0 = min(x[0].x0 for x in cl)
        y0 = min(x[0].y0 for x in cl)
        x1 = max(x[0].x1 for x in cl)
        y1 = max(x[0].y1 for x in cl)
        yc = (y0 + y1) / 2.0
        txt = (
            tp.get_text_bounded(x0 - 1.0, y0 - 1.0, x1 + 1.0, y1 + 1.0)
            .replace("\r\n", " ")
            .replace("\n", " ")
            .strip()
        )
        txt = re.sub(r"\s+", " ", txt)
        if not txt:
            continue
        if yc < Y_LIMITE_NUMERO_PAGINA and re.fullmatch(r"\d{1,2}", txt):
            continue
        linhas.append((num_pagina, x0, yc, txt))
    return linhas


def reconstruir_markdown_linhas(
    linhas_meta: List[Tuple[int, float, float, str]],
) -> str:
    """
    Reconstrói cabeçalhos e parágrafos a partir das linhas geométricas (num_pagina, x0, yc, texto).
    Preserva a estrutura de capítulos/subseções e evita quebras artificiais no meio de frases.
    """
    blocos: List[str] = []
    in_siglas = False
    in_normativo = False
    i = 0

    while i < len(linhas_meta):
        pag, x0, _yc, txt = linhas_meta[i]

        # Páginas pré-textuais (1 a 4: capa, autoridades, ficha técnica e sumário)
        if not in_normativo and not RE_SEC_MAIN.match(txt):
            if txt in ("FICHA TÉCNICA", "SUMÁRIO", "CONSELHO NACIONAL DE TRÂNSITO"):
                blocos.append(f"## {txt}")
            else:
                blocos.append(txt)
            i += 1
            continue

        if RE_SEC_MAIN.match(txt):
            in_normativo = True
            in_siglas = txt.startswith("2.")
            blocos.append(f"## {txt}")
            i += 1
            continue

        if RE_SEC_SUB.match(txt):
            in_siglas = False
            if i + 1 < len(linhas_meta):
                _, nx0, _, ntxt = linhas_meta[i + 1]
                if nx0 < 100.0 and (ntxt == "(MBFT)" or ntxt.startswith("Faixa de Domínio")):
                    txt = f"{txt} {ntxt}"
                    i += 1
            blocos.append(f"## {txt}")
            i += 1
            continue

        if RE_SEC_INF.match(txt):
            in_siglas = False
            blocos.append(f"## {txt}")
            i += 1
            continue

        if in_siglas:
            blocos.append(txt)
            i += 1
            continue

        em_bullet_aberto = (
            bool(blocos)
            and blocos[-1].startswith("- ")
            and not blocos[-1].endswith((".", ";", ":"))
        )
        is_new_para = (
            bool(RE_LIST_ITEM.match(txt))
            or (
                not em_bullet_aberto
                and (X0_RECUO_PARAGRAFO_MIN <= x0 <= X0_RECUO_PARAGRAFO_MAX)
            )
            or (not blocos)
            or blocos[-1].startswith("## ")
        )
        if is_new_para:
            if txt.startswith("●"):
                txt = "- " + txt.lstrip("●").strip()
            blocos.append(txt)
        else:
            blocos[-1] = f"{blocos[-1]} {txt}"
        i += 1

    return limpar_ruidos_parte_geral("\n\n".join(blocos))


def extrair_parte_geral(
    pdf_path: Path,
    output_path: Path,
    pag_ini: int = 1,
    pag_fim: int = 31,
) -> Path:
    """
    Extrai as páginas iniciais (1 a 31) do PDF e grava em Markdown estruturado.
    """
    logger.info(f"Iniciando extração da Parte Geral (páginas {pag_ini} a {pag_fim})...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        linhas_meta: List[Tuple[int, float, float, str]] = []
        for idx_pag in range(pag_ini - 1, min(pag_fim, len(doc))):
            linhas_meta.extend(extrair_linhas_geometricas_pagina(doc[idx_pag], idx_pag + 1))
    finally:
        doc.close()

    conteudo_limpo = reconstruir_markdown_linhas(linhas_meta)

    cabecalho = (
        "# MANUAL BRASILEIRO DE FISCALIZAÇÃO DE TRÂNSITO (MBFT)\n"
        "## PARTE GERAL - DISPOSIÇÕES GERAIS E CONCEITOS\n\n"
        f"<!-- Páginas do documento original: {pag_ini} a {pag_fim} -->\n\n"
    )

    documento_final = cabecalho + conteudo_limpo + "\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(documento_final)

    logger.info(
        f"Parte Geral salva com sucesso em: {output_path} ({len(documento_final)} caracteres)"
    )
    return output_path

