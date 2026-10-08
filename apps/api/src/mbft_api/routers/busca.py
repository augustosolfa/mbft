from fastapi import APIRouter, Request, HTTPException, Query

router = APIRouter(prefix="/busca", tags=["Busca"])

@router.get("/")
async def buscar(request: Request, q: str = Query(..., min_length=2, max_length=200), limit: int = Query(5, ge=1, le=50)):
    buscador = getattr(request.app.state, "buscador", None)
    if not buscador:
        # TODO: Se estivermos na nuvem (Cloudflare), instanciar o BuscadorHibrido
        # usando os bindings do Workers (Vectorize, D1, AI) do request.scope["env"].
        # Como o scope local ainda não usa isso, levantamos erro.
        raise HTTPException(status_code=503, detail="Mecanismo de busca indisponível.")
        
    resultados_brutos = await buscador.recuperar_contexto(q, limit=limit)
    
    resultados_formatados = []
    for item in resultados_brutos:
        codigo = item["metadata"].get("codigo", "")
        # Se houver um código (ex: "518-51"), montamos a URL do SSG
        url_estatica = f"/fichas/{codigo}.html" if codigo else None
        
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
