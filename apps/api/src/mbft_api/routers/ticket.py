from fastapi import APIRouter, Depends, Header, Request, HTTPException
from typing import Any, Optional
import jwt
import datetime
import secrets
from ..database import get_db, FilaRepository
import os
import hashlib
import uuid

def seguro_compara_segredo(fornecido: Optional[str], esperado: Optional[str]) -> bool:
    if not fornecido or not esperado:
        return False
    hash_fornecido = hashlib.sha256(fornecido.encode("utf-8")).digest()
    hash_esperado = hashlib.sha256(esperado.encode("utf-8")).digest()
    return secrets.compare_digest(hash_fornecido, hash_esperado)

router = APIRouter(prefix="/ticket", tags=["Ticketizador"])

@router.post("/")
async def solicitar_ticket(
    request: Request,
    priority_token: Optional[str] = Header(None),
    db: Any = Depends(get_db)
):
    env = request.scope.get("env", os.environ)
    JWT_SECRET = env.get("JWT_SECRET")
    
    # Prevenção contra segredos default em prod (CWE-1188)
    if not JWT_SECRET or JWT_SECRET == "MUDAR_EM_PRODUCAO":
        if not env.get("PYTEST_CURRENT_TEST"):
            raise HTTPException(status_code=500, detail="JWT_SECRET não configurado ou inseguro.")
        JWT_SECRET = "MUDAR_EM_PRODUCAO"
        
    token_admin = env.get("TOKEN_ADMIN")
    token_testes = env.get("TOKEN_TESTES")
    
    agora = datetime.datetime.now(datetime.timezone.utc)
    repo = FilaRepository(db)
    
    # Prevenção contra Timing Attack (CWE-208)
    if seguro_compara_segredo(priority_token, token_admin):
        # Fura-fila imediato
        next_available_str = agora.isoformat()
    elif seguro_compara_segredo(priority_token, token_testes):
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
        
    # Valid After timestamp
    valid_after_dt = datetime.datetime.fromisoformat(next_available_str.replace("Z", "+00:00"))
    
    # Prevenção contra Replay Infinito (CWE-294) - Token expira em 2 minutos após a liberação
    exp_dt = valid_after_dt + datetime.timedelta(minutes=2)
    jti = str(uuid.uuid4())
        
    ticket = jwt.encode(
        {
            "valid_after": next_available_str,
            "exp": exp_dt.timestamp(),
            "jti": jti
        },
        JWT_SECRET,
        algorithm="HS256"
    )
    
    return {"ticket": ticket, "valid_after": next_available_str}
