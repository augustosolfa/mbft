import sqlite3
import os
from fastapi import Request
from typing import Any, Protocol
from .dependencies import get_env_binding
from .recuperador.cloudflare_adapters import _to_python

# Durante o dev local, usaremos um arquivo SQLite.
# Em produção (Cloudflare), usaremos request.scope["env"]["DB"] (binding D1)

LOCAL_DB_PATH = "fila.db"

def init_local_db():
    if not os.path.exists(LOCAL_DB_PATH):
        conn = sqlite3.connect(LOCAL_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fila_global (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                next_available DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO fila_global (id) VALUES (1)")
        conn.commit()
        conn.close()

class FilaRepository(Protocol):
    async def avancar_fila_global(self, segundos: int = 60) -> str:
        ...

class SqliteFilaRepository:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    async def avancar_fila_global(self, segundos: int = 60) -> str:
        query = '''
            UPDATE fila_global 
            SET next_available = datetime(
                max(
                    CAST(strftime('%s', next_available) AS INTEGER), 
                    CAST(strftime('%s', 'now') AS INTEGER)
                ) + ?, 
                'unixepoch'
            ) 
            WHERE id = 1 
            RETURNING next_available;
        '''
        cursor = self.db.cursor()
        cursor.execute(query, (segundos,))
        row = cursor.fetchone()
        self.db.commit()
        return row[0] if row else ""

class D1FilaRepository:
    def __init__(self, db: Any):
        self.db = db

    async def avancar_fila_global(self, segundos: int = 60) -> str:
        query = '''
            UPDATE fila_global 
            SET next_available = datetime(
                max(
                    CAST(strftime('%s', next_available) AS INTEGER), 
                    CAST(strftime('%s', 'now') AS INTEGER)
                ) + ?, 
                'unixepoch'
            ) 
            WHERE id = 1 
            RETURNING next_available;
        '''
        stmt = self.db.prepare(query).bind(segundos)
        result = _to_python(await stmt.first())
        if isinstance(result, dict):
            return str(result.get("next_available") or "")
        if result is not None and hasattr(result, "next_available"):
            return str(getattr(result, "next_available") or "")
        return ""

def get_db(request: Request) -> FilaRepository:
    """
    Dependência FastAPI que retorna a conexão com o banco como FilaRepository.
    Injeta o D1 no Cloudflare ou o SQLite em ambiente local.
    """
    env = request.scope.get("env")
    db_binding = get_env_binding(env, "DB")
    if db_binding is not None:
        yield D1FilaRepository(db_binding)
    else:
        init_local_db()
        conn = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
        try:
            yield SqliteFilaRepository(conn)
        finally:
            conn.close()
