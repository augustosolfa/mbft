import json
import logging
from typing import List, Optional

from mbft_core.paths import PROCESSED_DIR
from mbft_core.models.extracao import Ficha, SecaoFichaEnum
from mbft_core.models.enriquecimento import (
    FichaEnriquecida,
    CompetenciaFonteEnum,
    ParteGeralEnriquecida,
)
from mbft_enriquecedor.normalizador import (
    normalizar_gravidade, normalizar_penalidades, normalizar_medidas_administrativas,
    higienizar_infrator_crime, normalizar_constatacao, calcular_pontuacao, parse_amparo_legal,
    parse_resolucoes_contran, sanitizar_texto
)
from mbft_enriquecedor.tabelas_competencia import obter_competencia_atualizada
from mbft_enriquecedor.extrator_regras import ExtratorRegrasAtomo, expandir_codigos
from mbft_enriquecedor.parte_geral import processar_parte_geral

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class Enriquecedor:
    def __init__(self):
        self.extrator_regras = ExtratorRegrasAtomo()

    def processar_ficha(self, f_bruta: Ficha) -> FichaEnriquecida:
        # Normalização de atributos básicos
        gravidade_norm = normalizar_gravidade(f_bruta.gravidade)
        penalidades_norm = normalizar_penalidades(f_bruta.penalidade)
        medidas_norm = normalizar_medidas_administrativas(f_bruta.medida_administrativa)
        
        infratores_norm, tem_crime, artigos_ctb_crime = higienizar_infrator_crime(
            f_bruta.infrator, f_bruta.pode_configurar_crime_transito
        )
        
        constatacao_norm = normalizar_constatacao(f_bruta.constatacao_infracao)
        pts_valor, pts_suspensiva, pts_asterisco = calcular_pontuacao(f_bruta.pontuacao, penalidades_norm)
        
        competencia_norm, competencia_fonte = obter_competencia_atualizada(f_bruta.codigo_enquadramento, f_bruta.competencia)
        revisao_manual = (competencia_fonte == CompetenciaFonteEnum.NAO_RESOLVIDA)
        
        # Extração de itens atômicos
        quando_autuar_itens = self.extrator_regras.extrair_itens(f_bruta.quando_autuar, SecaoFichaEnum.QUANDO_AUTUAR, f_bruta.codigo_enquadramento)
        quando_nao_autuar_itens = self.extrator_regras.extrair_itens(f_bruta.quando_nao_autuar, SecaoFichaEnum.QUANDO_NAO_AUTUAR, f_bruta.codigo_enquadramento)
        definicoes_procedimentos_itens = self.extrator_regras.extrair_itens(f_bruta.definicoes_procedimentos, SecaoFichaEnum.DEFINICOES_PROCEDIMENTOS, f_bruta.codigo_enquadramento)
        exemplos_observacoes_ait_itens = self.extrator_regras.extrair_itens(f_bruta.exemplos_observacoes_ait, SecaoFichaEnum.EXEMPLOS_AIT, f_bruta.codigo_enquadramento)

        # Computação de amparo legal e artigos associados
        artigos_ctb = parse_amparo_legal(f_bruta.amparo_legal) + artigos_ctb_crime
        for regra in definicoes_procedimentos_itens:
            artigos_extras = parse_amparo_legal(regra.texto)
            for art in artigos_extras:
                if art not in artigos_ctb:
                    artigos_ctb.append(art)

        # Extração de resoluções
        resolucoes = []
        textos_busca = [f_bruta.informacoes_complementares, f_bruta.amparo_legal]
        if f_bruta.definicoes_procedimentos:
            textos_busca.extend(f_bruta.definicoes_procedimentos.itens)
        for txt in textos_busca:
            if txt:
                resolucoes.extend(parse_resolucoes_contran(txt))
        resolucoes_contran = sorted(list(set(resolucoes)))

        # Extração consolidada de enquadramentos correlatos (redirecionamentos, concomitantes e menções cruzadas)
        codigo_limpo = sanitizar_texto(f_bruta.codigo_enquadramento)
        correlatos_set = set()
        for regra in (
            quando_autuar_itens
            + quando_nao_autuar_itens
            + definicoes_procedimentos_itens
            + exemplos_observacoes_ait_itens
        ):
            correlatos_set.update(regra.codigos_redirecionamento)
            correlatos_set.update(regra.codigos_concomitantes)
            correlatos_set.update(expandir_codigos(regra.texto))
        if f_bruta.informacoes_complementares:
            correlatos_set.update(expandir_codigos(f_bruta.informacoes_complementares))
        correlatos_set.discard(codigo_limpo)
        enquadramentos_correlatos = sorted(correlatos_set)

        return FichaEnriquecida(
            id=f_bruta.id,
            tipificacao_resumida=sanitizar_texto(f_bruta.tipificacao_resumida),
            codigo_enquadramento=codigo_limpo,
            amparo_legal=sanitizar_texto(f_bruta.amparo_legal),
            tipificacao_enquadramento=sanitizar_texto(f_bruta.tipificacao_enquadramento),
            
            gravidade_original=f_bruta.gravidade,
            penalidade_original=f_bruta.penalidade,
            medida_administrativa_original=f_bruta.medida_administrativa,
            infrator_original=f_bruta.infrator,
            competencia_original=f_bruta.competencia or "",
            constatacao_infracao_original=f_bruta.constatacao_infracao,
            pontuacao_original=f_bruta.pontuacao,
            pode_configurar_crime_transito_original=f_bruta.pode_configurar_crime_transito,
            
            quando_autuar_original=f_bruta.quando_autuar,
            quando_nao_autuar_original=f_bruta.quando_nao_autuar,
            definicoes_procedimentos_original=f_bruta.definicoes_procedimentos,
            exemplos_observacoes_ait_original=f_bruta.exemplos_observacoes_ait,
            
            gravidade=gravidade_norm,
            penalidades=penalidades_norm,
            medidas_administrativas=medidas_norm,
            infratores=infratores_norm,
            competencias=competencia_norm,
            competencia_fonte=competencia_fonte,
            competencia_alterada_lei_14599=f_bruta.competencia_alterada_lei_14599,
            crime_transito=tem_crime,
            pontuacao_valor=pts_valor,
            pontuacao_suspensiva=pts_suspensiva,
            pontuacao_asterisco=pts_asterisco,
            constatacao_infracao=constatacao_norm,
            
            artigos_ctb=artigos_ctb,
            resolucoes_contran=resolucoes_contran,
            enquadramentos_correlatos=enquadramentos_correlatos,
            termos_chave=[],
            
            quando_autuar_itens=quando_autuar_itens,
            quando_nao_autuar_itens=quando_nao_autuar_itens,
            definicoes_procedimentos_itens=definicoes_procedimentos_itens,
            exemplos_observacoes_ait_itens=exemplos_observacoes_ait_itens,
            
            informacoes_complementares_html=f_bruta.informacoes_complementares,
            paginas=f_bruta.paginas,
            imagens=f_bruta.imagens,
            revisao_manual_necessaria=revisao_manual
        )


def carregar_fichas_brutas() -> List[Ficha]:
    input_path = PROCESSED_DIR / "extrator" / "fichas_mbft.json"
    logger.info(f"Carregando {input_path}...")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        logger.exception("Erro fatal ao ler JSON de fichas brutas.")
        raise
        
    fichas = [Ficha(**item) for item in data]
    logger.info(f"{len(fichas)} fichas carregadas do Extrator.")
    return fichas

def salvar_fichas_enriquecidas(fichas: List[FichaEnriquecida]):
    out_dir = PROCESSED_DIR / "enriquecedor"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_fichas_json = out_dir / "fichas_enriquecidas.json"
    
    with open(out_fichas_json, "w", encoding="utf-8") as f:
        json.dump([f.model_dump(mode='json') for f in fichas], f, ensure_ascii=False, indent=2)
    logger.info(f"Fichas enriquecidas salvas em {out_fichas_json}")

def salvar_parte_geral_enriquecida(parte_geral: ParteGeralEnriquecida):
    out_dir = PROCESSED_DIR / "enriquecedor"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_pg_json = out_dir / "parte_geral_enriquecida.json"

    with open(out_pg_json, "w", encoding="utf-8") as f:
        json.dump(parte_geral.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    logger.info(f"Parte Geral enriquecida salva em {out_pg_json}")

def gerar_relatorio(
    fichas: List[FichaEnriquecida],
    parte_geral: Optional[ParteGeralEnriquecida] = None,
):
    out_dir = PROCESSED_DIR / "enriquecedor"
    out_relatorio = out_dir / "relatorio_enriquecimento.md"
    logger.info("Gerando relatório...")
    
    with open(out_relatorio, "w", encoding="utf-8") as f:
        f.write("# Relatório de Enriquecimento MBFT\n\n")
        f.write(f"- **Fichas Processadas**: {len(fichas)}\n")
        
        fichas_com_crime = sum(1 for f in fichas if f.crime_transito)
        f.write(f"- **Fichas com configuração de Crime de Trânsito**: {fichas_com_crime}\n")

        fichas_com_correlatos = sum(1 for f in fichas if f.enquadramentos_correlatos)
        f.write(f"- **Fichas com Enquadramentos Correlatos**: {fichas_com_correlatos}\n")

        if parte_geral is not None:
            f.write(f"- **Seções da Parte Geral Estruturadas**: {len(parte_geral.secoes)}\n")
            f.write(f"- **Siglas do Glossário Extraídas**: {len(parte_geral.glossario)}\n")
            f.write(f"- **Seções Pré-Textuais/Editoriais Descartadas**: {parte_geral.secoes_descartadas}\n")

def main():
    fichas_brutas = carregar_fichas_brutas()
    if not fichas_brutas:
        return
        
    enriquecedor = Enriquecedor()
    fichas_enriquecidas = []
    
    logger.info("Iniciando normalização e extração atômica das regras...")
    for f in fichas_brutas:
        fichas_enriquecidas.append(enriquecedor.processar_ficha(f))
        
    salvar_fichas_enriquecidas(fichas_enriquecidas)

    parte_geral_md_path = PROCESSED_DIR / "extrator" / "mbft_parte_geral.md"
    parte_geral_enriquecida: Optional[ParteGeralEnriquecida] = None
    if parte_geral_md_path.exists():
        logger.info(f"Processando Parte Geral a partir de {parte_geral_md_path}...")
        md_texto = parte_geral_md_path.read_text(encoding="utf-8")
        parte_geral_enriquecida = processar_parte_geral(md_texto, fichas_enriquecidas)
        salvar_parte_geral_enriquecida(parte_geral_enriquecida)

    gerar_relatorio(fichas_enriquecidas, parte_geral_enriquecida)
    
    logger.info("Concluído!")

if __name__ == "__main__":
    main()

