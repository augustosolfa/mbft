from fastapi import APIRouter, Depends, Header, Request, HTTPException
from typing import Any, Optional
import jwt
import datetime
from ..database import get_db, FilaRepository
import os

router = APIRouter(prefix="/ticket", tags=["Ticketizador"])

@router.post("/")
async def solicitar_ticket(
    request: Request,
    priority_token: Optional[str] = Header(None),
    db: Any = Depends(get_db)
):
    env = request.scope.get("env", os.environ)
    JWT_SECRET = env.get("JWT_SECRET", "MUDAR_EM_PRODUCAO")
    token_admin = env.get("TOKEN_ADMIN", "admin123")
    token_testes = env.get("TOKEN_TESTES", "testes123")
    
    agora = datetime.datetime.utcnow()
    repo = FilaRepository(db)
    
    if priority_token == token_admin:
        # Fura-fila imediato
        next_available_str = agora.isoformat()
    elif priority_token == token_testes:
        # Fila rápida (+10s) global. Como é teste, podemos só somar no repo
        next_available_str = await repo.avancar_fila_global(segundos=10)
    else:
        # Fila Global padrão (+60s)
        next_available_str = await repo.avancar_fila_global(segundos=60)
        
    # Se retornou nulo (banco não inicializado)
    if not next_available_str:
        next_available_str = agora.isoformat()
        
    # O banco retorna 'YYYY-MM-DD HH:MM:SS', precisamos garantir que está em ISO para o frontend
    if "T" not in next_available_str:
        next_available_str = next_available_str.replace(" ", "T") + "Z"
        
    ticket = jwt.encode(
        {"valid_after": next_available_str},
        JWT_SECRET,
        algorithm="HS256"
    )
    
    return {"ticket": ticket, "valid_after": next_available_str}
