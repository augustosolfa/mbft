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
        return env["DB"]
    else:
        # Ambiente Local (Uvicorn)
        init_local_db()
        return sqlite3.connect(LOCAL_DB_PATH)
