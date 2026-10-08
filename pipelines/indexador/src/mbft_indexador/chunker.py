from typing import List
from mbft_core.models import FichaEnriquecida
from mbft_core.models.indexacao import ChunkMetadados

def extrair_texto_secao(ficha: FichaEnriquecida, secao: str) -> str:
    """Extrai o texto atômico combinado da seção, se existir."""
    itens = getattr(ficha, f"{secao.lower()}_itens", [])
    if not itens:
        return ""
    
    linhas = []
    for item in itens:
        linhas.append(f"- {item.texto.strip()}")
    
    return "\n".join(linhas)

def processar_ficha(ficha: FichaEnriquecida) -> List[dict]:
    """
    Fraciona uma ficha enriquecida em chunks atômicos (1 por seção, por enquanto).
    O prefixo contextual é inserido para orientar o attention do embedding denso.
    """
    artigo_principal = ficha.artigos_ctb[0].artigo if ficha.artigos_ctb else "N/D"
    chunks = []
    
    secoes_tematicas = [
        "quando_autuar",
        "quando_nao_autuar",
        "definicoes_procedimentos",
        "exemplos_observacoes_ait"
    ]
    
    for secao in secoes_tematicas:
        texto_secao = extrair_texto_secao(ficha, secao)
        if not texto_secao:
            continue
            
        nome_secao_amigavel = secao.replace("_", " ").title()
        
        # Prefixo enxuto sem diluição semântica excessiva
        prefixo = f"[Infração {ficha.codigo_enquadramento} - {ficha.tipificacao_resumida} | Art. {artigo_principal} | {nome_secao_amigavel}]"
        texto_final = f"{prefixo}\n{texto_secao}"
        
        infratores_lista = [inf.value for inf in ficha.infratores]
        competencias_lista = [comp.value for comp in ficha.competencias]
        
        metadados = ChunkMetadados(
            origem_id=ficha.codigo_enquadramento,
            secao=secao.upper(),
            codigo=ficha.codigo_enquadramento,
            artigo=artigo_principal,
            gravidade=ficha.gravidade.value,
            infratores=infratores_lista,
            competencias=competencias_lista,
            texto_contextualizado=texto_final
        )
        
        chunk_id = f"{ficha.codigo_enquadramento}_{secao.upper()}"
        
        chunks.append({
            "id": chunk_id,
            "texto_para_embedding": texto_final,
            "metadata": metadados
        })
        
    return chunks
