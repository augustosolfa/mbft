from fastapi import APIRouter, Header, Request, HTTPException
import jwt
import datetime
import os

router = APIRouter(prefix="/chat", tags=["Gerador LLM"])

@router.post("/")
async def fazer_pergunta(pergunta: str, request: Request, x_ticket: str = Header(...)):
    env = request.scope.get("env", os.environ)
    JWT_SECRET = env.get("JWT_SECRET", "MUDAR_EM_PRODUCAO")

    try:
        payload = jwt.decode(x_ticket, JWT_SECRET, algorithms=["HS256"])
        
        # Como as strings iso podem vir com 'Z' e o fromisoformat pode encrencar (antes do 3.11), 
        # limpamos para parsear (nosso server local deve suportar, mas precaução)
        valid_after_str = payload["valid_after"].replace("Z", "+00:00")
        valid_after = datetime.datetime.fromisoformat(valid_after_str).replace(tzinfo=None)
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
