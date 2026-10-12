import re
import unicodedata
from typing import Any, Dict, List
from fastapi import HTTPException
from .gerador.prompts import FRASE_CANONICA_RECUSA

MAX_PERGUNTA_CHARS = 350
LIMIAR_SIMILARIDADE_VETORIAL = 0.40

def remover_acentos(texto: str) -> str:
    """Normaliza o texto removendo acentos e marcas diacríticas."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))

# Padrões conhecidos de jailbreak, subversão de regras e adoção de persona
PADROES_INJECAO = [
    re.compile(r"\besque[çc][ae]\b.*?\b(?:instru[çc][õo]es|instruco?es|regras|diretrizes|comandos|tudo)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bignore\b.*?\b(?:instructions?|instru[çc][õo]es|instruco?es|regras|diretrizes|all|tudo|previous)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bforget\b.*?\b(?:instructions?|rules|everything|previous|all)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:aja|atue)\s+como\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\b", re.IGNORECASE),
    re.compile(r"\b(?:modo[\s\-_:]*dan|dan[\s\-_:]*mode)\b", re.IGNORECASE),
    re.compile(r"\bdesconsidere\b.*?\b(?:regras|instru[çc][õo]es|instruco?es|diretrizes|comandos|tudo)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bdisregard\b.*?\b(?:instructions?|rules|all)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"</?pergunta_usuario>", re.IGNORECASE),
    re.compile(r"\b(?:system\s*prompt|prompt\s+(?:de|do)\s+sistema)\b", re.IGNORECASE),
    re.compile(r"\b(?:agora\s+voc[eê]\s+[eé]|voc[eê]\s+agora\s+[eé]|you\s+are\s+now)\b", re.IGNORECASE),
]

def contem_injecao_direta(texto: str) -> bool:
    """
    Verifica se o texto contém padrões de injeção direta de prompt ou jailbreak.
    Aplica correspondência sobre o texto original e sobre a versão sem acentos.
    """
    texto_sem_acentos = remover_acentos(texto)
    for padrao in PADROES_INJECAO:
        if padrao.search(texto) or padrao.search(texto_sem_acentos):
            return True
    return False

def validar_pergunta(pergunta: str) -> None:
    """
    Valida a pergunta do usuário no edge/endpoint sem custo de tokens:
    1. Rejeita perguntas vazias ou apenas espaços (HTTP 400).
    2. Rejeita se ultrapassar 350 caracteres (HTTP 400).
    3. Rejeita se casar com padrões de prompt injection / subversão (HTTP 400).
    """
    if not pergunta or not pergunta.strip():
        raise HTTPException(
            status_code=400,
            detail="A pergunta não pode ser vazia.",
        )

    if len(pergunta) > MAX_PERGUNTA_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"A pergunta excede o limite máximo permitido de {MAX_PERGUNTA_CHARS} caracteres.",
        )

    if contem_injecao_direta(pergunta):
        raise HTTPException(
            status_code=400,
            detail="A pergunta contém instruções ou termos não permitidos.",
        )

def avaliar_relevancia_contexto(
    contexto: List[Dict[str, Any]],
    limiar_similaridade: float = LIMIAR_SIMILARIDADE_VETORIAL,
) -> bool:
    """
    Avalia se os resultados recuperados pelo BuscadorHibrido possuem relevância
    suficiente para acionar o LLM.

    Critérios de short-circuit (retorna False):
    - Se a lista de chunks estiver vazia;
    - Se a busca textual (FTS5) não retornou resultados E a maior similaridade vetorial
      for insignificante/baixa (< limiar).

    Retorna True se houver contexto relevante para responder à pergunta.
    """
    if not contexto:
        return False

    # 1. Verifica se houve match textual no FTS5
    tem_fts = getattr(contexto, "tem_match_fts", None)
    if tem_fts is None:
        tem_fts = any(bool(item.get("match_fts", False)) for item in contexto)

    if tem_fts:
        return True

    # 2. Se não houve FTS5, verifica similaridade vetorial máxima
    max_vetor = getattr(contexto, "max_similaridade_vetorial", None)
    if max_vetor is None:
        scores = [
            float(item.get("score_vetorial", item.get("score", 0.0)) or 0.0)
            for item in contexto
        ]
        max_vetor = max(scores, default=0.0)

    if max_vetor < limiar_similaridade:
        return False

    return True
