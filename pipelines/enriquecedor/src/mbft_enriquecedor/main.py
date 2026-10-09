import json
import logging
from typing import List

from mbft_core.paths import PROCESSED_DIR
from mbft_core.models.extracao import Ficha
from mbft_core.models.enriquecimento import FichaEnriquecida, CompetenciaFonteEnum
from mbft_enriquecedor.normalizador import (
    normalizar_gravidade, normalizar_penalidades, normalizar_medidas_administrativas,
    higienizar_infrator_crime, normalizar_constatacao, calcular_pontuacao, parse_amparo_legal,
    parse_resolucoes_contran, sanitizar_texto
)
from mbft_enriquecedor.tabelas_competencia import obter_competencia_atualizada
from mbft_enriquecedor.extrator_regras import ExtratorRegrasAtomo

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
        pts_valor, pts_suspensiva = calcular_pontuacao(f_bruta.pontuacao, penalidades_norm)
        
        competencia_norm, via_lei_14599 = obter_competencia_atualizada(f_bruta.codigo_enquadramento, f_bruta.competencia)
        competencia_fonte = CompetenciaFonteEnum.RESOLUCAO_LEI_14599 if via_lei_14599 else CompetenciaFonteEnum.MBFT_ORIGINAL
        
        # Extração de itens atômicos
        quando_autuar_itens = self.extrator_regras.extrair_itens(f_bruta.quando_autuar, "QUANDO_AUTUAR", f_bruta.codigo_enquadramento)
        quando_nao_autuar_itens = self.extrator_regras.extrair_itens(f_bruta.quando_nao_autuar, "QUANDO_NAO_AUTUAR", f_bruta.codigo_enquadramento)
        definicoes_procedimentos_itens = self.extrator_regras.extrair_itens(f_bruta.definicoes_procedimentos, "DEFINICOES_PROCEDIMENTOS", f_bruta.codigo_enquadramento)
        exemplos_observacoes_ait_itens = self.extrator_regras.extrair_itens(f_bruta.exemplos_observacoes_ait, "EXEMPLOS_AIT", f_bruta.codigo_enquadramento)

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

        return FichaEnriquecida(
            id=f_bruta.id,
            tipificacao_resumida=sanitizar_texto(f_bruta.tipificacao_resumida),
            codigo_enquadramento=sanitizar_texto(f_bruta.codigo_enquadramento),
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
            constatacao_infracao=constatacao_norm,
            
            artigos_ctb=artigos_ctb,
            resolucoes_contran=resolucoes_contran,
            enquadramentos_correlatos=[],
            termos_chave=[],
            
            quando_autuar_itens=quando_autuar_itens,
            quando_nao_autuar_itens=quando_nao_autuar_itens,
            definicoes_procedimentos_itens=definicoes_procedimentos_itens,
            exemplos_observacoes_ait_itens=exemplos_observacoes_ait_itens,
            
            informacoes_complementares_html=f_bruta.informacoes_complementares,
            paginas=f_bruta.paginas,
            imagens=f_bruta.imagens
        )


def carregar_fichas_brutas() -> List[Ficha]:
    input_path = PROCESSED_DIR / "extrator" / "fichas_mbft.json"
    logger.info(f"Carregando {input_path}...")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Erro ao ler JSON: {e}")
        return []
        
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

def gerar_relatorio(fichas: List[FichaEnriquecida]):
    out_dir = PROCESSED_DIR / "enriquecedor"
    out_relatorio = out_dir / "relatorio_enriquecimento.md"
    logger.info("Gerando relatório...")
    
    with open(out_relatorio, "w", encoding="utf-8") as f:
        f.write("# Relatório de Enriquecimento MBFT\n\n")
        f.write(f"- **Fichas Processadas**: {len(fichas)}\n")
        
        fichas_com_crime = sum(1 for f in fichas if f.crime_transito)
        f.write(f"- **Fichas com configuração de Crime de Trânsito**: {fichas_com_crime}\n")

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
    gerar_relatorio(fichas_enriquecidas)
    
    logger.info("Concluído!")

if __name__ == "__main__":
    main()
