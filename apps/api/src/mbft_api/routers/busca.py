from fastapi import APIRouter

router = APIRouter(prefix="/busca", tags=["Busca"])

@router.get("/")
async def buscar(q: str):
    # TODO: Integrar mbft-recuperador
    # Retorna lista de links para /fichas/XXX.html
    return {"query": q, "resultados": []}
