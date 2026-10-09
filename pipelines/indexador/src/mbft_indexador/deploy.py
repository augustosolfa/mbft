import os
import subprocess
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

def rodar_comando_wrangler(comando: list, description: str):
    if shutil.which("wrangler") is None:
        raise RuntimeError("Executável 'wrangler' não encontrado no PATH.")

    logger.info(f"Executando deploy: {description}")
    logger.info(f"Comando: {' '.join(comando)}")
    
    try:
        resultado = subprocess.run(comando, check=True, text=True, capture_output=True)
        logger.info(f"Sucesso: {resultado.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Erro ao executar wrangler: {e.stderr}")
        logger.error("Certifique-se de que o Node.js/Wrangler estão instalados e você está autenticado (wrangler login).")
        raise RuntimeError(f"Falha ao executar wrangler: {e.stderr}") from e

def fazer_deploy_vectorize(jsonl_path: Path, index_name: str = "mbft-vectors"):
    if not jsonl_path.exists():
        raise FileNotFoundError(f"Arquivo JSONL não encontrado em {jsonl_path}")
        
    comando = [
        "wrangler", "vectorize", "insert", index_name,
        "--file", str(jsonl_path)
    ]
    rodar_comando_wrangler(comando, f"Upload JSONL para Vectorize ({index_name})")

def fazer_deploy_d1(sql_script_path: Path, db_name: str = "mbft-db"):
    if not sql_script_path.exists():
        raise FileNotFoundError(f"Script SQL não encontrado em {sql_script_path}")
        
    comando = [
        "wrangler", "d1", "execute", db_name,
        "--file", str(sql_script_path),
        "--remote"
    ]
    rodar_comando_wrangler(comando, f"Executar script SQL no D1 ({db_name})")
