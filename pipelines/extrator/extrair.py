#!/usr/bin/env python3
"""
Ponto de entrada do Extrator MBFT.
Uso:
    uv run python extrair.py geral
    uv run python extrair.py fichas --paginas 32-37
    uv run python extrair.py fichas --salvar-individuais
    uv run python extrair.py tudo
"""

from mbft_extrator.cli import main

if __name__ == "__main__":
    main()
