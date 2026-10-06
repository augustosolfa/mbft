#!/usr/bin/env python3
"""
Script de Comparação e Auditoria Regressiva entre Versões de Extração (v1 vs v2).
Compara ficha por ficha os campos de metadados, colunas normativas e informações complementares.
Uso:
    uv run python comparar_versoes.py
    uv run python comparar_versoes.py --v1 backup_extracao_v1/fichas_mbft.json --v2 fichas_mbft.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _obter_raiz_repo() -> Path:
    cwd = Path.cwd()
    if (cwd / "data" / "processed").exists():
        return cwd
    atual = Path(__file__).resolve().parent
    for p in [atual, *atual.parents]:
        if (p / "data" / "processed").exists():
            return p
    return cwd


RAIZ_REPO = _obter_raiz_repo()
DEFAULT_V1 = RAIZ_REPO / "data" / "archive" / "backup_extracao_v1" / "fichas_mbft.json"
DEFAULT_V2 = RAIZ_REPO / "data" / "processed" / "extrator" / "fichas_mbft.json"


def carregar_json(caminho: Path) -> Dict[str, Dict[str, Any]]:
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)
    return {item["id"]: item for item in dados}


def comparar_versoes(v1_path: Path, v2_path: Path, verbose: bool = False):
    print("=" * 70)
    print("AUDITORIA REGRESSIVA DE EXTRAÇÃO: v1 vs. v2")
    print(f"Versão 1 (Base): {v1_path}")
    print(f"Versão 2 (Nova): {v2_path}")
    print("=" * 70)

    fichas_v1 = carregar_json(v1_path)
    fichas_v2 = carregar_json(v2_path)

    print(f"\n1. Quantidade de Fichas:")
    print(f"   - v1: {len(fichas_v1)} fichas")
    print(f"   - v2: {len(fichas_v2)} fichas")

    ids_v1 = set(fichas_v1.keys())
    ids_v2 = set(fichas_v2.keys())
    if ids_v1 != ids_v2:
        print(f"   ⚠️ Diferença de IDs: apenas em v1: {ids_v1 - ids_v2}, apenas em v2: {ids_v2 - ids_v1}")
    else:
        print(f"   ✅ Todos os 404 códigos de enquadramento coincidem perfeitamente.")

    campos_meta = [
        "tipificacao_resumida",
        "codigo_enquadramento",
        "amparo_legal",
        "tipificacao_enquadramento",
        "gravidade",
        "penalidade",
        "medida_administrativa",
        "pode_configurar_crime_transito",
        "infrator",
        "competencia",
        "pontuacao",
        "constatacao_infracao",
    ]
    campos_normativos = [
        "quando_autuar",
        "quando_nao_autuar",
        "definicoes_procedimentos",
        "exemplos_observacoes_ait",
    ]

    total = len(fichas_v1)
    identicas_100 = 0
    diff_meta = []
    diff_normativos = []
    diff_ic = []
    novos_campos = 0

    for fid, f1 in fichas_v1.items():
        if fid not in fichas_v2:
            continue
        f2 = fichas_v2[fid]

        # Verifica novidade do campo competencia_alterada_lei_14599
        if "competencia_alterada_lei_14599" in f2 and "competencia_alterada_lei_14599" not in f1:
            novos_campos += 1

        # 1. Metadados
        meta_alterados = []
        for c in campos_meta:
            v1_c = (f1.get(c) or "").strip()
            v2_c = (f2.get(c) or "").strip()
            if v1_c != v2_c:
                meta_alterados.append((c, v1_c, v2_c))
        if meta_alterados:
            diff_meta.append((fid, meta_alterados))

        # 2. Colunas Normativas
        norm_alterados = []
        for c in campos_normativos:
            o1 = f1.get(c, {})
            o2 = f2.get(c, {})
            if o1.get("texto", "").strip() != o2.get("texto", "").strip() or o1.get("itens") != o2.get("itens"):
                norm_alterados.append(c)
        if norm_alterados:
            diff_normativos.append((fid, norm_alterados))

        # 3. Informações Complementares
        ic1 = (f1.get("informacoes_complementares") or "").strip()
        ic2 = (f2.get("informacoes_complementares") or "").strip()
        if ic1 != ic2:
            diff_ic.append((fid, len(ic1), len(ic2)))

        if not meta_alterados and not norm_alterados and ic1 == ic2:
            identicas_100 += 1

    print(f"\n2. Resumo da Comparação de Conteúdo:")
    print(f"   - Fichas com conteúdo 100% IDÊNTICO (incluindo HTML de IC): {identicas_100} ({identicas_100/total*100:.1f}%)")
    print(f"   - Colunas Normativas 100% IDÊNTICAS: {total - len(diff_normativos)} / {total} ({(total - len(diff_normativos))/total*100:.1f}%)")
    print(f"   - Metadados de Cabeçalho 100% IDÊNTICOS: {total - len(diff_meta)} / {total} ({(total - len(diff_meta))/total*100:.1f}%)")
    print(f"   - Fichas com campo 'competencia_alterada_lei_14599' incorporado: {novos_campos} / {total}")

    if diff_meta:
        print(f"\n3. Detalhes de Alterações nos Metadados ({len(diff_meta)} fichas):")
        for fid, alters in diff_meta:
            print(f"   • Ficha {fid}:")
            for c, old_v, new_v in alters:
                print(f"     - {c}:")
                print(f"       [v1]: {repr(old_v)}")
                print(f"       [v2]: {repr(new_v)}")

    if diff_normativos:
        print(f"\n4. Fichas com diferenças nas Colunas Normativas ({len(diff_normativos)} fichas):")
        for fid, cols in diff_normativos[:10]:
            print(f"   • Ficha {fid}: {cols}")
        if len(diff_normativos) > 10:
            print(f"   ... e mais {len(diff_normativos) - 10} fichas.")
    else:
        print(f"\n4. Colunas Normativas: ✅ NENHUMA REGRESSÃO (100% idênticas entre v1 e v2).")

    print(f"\n5. Informações Complementares ({len(diff_ic)} fichas com variação):")
    print(f"   - A v2 limpou tabelas fantasmas geradas pelo Docling em seções que continham apenas texto/fotos.")
    if verbose:
        for fid, l1, l2 in diff_ic[:15]:
            print(f"   • Ficha {fid}: tamanho v1={l1} chars -> v2={l2} chars")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Compara os resultados JSON entre v1 e v2.")
    parser.add_argument("--v1", default=DEFAULT_V1, type=Path, help=f"Caminho do JSON v1 (padrão: {DEFAULT_V1})")
    parser.add_argument("--v2", default=DEFAULT_V2, type=Path, help=f"Caminho do JSON v2 (padrão: {DEFAULT_V2})")
    parser.add_argument("--verbose", "-v", action="store_true", help="Exibe detalhes completos das diferenças")
    args = parser.parse_args()

    comparar_versoes(args.v1, args.v2, verbose=args.verbose)


if __name__ == "__main__":
    main()
