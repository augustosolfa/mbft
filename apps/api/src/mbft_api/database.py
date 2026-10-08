import sqlite3
import os
from fastapi import Request, Depends
from typing import Any

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

def get_db(request: Request) -> Any:
    """
    Dependência FastAPI que retorna a conexão com o banco.
    Injeta o D1 no Cloudflare ou o SQLite em ambiente local.
    """
    env = request.scope.get("env", {})
    if "DB" in env:
        # Retorna o binding D1 nativo do Cloudflare
        yield env["DB"]
    else:
        # Ambiente Local (Uvicorn)
        init_local_db()
        conn = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

class FilaRepository:
    def __init__(self, db: Any):
        self.db = db
        # Se db possuir o atributo 'cursor', é o SQLite local. Caso contrário, é o D1.
        self.is_local = hasattr(self.db, "cursor")

    async def avancar_fila_global(self, segundos: int = 60) -> str:
        """
        Avança a fila global de forma atômica e retorna o novo horário ISO.
        """
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
        
        if self.is_local:
            cursor = self.db.cursor()
            cursor.execute(query, (segundos,))
            row = cursor.fetchone()
            self.db.commit()
            return row[0] if row else ""
        else:
            # Bindings do Cloudflare D1 em Python
            # A API pyodide do Cloudflare mapeia prepare().bind().first()
            stmt = self.db.prepare(query).bind(segundos)
            result = await stmt.first()
            return result["next_available"] if result else ""

