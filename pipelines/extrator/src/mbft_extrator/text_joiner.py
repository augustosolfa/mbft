"""
Módulo especializado na mesclagem e normalização espacial/textual de fragmentos (SRP).
"""

import re
from typing import List, Tuple

DEFAULT_GAP_THRESHOLD: float = 2.5


def join_line_fragments(
    frags: List[Tuple[float, float, str]],
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> str:
    """
    Junta fragmentos de texto na mesma linha horizontal com tolerância espacial.

    Args:
        frags: Lista de tuplas (x0, x1, texto).
        gap_threshold: Distância máxima em pontos para considerar caracteres contíguos da mesma palavra.

    Returns:
        Texto da linha unificado e normalizado.
    """
    if not frags:
        return ""

    frags_sorted = sorted(frags, key=lambda f: f[0])
    res = [frags_sorted[0][2]]

    for i in range(1, len(frags_sorted)):
        prev_x1 = frags_sorted[i - 1][1]
        curr_x0 = frags_sorted[i][0]
        curr_txt = frags_sorted[i][2]
        gap = curr_x0 - prev_x1

        if gap < gap_threshold and not res[-1].endswith(" ") and not curr_txt.startswith(" "):
            res.append(curr_txt)
        else:
            res.append(" " + curr_txt)

    joined = "".join(res)
    # Corrige quebras em códigos de enquadramento como "502 - 91" -> "502-91"
    joined = re.sub(r"(\d+)\s*-\s*(\d+)", r"\1-\2", joined)
    return re.sub(r"\s+", " ", joined).strip()


def unificar_linhas_e_hifens(lines: List[str]) -> str:
    """
    Unifica uma sequência de linhas de texto corrido, removendo quebras duras e
    reunindo palavras hifenizadas no final da linha (ex: 'cruzamen-' + 'to' -> 'cruzamento').
    """
    if not lines:
        return ""

    texto = lines[0].strip()
    for l in lines[1:]:
        l = l.strip()
        if not l:
            continue
        if texto.endswith("-") and not texto.endswith(" -"):
            texto = texto[:-1] + l
        else:
            texto = texto + " " + l
    return texto


__all__ = ["join_line_fragments", "unificar_linhas_e_hifens"]
