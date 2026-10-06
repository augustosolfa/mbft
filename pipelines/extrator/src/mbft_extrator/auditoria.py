"""
Módulo de auditoria e validação de qualidade das fichas extraídas do MBFT.
Gera o relatório 'relatorio_extracao.md'.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any

from .models import Ficha

logger = logging.getLogger("MBFT-Auditoria")


def gerar_relatorio_auditoria(
    fichas: List[Ficha],
    total_paginas_pdf: int,
    output_path: Path,
) -> Path:
    """
    Gera relatório em Markdown detalhando a integridade dos dados extraídos.
    """
    logger.info("Gerando relatório de auditoria e controle de qualidade...")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_fichas = len(fichas)
    fichas_multipagina = [f for f in fichas if len(f.paginas) > 1]
    fichas_com_imagens = [f for f in fichas if len(f.imagens) > 0]
    total_imagens = sum(len(f.imagens) for f in fichas)

    # Identifica anomalias em campos essenciais
    alertas: List[str] = []
    for f in fichas:
        if not f.tipificacao_resumida:
            alertas.append(f"Ficha {f.id}: Campo 'tipificacao_resumida' vazio.")
        if not f.amparo_legal:
            alertas.append(f"Ficha {f.id}: Campo 'amparo_legal' vazio.")
        if not f.infrator:
            alertas.append(f"Ficha {f.id}: Campo 'infrator' vazio.")
        if not f.competencia:
            alertas.append(f"Ficha {f.id}: Campo 'competencia' vazio.")

    linhas = [
        "# Relatório de Auditoria e Controle de Qualidade da Extração - MBFT",
        "",
        "## 1. Estatísticas Gerais da Execução",
        f"- **Total de Fichas Extraídas:** {total_fichas}",
        f"- **Total de Páginas do PDF:** {total_paginas_pdf}",
        f"- **Fichas Multipágina (2 ou mais páginas):** {len(fichas_multipagina)} ({len(fichas_multipagina)/total_fichas*100:.1f}%)" if total_fichas > 0 else "",
        f"- **Fichas com Imagens Extraídas:** {len(fichas_com_imagens)}",
        f"- **Total de Imagens Geradas (PNG Nativas):** {total_imagens}",
        f"- **Total de Alertas/Anomalias:** {len(alertas)}",
        "",
        "## 2. Casos Canônicos de Validação",
    ]

    # Verifica os 3 casos do benchmark
    codigos_benchmark = ["563-00", "599-10", "683-11"]
    for cod in codigos_benchmark:
        f_b = next((f for f in fichas if f.id == cod), None)
        if f_b:
            linhas.append(f"### Ficha {cod}")
            linhas.append(f"- **Páginas:** {f_b.paginas}")
            linhas.append(f"- **Quando Autuar (itens):** {len(f_b.quando_autuar.itens)}")
            linhas.append(f"- **Definições e Procedimentos (itens):** {len(f_b.definicoes_procedimentos.itens)}")
            linhas.append(f"- **Imagens associadas:** {f_b.imagens}")
            linhas.append("")
        else:
            linhas.append(f"- *Ficha {cod} não processada nesta rodada.*")

    linhas.extend([
        "## 3. Alertas e Anomalias",
    ])
    if alertas:
        for a in alertas[:50]:
            linhas.append(f"- ⚠️ {a}")
        if len(alertas) > 50:
            linhas.append(f"- *... e mais {len(alertas) - 50} alertas omitidos.*")
    else:
        linhas.append("- ✅ Nenhuma anomalia crítica ou campo obrigatório vazio detectado.")

    linhas.append("")
    conteudo_md = "\n".join(linhas)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(conteudo_md)

    logger.info(f"Relatório de auditoria gravado em: {output_path}")
    return output_path
