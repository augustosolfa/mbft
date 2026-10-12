import hashlib
import json
import logging
import re
from typing import Optional
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..database import HistoricoRepository
from ..dependencies import get_buscador, get_gerador, get_historico_repo
from ..gerador.orquestrador import OrquestradorGeracao
from ..gerador.prompts import FRASE_CANONICA_RECUSA, SYSTEM_PROMPT_TEMPLATE
from ..recuperador.buscador import BuscadorHibrido
from ..seguranca import avaliar_relevancia_contexto, validar_pergunta

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Gerador LLM"])


class PerguntaPayload(BaseModel):
    pergunta: str = Field(..., description="Dúvida natural a ser respondida pela IA.")


@router.post("/")
async def fazer_pergunta(
    payload: PerguntaPayload = Body(...),
    response: Response = None,
    buscador: BuscadorHibrido = Depends(get_buscador),
    gerador: OrquestradorGeracao = Depends(get_gerador),
    historico_repo: HistoricoRepository = Depends(get_historico_repo),
):
    # Fallback defensivo para chamadas diretas em testes sem injeção FastAPI
    if not isinstance(historico_repo, HistoricoRepository):
        historico_repo = HistoricoRepository()

    # Filtro Heurístico no Edge / Endpoint (Custo: 0 tokens, aborta antes de Vectorize/D1/LLM)
    validar_pergunta(payload.pergunta)

    # 1. Hash Normalizado da consulta (SHA-256)
    query_hash = hashlib.sha256(payload.pergunta.strip().lower().encode("utf-8")).hexdigest()

    # 2. Checagem de Cache (Hit)
    registro_cache = None
    try:
        registro_cache = await historico_repo.buscar_cache_por_hash(query_hash)
    except Exception as exc:
        logger.warning(f"Falha ao consultar cache de histórico: {exc}")

    if registro_cache and registro_cache.get("resposta"):
        if response is not None:
            response.headers["X-Cache"] = "HIT"
            response.headers["X-Cache-Hit"] = "true"
        return {"resposta": registro_cache["resposta"]}

    # 3. Execução Normal (Miss): RAG Híbrido
    contexto_bruto = await buscador.recuperar_contexto(payload.pergunta, limit=5)

    # Corte por Limiar de Relevância / Short-Circuit (Custo: 0 tokens de LLM)
    if not avaliar_relevancia_contexto(contexto_bruto):
        try:
            await historico_repo.salvar_consulta(
                id=str(uuid.uuid4()),
                query_hash=query_hash,
                pergunta=payload.pergunta,
                busca_resultados_json=json.dumps([]),
                prompt_completo="",
                resposta=FRASE_CANONICA_RECUSA,
                from_cache=False,
            )
        except Exception as exc:
            logger.error(f"Falha ao persistir auditoria de short-circuit: {exc}")

        if response is not None:
            response.headers["X-Cache"] = "MISS"
            response.headers["X-Cache-Hit"] = "false"
        return {"resposta": FRASE_CANONICA_RECUSA}

    # Formata o contexto para o prompt
    textos_contexto = [
        (item.get("metadata") or {}).get("texto_contextualizado", "")
        for item in contexto_bruto
    ]
    contexto_formatado = "\n\n---\n\n".join(t for t in textos_contexto if t.strip())
    if not contexto_formatado:
        try:
            await historico_repo.salvar_consulta(
                id=str(uuid.uuid4()),
                query_hash=query_hash,
                pergunta=payload.pergunta,
                busca_resultados_json=json.dumps([]),
                prompt_completo="",
                resposta=FRASE_CANONICA_RECUSA,
                from_cache=False,
            )
        except Exception as exc:
            logger.error(f"Falha ao persistir auditoria de contexto vazio: {exc}")

        if response is not None:
            response.headers["X-Cache"] = "MISS"
            response.headers["X-Cache-Hit"] = "false"
        return {"resposta": FRASE_CANONICA_RECUSA}

    # Orquestração do prompt completo estruturado
    if hasattr(gerador, "montar_prompt") and callable(gerador.montar_prompt):
        prompt_completo = gerador.montar_prompt(payload.pergunta, contexto_formatado)
    else:
        pergunta_limpa = re.sub(r"</?pergunta_usuario>", "", payload.pergunta.strip(), flags=re.IGNORECASE)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(contexto=contexto_formatado)
        prompt_completo = f"{system_prompt}\n\n<pergunta_usuario>{pergunta_limpa}</pergunta_usuario>"

    # Fase 2: Geração Strict RAG (Zero-Hallucination)
    try:
        resposta_llm = await gerador.gerar_resposta(payload.pergunta, contexto_formatado)
    except Exception as e:
        logger.error(f"Erro ao consultar o Oráculo de IA: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao consultar o Oráculo de IA. Tente novamente mais tarde.")

    # Auditoria e Telemetria: Salva registro completo no banco
    try:
        await historico_repo.salvar_consulta(
            id=str(uuid.uuid4()),
            query_hash=query_hash,
            pergunta=payload.pergunta,
            busca_resultados_json=json.dumps(list(contexto_bruto), ensure_ascii=False, default=str),
            prompt_completo=prompt_completo,
            resposta=resposta_llm,
            from_cache=False,
        )
    except Exception as exc:
        logger.error(f"Falha ao persistir auditoria da consulta: {exc}")

    if response is not None:
        response.headers["X-Cache"] = "MISS"
        response.headers["X-Cache-Hit"] = "false"

    return {"resposta": resposta_llm}
