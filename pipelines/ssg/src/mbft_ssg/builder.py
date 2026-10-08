import json
import os
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Importa a tipagem do mbft-core
from mbft_core.models.enriquecimento import FichaEnriquecida

def run_build():
    print("Iniciando build do Site Estático (SSG)...")
    
    # Caminhos
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    templates_dir = Path(__file__).resolve().parent / "templates"
    output_dir = project_root / "data" / "processed" / "site"
    fichas_out_dir = output_dir / "fichas"
    
    json_path = project_root / "data" / "processed" / "enriquecedor" / "fichas_enriquecidas.json"
    imagens_src = project_root / "data" / "processed" / "extrator" / "imagens"
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
    print(f"Lendo dados de: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        dados_brutos = json.load(f)
        
    fichas = []
    for item in dados_brutos:
        # Validação estrita via Pydantic
        ficha = FichaEnriquecida(**item)
        fichas.append(ficha)
        
        # Gera HTML da Ficha
        html_ficha = template_ficha.render(ficha=ficha)
        out_ficha = fichas_out_dir / f"{ficha.codigo_enquadramento}.html"
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

    print(f"Build concluído com sucesso! {len(fichas)} fichas geradas em: {output_dir}")

if __name__ == "__main__":
    run_build()
