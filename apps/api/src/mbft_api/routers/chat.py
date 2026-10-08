from fastapi import APIRouter, Header, Request, HTTPException, Query
import jwt
import datetime
import os

router = APIRouter(prefix="/chat", tags=["Gerador LLM"])

@router.post("/")
async def fazer_pergunta(
    request: Request, 
    pergunta: str = Query(..., min_length=5, max_length=500, description="Dúvida natural a ser respondida pela IA."),
    x_ticket: str = Header(...)
):
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
        raise HTTPException(status_code=500, detail=f"Erro ao consultar o Oráculo de IA: {e}")
        
    return {"resposta": resposta_llm}
