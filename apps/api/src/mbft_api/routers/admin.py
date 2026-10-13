"""Router administrativo para inspeção e visualização de tabelas do D1/SQLite.

Acesso restrito exclusivamente ao e-mail declarado em ADMIN_EMAIL, com autenticação
via token JWT do Cloudflare Access (RS256).

Segurança:
- Fechado por padrão (Fail-Safe / Secure by Default).
- Em ambiente de desenvolvimento local (fora do Workers e com ENVIRONMENT explicitamente
  definido como 'dev', 'development', 'local' ou 'test'), o acesso é liberado para testes.
"""

from collections.abc import Mapping
import inspect
import logging
import math
import os
import sqlite3
import sys
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..database import _resolver_awaitable, _to_python
from ..dependencies import get_env_binding
from ..rate_limit import _obter_verificador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

PAGE_SIZE_PADRAO = 100
PAGE_SIZE_MAXIMO = 100


def _serializar_valor(valor: Any) -> Any:
    """Converte valores do SQLite/D1 para tipos seguros em JSON."""
    if valor is None:
        return None
    if isinstance(valor, bytes):
        try:
            return valor.decode("utf-8")
        except UnicodeDecodeError:
            return valor.hex()
    if isinstance(valor, (int, float, str, bool)):
        return valor
    return str(valor)


def _garantir_schema_dev(conn: sqlite3.Connection) -> None:
    """Garante tabelas essenciais em desenvolvimento local em memória."""
    try:
        cur = conn.cursor()
        cur.execute(
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identidade TEXT NOT NULL,
                recurso TEXT NOT NULL,
                criado_em INTEGER NOT NULL,
                conta_cota INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Falha ao garantir schema de dev: %s", exc)


def get_admin_db(request: Request) -> Any:
    """Obtém o banco de dados (binding D1 em produção ou SQLite em desenvolvimento)."""
    env = request.scope.get("env")
    db_binding = get_env_binding(env, "DB")
    if db_binding is not None:
        return db_binding

    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    if state is not None:
        db = getattr(state, "admin_db", None)
        if db is not None:
            return db

        repo = getattr(state, "historico_repo", None)
        if repo is not None and getattr(repo, "db", None) is not None:
            db = repo.db
            setattr(state, "admin_db", db)
            if isinstance(db, sqlite3.Connection):
                _garantir_schema_dev(db)
            return db

        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _garantir_schema_dev(conn)
        setattr(state, "admin_db", conn)
        return conn

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _garantir_schema_dev(conn)
    return conn


async def obter_admin_verificado(request: Request) -> str:
    """Dependência que valida privilégios de administrador (Secure by Default)."""
    env = request.scope.get("env")
    db_binding = get_env_binding(env, "DB")
    raw_env = (
        get_env_binding(env, "ENVIRONMENT") or os.environ.get("ENVIRONMENT") or ""
    ).strip().lower()
    admin_email = (
        get_env_binding(env, "ADMIN_EMAIL") or os.environ.get("ADMIN_EMAIL") or ""
    ).strip().lower()

    # Exceção estrita de desenvolvimento local
    if (
        sys.platform != "emscripten"
        and db_binding is None
        and raw_env in ("dev", "development", "local", "test")
    ):
        return admin_email or "admin-local@mbft.local"

    # Regra geral (fechado por padrão): exige token válido e ADMIN_EMAIL configurado
    if not admin_email:
        logger.error("Acesso ao /admin bloqueado: ADMIN_EMAIL não configurado.")
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito: ADMIN_EMAIL não configurado nas variáveis do Worker.",
        )

    token = request.headers.get("cf-access-jwt-assertion") or request.cookies.get(
        "CF_Authorization"
    )
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token do Cloudflare Access ausente.",
        )

    verificador = _obter_verificador(env)
    if verificador is None:
        raise HTTPException(
            status_code=403,
            detail="Validação de identidade indisponível (Cloudflare Access não configurado).",
        )

    email_logado = await verificador.email_verificado(token)
    if not email_logado:
        raise HTTPException(
            status_code=401,
            detail="Token do Cloudflare Access inválido ou expirado.",
        )

    if email_logado != admin_email:
        logger.warning(
            "Tentativa não autorizada ao painel admin: %s (esperado: %s)",
            email_logado,
            admin_email,
        )
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito: usuário não possui privilégios de administrador.",
        )

    return email_logado


async def _executar_sql_admin(db: Any, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Executa SQL de forma agnóstica em Cloudflare D1 ou SQLite local."""
    if hasattr(db, "prepare") and callable(getattr(db, "prepare")):
        stmt = db.prepare(sql).bind(*params)
        raw = await _resolver_awaitable(stmt.all())
        res = _to_python(raw)
        linhas: list[Any] = []
        if isinstance(res, dict):
            linhas = _to_python(res.get("results")) or []
        elif hasattr(res, "results"):
            linhas = _to_python(res.results) or []
        elif isinstance(res, list):
            linhas = res

        resultado: list[dict[str, Any]] = []
        for linha in linhas:
            py_linha = _to_python(linha)
            if isinstance(py_linha, Mapping):
                resultado.append({k: _serializar_valor(v) for k, v in dict(py_linha).items()})
        return resultado

    cur = db.cursor()
    res = cur.execute(sql, params)
    if inspect.isawaitable(res) or hasattr(res, "__await__"):
        cur = await res
    rows = await _resolver_awaitable(cur.fetchall())
    cols = [d[0] for d in cur.description] if cur.description else []
    resultado = []
    for row in rows:
        if isinstance(row, sqlite3.Row):
            d = dict(row)
        elif isinstance(row, Mapping):
            d = dict(row)
        else:
            d = dict(zip(cols, row))
        resultado.append({k: _serializar_valor(v) for k, v in d.items()})
    return resultado


async def _listar_tabelas_catalogo(db: Any) -> list[dict[str, str]]:
    """Devolve a lista com todas as tabelas e views do sqlite_master, exceto internas reservadas."""
    sql = (
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table', 'view') "
        "  AND name NOT LIKE '_cf_%' "
        "  AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name;"
    )
    linhas = await _executar_sql_admin(db, sql)
    return [{"name": str(l.get("name")), "type": str(l.get("type"))} for l in linhas if l.get("name")]


@router.get("/tables")
async def listar_tabelas(
    _admin: str = Depends(obter_admin_verificado),
    db: Any = Depends(get_admin_db),
) -> dict[str, Any]:
    """Lista todas as tabelas e views presentes no banco de dados."""
    tabelas = await _listar_tabelas_catalogo(db)
    return {"tables": tabelas}


@router.get("/tables/{table_name}")
async def obter_dados_tabela(
    table_name: str,
    page: int = Query(1, ge=1, description="Número da página (1-indexed)"),
    page_size: int = Query(
        PAGE_SIZE_PADRAO,
        ge=1,
        le=PAGE_SIZE_MAXIMO,
        description="Tamanho da página (máximo 100)",
    ),
    _admin: str = Depends(obter_admin_verificado),
    db: Any = Depends(get_admin_db),
) -> dict[str, Any]:
    """Exibe os dados paginados da tabela selecionada."""
    if table_name.startswith("_cf_") or table_name.startswith("sqlite_"):
        raise HTTPException(
            status_code=403,
            detail=f"Acesso à tabela interna do sistema '{table_name}' é restrito pela Cloudflare.",
        )

    catalogo = await _listar_tabelas_catalogo(db)
    nomes_validos = {t["name"] for t in catalogo}
    if table_name not in nomes_validos:
        raise HTTPException(
            status_code=404,
            detail=f"Tabela '{table_name}' não encontrada no banco de dados.",
        )

    try:
        nome_limpo = table_name.replace('"', '""')
        tabela_escapada = f'"{nome_limpo}"'

        # Metadados das colunas via PRAGMA table_info
        info_colunas = await _executar_sql_admin(db, f"PRAGMA table_info({tabela_escapada});")
        colunas = [str(c.get("name")) for c in info_colunas if c.get("name")]

        # Determina chave primária para ordenação decrescente (registros recentes primeiro)
        coluna_pk = next((str(c.get("name")) for c in info_colunas if int(c.get("pk") or 0) > 0), None)
        if not coluna_pk:
            for cand in ("created_at", "criado_em", "id", "timestamp"):
                if cand in colunas:
                    coluna_pk = cand
                    break

        # Contagem total de linhas
        sql_count = f"SELECT COUNT(*) AS total FROM {tabela_escapada};"
        res_count = await _executar_sql_admin(db, sql_count)
        total_linhas = int(res_count[0].get("total", 0)) if res_count else 0
        total_paginas = max(1, math.ceil(total_linhas / page_size)) if total_linhas > 0 else 1

        pagina_atual = min(page, total_paginas)
        offset = (pagina_atual - 1) * page_size

        # Cláusula de ordenação com fallback seguro
        if coluna_pk:
            pk_limpa = coluna_pk.replace('"', '""')
            clausula_ordem = f'ORDER BY "{pk_limpa}" DESC'
        else:
            clausula_ordem = "ORDER BY rowid DESC"

        sql_select = f"SELECT * FROM {tabela_escapada} {clausula_ordem} LIMIT ? OFFSET ?;"
        try:
            linhas = await _executar_sql_admin(db, sql_select, (page_size, offset))
        except Exception:
            # Fallback sem ORDER BY caso rowid não seja suportado (ex.: tabelas virtuais FTS5)
            sql_fallback = f"SELECT * FROM {tabela_escapada} LIMIT ? OFFSET ?;"
            linhas = await _executar_sql_admin(db, sql_fallback, (page_size, offset))

        # Se colunas estava vazio (ex.: views ou tabelas sem PRAGMA), extrai das chaves das linhas
        if not colunas and linhas:
            colunas = list(linhas[0].keys())

        return {
            "table": table_name,
            "page": pagina_atual,
            "page_size": page_size,
            "total_rows": total_linhas,
            "total_pages": total_paginas,
            "columns": colunas,
            "rows": linhas,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Falha ao consultar tabela '%s': %s", table_name, exc)
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível consultar a tabela '{table_name}': {exc}",
        ) from exc
