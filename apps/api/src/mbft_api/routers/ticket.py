from fastapi import APIRouter, Depends, Header, HTTPException
from typing import Any, Optional
import jwt
import datetime
from ..database import get_db

router = APIRouter(prefix="/ticket", tags=["Ticketizador"])

JWT_SECRET = "MUDAR_EM_PRODUCAO" # Em prod, ler de env

@router.post("/")
async def solicitar_ticket(
    priority_token: Optional[str] = Header(None),
    db: Any = Depends(get_db)
):
    # Lógica simplificada. Aqui leremos as variáveis de ambiente em prod.
    token_admin = "fura_fila_secreto"
    token_testes = "testes_secreto"
    
    agora = datetime.datetime.utcnow()
    
    if priority_token == token_admin:
        next_available = agora
    elif priority_token == token_testes:
        next_available = agora + datetime.timedelta(seconds=10)
    else:
        # Fila Global (+60s)
        # TODO: Implementar o UPDATE no SQLite/D1
        next_available = agora + datetime.timedelta(seconds=60)
        
    ticket = jwt.encode(
        {"valid_after": next_available.isoformat()},
        JWT_SECRET,
        algorithm="HS256"
    )
    
    return {"ticket": ticket, "valid_after": next_available.isoformat()}
