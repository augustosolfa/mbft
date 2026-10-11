from collections.abc import Iterable
import logging
from typing import Any, Dict, List

from .interfaces import (
    FTS_RESERVED,
    IEmbedderClient,
    IRelationalDB,
    IVectorDB,
    RE_ROMANO,
    formatar_query_fts,
    formatar_token_fts,
)

logger = logging.getLogger(__name__)

DEFAULT_CF_EMBEDDING_MODEL = "@cf/baai/bge-m3"
MAX_VECTORIZE_TOPK_WITH_METADATA = 50


def is_js_null_or_undefined(val: Any) -> bool:
    """Identifica None ou sentinelas JsNull/JsUndefined vindos do FFI Pyodide."""
    if val is None:
        return True
    type_name = type(val).__name__
    return type_name in ("JsNull", "JsUndefined") or getattr(val, "typeof", None) == "undefined"


def _to_python(obj: Any) -> Any:
    """Converte objetos JsProxy/JsNull/JsUndefined do Pyodide em estruturas nativas do Python."""
    if is_js_null_or_undefined(obj):
        return None
    if hasattr(obj, "to_py") and callable(obj.to_py):
        res = obj.to_py()
        return None if is_js_null_or_undefined(res) else res
    return obj


def _to_js(value: Any) -> Any:
    """Converte dicts/listas Python em Object/Array JavaScript quando em Pyodide."""
    try:
        import js  # type: ignore[import-not-found]
        from pyodide.ffi import to_js  # type: ignore[import-not-found]

        return to_js(value, dict_converter=js.Object.fromEntries)
    except ImportError:
        return value


class D1RelationalDB(IRelationalDB):
    """
    Adaptador de busca textual exata (FTS5 / BM25) sobre o binding Cloudflare D1 (`env.DB`).
    Compartilha a mesma normalização e formatação de tokens FTS5 do `LocalSqliteDB`.
    """

    _RE_ROMANO = RE_ROMANO
    _FTS_RESERVED = FTS_RESERVED
    _formatar_token_fts = staticmethod(formatar_token_fts)
    _formatar_query_fts = staticmethod(formatar_query_fts)

    def __init__(self, d1_binding: Any):
        self.db = d1_binding

    async def buscar_fts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []

        fts_query = self._formatar_query_fts(query)
        if not fts_query:
            return []

        sql = """
            SELECT id, codigo, artigo, secao, texto_contextualizado, bm25(fts_chunks) as score
            FROM fts_chunks
            WHERE fts_chunks MATCH ?
            ORDER BY score ASC
            LIMIT ?
        """
        stmt = self.db.prepare(sql).bind(fts_query, int(limit))
        raw_res = await stmt.all()
        res = _to_python(raw_res)

        if isinstance(res, dict):
            rows = _to_python(res.get("results")) or []
        elif hasattr(res, "results"):
            rows = _to_python(res.results) or []
        elif isinstance(res, list):
            rows = res
        else:
            rows = []

        resultados: List[Dict[str, Any]] = []
        for row in rows:
            row_dict = _to_python(row)
            if not isinstance(row_dict, dict):
                continue
            row_id = _to_python(row_dict.get("id"))
            if row_id is None:
                continue
            raw_score = _to_python(row_dict.get("score", 0.0))
            resultados.append(
                {
                    "id": str(row_id),
                    "metadata": {
                        "codigo": str(_to_python(row_dict.get("codigo")) or ""),
                        "artigo": str(_to_python(row_dict.get("artigo")) or ""),
                        "secao": str(_to_python(row_dict.get("secao")) or ""),
                        "texto_contextualizado": str(_to_python(row_dict.get("texto_contextualizado")) or ""),
                    },
                    "score": abs(float(raw_score if raw_score is not None else 0.0)),
                }
            )
        return resultados


class VectorizeDB(IVectorDB):
    """
    Adaptador de busca vetorial densa sobre o binding Cloudflare Vectorize (`env.VECTORIZE`).
    Respeita o teto de `topK <= 50` exigido pelo Vectorize V2 quando `returnMetadata="all"`.
    """

    def __init__(self, vectorize_binding: Any):
        self.index = vectorize_binding

    async def buscar_similares(self, vetor: List[float], limit: int = 5) -> List[Dict[str, Any]]:
        if limit <= 0 or not vetor:
            return []

        top_k = min(int(limit), MAX_VECTORIZE_TOPK_WITH_METADATA)
        options = {"topK": top_k, "returnMetadata": "all"}
        raw_res = await self.index.query(_to_js([float(x) for x in vetor]), _to_js(options))
        res = _to_python(raw_res)

        if isinstance(res, dict):
            matches = _to_python(res.get("matches")) or []
        elif hasattr(res, "matches"):
            matches = _to_python(res.matches) or []
        elif isinstance(res, list):
            matches = res
        else:
            matches = []

        resultados: List[Dict[str, Any]] = []
        for match in matches:
            m_dict = _to_python(match)
            if not isinstance(m_dict, dict):
                continue
            match_id = _to_python(m_dict.get("id"))
            if match_id is None:
                continue
            meta = _to_python(m_dict.get("metadata") or {})
            raw_score = _to_python(m_dict.get("score", 0.0))
            resultados.append(
                {
                    "id": str(match_id),
                    "score": float(raw_score if raw_score is not None else 0.0),
                    "metadata": dict(meta) if isinstance(meta, dict) else {},
                }
            )
        return resultados[:limit]


class WorkersAIEmbedder(IEmbedderClient):
    """
    Adaptador de geração de embeddings de 1024 dimensões via Cloudflare Workers AI (`env.AI`).
    Utiliza o modelo `@cf/baai/bge-m3` por padrão, mantendo compatibilidade com o indexador offline.
    """

    def __init__(self, ai_binding: Any, model: str = DEFAULT_CF_EMBEDDING_MODEL):
        self.ai = ai_binding
        self.model = model or DEFAULT_CF_EMBEDDING_MODEL

    async def embed_query(self, query: str) -> List[float]:
        if not query or not query.strip():
            return []

        try:
            raw_res = await self.ai.run(self.model, _to_js({"text": [query]}))
        except Exception as exc:
            logger.error("Erro ao gerar embedding no Workers AI (%s): %s", self.model, exc)
            return []

        res = _to_python(raw_res)
        if res is None:
            return []

        if isinstance(res, dict):
            data = _to_python(res.get("data"))
        else:
            data = _to_python(getattr(res, "data", None))

        if not data or not isinstance(data, Iterable) or isinstance(data, (str, bytes, dict)):
            return []

        data_list = list(data)
        if not data_list:
            return []

        first = _to_python(data_list[0])
        if first is None:
            return []
        if isinstance(first, Iterable) and not isinstance(first, (str, bytes, dict)):
            return [float(x) for x in first]
        return [float(x) for x in data_list]
