from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Sistema"])

@router.get("/")
async def check_health():
    return {"status": "ok", "service": "mbft-api"}
