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
