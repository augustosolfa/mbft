#!/usr/bin/env python3
"""
Ponto de entrada do Extrator MBFT.
Uso:
    uv run python extrair.py geral
    uv run python extrair.py fichas --range 32-37
    uv run python extrair.py fichas --salvar-individuais
    uv run python extrair.py tudo
"""

import sys
from pathlib import Path

# Garante que a pasta do pacote esteja no sys.path se executado diretamente sem instalação prévia
pkg_dir = Path(__file__).resolve().parent
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

from mbft_extrator.cli import main

if __name__ == "__main__":
    main()
