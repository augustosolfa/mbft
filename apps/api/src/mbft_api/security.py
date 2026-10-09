import jwt
import datetime
import uuid
import hashlib
import secrets
import os
from typing import Optional, Any
from fastapi import Request, Header, HTTPException, Depends
from .database import get_db, FilaRepository

class Settings:
    def __init__(self, env: dict):
        self.jwt_secret = env.get("JWT_SECRET")
        self.token_admin = env.get("TOKEN_ADMIN")
        self.token_testes = env.get("TOKEN_TESTES")
        self.kv_tickets = env.get("KV_TICKETS")

        if not self.jwt_secret or self.jwt_secret == "MUDAR_EM_PRODUCAO":
            raise HTTPException(status_code=500, detail="JWT_SECRET não configurado ou inseguro.")

def get_settings(request: Request) -> Settings:
    env = request.scope.get("env", os.environ)
    return Settings(env)

def seguro_compara_segredo(fornecido: Optional[str], esperado: Optional[str]) -> bool:
    if not fornecido or not esperado:
        return False
    hash_fornecido = hashlib.sha256(fornecido.encode("utf-8")).digest()
    hash_esperado = hashlib.sha256(esperado.encode("utf-8")).digest()
    return secrets.compare_digest(hash_fornecido, hash_esperado)

class TicketService:
    def __init__(self, settings: Settings, repo: FilaRepository):
        self.settings = settings
        self.repo = repo

    async def emitir(self, priority_token: Optional[str]) -> dict:
        agora = datetime.datetime.now(datetime.timezone.utc)
        
        if seguro_compara_segredo(priority_token, self.settings.token_admin):
            next_available_str = agora.isoformat()
        elif seguro_compara_segredo(priority_token, self.settings.token_testes):
            next_available_str = await self.repo.avancar_fila_global(segundos=10)
        else:
            next_available_str = await self.repo.avancar_fila_global(segundos=60)
            
        if not next_available_str:
            next_available_str = agora.isoformat()
            
        if "T" not in next_available_str:
            next_available_str = next_available_str.replace(" ", "T") + "Z"
            
        valid_after_dt = datetime.datetime.fromisoformat(next_available_str.replace("Z", "+00:00"))
        
        exp_dt = valid_after_dt + datetime.timedelta(minutes=2)
        jti = str(uuid.uuid4())
            
        ticket = jwt.encode(
            {
                "valid_after": next_available_str,
                "exp": exp_dt.timestamp(),
                "jti": jti
            },
            self.settings.jwt_secret,
            algorithm="HS256"
        )
        
        return {"ticket": ticket, "valid_after": next_available_str}

    async def validar_e_consumir(self, x_ticket: str):
        try:
            payload = jwt.decode(
                x_ticket, 
                self.settings.jwt_secret, 
                algorithms=["HS256"],
                options={"require": ["exp", "valid_after", "jti"]}
            )
            
            valid_after_str = payload["valid_after"].replace("Z", "+00:00")
            valid_after = datetime.datetime.fromisoformat(valid_after_str)
            if valid_after.tzinfo is None:
                valid_after = valid_after.replace(tzinfo=datetime.timezone.utc)
                
            agora = datetime.datetime.now(datetime.timezone.utc)
            
            if agora < valid_after:
                espera = (valid_after - agora).total_seconds()
                raise HTTPException(status_code=429, detail=f"Aguarde na fila. Seu ticket será válido em {espera:.0f} segundos.")
                
            jti = payload.get("jti")
            if self.settings.kv_tickets and jti:
                ticket_usado = await self.settings.kv_tickets.get(jti)
                if ticket_usado:
                    raise HTTPException(status_code=409, detail="Ticket já consumido. Solicite um novo.")
                ttl = int((datetime.datetime.fromtimestamp(payload["exp"], tz=datetime.timezone.utc) - agora).total_seconds())
                if ttl > 0:
                    await self.settings.kv_tickets.put(jti, "1", expirationTtl=ttl)
                
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Ticket expirado.")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Ticket inválido.")

async def ticket_valido(
    x_ticket: str = Header(...),
    settings: Settings = Depends(get_settings),
    db: FilaRepository = Depends(get_db)
):
    service = TicketService(settings, db)
    await service.validar_e_consumir(x_ticket)
    return x_ticket
