from enum import Enum
from typing import List, Dict, Any
from pydantic import BaseModel
from mbft_core.models.enriquecimento import FichaEnriquecida
from mbft_core.models.indexacao import ChunkMetadados

class Secao(str, Enum):
    QUANDO_AUTUAR = "quando_autuar_itens"
    QUANDO_NAO_AUTUAR = "quando_nao_autuar_itens"
    DEFINICOES_PROCEDIMENTOS = "definicoes_procedimentos_itens"
    EXEMPLOS_AIT = "exemplos_observacoes_ait_itens"

class UnembeddedChunk(BaseModel):
    id: str
    texto_para_embedding: str
    tokens_estimados: int
    metadata: ChunkMetadados

def _estimar_tokens(texto: str) -> int:
    """Estimativa rápida (heurística) de tokens."""
    return int(len(texto.split()) * 1.5)

def gerar_chunks_ficha(ficha: FichaEnriquecida) -> List[UnembeddedChunk]:
    chunks = []
    
    artigo_principal = ficha.artigos_ctb[0].artigo if ficha.artigos_ctb else "N/D"
    infratores_lista = [inf.value for inf in ficha.infratores]
    competencias_lista = [comp.value for comp in ficha.competencias]
    
    # Contexto unificado
    prefixo_contexto = (
        f"[Infração {ficha.codigo_enquadramento} - {ficha.tipificacao_resumida} | "
        f"Art. {artigo_principal} | Amparo: {ficha.amparo_legal} | Infrator: {infratores_lista} | "
        f"Gravidade: {ficha.gravidade.value} | Penalidade: {ficha.penalidade_original.strip()} | "
        f"Competência: {competencias_lista}]"
    )
    
    def _criar_chunk(secao_nome: str, item_numero: int, texto_conteudo: str, natureza: str = None) -> UnembeddedChunk:
        texto_final = f"{prefixo_contexto}\n[Seção: {secao_nome}]\n{texto_conteudo}"
        
        chunk_id = f"{ficha.id}_{secao_nome}"
        if item_numero > 0:
            chunk_id += f"_ITEM_{item_numero}"
            
        metadados = ChunkMetadados(
            origem_id=ficha.id,
            secao=secao_nome,
            codigo=ficha.codigo_enquadramento,
            artigo=artigo_principal,
            gravidade=ficha.gravidade.value,
            infratores=infratores_lista,
            competencias=competencias_lista,
            texto_contextualizado=texto_final,
            natureza_regra=natureza
        )
        
        return UnembeddedChunk(
            id=chunk_id,
            texto_para_embedding=texto_final,
            tokens_estimados=_estimar_tokens(texto_final),
            metadata=metadados
        )

    for secao in Secao:
        itens = getattr(ficha, secao.value, [])
        for i, item in enumerate(itens):
            chunks.append(_criar_chunk(secao.name, i + 1, item.texto.strip(), item.natureza_regra.value))
            
    # Chunk isolado da ementa / amparo legal (substitui o antigo)
    # Como o prefixo já tem essas informações, o texto base para a ementa é apenas ele mesmo
    chunks.append(_criar_chunk("EMENTA", 0, "Visão geral da infração e penalidades associadas."))

    return chunks
