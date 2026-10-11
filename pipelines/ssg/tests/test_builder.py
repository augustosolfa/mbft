import json
import logging
from pathlib import Path
from mbft_core.models.enriquecimento import (
    FichaEnriquecida,
    GravidadeEnum,
    PenalidadeEnum,
    MedidaAdministrativaEnum,
    InfratorEnum,
    ConstatacaoInfracaoEnum,
    CompetenciaEnum,
    CompetenciaFonteEnum,
    NaturezaRegraEnum,
    ItemRegra,
    ReferenciaCTB,
)
from mbft_core.models.extracao import CampoNormativo
from mbft_ssg.builder import run_build


def _criar_ficha_exemplo() -> FichaEnriquecida:
    return FichaEnriquecida(
        id="751-01",
        codigo_enquadramento="751-01",
        tipificacao_resumida="Iniciar obra sem permissão",
        amparo_legal="Art. 95",
        tipificacao_enquadramento="Nenhuma obra será iniciada sem permissão...",
        gravidade_original="NÃO APLICÁVEL",
        penalidade_original="MULTA",
        medida_administrativa_original="NÃO APLICÁVEL",
        infrator_original="PESSOA FÍSICA OU JURÍDICA",
        competencia_original="MUNICIPAL",
        constatacao_infracao_original="MEDIANTE ABORDAGEM",
        pontuacao_original="NÃO COMPUTÁVEL",
        quando_autuar_original=CampoNormativo(),
        quando_nao_autuar_original=CampoNormativo(),
        definicoes_procedimentos_original=CampoNormativo(),
        exemplos_observacoes_ait_original=CampoNormativo(),
        gravidade=GravidadeEnum.NAO_APLICAVEL,
        penalidades=[PenalidadeEnum.MULTA],
        medidas_administrativas=[MedidaAdministrativaEnum.NAO_APLICAVEL],
        infratores=[InfratorEnum.PESSOA_FISICA_OU_JURIDICA],
        competencias=[CompetenciaEnum.MUNICIPAL],
        competencia_fonte=CompetenciaFonteEnum.MBFT_ORIGINAL,
        competencia_alterada_lei_14599=False,
        crime_transito=False,
        constatacao_infracao=[ConstatacaoInfracaoEnum.COM_ABORDAGEM],
        artigos_ctb=[ReferenciaCTB(artigo="95")],
        quando_autuar_itens=[
            ItemRegra(texto="Regra válida 1", natureza_regra=NaturezaRegraEnum.HIPOTESE_AUTUACAO),
        ],
        quando_nao_autuar_itens=[],
        definicoes_procedimentos_itens=[],
        exemplos_observacoes_ait_itens=[],
        informacoes_complementares_html="<p>Texto</p>",
        paginas=[32, 33],
        imagens=[],
    )


def test_run_build_emite_logs_info_e_gera_artefatos(tmp_path: Path, caplog):
    ficha = _criar_ficha_exemplo()
    fichas_json = tmp_path / "fichas_enriquecidas.json"
    fichas_json.write_text(
        json.dumps([ficha.model_dump(mode="json")]),
        encoding="utf-8",
    )
    output_dir = tmp_path / "site"
    imagens_src = tmp_path / "imagens"

    # Mesmo sem chamar caplog.set_level(logging.INFO), run_build deve habilitar INFO no logger mbft_ssg.builder
    logging.getLogger("mbft_ssg.builder").setLevel(logging.NOTSET)
    run_build(
        fichas_json=fichas_json,
        output_dir=output_dir,
        imagens_src=imagens_src,
    )

    mensagens = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("Iniciando build do Site Estático (SSG)" in m for m in mensagens)
    assert any("Build concluído com sucesso! 1 fichas geradas" in m for m in mensagens)
    assert (output_dir / "fichas" / "751-01.html").exists()
    assert (output_dir / "lista.html").exists()
    assert (output_dir / "index.html").exists()
    assert (output_dir / "chat.html").exists()
    assert (output_dir / "config.js").exists()
    assert 'apiBaseUrl: ""' in (output_dir / "config.js").read_text(encoding="utf-8")
    assert "exemplo.com" not in (output_dir / "index.html").read_text(encoding="utf-8")
    assert "exemplo.com" not in (output_dir / "chat.html").read_text(encoding="utf-8")


def test_run_build_com_parte_geral_renderiza_pagina_e_ancoras_na_ficha(tmp_path: Path):
    from mbft_core.models.enriquecimento import (
        ItemGlossario,
        ParteGeralEnriquecida,
        SecaoParteGeral,
        TipoSecaoParteGeralEnum,
    )

    ficha = _criar_ficha_exemplo()
    ficha.medidas_administrativas = [MedidaAdministrativaEnum.RETENCAO_VEICULO]
    ficha.medida_administrativa_original = "Retenção do veículo (Vide a Parte Geral deste Manual)."
    ficha.enquadramentos_correlatos = ["751-02"]

    pg = ParteGeralEnriquecida(
        secoes_descartadas=2,
        glossario=[ItemGlossario(sigla="AIT", significado="Auto de Infração de Trânsito")],
        secoes=[
            SecaoParteGeral(
                id="PG_8_1",
                slug="pg_8_1",
                numero="8.1",
                titulo="8.1. Retenção do Veículo",
                tipo=TipoSecaoParteGeralEnum.TEMATICO,
                texto="Consiste na imobilização do veículo.",
                paragrafos=["Consiste na imobilização do veículo."],
                medidas_associadas=[MedidaAdministrativaEnum.RETENCAO_VEICULO],
                enquadramentos_alvo=["751-01"],
            ),
            SecaoParteGeral(
                id="PG_8_2",
                slug="pg_8_2",
                numero="8.2",
                titulo="8.2. Remoção do Veículo",
                tipo=TipoSecaoParteGeralEnum.TEMATICO,
                texto="Consiste no deslocamento do veículo.",
                paragrafos=["Consiste no deslocamento do veículo."],
                medidas_associadas=[MedidaAdministrativaEnum.REMOCAO_VEICULO],
                enquadramentos_alvo=[],
            ),
        ],
    )

    fichas_json = tmp_path / "fichas_enriquecidas.json"
    fichas_json.write_text(json.dumps([ficha.model_dump(mode="json")]), encoding="utf-8")
    pg_json = tmp_path / "parte_geral_enriquecida.json"
    pg_json.write_text(json.dumps(pg.model_dump(mode="json")), encoding="utf-8")

    output_dir = tmp_path / "site"
    run_build(
        fichas_json=fichas_json,
        parte_geral_json=pg_json,
        output_dir=output_dir,
        imagens_src=tmp_path / "imagens",
    )

    pg_dir = output_dir / "parte-geral"
    assert pg_dir.exists()
    assert not (output_dir / "parte-geral.html").exists()

    pg_index_path = pg_dir / "index.html"
    assert pg_index_path.exists()
    pg_index_html = pg_index_path.read_text(encoding="utf-8")
    assert 'href="pg_8_1.html"' in pg_index_html
    assert 'href="pg_8_2.html"' in pg_index_html
    assert "Auto de Infração de Trânsito" in pg_index_html

    pg_secao_path = pg_dir / "pg_8_1.html"
    assert pg_secao_path.exists()
    pg_secao_html = pg_secao_path.read_text(encoding="utf-8")
    assert "8.1. Retenção do Veículo" in pg_secao_html
    assert "Consiste na imobilização do veículo." in pg_secao_html
    assert 'href="../fichas/751-01.html"' in pg_secao_html
    assert 'href="index.html"' in pg_secao_html
    assert 'href="pg_8_2.html"' in pg_secao_html  # Próxima seção
    assert "Início" in pg_secao_html
    assert "Parte Geral" in pg_secao_html

    pg_secao2_path = pg_dir / "pg_8_2.html"
    assert pg_secao2_path.exists()
    pg_secao2_html = pg_secao2_path.read_text(encoding="utf-8")
    assert 'href="pg_8_1.html"' in pg_secao2_html  # Seção anterior

    ficha_html = (output_dir / "fichas" / "751-01.html").read_text(encoding="utf-8")
    assert '../parte-geral/pg_8_1.html' in ficha_html
    assert '../parte-geral/index.html' in ficha_html
    assert 'href="751-02.html"' in ficha_html

