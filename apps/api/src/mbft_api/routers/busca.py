from typing import Optional

from fastapi import APIRouter, Depends, Query
from ..dependencies import get_buscador
from ..rate_limit import LimitadorTaxa, get_limitador
from ..recuperador.buscador import BuscadorHibrido

router = APIRouter(prefix="/busca", tags=["Busca"])

@router.get("/")
async def buscar(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(5, ge=1, le=50),
    buscador: BuscadorHibrido = Depends(get_buscador),
    limitador: Optional[LimitadorTaxa] = Depends(get_limitador),
):
    # Rate limit (PMS-011). Só chamadas com parâmetros válidos chegam aqui e consomem.
    if isinstance(limitador, LimitadorTaxa):
        await limitador.consumir("busca")

    resultados_brutos = await buscador.recuperar_contexto(q, limit=limit)
    
    resultados_formatados = []
    for item in resultados_brutos:
        codigo = item["metadata"].get("codigo", "")
        secao = item["metadata"].get("secao", "")
        # Se for uma seção da Parte Geral (ex: "PG_8_1"), aponta para /parte-geral/{codigo.lower()}.html
        if secao == "PARTE_GERAL" or codigo.startswith("PG_"):
            url_estatica = f"/parte-geral/{codigo.lower()}.html"
        elif codigo:
            url_estatica = f"/fichas/{codigo}.html"
        else:
            url_estatica = None

        
        resultados_formatados.append({
            "id": item["id"],
            "score": item.get("rrf_score", 0.0),
            "codigo": codigo,
            "url": url_estatica,
            "trecho": item["metadata"].get("texto_contextualizado", "")
        })
        
    return {
        "query": q, 
        "resultados": resultados_formatados
    }

