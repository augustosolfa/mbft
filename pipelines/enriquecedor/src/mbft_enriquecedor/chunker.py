import re
from typing import List, Dict, Any
from mbft_core.models.enriquecimento import ChunkPayload, ChunkMetadados, FichaEnriquecida, ItemRegra

def _estimar_tokens(texto: str) -> int:
    """
    Estimativa rápida (heurística) de tokens.
    O ideal em produção seria usar o tokenizador exato do BAAI/bge-m3.
    Em média, 1 palavra = 1.3 a 1.5 tokens no BGE-M3 (multilíngue).
    """
    return int(len(texto.split()) * 1.5)

def gerar_chunks_ficha(ficha: FichaEnriquecida) -> List[ChunkPayload]:
    chunks = []
    
    # Função auxiliar para processar uma seção
    def _processar_secao(secao_nome: str, itens: List[ItemRegra]):
        for i, item in enumerate(itens):
            # Template Denso
            texto_contextualizado = f"[Ficha: {ficha.id} - {ficha.tipificacao_resumida}] [Seção: {secao_nome}] {item.texto}"
            
            chunk_id = f"{ficha.id}_{secao_nome}_ITEM_{i+1}"
            
            metadados = ChunkMetadados(
                chunk_id=chunk_id,
                tipo_documento="FICHA",
                origem_id=ficha.id,
                secao=secao_nome,
                hierarquia_titulos=[ficha.tipificacao_resumida, secao_nome],
                paginas=ficha.paginas,
                artigos_ctb_associados=[ref.artigo for ref in ficha.artigos_ctb],
                competencia=ficha.competencia.value,
                natureza_regra=item.natureza_regra,
                codigos_concomitantes=item.codigos_concomitantes,
                codigo_redirecionamento=item.codigo_redirecionamento
            )
            
            payload = ChunkPayload(
                metadados=metadados,
                texto_contextualizado=texto_contextualizado,
                tokens_estimados=_estimar_tokens(texto_contextualizado)
            )
            chunks.append(payload)

    # Processar as seções principais atômicas
    if ficha.quando_autuar_itens:
        _processar_secao("QUANDO_AUTUAR", ficha.quando_autuar_itens)
        
    if ficha.quando_nao_autuar_itens:
        _processar_secao("QUANDO_NAO_AUTUAR", ficha.quando_nao_autuar_itens)
        
    if ficha.definicoes_procedimentos_itens:
        _processar_secao("DEFINICOES_PROCEDIMENTOS", ficha.definicoes_procedimentos_itens)
        
    if ficha.exemplos_observacoes_ait_itens:
        _processar_secao("EXEMPLOS_AIT", ficha.exemplos_observacoes_ait_itens)
        
    # Chunk isolado da ementa / amparo legal
    ementa_texto = f"Amparo Legal: {ficha.amparo_legal} | Infrator: {[i.value for i in ficha.infratores]} | Gravidade: {ficha.gravidade.value}"
    texto_ementa_contextualizado = f"[Ficha: {ficha.id} - {ficha.tipificacao_resumida}] [Seção: EMENTA] {ementa_texto}"
    
    meta_ementa = ChunkMetadados(
        chunk_id=f"{ficha.id}_EMENTA",
        tipo_documento="FICHA",
        origem_id=ficha.id,
        secao="EMENTA",
        hierarquia_titulos=[ficha.tipificacao_resumida, "EMENTA"],
        paginas=ficha.paginas,
        artigos_ctb_associados=[ref.artigo for ref in ficha.artigos_ctb],
        competencia=ficha.competencia.value
    )
    chunks.append(ChunkPayload(
        metadados=meta_ementa,
        texto_contextualizado=texto_ementa_contextualizado,
        tokens_estimados=_estimar_tokens(texto_ementa_contextualizado)
    ))

    return chunks

def gerar_chunks_parte_geral(md_path: str) -> List[ChunkPayload]:
    """
    Função stub para chunking da Parte Geral.
    Implementar o parser de Markdown Headers depois.
    """
    return []
