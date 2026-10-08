from fastapi import APIRouter, Header, Request, HTTPException, Body
from pydantic import BaseModel, Field
import jwt
import datetime
import os

router = APIRouter(prefix="/chat", tags=["Gerador LLM"])

class PerguntaPayload(BaseModel):
    pergunta: str = Field(..., min_length=5, max_length=500, description="Dúvida natural a ser respondida pela IA.")

@router.post("/")
async def fazer_pergunta(
    request: Request, 
    payload_body: PerguntaPayload = Body(...),
    x_ticket: str = Header(...)
):
    pergunta = payload_body.pergunta
    env = request.scope.get("env", os.environ)
    JWT_SECRET = env.get("JWT_SECRET")
    
    if not JWT_SECRET or JWT_SECRET == "MUDAR_EM_PRODUCAO":
        if not env.get("PYTEST_CURRENT_TEST"):
            raise HTTPException(status_code=500, detail="JWT_SECRET não configurado ou inseguro.")
        JWT_SECRET = "MUDAR_EM_PRODUCAO"

    try:
        payload = jwt.decode(
            x_ticket, 
            JWT_SECRET, 
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
            
        # Proteção contra Replay usando o KV_TICKETS
        jti = payload.get("jti")
        if "KV_TICKETS" in env and jti:
            ticket_usado = await env["KV_TICKETS"].get(jti)
            if ticket_usado:
                raise HTTPException(status_code=409, detail="Ticket já consumido. Solicite um novo.")
            # Marca o ticket como consumido com TTL igual ao restante de validade do ticket
            ttl = int((datetime.datetime.fromtimestamp(payload["exp"], tz=datetime.timezone.utc) - agora).total_seconds())
            if ttl > 0:
                await env["KV_TICKETS"].put(jti, "1", expirationTtl=ttl)
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Ticket expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Ticket inválido.")
        
    buscador = getattr(request.app.state, "buscador", None)
    gerador = getattr(request.app.state, "gerador", None)
    
    if not buscador or not gerador:
        raise HTTPException(status_code=503, detail="Motor de Inteligência Indisponível.")
        
    # Fase 1: RAG Híbrido
    contexto_bruto = await buscador.recuperar_contexto(pergunta, limit=5)
    
    # Formata o contexto para o prompt
    textos_contexto = [item["metadata"].get("texto_contextualizado", "") for item in contexto_bruto]
    contexto_formatado = "\n\n---\n\n".join(textos_contexto)
    
    # Fase 2: Geração Strict RAG (Zero-Hallucination)
    try:
        resposta_llm = await gerador.gerar_resposta(pergunta, contexto_formatado)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Erro ao consultar o Oráculo de IA: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao consultar o Oráculo de IA. Tente novamente mais tarde.")
        
    return {"resposta": resposta_llm}
