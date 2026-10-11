import json
import os
import shutil
import logging
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape

from mbft_core.models.enriquecimento import FichaEnriquecida
from mbft_core.paths import PROCESSED_DIR

logger = logging.getLogger(__name__)

def run_build(
    fichas_json: Optional[Path] = None,
    templates_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    imagens_src: Optional[Path] = None
):
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    logger.setLevel(logging.INFO)
    if fichas_json is None:
        fichas_json = PROCESSED_DIR / "enriquecedor" / "fichas_enriquecidas.json"
    if templates_dir is None:
        templates_dir = Path(__file__).resolve().parent / "templates"
    if output_dir is None:
        output_dir = PROCESSED_DIR / "site"
    if imagens_src is None:
        imagens_src = PROCESSED_DIR / "extrator" / "imagens"

    logger.info("Iniciando build do Site Estático (SSG)...")
    
    fichas_out_dir = output_dir / "fichas"
    imagens_dst = output_dir / "imagens"
    
    # Prepara diretório de saída
    if output_dir.exists():
        shutil.rmtree(output_dir)
    fichas_out_dir.mkdir(parents=True, exist_ok=True)
    
    if imagens_src.exists():
        shutil.copytree(imagens_src, imagens_dst)
    
    # Configura Jinja2
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html", "xml"])
    )
    template_ficha = env.get_template("ficha.html")
    
    # Carrega e converte os dados
    logger.info(f"Lendo dados de: {fichas_json}")
    with open(fichas_json, "r", encoding="utf-8") as f:
        dados_brutos = json.load(f)
        
    fichas = []
    seen_ids = set()
    for item in dados_brutos:
        # Validação estrita via Pydantic
        ficha = FichaEnriquecida(**item)
        fichas.append(ficha)
        
        if ficha.id in seen_ids:
            raise ValueError(f"Colisão de ID detectada: o arquivo {ficha.id}.html seria sobrescrito.")
        seen_ids.add(ficha.id)
        
        # Gera HTML da Ficha
        html_ficha = template_ficha.render(ficha=ficha)
        out_ficha = fichas_out_dir / f"{ficha.id}.html"
        out_ficha.write_text(html_ficha, encoding="utf-8")
        
    # Gera HTML da Lista Completa
    template_lista = env.get_template("lista.html")
    html_lista = template_lista.render(fichas=fichas)
    out_lista = output_dir / "lista.html"
    out_lista.write_text(html_lista, encoding="utf-8")
    
    # Processa e copia o index.html (Portal estático com busca RAG)
    template_index = env.get_template("index.html")
    html_index = template_index.render()
    out_index = output_dir / "index.html"
    out_index.write_text(html_index, encoding="utf-8")
    
    # Processa e copia o chat.html (puramente estático)
    template_chat = env.get_template("chat.html")
    html_chat = template_chat.render()
    out_chat = output_dir / "chat.html"
    out_chat.write_text(html_chat, encoding="utf-8")

    # Gera arquivo de configuração neutro de runtime (pode ser sobrescrito no deploy sem re-rodar o SSG)
    out_config = output_dir / "config.js"
    out_config.write_text(
        'window.MBFT_CONFIG = {\n  apiBaseUrl: ""\n};\n',
        encoding="utf-8",
    )

    logger.info(f"Build concluído com sucesso! {len(fichas)} fichas geradas em: {output_dir}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    run_build()
