import re
from typing import List, Protocol, Dict, Any

RE_ROMANO = re.compile(
    r"^(?=[MDCLXVI]+$)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)
FTS_RESERVED = {"AND", "OR", "NOT", "NEAR"}


def formatar_token_fts(token: str) -> str:
    """
    Formata um token individual para consulta FTS5:
    - Escapa operadores booleanos reservados (AND, OR, NOT, NEAR);
    - Preserva termos curtos (<4 chars), numéricos e algarismos romanos de forma exata;
    - Adiciona sufixo de prefixo (*) em palavras comuns com 4+ letras.
    """
    if not token:
        return ""
    if token.upper() in FTS_RESERVED:
        return f'"{token}"'
    if (
        len(token) >= 4
        and not any(c.isdigit() for c in token)
        and not RE_ROMANO.fullmatch(token)
    ):
        return f"{token}*"
    return token


def formatar_query_fts(query: str) -> str:
    """
    Normaliza símbolo de grau (°) após dígitos para indicador ordinal (º),
    extrai tokens alfanuméricos sem sublinhados (alinhado ao unicode61 do FTS5)
    e monta a expressão de busca para a cláusula MATCH.
    """
    if not query:
        return ""
    query_norm = re.sub(r"(\d)\s*°", r"\1º", query)
    tokens = re.findall(r"[^\W_]+", query_norm)
    if not tokens:
        return ""
    return " ".join(t_fmt for t in tokens if (t_fmt := formatar_token_fts(t)))


class IVectorDB(Protocol):
    async def buscar_similares(self, vetor: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retorna uma lista de chunks.
        Exemplo de retorno: [{"id": "751-01_QUANDO_AUTUAR", "score": 0.85, "metadata": {...}}]
        """
        ...

class IRelationalDB(Protocol):
    async def buscar_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retorna uma lista de chunks via busca textual exata (BM25).
        Exemplo de retorno: [{"id": "751-01_QUANDO_AUTUAR", "score": 0.9, "metadata": {...}}]
        """
        ...

class IEmbedderClient(Protocol):
    async def embed_query(self, query: str) -> List[float]:
        """Gera o vetor denso de 1024 dimensões da pergunta."""
        ...

