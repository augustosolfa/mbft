from fastapi import APIRouter, Header, HTTPException
import jwt
import datetime

router = APIRouter(prefix="/chat", tags=["Gerador LLM"])

JWT_SECRET = "MUDAR_EM_PRODUCAO"

@router.post("/")
async def fazer_pergunta(pergunta: str, x_ticket: str = Header(...)):
    try:
        payload = jwt.decode(x_ticket, JWT_SECRET, algorithms=["HS256"])
        valid_after = datetime.datetime.fromisoformat(payload["valid_after"])
        agora = datetime.datetime.utcnow()
        
        if agora < valid_after:
            espera = (valid_after - agora).total_seconds()
            raise HTTPException(status_code=429, detail=f"Aguarde na fila. Seu ticket será válido em {espera:.0f} segundos.")
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Ticket expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Ticket inválido.")
        
    # TODO: Integrar mbft-gerador
    return {"resposta": "LLM Responderia aqui."}
