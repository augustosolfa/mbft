import json
import logging
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from mbft_core.models.enriquecimento import (
    FichaEnriquecida,
    MedidaAdministrativaEnum,
    ParteGeralEnriquecida,
    SecaoParteGeral,
)
from mbft_core.paths import PROCESSED_DIR

logger = logging.getLogger(__name__)


def _obter_ancora_medida_pg(ficha: FichaEnriquecida) -> str | None:
    """
    Determina a âncora específica de Medida Administrativa na Parte Geral
    quando a ficha referencia a Parte Geral ou prevê medida administrativa.
    """
    medidas = ficha.medidas_administrativas
    if MedidaAdministrativaEnum.RETENCAO_VEICULO in medidas:
        return "pg_8_1"
    if MedidaAdministrativaEnum.REMOCAO_VEICULO in medidas:
        return "pg_8_2"
    if MedidaAdministrativaEnum.RECOLHIMENTO_CNH in medidas:
        return "pg_8_3"
    if MedidaAdministrativaEnum.RECOLHIMENTO_CRLV in medidas:
        return "pg_8_4"
    if MedidaAdministrativaEnum.TRANSBORDO_CARGA in medidas:
        return "pg_8_5"
    if (
        MedidaAdministrativaEnum.RECOLHIMENTO_PLACAS in medidas
        or MedidaAdministrativaEnum.REMOCAO_MERCADORIA_MATERIAL in medidas
    ):
        return "pg_8_7"
    if "PARTE GERAL" in (ficha.medida_administrativa_original or "").upper():
        return "pg_8"
    return None


def run_build(
    fichas_json: Path | None = None,
    templates_dir: Path | None = None,
    output_dir: Path | None = None,
    imagens_src: Path | None = None,
    parte_geral_json: Path | None = None,
):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.setLevel(logging.INFO)
    if fichas_json is None:
        fichas_json = PROCESSED_DIR / "enriquecedor" / "fichas_enriquecidas.json"
    if parte_geral_json is None:
        candidato_pg = fichas_json.parent / "parte_geral_enriquecida.json"
        if candidato_pg.exists():
            parte_geral_json = candidato_pg
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
        autoescape=select_autoescape(["html", "xml"]),
    )
    template_ficha = env.get_template("ficha.html")

    # Carrega Parte Geral enriquecida quando disponível
    parte_geral: ParteGeralEnriquecida | None = None
    mapa_secoes_por_ficha: dict[str, list[SecaoParteGeral]] = {}
    if parte_geral_json is not None and parte_geral_json.exists():
        logger.info(f"Lendo Parte Geral enriquecida de: {parte_geral_json}")
        with open(parte_geral_json, "r", encoding="utf-8") as f_pg:
            parte_geral = ParteGeralEnriquecida.model_validate(json.load(f_pg))
        for secao in parte_geral.secoes:
            for cod in secao.enquadramentos_alvo:
                mapa_secoes_por_ficha.setdefault(cod, []).append(secao)

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
            raise ValueError(
                f"Colisão de ID detectada: o arquivo {ficha.id}.html seria sobrescrito."
            )
        seen_ids.add(ficha.id)

        secoes_pg_ficha = mapa_secoes_por_ficha.get(ficha.codigo_enquadramento, [])
        ancora_medida_pg = (
            _obter_ancora_medida_pg(ficha) if parte_geral is not None else None
        )

        # Gera HTML da Ficha
        html_ficha = template_ficha.render(
            ficha=ficha,
            secoes_parte_geral=secoes_pg_ficha,
            ancora_medida_pg=ancora_medida_pg,
        )
        out_ficha = fichas_out_dir / f"{ficha.id}.html"
        out_ficha.write_text(html_ficha, encoding="utf-8")

    # Gera HTML da Parte Geral quando disponível e os templates existirem
    if parte_geral is not None and (templates_dir / "parte_geral_index.html").exists():
        pg_out_dir = output_dir / "parte-geral"
        pg_out_dir.mkdir(parents=True, exist_ok=True)

        template_pg_index = env.get_template("parte_geral_index.html")
        html_pg_index = template_pg_index.render(parte_geral=parte_geral)
        out_pg_index = pg_out_dir / "index.html"
        out_pg_index.write_text(html_pg_index, encoding="utf-8")

        if (templates_dir / "parte_geral_secao.html").exists():
            template_pg_secao = env.get_template("parte_geral_secao.html")
            num_secoes = len(parte_geral.secoes)
            for i, secao in enumerate(parte_geral.secoes):
                secao_ant = parte_geral.secoes[i - 1] if i > 0 else None
                secao_prox = parte_geral.secoes[i + 1] if i + 1 < num_secoes else None
                html_secao = template_pg_secao.render(
                    secao=secao,
                    secao_anterior=secao_ant,
                    secao_proxima=secao_prox,
                )
                out_secao = pg_out_dir / f"{secao.slug}.html"
                out_secao.write_text(html_secao, encoding="utf-8")

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

    # Página 404 personalizada, consumida por `assets.not_found_handling = "404-page"`
    # do Worker único (PMS-010) para navegações que não casam com nenhum asset.
    template_404 = env.get_template("404.html")
    html_404 = template_404.render()
    out_404 = output_dir / "404.html"
    out_404.write_text(html_404, encoding="utf-8")

    # Painel administrativo (/admin e /admin/index.html)
    admin_out_dir = output_dir / "admin"
    admin_out_dir.mkdir(parents=True, exist_ok=True)
    template_admin = env.get_template("admin.html")
    html_admin = template_admin.render()
    (admin_out_dir / "index.html").write_text(html_admin, encoding="utf-8")
    (output_dir / "admin.html").write_text(html_admin, encoding="utf-8")

    logger.info(
        f"Build concluído com sucesso! {len(fichas)} fichas geradas em: {output_dir}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_build()
