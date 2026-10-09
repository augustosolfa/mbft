from pathlib import Path

def obter_raiz_repo() -> Path:
    """Encontra a raiz do monorepo de forma resiliente."""
    cwd = Path.cwd()
    if (cwd / "data" / "raw").exists():
        return cwd
    atual = Path(__file__).resolve().parent
    for p in [atual, *atual.parents]:
        if (p / "data" / "raw").exists():
            return p
    return cwd

RAIZ_REPO = obter_raiz_repo()
DATA_DIR = RAIZ_REPO / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
