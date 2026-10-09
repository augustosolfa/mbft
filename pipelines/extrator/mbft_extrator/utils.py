import hashlib
from pathlib import Path

def calcular_hash_pdf(pdf_path: Path) -> str:
    hash_sha256 = hashlib.sha256()
    with open(pdf_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

VERSAO_PIPELINE = "1.0.0"
