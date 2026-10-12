from collections.abc import Mapping
import inspect
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


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


async def _resolver_awaitable(val: Any) -> Any:
    """Resolve awaitable ou Promessa Pyodide de forma transparente."""
    if inspect.isawaitable(val) or hasattr(val, "__await__"):
        return await val
    return val


class HistoricoRepository:
    """
    Repositório de persistência e consulta para telemetria de RAG e cache exato.
    Suporta tanto Cloudflare D1 (via binding em Workers) quanto SQLite local/em memória.
    """

    def __init__(self, db: Any = None):
        if db is None:
            # Fallback padrão: SQLite local em memória com schema aplicado
            self.db = self._criar_sqlite_memoria()
        else:
            self.db = db
            # Se for conexão SQLite direta, garante que a tabela existe
            if isinstance(self.db, sqlite3.Connection):
                self._garantir_tabela_sqlite(self.db)

    @staticmethod
    def _criar_sqlite_memoria() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        HistoricoRepository._garantir_tabela_sqlite(conn)
        return conn

    @staticmethod
    def _garantir_tabela_sqlite(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_consultas (
                id TEXT PRIMARY KEY,
                query_hash TEXT NOT NULL,
                pergunta TEXT NOT NULL,
                busca_resultados_json TEXT NOT NULL,
                prompt_completo TEXT NOT NULL,
                resposta TEXT NOT NULL,
                from_cache INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_consultas_query_hash ON historico_consultas (query_hash);"
        )
        conn.commit()

    async def buscar_cache_por_hash(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retorna o registro mais recente para o hash da consulta (se existir no banco).
        """
        if not query_hash or not query_hash.strip():
            return None

        sql = """
            SELECT id, query_hash, pergunta, busca_resultados_json, prompt_completo, resposta, from_cache, created_at
            FROM historico_consultas
            WHERE query_hash = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
        """

        if hasattr(self.db, "prepare") and callable(getattr(self.db, "prepare")):
            # API Cloudflare D1
            stmt = self.db.prepare(sql).bind(query_hash)
            if hasattr(stmt, "first") and callable(stmt.first):
                raw = await _resolver_awaitable(stmt.first())
                res = _to_python(raw)
                if res and isinstance(res, (dict, Mapping)):
                    return self._normalizar_registro(dict(res))
                return None
            elif hasattr(stmt, "all") and callable(stmt.all):
                raw = await _resolver_awaitable(stmt.all())
                res = _to_python(raw)
                rows = []
                if isinstance(res, dict):
                    rows = _to_python(res.get("results")) or []
                elif hasattr(res, "results"):
                    rows = _to_python(res.results) or []
                elif isinstance(res, list):
                    rows = res
                if rows:
                    first_row = _to_python(rows[0])
                    if isinstance(first_row, (dict, Mapping)):
                        return self._normalizar_registro(dict(first_row))
                return None
            return None

        # API SQLite Local
        cur = self.db.cursor()
        res = cur.execute(sql, (query_hash,))
        if inspect.isawaitable(res) or hasattr(res, "__await__"):
            cur = await res
        row = await _resolver_awaitable(cur.fetchone())
        if row is None:
            return None

        if isinstance(row, sqlite3.Row):
            registro = dict(row)
        elif isinstance(row, (dict, Mapping)):
            registro = dict(row)
        else:
            cols = [d[0] for d in cur.description] if cur.description else []
            registro = dict(zip(cols, row))

        return self._normalizar_registro(registro)

    async def salvar_consulta(
        self,
        id: str,
        query_hash: str,
        pergunta: str,
        busca_resultados_json: str,
        prompt_completo: str,
        resposta: str,
        from_cache: bool = False,
    ) -> None:
        """
        Grava a execução completa no banco de dados de forma assíncrona.
        """
        sql = """
            INSERT INTO historico_consultas (
                id, query_hash, pergunta, busca_resultados_json, prompt_completo, resposta, from_cache
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        from_cache_int = 1 if from_cache else 0

        if hasattr(self.db, "prepare") and callable(getattr(self.db, "prepare")):
            # API Cloudflare D1
            stmt = self.db.prepare(sql).bind(
                id,
                query_hash,
                pergunta,
                busca_resultados_json,
                prompt_completo,
                resposta,
                from_cache_int,
            )
            if hasattr(stmt, "run") and callable(stmt.run):
                await _resolver_awaitable(stmt.run())
            elif hasattr(stmt, "all") and callable(stmt.all):
                await _resolver_awaitable(stmt.all())
            return

        # API SQLite Local
        res = self.db.execute(
            sql,
            (
                id,
                query_hash,
                pergunta,
                busca_resultados_json,
                prompt_completo,
                resposta,
                from_cache_int,
            ),
        )
        if inspect.isawaitable(res) or hasattr(res, "__await__"):
            await res
        if hasattr(self.db, "commit"):
            await _resolver_awaitable(self.db.commit())

    @staticmethod
    def _normalizar_registro(registro: Mapping[str, Any]) -> Dict[str, Any]:
        """Normaliza campos do registro para tipos nativos do Python."""
        return {
            "id": str(_to_python(registro.get("id")) or ""),
            "query_hash": str(_to_python(registro.get("query_hash")) or ""),
            "pergunta": str(_to_python(registro.get("pergunta")) or ""),
            "busca_resultados_json": str(_to_python(registro.get("busca_resultados_json")) or ""),
            "prompt_completo": str(_to_python(registro.get("prompt_completo")) or ""),
            "resposta": str(_to_python(registro.get("resposta")) or ""),
            "from_cache": bool(_to_python(registro.get("from_cache"))),
            "created_at": _to_python(registro.get("created_at")),
        }
