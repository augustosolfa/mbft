from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from mbft_core.models.enriquecimento import FichaEnriquecida, ParteGeralEnriquecida
from mbft_core.models.indexacao import ChunkMetadados

class Secao(str, Enum):
    QUANDO_AUTUAR = "quando_autuar_itens"
    QUANDO_NAO_AUTUAR = "quando_nao_autuar_itens"
    DEFINICOES_PROCEDIMENTOS = "definicoes_procedimentos_itens"
    EXEMPLOS_AIT = "exemplos_observacoes_ait_itens"

class UnembeddedChunk(BaseModel):
    id: str
    tokens_estimados: int
    metadata: ChunkMetadados

    @property
    def texto_para_embedding(self) -> str:
        return self.metadata.texto_contextualizado

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
    
    def _criar_chunk(
        secao_nome: str,
        item_numero: int,
        texto_conteudo: str,
        natureza: Optional[str] = None
    ) -> UnembeddedChunk:
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
            tokens_estimados=_estimar_tokens(texto_final),
            metadata=metadados
        )

    secoes_mapeamento = [
        ("QUANDO_AUTUAR", ficha.quando_autuar_itens),
        ("QUANDO_NAO_AUTUAR", ficha.quando_nao_autuar_itens),
        ("DEFINICOES_PROCEDIMENTOS", ficha.definicoes_procedimentos_itens),
        ("EXEMPLOS_AIT", ficha.exemplos_observacoes_ait_itens),
    ]

    for secao_nome, itens in secoes_mapeamento:
        for i, item in enumerate(itens):
            texto = item.texto.strip()
            if not texto:
                continue
            natureza = item.natureza_regra.value if hasattr(item.natureza_regra, "value") else str(item.natureza_regra)
            chunks.append(_criar_chunk(secao_nome, i + 1, texto, natureza))
            
    # Chunk isolado da ementa / amparo legal (substitui o antigo)
    # Como o prefixo já tem essas informações, o texto base para a ementa é apenas ele mesmo
    chunks.append(_criar_chunk("EMENTA", 0, "Visão geral da infração e penalidades associadas."))

    return chunks


def _agrupar_paragrafos_em_blocos(paragrafos: List[str], max_chars: int = 1200) -> List[str]:
    """Agrupa parágrafos consecutivos de uma seção da Parte Geral em blocos coesos."""
    blocos: List[str] = []
    buffer_atual: List[str] = []
    tamanho_atual = 0

    for p in paragrafos:
        texto_p = p.strip()
        if not texto_p:
            continue
        if buffer_atual and (tamanho_atual + len(texto_p) + 2 > max_chars):
            blocos.append("\n".join(buffer_atual))
            buffer_atual = [texto_p]
            tamanho_atual = len(texto_p)
        else:
            buffer_atual.append(texto_p)
            tamanho_atual += len(texto_p) + 2

    if buffer_atual:
        blocos.append("\n".join(buffer_atual))

    return blocos


def gerar_chunks_parte_geral(parte_geral: ParteGeralEnriquecida) -> List[UnembeddedChunk]:
    """
    Converte as seções estruturadas da Parte Geral em `UnembeddedChunk`
    com prefixo semântico contextualizado e `secao="PARTE_GERAL"`.
    """
    chunks: List[UnembeddedChunk] = []
    competencias_padrao = ["MUNICIPAL", "ESTADUAL", "RODOVIARIO"]

    for secao in parte_geral.secoes:
        artigo_principal = secao.artigos_ctb[0].artigo if secao.artigos_ctb else "N/D"
        artigos_lista = [a.artigo for a in secao.artigos_ctb]
        infratores_lista = [inf.value for inf in secao.infratores_associados]
        medidas_lista = [m.value for m in secao.medidas_associadas]
        tipo_valor = secao.tipo.value if hasattr(secao.tipo, "value") else str(secao.tipo)

        prefixo_contexto = (
            f"[Parte Geral do MBFT - {secao.titulo} | Código: {secao.id} | "
            f"Tipo: {tipo_valor} | Artigos CTB: {artigos_lista} | "
            f"Medidas Administrativas: {medidas_lista} | Infrator: {infratores_lista}]"
        )

        blocos = _agrupar_paragrafos_em_blocos(secao.paragrafos, max_chars=1200)
        for idx, bloco in enumerate(blocos, start=1):
            texto_final = f"{prefixo_contexto}\n[Seção: PARTE_GERAL]\n{bloco}"
            chunk_id = secao.id if len(blocos) == 1 else f"{secao.id}_PARTE_{idx}"

            metadados = ChunkMetadados(
                origem_id=secao.id,
                secao="PARTE_GERAL",
                codigo=secao.id,
                artigo=artigo_principal,
                gravidade="NAO_APLICAVEL",
                infratores=infratores_lista,
                competencias=competencias_padrao,
                texto_contextualizado=texto_final,
                natureza_regra=f"PARTE_GERAL_{tipo_valor}",
            )

            chunks.append(
                UnembeddedChunk(
                    id=chunk_id,
                    tokens_estimados=_estimar_tokens(texto_final),
                    metadata=metadados,
                )
            )

    return chunks

