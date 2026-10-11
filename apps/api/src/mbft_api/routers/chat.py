from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel, Field
from ..dependencies import get_buscador, get_gerador
from ..gerador.orquestrador import OrquestradorGeracao
from ..recuperador.buscador import BuscadorHibrido
from ..security import ticket_valido

router = APIRouter(prefix="/chat", tags=["Gerador LLM"])

class PerguntaPayload(BaseModel):
    pergunta: str = Field(..., min_length=5, max_length=500, description="Dúvida natural a ser respondida pela IA.")

@router.post("/")
async def fazer_pergunta(
    payload: PerguntaPayload = Body(...),
    buscador: BuscadorHibrido = Depends(get_buscador),
    gerador: OrquestradorGeracao = Depends(get_gerador),
    _ticket: str = Depends(ticket_valido),
):
    # Fase 1: RAG Híbrido
    contexto_bruto = await buscador.recuperar_contexto(payload.pergunta, limit=5)
    
    # Formata o contexto para o prompt
    textos_contexto = [item["metadata"].get("texto_contextualizado", "") for item in contexto_bruto]
    contexto_formatado = "\n\n---\n\n".join(textos_contexto)
    
    # Fase 2: Geração Strict RAG (Zero-Hallucination)
    try:
        resposta_llm = await gerador.gerar_resposta(payload.pergunta, contexto_formatado)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Erro ao consultar o Oráculo de IA: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao consultar o Oráculo de IA. Tente novamente mais tarde.")
        
    return {"resposta": resposta_llm}

