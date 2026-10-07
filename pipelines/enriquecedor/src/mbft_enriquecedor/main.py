import json
import os
from typing import List

from mbft_core.models.extracao import Ficha
from mbft_core.models.enriquecimento import FichaEnriquecida, CompetenciaFonteEnum
from mbft_enriquecedor.normalizador import (
    normalizar_gravidade, normalizar_penalidades, normalizar_medidas_administrativas,
    higienizar_infrator_crime, normalizar_constatacao, calcular_pontuacao
)
from mbft_enriquecedor.tabelas_competencia import obter_competencia_atualizada
from mbft_enriquecedor.extrator_regras import ExtratorRegrasAtomo
from mbft_enriquecedor.chunker import gerar_chunks_ficha
from mbft_enriquecedor.vetorizador import vetorizar_e_exportar


def processar_ficha(f_bruta: Ficha, extrator_regras: ExtratorRegrasAtomo) -> FichaEnriquecida:
    """
    Função principal que orquestra a transformação de uma Ficha bruta do Extrator
    para uma FichaEnriquecida, passando pelo normalizador e extração atômica.
    """
    
    # Normalização de atributos
    gravidade_norm = normalizar_gravidade(f_bruta.gravidade)
    penalidades_norm = normalizar_penalidades(f_bruta.penalidade)
    medidas_norm = normalizar_medidas_administrativas(f_bruta.medida_administrativa)
    
    infratores_norm, tem_crime, artigos_ctb = higienizar_infrator_crime(
        f_bruta.infrator, f_bruta.pode_configurar_crime_transito
    )
    
    constatacao_norm = normalizar_constatacao(f_bruta.constatacao_infracao)
    pts_valor, pts_suspensiva = calcular_pontuacao(f_bruta.pontuacao)
    
    competencia_norm, via_lei_14599 = obter_competencia_atualizada(f_bruta.codigo_enquadramento, f_bruta.competencia)
    competencia_fonte = CompetenciaFonteEnum.RESOLUCAO_LEI_14599 if via_lei_14599 else CompetenciaFonteEnum.MBFT_ORIGINAL
    
    # Instanciando a ficha
    f_enriquecida = FichaEnriquecida(
        id=f_bruta.id,
        tipificacao_resumida=f_bruta.tipificacao_resumida,
        codigo_enquadramento=f_bruta.codigo_enquadramento,
        amparo_legal=f_bruta.amparo_legal,
        tipificacao_enquadramento=f_bruta.tipificacao_enquadramento,
        
        gravidade_original=f_bruta.gravidade,
        penalidade_original=f_bruta.penalidade,
        medida_administrativa_original=f_bruta.medida_administrativa,
        infrator_original=f_bruta.infrator,
        competencia_original=f_bruta.competencia or "",
        constatacao_infracao_original=f_bruta.constatacao_infracao,
        pontuacao_original=f_bruta.pontuacao,
        
        gravidade=gravidade_norm,
        penalidades=penalidades_norm,
        medidas_administrativas=medidas_norm,
        infratores=infratores_norm,
        competencia=competencia_norm,
        competencia_fonte=competencia_fonte,
        competencia_alterada_lei_14599=f_bruta.competencia_alterada_lei_14599,
        crime_transito=tem_crime,
        pontuacao_valor=pts_valor,
        pontuacao_suspensiva=pts_suspensiva,
        constatacao_infracao=constatacao_norm,
        
        artigos_ctb=artigos_ctb,
        resolucoes_contran=[],
        enquadramentos_correlatos=[],
        termos_chave=[],
        
        quando_autuar_itens=extrator_regras.extrair_itens(f_bruta.quando_autuar, "QUANDO_AUTUAR"),
        quando_nao_autuar_itens=extrator_regras.extrair_itens(f_bruta.quando_nao_autuar, "QUANDO_NAO_AUTUAR"),
        definicoes_procedimentos_itens=extrator_regras.extrair_itens(f_bruta.definicoes_procedimentos, "DEFINICOES_PROCEDIMENTOS"),
        exemplos_observacoes_ait_itens=extrator_regras.extrair_itens(f_bruta.exemplos_observacoes_ait, "EXEMPLOS_AIT"),
        
        informacoes_complementares_html=f_bruta.informacoes_complementares,
        paginas=f_bruta.paginas,
        imagens=f_bruta.imagens
    )
    
    return f_enriquecida


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    input_path = os.path.join(base_dir, "data", "processed", "extrator", "fichas_mbft.json")
    out_dir = os.path.join(base_dir, "data", "processed", "enriquecedor")
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"[Enriquecedor] Carregando {input_path}...")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Erro ao ler JSON: {e}")
        return
        
    fichas_brutas = [Ficha(**item) for item in data]
    print(f"[Enriquecedor] {len(fichas_brutas)} fichas carregadas do Extrator.")
    
    extrator_regras = ExtratorRegrasAtomo()
    fichas_enriquecidas = []
    
    # 1. Enriquecimento
    print("[Enriquecedor] Iniciando normalização e extração atômica das regras...")
    # Processar apenas as 10 primeiras para teste rápido, remover o slice para processar tudo
    for f in fichas_brutas:
        f_enriquecida = processar_ficha(f, extrator_regras)
        fichas_enriquecidas.append(f_enriquecida)
        
    # Salvar Fichas Enriquecidas
    out_fichas_json = os.path.join(out_dir, "fichas_enriquecidas.json")
    with open(out_fichas_json, "w", encoding="utf-8") as f:
        json.dump([f.model_dump(mode='json') for f in fichas_enriquecidas], f, ensure_ascii=False, indent=2)
    print(f"[Enriquecedor] Fichas enriquecidas salvas em {out_fichas_json}")
    
    # 2. Chunking
    print("[Enriquecedor] Gerando chunks atômicos e templates contextuais...")
    chunks_totais = []
    for f_enq in fichas_enriquecidas:
        chunks = gerar_chunks_ficha(f_enq)
        chunks_totais.extend(chunks)
        
    print(f"[Enriquecedor] {len(chunks_totais)} chunks gerados.")
    
    # 3. Vetorização
    print("[Enriquecedor] Iniciando vetorização (BAAI/bge-m3)...")
    out_parquet = os.path.join(out_dir, "embeddings_mbft.parquet")
    vetorizar_e_exportar(chunks_totais, out_parquet)
    
    print("[Enriquecedor] Concluído!")

if __name__ == "__main__":
    main()
